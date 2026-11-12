import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Play, RadioTower } from "lucide-react";
import { useApp } from "../app/AppState";
import { PeriodChart } from "../components/charts";
import { Chip, EmptyState, JobProgress, Loader, Panel, SevChip, StatusChip, fmt, pct } from "../components/ui";
import { FindingsTable } from "../features/findings";
import { useJobRunner } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { FullReport, HistoryPoint, Target } from "../types/api";

const DEFAULT_TH: Record<string, number> = {
  error_rate: 0.05, p95_latency_ms: 10000, degenerate_rate: 0.1, empty_rate: 0.05, truncation_rate: 0.1, distinct2_drop: 0.25,
};
const TH_LABEL: Record<string, string> = {
  error_rate: "Error rate", p95_latency_ms: "p95 latency (ms)", degenerate_rate: "Degenerate rate", empty_rate: "Empty rate",
  truncation_rate: "Truncation rate", distinct2_drop: "Distinct-2 drop",
};
const CAT_COLORS: Record<string, string> = {
  instruction: "#00E5FF", knowledge: "#39FF88", grounding: "#FFB000", injection: "#FF4D8D", consistency: "#A255FF", stress: "#e8f5ee", custom: "#9aa8c7",
};

function ProductionMonitor() {
  const { project, refreshKey, notify } = useApp();
  const [path, setPath] = useState("");
  const [period, setPeriod] = useState("week");
  const [th, setTh] = useState(DEFAULT_TH);
  const [rep, setRep] = useState<FullReport | null>(null);
  const { job, run, cancel, busy } = useJobRunner();
  const folders = useMemo(() => {
    const s = new Set<string>();
    for (const i of project?.inventory ?? []) {
      const parts = i.path.split("/");
      for (let k = 1; k < parts.length; k++) s.add(parts.slice(0, k).join("/"));
    }
    return [...s].sort();
  }, [project]);
  useEffect(() => {
    setRep(null);
    if (!project) return;
    api.reports(project.id).then(async (ms) => {
      const m = ms.find((x) => x.kind === "monitor");
      if (m) setRep(await api.report(m.id));
    }).catch((e) => notify("error", e.message));
  }, [project?.id, refreshKey]);
  if (!project) return <Panel title="Production log monitor" tone="cyan"><EmptyState small title="Select a project" text="Production logs are read from a folder of the selected project (Projects & Experiments)." /></Panel>;
  const block = rep?.report.sections.monitor?.[0];
  const tl = ((block?.metrics.timeline ?? []) as Record<string, any>[]);
  const used = (block?.metrics.thresholds ?? th) as Record<string, number>;
  const alerts = (rep?.report.findings ?? []).filter((f) => f.severity !== "INFO");
  return (
    <>
      <Panel title="Production log monitor" tone="cyan" icon={<RadioTower size={14} />}>
        <div className="flex flex-wrap items-end gap-2">
          <label className="text-[11px] text-muted flex flex-col gap-1 flex-1 min-w-[220px]">Log folder or file (relative to project)
            <input className="field" list="dmi-folders" value={path} onChange={(e) => setPath(e.target.value)} placeholder="e.g. synthetic_production" aria-label="Log folder" />
            <datalist id="dmi-folders">{folders.map((f) => <option key={f} value={f} />)}</datalist>
          </label>
          <label className="text-[11px] text-muted flex flex-col gap-1">Period
            <select className="field w-28" value={period} onChange={(e) => setPeriod(e.target.value)} aria-label="Period"><option value="day">day</option><option value="week">week</option></select>
          </label>
          <button className="btn btn-primary" disabled={busy || !path} onClick={() => run({ project_id: project.id, kind: "monitor", params: { path, period, thresholds: th } })}><Play size={12} /> Run monitor</button>
          <JobProgress job={job} onCancel={cancel} />
        </div>
        <details className="mt-2 text-[12px]">
          <summary className="cursor-pointer text-amber">Alert thresholds</summary>
          <div className="grid sm:grid-cols-3 gap-2 mt-2">
            {Object.keys(DEFAULT_TH).map((k) => (
              <label key={k} className="text-[11px] text-muted flex flex-col gap-1">{TH_LABEL[k]}
                <input className="field" type="number" step="any" min={0} value={th[k]} onChange={(e) => setTh({ ...th, [k]: Number(e.target.value) })} />
              </label>
            ))}
          </div>
        </details>
        <p className="text-[11.5px] text-muted mt-2">Export one JSONL per day/week (or include a <code>timestamp</code>) with <code>output</code>, optional <code>prompt</code>, <code>latency_ms</code>, <code>error</code>, <code>finish_reason</code>. Batch analysis — not real-time.</p>
      </Panel>
      {rep && block && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <span>Monitor run <span className="text-cyan">{rep.meta.id}</span> · {new Date(rep.meta.created).toLocaleString()} · {block.source}</span>
            {alerts.length ? <Chip tone="danger">{alerts.length} alerts</Chip> : <Chip>all clear</Chip>}
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title="Quality signals per period" tone="amber">
              <PeriodChart ariaLabel="Quality signals" rows={tl} xKey="period" yFormatter={(v) => `${(v * 100).toFixed(1)}%`}
                defs={[{ key: "degenerate_rate", label: "Degenerate", color: "#FF4D8D" }, { key: "error_rate", label: "Errors", color: "#FFB000" },
                  { key: "empty_rate", label: "Empty", color: "#A255FF" }, { key: "truncation_rate", label: "Truncated", color: "#00E5FF" }]} />
            </Panel>
            <Panel title="Latency p95 per period" tone="cyan">
              <PeriodChart ariaLabel="Latency" rows={tl} xKey="period" threshold={{ value: used.p95_latency_ms, label: "threshold" }}
                defs={[{ key: "latency_p95_ms", label: "p95 (ms)", color: "#00E5FF" }, { key: "latency_p50_ms", label: "p50 (ms)", color: "#39FF88" }]} />
            </Panel>
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Panel title="Timeline" tone="green">
              <div className="overflow-x-auto"><table className="data-table">
                <thead><tr><th>Period</th><th>Requests</th><th>Errors</th><th>Degenerate</th><th>Empty</th><th>Truncated</th><th>Distinct-2</th><th>p95 ms</th></tr></thead>
                <tbody>{tl.map((t) => (
                  <tr key={t.period}>
                    <td className="text-cyan">{t.period}</td><td>{fmt(t.requests)}</td>
                    {(["error_rate", "degenerate_rate", "empty_rate", "truncation_rate"] as const).map((k) => (
                      <td key={k} className={t[k] > used[k] ? "text-danger font-semibold" : ""}>{pct(t[k])}</td>
                    ))}
                    <td>{fmt(t.distinct_2, 3)}</td>
                    <td className={t.latency_p95_ms > used.p95_latency_ms ? "text-danger font-semibold" : ""}>{fmt(t.latency_p95_ms, 0)}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            </Panel>
            <Panel title="Alerts" tone="danger" icon={<AlertTriangle size={14} />}>
              {alerts.length === 0 && <div className="text-muted text-[13px]">No threshold breached in the latest period.</div>}
              <ul className="space-y-1.5">{alerts.map((f) => (
                <li key={f.id} className="border border-white/10 p-2 text-[13px]"><div>{f.title}</div>
                  <div className="flex gap-1.5 mt-1"><SevChip s={f.severity} /><StatusChip s={f.status} /><span className="text-[11px] text-muted">{f.rule}</span></div></li>
              ))}</ul>
            </Panel>
          </div>
          <Panel title="Monitor findings" tone="muted"><FindingsTable findings={rep.report.findings} report={rep} /></Panel>
        </>
      )}
    </>
  );
}

function ModelHealth() {
  const { refreshKey } = useApp();
  const [targets, setTargets] = useState<Target[]>([]);
  const [sel, setSel] = useState("");
  const [hist, setHist] = useState<HistoryPoint[] | null>(null);
  useEffect(() => { api.targets().then((t) => { setTargets(t); setSel((s) => s || t[0]?.id || ""); }).catch(() => setTargets([])); }, [refreshKey]);
  useEffect(() => { setHist(null); if (sel) api.history(sel).then(setHist).catch(() => setHist([])); }, [sel, refreshKey]);
  const rows = (hist ?? []).map((h, i) => ({ run: `#${i + 1} ${new Date(h.created).toLocaleDateString()}`, ...Object.fromEntries(Object.entries(h.pass_rates).map(([k, v]) => [k, v])),
    p95: h.latency_p95_ms, median: h.latency_median_ms, errors: h.error_rate }));
  const cats = [...new Set((hist ?? []).flatMap((h) => Object.entries(h.pass_rates).filter(([, v]) => v !== null).map(([k]) => k)))];
  return (
    <Panel title="Model health history (live probes)" tone="purple" icon={<Activity size={14} />}>
      <div className="flex flex-wrap gap-2 items-end mb-2">
        <label className="text-[11px] text-muted flex flex-col gap-1 min-w-[240px]">Model
          <select className="field" value={sel} onChange={(e) => setSel(e.target.value)} aria-label="Model for history">
            {targets.length === 0 && <option value="">No registered models</option>}
            {targets.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <span className="text-[12px] text-muted">{hist ? `${hist.length} inspections` : ""} · run the Model Lab periodically to build a trend.</span>
      </div>
      {!hist ? <Loader label="Loading history" /> : hist.length === 0 ? <div className="text-muted text-[13px]">No inspections for this model yet.</div> : (
        <div className="grid gap-3 xl:grid-cols-2">
          <PeriodChart ariaLabel="Pass rate history" rows={rows} xKey="run" yFormatter={(v) => `${(v * 100).toFixed(0)}%`}
            defs={cats.map((c) => ({ key: c, label: c, color: CAT_COLORS[c] ?? "#9aa8c7" }))} />
          <PeriodChart ariaLabel="Latency history" rows={rows} xKey="run"
            defs={[{ key: "p95", label: "p95 ms", color: "#00E5FF" }, { key: "median", label: "median ms", color: "#39FF88" }]} />
        </div>
      )}
    </Panel>
  );
}

export default function Monitor() {
  return (
    <div className="space-y-3">
      <ProductionMonitor />
      <ModelHealth />
    </div>
  );
}
