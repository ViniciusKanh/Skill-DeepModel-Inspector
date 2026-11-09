// Hooks de execução de análises (jobs com polling e cancelamento) e de leitura de relatórios.
import { useCallback, useEffect, useRef, useState } from "react";
import { useApp } from "../app/AppState";
import { api, ApiError } from "../services/api";
import type { FullReport, Job, ReportMeta } from "../types/api";

export function useJobRunner() {
  const { notify, bump } = useApp();
  const [job, setJob] = useState<Job | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);

  const poll = useCallback(
    (id: string, onDone?: (j: Job) => void) => {
      const tick = async () => {
        try {
          const j = await api.job(id);
          setJob(j);
          if (j.status === "queued" || j.status === "running") {
            timer.current = window.setTimeout(tick, 400);
            return;
          }
          if (j.status === "done") {
            notify("success", `Analysis completed (${j.kind}).`);
            bump();
            onDone?.(j);
          } else if (j.status === "failed") notify("error", j.error || "Analysis failed.");
          else notify("info", "Analysis cancelled.");
        } catch (e) {
          notify("error", (e as Error).message);
        }
      };
      tick();
    },
    [notify, bump],
  );

  const run = useCallback(
    async (body: Parameters<typeof api.submitJob>[0], onDone?: (j: Job) => void) => {
      try {
        const j = await api.submitJob(body);
        setJob(j);
        poll(j.id, onDone);
      } catch (e) {
        notify("error", e instanceof ApiError ? e.message : String(e));
      }
    },
    [poll, notify],
  );

  const cancel = useCallback(async () => {
    if (job) setJob(await api.cancelJob(job.id));
  }, [job]);

  const busy = job?.status === "queued" || job?.status === "running";
  return { job, run, cancel, busy };
}

/** Relatório mais recente do experimento ativo que contém a seção pedida (ou qualquer um). */
export function useLatestReport(section?: string, kinds?: string[]) {
  const { experiment, project, refreshKey } = useApp();
  const [state, setState] = useState<{ loading: boolean; data: FullReport | null; metas: ReportMeta[]; error: string | null }>(
    { loading: false, data: null, metas: [], error: null },
  );
  const kindsKey = kinds?.join(",") ?? "";
  useEffect(() => {
    let alive = true;
    if (!project || !experiment) {
      setState({ loading: false, data: null, metas: [], error: null });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    (async () => {
      try {
        const metas = await api.reports(project.id, experiment.id);
        const ks = kindsKey ? kindsKey.split(",") : null;
        const m = metas.find((x) => (!section || x.analyses_run.includes(section)) && (!ks || ks.includes(x.kind)));
        const data = m ? await api.report(m.id) : null;
        if (alive) setState({ loading: false, data, metas, error: null });
      } catch (e) {
        if (alive) setState({ loading: false, data: null, metas: [], error: (e as Error).message });
      }
    })();
    return () => {
      alive = false;
    };
  }, [project, experiment, section, kindsKey, refreshKey]);
  return state;
}

/** Caminho relativo (no projeto) de uma fonte citada no relatório. */
export function sourcePath(report: FullReport | null, source: string): string | null {
  if (!report) return null;
  const item = report.report.inventory.find((i) => i.name === source || i.path === source || i.path.endsWith("/" + source));
  return item ? item.path : null;
}
