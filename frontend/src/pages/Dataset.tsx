import { useEffect, useMemo, useState } from "react";
import { Copy, Database, FileWarning, Link2, ListChecks, Play } from "lucide-react";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { BarsChart } from "../components/charts";
import { EmptyState, JobProgress, KeyValues, Loader, Panel, StatCard, fmt, pct } from "../components/ui";
import { AuditBar, SingleRunBar, useInventory } from "../features/analysis";
import { FindingsTable } from "../features/findings";
import { sourcePath, useJobRunner, useLatestReport } from "../hooks/useAnalysis";
import { api } from "../services/api";

function LeakageForm() {
  const { project, experiment } = useApp();
  const files = useInventory(["dataset"]);
  const trains = files.filter((f) => f.split === "train");
  const evals = files.filter((f) => f.split === "validation" || f.split === "test");
  const [train, setTrain] = useState("");
  const [test, setTest] = useState("");
  const { job, run, cancel, busy } = useJobRunner();
  const tr = train || trains[0]?.path || "";
  const te = test || evals[0]?.path || "";
  return (
    <div className="flex flex-wrap items-end gap-2">
      <label className="text-[11px] text-muted flex flex-col gap-1 flex-1 min-w-[180px]">Train split
        <select className="field" value={tr} onChange={(e) => setTrain(e.target.value)} aria-label="Train split">
          {(trains.length ? trains : files).map((f) => <option key={f.path}>{f.path}</option>)}
        </select>
      </label>
      <label className="text-[11px] text-muted flex flex-col gap-1 flex-1 min-w-[180px]">Evaluation split
        <select className="field" value={te} onChange={(e) => setTest(e.target.value)} aria-label="Evaluation split">
          {(evals.length ? evals : files).map((f) => <option key={f.path}>{f.path}</option>)}
        </select>
      </label>
      <button className="btn btn-purple" disabled={busy || !tr || !te || tr === te || !project}
        onClick={() => project && run({ project_id: project.id, experiment_id: experiment?.id, kind: "leakage", params: { train: tr, tests: [te] } })}>
        <Play size={12} /> Run leakage
      </button>
      <JobProgress job={job} onCancel={cancel} />
    </div>
  );
}

