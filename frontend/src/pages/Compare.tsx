import { useEffect, useState } from "react";
import { AlertOctagon, GitCompare, Play } from "lucide-react";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { TimeSeriesChart } from "../components/charts";
import { Chip, EmptyState, JobProgress, Loader, Panel, fmt, pct } from "../components/ui";
import { AuditBar } from "../features/analysis";
import { FindingsTable } from "../features/findings";
import { useJobRunner, useLatestReport } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { SeriesResponse } from "../types/api";

const assessTone: Record<string, "danger" | "green" | "muted" | "cyan"> = {
  regression: "danger", improvement: "green", within_tolerance: "muted", unknown_direction: "cyan",
};

function RunCurve({ runName }: { runName: string }) {
  const { project } = useApp();
  const [s, setS] = useState<SeriesResponse | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const run = project?.inventory.find((i) => i.kind === "run" && (i.name === runName || i.path === runName));
  const log = project?.inventory.find((i) => i.kind === "training_log" && run && i.path.startsWith(run.path + "/"))
    ?? project?.inventory.find((i) => i.kind === "training_log" && (i.path === runName || i.name === runName));
  useEffect(() => {
    setS(null);
    setMsg(null);
    if (!project || !log) {
      setMsg("No loss log found for this run.");
      return;
    }
    api.series(project.id, log.path).then(setS).catch((e) => setMsg(e.message));
  }, [project?.id, log?.path]);
  return (
    <Panel title={`${runName} — loss`} tone="cyan">
      {msg && <div className="text-muted text-[13px]">{msg}</div>}
      {!s && !msg && <Loader label="Reading series" />}
      {s && <TimeSeriesChart ariaLabel={`${runName} loss`} series={s.series as any} height={220} showStats={false}
        defs={[{ key: "train_loss", label: "Train", color: "#39FF88" }, { key: "val_loss", label: "Val", color: "#FF4DD8" }]} />}
    </Panel>
  );
}

export default function Compare() {
  const { project, experiment } = useApp();
  const { data, loading } = useLatestReport("comparison");
  const candidates = (project?.inventory ?? []).filter((i) => i.kind === "run" || i.kind === "training_log")
    .sort((x, y) => (x.kind === "run" ? 0 : 1) - (y.kind === "run" ? 0 : 1));
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  const { job, run, cancel, busy } = useJobRunner();
  const b = before || candidates[0]?.path || "";
  const a = after || candidates[1]?.path || "";
  const block = data?.report.sections.comparison?.[0];
  const m = block?.metrics ?? {};
  const findings = (data?.report.findings ?? []).filter((f) => block?.finding_ids.includes(f.id));
  const incompatible = findings.find((f) => f.rule === "CMP.INCOMPATIBLE");
  const [runA, runB] = (block?.source ?? "").split(" -> ");

  return (
    <ExperimentGate>
      <AuditBar report={data} />
      <Panel title="Select two experiments" tone="muted">
        <div className="flex flex-wrap items-end gap-2">
          {[["Before (baseline)", b, setBefore], ["After (candidate)", a, setAfter]].map(([label, val, set]) => (
            <label key={label as string} className="text-[11px] text-muted flex flex-col gap-1 flex-1 min-w-[200px]">{label as string}
              <select className="field" value={val as string} onChange={(e) => (set as (v: string) => void)(e.target.value)} aria-label={label as string}>
                {candidates.length === 0 && <option value="">No run directories or logs in inventory</option>}
                {candidates.map((c) => <option key={c.path} value={c.path}>{c.path} ({c.kind})</option>)}
              </select>
            </label>
          ))}
          <button className="btn btn-cyan" disabled={busy || !a || !b || a === b || !project}
            onClick={() => project && run({ project_id: project.id, experiment_id: experiment?.id, kind: "compare", params: { before: b, after: a } })}>
            <Play size={12} /> Compare
          </button>
          <JobProgress job={job} onCancel={cancel} />
        </div>
        <p className="text-[11.5px] text-muted mt-2">The engine refuses loss/perplexity regressions when tokenizer, vocabulary, eval set or protocol differ.</p>
      </Panel>
      {loading && <Loader label="Loading comparison" />}
      {!loading && !block && <Panel tone="purple"><EmptyState title="No comparison yet" text="Pick two runs (directories with config/metrics or loss logs) and compare them." small /></Panel>}
      {block && (
        <>
          {incompatible && (
            <div className="panel panel-amber p-3 flex gap-3 items-start" role="alert">
              <AlertOctagon className="text-amber flex-none" />
              <div><div className="panel-title">Methodological incompatibility</div>
                <div className="text-[13px] mt-1">{incompatible.explanation}</div>
                <div className="text-[12px] text-muted mt-1">Differs: {(incompatible.evidence.differs as string[]).join(", ")}. {incompatible.recommendation}</div></div>
            </div>
          )}
          <div className="text-[13px] flex items-center gap-2"><GitCompare size={16} className="text-cyan" /> <b>{block.source}</b></div>
          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title="Metric comparison" tone="green">
              <div className="overflow-x-auto"><table className="data-table">
                <thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Δ rel.</th><th>Better</th><th>Assessment</th></tr></thead>
                <tbody>{Object.entries((m.metric_deltas ?? {}) as Record<string, any>).map(([k, v]) => (
                  <tr key={k}><td>{k}</td><td>{fmt(v.before)}</td><td>{fmt(v.after)}</td><td>{pct(v.relative_change)}</td><td>{v.direction}</td>
                    <td><Chip tone={assessTone[v.assessment] ?? "muted"}>{v.assessment.replace(/_/g, " ")}</Chip></td></tr>
                ))}</tbody>
              </table></div>
              {incompatible && <p className="text-[12px] text-amber mt-2">Deltas shown for transparency only; no regression is claimed for incompatible runs.</p>}
            </Panel>
            <Panel title="Hyperparameter differences" tone="purple">
              <div className="overflow-x-auto"><table className="data-table">
                <thead><tr><th>Parameter</th><th>Before</th><th>After</th><th></th></tr></thead>
                <tbody>{Object.entries((m.hyperparameters ?? {}) as Record<string, any>).map(([k, v]) => (
                  <tr key={k} className={v.changed ? "text-amber" : ""}><td>{k}</td><td>{fmt(v.before)}</td><td>{fmt(v.after)}</td><td>{v.changed ? <Chip tone="amber">changed</Chip> : ""}</td></tr>
                ))}</tbody>
              </table></div>
              <div className="mt-3 text-[12px] text-cyan">COMPATIBILITY</div>
              <table className="data-table"><tbody>{Object.entries((m.compatibility ?? {}) as Record<string, any>).map(([k, v]) => (
                <tr key={k}><td>{k}</td><td>{fmt(v.before)}</td><td>{fmt(v.after)}</td><td>{v.before == null || v.after == null ? <Chip tone="muted">unverified</Chip> : v.before === v.after ? <Chip>match</Chip> : <Chip tone="danger">differs</Chip>}</td></tr>
              ))}</tbody></table>
            </Panel>
          </div>
          {runA && runB && <div className="grid gap-3 xl:grid-cols-2"><RunCurve runName={runA} /><RunCurve runName={runB} /></div>}
          <Panel title="Observable regressions & alerts" tone="amber"><FindingsTable findings={findings} report={data} /></Panel>
        </>
      )}
    </ExperimentGate>
  );
}
