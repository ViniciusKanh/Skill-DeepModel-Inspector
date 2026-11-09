// Barras de ação compartilhadas: executar auditoria do experimento ou análise específica sobre um arquivo.
import { useMemo, useState, type ReactNode } from "react";
import { Play } from "lucide-react";
import { useApp } from "../app/AppState";
import { useJobRunner } from "../hooks/useAnalysis";
import type { FullReport, InventoryItem } from "../types/api";
import { JobProgress } from "../components/ui";

export function AuditBar({ report, extra }: { report: FullReport | null; extra?: ReactNode }) {
  const { project, experiment, t } = useApp();
  const { job, run, cancel, busy } = useJobRunner();
  return (
    <div className="panel panel-muted px-3 py-2 flex flex-wrap items-center gap-3">
      <div className="text-[12px] text-muted min-w-0">
        {report ? (
          <>Latest result <span className="text-cyan">{report.meta.id}</span> · {report.meta.kind} · {new Date(report.meta.created).toLocaleString()}</>
        ) : (
          "No result yet for this experiment."
        )}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <JobProgress job={job} onCancel={cancel} />
        {extra}
        <button className="btn btn-primary" disabled={busy || !experiment}
          onClick={() => project && experiment && run({ project_id: project.id, experiment_id: experiment.id, kind: "audit" })}>
          <Play size={12} /> {t("runAudit")}
        </button>
      </div>
    </div>
  );
}

/** Arquivos do inventário do projeto com os tipos aceitos (dentro dos itens do experimento quando possível). */
export function useInventory(kinds: string[]): InventoryItem[] {
  const { project, experiment } = useApp();
  return useMemo(() => {
    if (!project) return [];
    const inv = project.inventory.filter((i) => kinds.includes(i.kind)).sort((a, b) => kinds.indexOf(a.kind) - kinds.indexOf(b.kind));
    if (!experiment) return inv;
    const scoped = inv.filter((i) => experiment.items.some((it) => i.path === it || i.path.startsWith(it.replace(/\/$/, "") + "/")));
    return scoped.length ? scoped : inv;
  }, [project, experiment, kinds.join(",")]);
}

export function SingleRunBar(props: {
  kind: string; label: string; fileKinds: string[]; extraParams?: Record<string, unknown>; children?: ReactNode;
  paramName?: string;
}) {
  const { project, experiment } = useApp();
  const files = useInventory(props.fileKinds);
  const [path, setPath] = useState("");
  const { job, run, cancel, busy } = useJobRunner();
  const chosen = path || files[0]?.path || "";
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-[11px] text-muted flex flex-col gap-1 min-w-[220px] flex-1">
        {props.label}
        <select className="field" value={chosen} onChange={(e) => setPath(e.target.value)} aria-label={props.label}>
          {files.length === 0 && <option value="">No matching file in project inventory</option>}
          {files.map((f) => <option key={f.path} value={f.path}>{f.path}{f.split ? ` [${f.split}]` : ""}</option>)}
        </select>
      </label>
      {props.children}
      <button className="btn btn-cyan" disabled={busy || !chosen || !project}
        onClick={() => project && run({ project_id: project.id, experiment_id: experiment?.id, kind: props.kind,
          params: { [props.paramName ?? "path"]: chosen, ...(props.extraParams ?? {}) } })}>
        <Play size={12} /> Run {props.kind}
      </button>
      <JobProgress job={job} onCancel={cancel} />
    </div>
  );
}