export default function Dataset() {
  const { data, loading } = useLatestReport("dataset");
  const leakRep = useLatestReport("leakage").data;
  const { project } = useApp();
  const blocks = data?.report.sections.dataset ?? [];
  const largest = blocks.reduce((best, b, i) => ((b.metrics.records ?? 0) > (blocks[best]?.metrics.records ?? -1) ? i : best), 0);
  const [bi, setBi] = useState<number | null>(null);
  const block = blocks[Math.min(bi ?? largest, blocks.length - 1)];
  const leak = leakRep?.report.sections.leakage?.[0];
  const path = block ? sourcePath(data, block.source) : null;
  const [hist, setHist] = useState<{ label: string; value: number }[] | null>(null);

  useEffect(() => {
    setHist(null);
    if (project && path) api.lengths(project.id, path).then((r) => setHist(r.bins.map((b) => ({ label: b.label, value: b.count })))).catch(() => setHist([]));
  }, [project?.id, path]);

  const findings = useMemo(() => (data?.report.findings ?? []).filter((f) => block?.finding_ids.includes(f.id)), [data, block]);
  const leakFindings = (leakRep?.report.findings ?? []).filter((f) => leak?.finding_ids.includes(f.id));
  const m = block?.metrics ?? {};
  const splits = Object.entries((leak?.metrics.splits ?? {}) as Record<string, any>);
  const firstSplit = splits[0]?.[1];
  const structTotal = Object.values((m.structure_issues ?? {}) as Record<string, number>).reduce((a, b) => a + b, 0);

  return (
    <ExperimentGate>
      <AuditBar report={data} />
      <div className="grid gap-3 xl:grid-cols-2">
        <Panel title="Audit a dataset file" tone="muted"><SingleRunBar kind="dataset" label="Dataset (JSONL / JSON / CSV / TXT)" fileKinds={["dataset", "generations"]} /></Panel>
        <Panel title="Check train ↔ eval contamination" tone="muted"><LeakageForm /></Panel>
      </div>
      {loading && <Loader label="Loading dataset quality" />}
      {!loading && !block && <Panel tone="purple"><EmptyState title="No dataset analyzed" text="Run the audit or audit a dataset file above." small /></Panel>}
      {block && (
        <>
          {blocks.length > 1 && (
            <div className="flex flex-wrap gap-2">{blocks.map((b, i) => (
              <button key={i} className={`btn btn-sm ${i === (bi ?? largest) ? "btn-primary" : ""}`} onClick={() => setBi(i)}>{b.source}</button>
            ))}</div>
          )}
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
            <StatCard icon={<Database size={20} />} label="Records" value={fmt(m.records)} sub={Object.entries(m.formats ?? {}).map(([k, v]) => `${k}: ${v}`).join(" · ")} />
            <StatCard tone="cyan" icon={<Copy size={20} />} label="Exact duplicates" value={pct(m.exact_duplicate_rate)} sub={`${fmt(m.exact_duplicate_extra_records)} extra copies`} />
            <StatCard tone="cyan" icon={<Copy size={20} />} label="Near duplicates" value={fmt(m.near_duplicate_pairs)} sub={`pairs · Jaccard ≥ ${m.near_duplicate_threshold}`} />
            <StatCard tone="purple" icon={<Link2 size={20} />} label="Contamination" value={firstSplit ? pct(firstSplit.exact_overlap_rate) : "not analyzed"}
              sub={firstSplit ? `${firstSplit.exact_overlap} exact · ${firstSplit.near_duplicate_overlap} near · ${splits[0][0]}` : "run leakage check"} />
            <StatCard tone="amber" icon={<ListChecks size={20} />} label="Schema issues" value={fmt(structTotal)} sub={`${fmt(m.empty_records)} empty records`} />
            <StatCard tone="danger" icon={<FileWarning size={20} />} label="Encoding" value={fmt((m.unicode?.mojibake_records ?? 0) + (m.unicode?.control_char_records ?? 0))}
              sub={`mojibake / control · ${fmt(m.instruction_like_records)} instruction-like`} />
          </div>
          <div className="grid gap-3 xl:grid-cols-3">
            <Panel title="Text length distribution (words)" tone="green" className="xl:col-span-2">
              {!hist ? <Loader label="Counting lengths" /> : <BarsChart ariaLabel="Length histogram" data={hist} valueLabel="records" />}
              <div className="mt-2"><KeyValues rows={[["min / median / mean", `${fmt(m.length_words?.min)} / ${fmt(m.length_words?.median)} / ${fmt(m.length_words?.mean, 1)}`], ["p95 / max", `${fmt(m.length_words?.p95)} / ${fmt(m.length_words?.max)}`]]} /></div>
            </Panel>
            <Panel title="Sample format validation" tone="cyan">
              <table className="data-table">
                <thead><tr><th>Check</th><th className="text-right">Records</th></tr></thead>
                <tbody>
                  {Object.entries(m.formats ?? {}).map(([k, v]) => <tr key={k}><td>format: {k}</td><td className="text-right">{fmt(v)}</td></tr>)}
                  {Object.entries(m.structure_issues ?? {}).map(([k, v]) => <tr key={k}><td className="text-amber">{k.replace(/_/g, " ")}</td><td className="text-right">{fmt(v)}</td></tr>)}
                  {Object.entries(m.unicode ?? {}).map(([k, v]) => <tr key={k}><td>{k.replace(/_/g, " ")}</td><td className="text-right">{fmt(v)}</td></tr>)}
                </tbody>
              </table>
            </Panel>
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title="Dataset split & contamination" tone="purple">
              {splits.length === 0 ? <div className="text-muted text-[13px]">No leakage analysis yet. Select train and evaluation splits above.</div> : (
                <div className="overflow-x-auto"><table className="data-table">
                  <thead><tr><th>Eval split</th><th>Records</th><th>Exact</th><th>Near</th><th>Prompt seen</th><th>13-gram hits</th></tr></thead>
                  <tbody>{splits.map(([k, v]) => (
                    <tr key={k}><td>{k}</td><td>{fmt(v.records)}</td><td className="text-danger">{fmt(v.exact_overlap)} ({pct(v.exact_overlap_rate)})</td><td>{fmt(v.near_duplicate_overlap)}</td><td>{fmt(v.prompt_seen_in_train)}</td><td>{fmt(v.records_with_13gram_overlap)}</td></tr>
                  ))}</tbody>
                </table>
                <div className="text-[11.5px] text-muted mt-2">Source: {leak?.source}. Within-file duplicates are reported separately; only cross-split overlap counts as leakage.</div>
                <div className="mt-2"><FindingsTable findings={leakFindings} report={leakRep} compact /></div></div>
              )}
            </Panel>
            <Panel title="Language & script distribution" tone="cyan">
              <KeyValues rows={[
                ...Object.entries(m.language_estimate ?? {}).map(([k, v]) => [`language ${k}`, fmt(v)] as [string, string]),
                ...Object.entries(m.scripts ?? {}).map(([k, v]) => [`script ${k}`, pct(v)] as [string, string]),
              ]} />
              <div className="text-[11px] text-muted mt-2">{m.language_method}</div>
            </Panel>
          </div>
          <Panel title="Issues found & recommended treatment" tone="amber">
            <FindingsTable findings={findings} report={data} emptyText="No dataset rule fired at the documented thresholds." />
            {findings.length > 0 && (
              <ul className="mt-3 grid md:grid-cols-2 gap-2 text-[13px]">
                {findings.filter((f) => f.severity !== "INFO").map((f) => <li key={f.id} className="border border-white/10 p-2"><span className="text-phosphor">■</span> {f.recommendation} <span className="text-muted text-[11px]">({f.id})</span></li>)}
              </ul>
            )}
          </Panel>
        </>
      )}
    </ExperimentGate>
  );
}
