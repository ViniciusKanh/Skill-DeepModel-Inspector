import { useEffect, useMemo, useState } from "react";
import { Repeat, Ruler, Shuffle, Scissors } from "lucide-react";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { BarsChart } from "../components/charts";
import { Chip, EmptyState, Hint, Loader, Panel, StatCard, fmt, pct } from "../components/ui";
import { AuditBar, SingleRunBar } from "../features/analysis";
import { FindingsTable } from "../features/findings";
import { sourcePath, useLatestReport } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { RecordRow } from "../types/api";

const METRICS: [string, string, (m: any) => string][] = [
  ["responses", "Responses", (m) => fmt(m.responses)],
  ["empty", "Empty", (m) => fmt(m.empty)],
  ["short", "Short (< min words)", (m) => fmt(m.short_responses)],
  ["d1", "Distinct-1", (m) => fmt(m.distinct_1, 3)],
  ["d2", "Distinct-2", (m) => fmt(m.distinct_2, 3)],
  ["d3", "Distinct-3", (m) => fmt(m.distinct_3, 3)],
  ["rep", "Mean 3-gram repetition", (m) => fmt(m.repetition_rate?.mean, 3)],
  ["deg", "Degenerate responses (>50%)", (m) => fmt(m.degenerate_responses)],
  ["mattr", "MATTR (window 50)", (m) => fmt(m.mattr, 3)],
  ["len", "Length words (mean · p95)", (m) => `${fmt(m.length_words?.mean, 1)} · ${fmt(m.length_words?.p95)}`],
  ["sim", "Mean pairwise similarity", (m) => fmt(m.mean_pairwise_similarity, 3)],
  ["nid", "Near-identical fraction", (m) => pct(m.near_identical_fraction)],
  ["trunc", "finish_reason = length", (m) => fmt(m.finish_reason_length)],
];

export default function Generation() {
  const { data, loading } = useLatestReport("generation");
  const { project } = useApp();
  const block = data?.report.sections.generation?.[0];
  const groups = Object.entries((block?.metrics.groups ?? {}) as Record<string, any>);
  const findings = (data?.report.findings ?? []).filter((f) => block?.finding_ids.includes(f.id));
  const path = block ? sourcePath(data, block.source) : null;
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [cfg, setCfg] = useState("");
  const [minRep, setMinRep] = useState(0);
  const [qtext, setQ] = useState("");

  useEffect(() => {
    setRows(null);
    if (project && path) api.records(project.id, path, undefined, 200).then((r) => setRows(r.rows)).catch(() => setRows([]));
  }, [project?.id, path]);

  const shown = useMemo(() => (rows ?? []).filter((r) => (!cfg || String(r.meta.config ?? r.meta.run ?? r.meta.model ?? "all") === cfg) &&
    (r.repetition_rate ?? 0) >= minRep && (!qtext || r.output.toLowerCase().includes(qtext.toLowerCase()))), [rows, cfg, minRep, qtext]);
  const g0 = groups[0]?.[1];
  const comp = Object.entries((block?.metrics.comparison ?? {}) as Record<string, any>);

  return (
    <ExperimentGate>
      <AuditBar report={data} />
      <Panel title="Analyze generated outputs" tone="muted">
        <SingleRunBar kind="generation" label="Outputs JSONL (output + optional config/decoding fields/reference)" fileKinds={["generations", "dataset"]} />
      </Panel>
      {loading && <Loader label="Loading generation behaviour" />}
      {!loading && !block && <Panel tone="purple"><EmptyState title="No generations analyzed" text="Run the audit or analyze an outputs file above." small /></Panel>}
      {block && (
        <>
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard tone="danger" icon={<Repeat size={20} />} label="Degenerate repetition" value={fmt(g0?.degenerate_responses)} sub={`of ${fmt(g0?.responses)} · ${groups[0]?.[0]}`} />
            <StatCard tone="cyan" icon={<Shuffle size={20} />} label="Distinct-2" value={fmt(g0?.distinct_2, 3)} sub={`distinct-1 ${fmt(g0?.distinct_1, 3)} · distinct-3 ${fmt(g0?.distinct_3, 3)}`} />
            <StatCard tone="amber" icon={<Ruler size={20} />} label="Mean length" value={`${fmt(g0?.length_words?.mean, 1)} w`} sub={`${fmt(g0?.empty)} empty · ${fmt(g0?.short_responses)} short`} />
            <StatCard tone="purple" icon={<Scissors size={20} />} label="Hit token limit" value={fmt(Math.max(g0?.finish_reason_length ?? 0, g0?.reached_max_tokens ?? 0))} sub="finish_reason = length / max tokens" />
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Panel title="Metrics by configuration" tone="cyan">
              <div className="overflow-x-auto"><table className="data-table">
                <thead><tr><th>Metric</th>{groups.map(([g]) => <th key={g}>{g}</th>)}</tr></thead>
                <tbody>
                  {METRICS.map(([k, label, f]) => <tr key={k}><td>{label}</td>{groups.map(([g, m]) => <td key={g} className="tabular-nums">{f(m)}</td>)}</tr>)}
                  <tr><td>Decoding params</td>{groups.map(([g, m]) => <td key={g} className="text-[11.5px] text-muted">{Object.entries(m.decoding_params ?? {}).map(([k, v]) => `${k}=${(v as string[]).join("|")}`).join(", ") || "not provided"}</td>)}</tr>
                  {groups.some(([, m]) => m.grounding) && <tr><td>Unsupported sentences <Hint text="Lexical check against the provided reference only." /></td>{groups.map(([g, m]) => <td key={g}>{m.grounding ? `${m.grounding.unsupported_sentences}/${m.grounding.sentences}` : "—"}</td>)}</tr>}
                </tbody>
              </table></div>
            </Panel>
            <Panel title="Diversity vs repetition" tone="purple">
              <BarsChart ariaLabel="Distinct-2 by configuration" color="#00E5FF" height={150} valueLabel="distinct-2" data={groups.map(([g, m]) => ({ label: `${g} d2`, value: m.distinct_2 ?? 0 }))} />
              <BarsChart ariaLabel="Repetition by configuration" color="#FF4D8D" height={150} valueLabel="mean repetition" data={groups.map(([g, m]) => ({ label: `${g} rep`, value: m.repetition_rate?.mean ?? 0 }))} />
              {comp.map(([k, v]) => (
                <div key={k} className="text-[12px] mt-2 border border-white/10 p-2">
                  <b className="text-cyan">{k}</b>: Δ repetition {fmt(v.repetition_rate_diff, 3)} (95% CI {fmt(v.ci95?.[0], 3)} … {fmt(v.ci95?.[1], 3)}) {v.significant ? <Chip tone="amber">CI excludes 0</Chip> : <Chip tone="muted">not significant</Chip>}
                  <div className="text-muted mt-1">Bootstrap difference in behaviour; it does not identify which parameter caused it.</div>
                </div>
              ))}
            </Panel>
          </div>
          <Panel title="Generation examples" tone="green" actions={<span className="text-[11px] text-muted">{shown.length}/{rows?.length ?? 0} rows · redacted</span>}>
            <div className="flex flex-wrap gap-2 mb-2">
              <input className="field flex-1 min-w-[160px]" placeholder="Search output text" value={qtext} onChange={(e) => setQ(e.target.value)} aria-label="Search outputs" />
              <select className="field w-auto" value={cfg} onChange={(e) => setCfg(e.target.value)} aria-label="Filter by configuration">
                <option value="">All configs</option>{groups.map(([g]) => <option key={g}>{g}</option>)}
              </select>
              <label className="text-[12px] text-muted flex items-center gap-2">min repetition {minRep.toFixed(2)}
                <input type="range" min={0} max={1} step={0.05} value={minRep} onChange={(e) => setMinRep(Number(e.target.value))} aria-label="Minimum repetition rate" />
              </label>
            </div>
            {!rows ? <Loader label="Reading outputs" /> : (
              <div className="overflow-x-auto max-h-[420px]"><table className="data-table">
                <thead><tr><th>#</th><th>Config</th><th>Words</th><th>Rep.</th><th>Finish</th><th>Output</th></tr></thead>
                <tbody>{shown.slice(0, 100).map((r) => (
                  <tr key={r.index}><td>{r.index}</td><td>{String(r.meta.config ?? r.meta.run ?? "—")}</td><td>{r.words}</td>
                    <td className={(r.repetition_rate ?? 0) > 0.5 ? "text-danger" : ""}>{fmt(r.repetition_rate, 2)}</td>
                    <td>{String(r.meta.finish_reason ?? "—")}</td><td className="min-w-[320px] break-words">{r.output}</td></tr>
                ))}</tbody>
              </table></div>
            )}
          </Panel>
          <Panel title="Contextual diagnostics" tone="amber">
            <FindingsTable findings={findings} report={data} emptyText="No generation rule fired at the documented thresholds." />
          </Panel>
        </>
      )}
    </ExperimentGate>
  );
}
