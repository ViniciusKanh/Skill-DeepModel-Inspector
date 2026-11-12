import { useNavigate } from "react-router-dom";
import { AlertTriangle, BarChart3, Cpu, Database, FileText, GitCompare, PlayCircle, Search, ShieldAlert, Target } from "lucide-react";
import mascot from "../assets/brand/mascot.png";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { BarsChart, TimeSeriesChart } from "../components/charts";
import { Chip, EmptyState, Loader, Panel, SevChip, StatCard, StatusChip, fmt, pct } from "../components/ui";
import { AuditBar } from "../features/analysis";
import { ExperimentsChecklist, FindingsTable, severityCounts } from "../features/findings";
import { useLatestReport } from "../hooks/useAnalysis";
import type { Report } from "../types/api";

const NA = "not analyzed";

function cards(r: Report) {
  const s = r.sections;
  const tr = s.training?.[0]?.metrics;
  const ds = [...(s.dataset ?? [])].sort((a, b) => (b.metrics.records ?? 0) - (a.metrics.records ?? 0))[0]?.metrics;
  const tk = s.tokenizer?.[0]?.metrics?.groups as Record<string, any> | undefined;
  const tkFirst = tk ? Object.entries(tk)[0] : undefined;
  const gen = s.generation?.[0]?.metrics?.groups as Record<string, any> | undefined;
  const genFirst = gen ? Object.entries(gen)[0] : undefined;
  const cmp = r.findings.filter((f) => f.rule === "CMP.REGRESSION").length;
  return { tr, ds, tkFirst, genFirst, cmp, hasCmp: !!s.comparison?.length };
}

export default function Dashboard() {
  const { data, loading, metas, error } = useLatestReport(undefined, ["audit", "investigate", "probe", "hub"]);
  const nav = useNavigate();
  const { experiment } = useApp();
  const rep = data?.report;
  return (
    <ExperimentGate>
      <AuditBar report={data} />
      {loading && <Loader label="Loading latest analysis" />}
      {error && <div className="text-danger">{error}</div>}
      {!loading && !rep && (
        <Panel tone="purple">
          <EmptyState title="No analysis yet" text={`Run an audit on "${experiment?.name}" to populate the command center with real engine results.`} />
        </Panel>
      )}
      {rep && (() => {
        const c = cards(rep);
        const bySev = rep.summary.findings_by_severity;
        const bySt = rep.summary.findings_by_status;
        const alerts = rep.findings.filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH");
        const topHyp = rep.hypotheses[0];
        return (
          <>
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 2xl:grid-cols-6">
              <StatCard tone="danger" icon={<ShieldAlert size={20} />} label="Findings" value={rep.findings.length}
                sub={`${bySev.CRITICAL ?? 0} critical · ${bySev.HIGH ?? 0} high`} />
              <StatCard tone="green" icon={<Target size={20} />} label="Status mix" value={`${bySt.CONFIRMED ?? 0}/${bySt.POTENTIAL ?? 0}/${bySt.INCONCLUSIVE ?? 0}`}
                sub="confirmed / potential / inconclusive" />
              <StatCard tone="purple" icon={<BarChart3 size={20} />} label="Training" value={c.tr ? fmt(c.tr.train_loss?.last) : NA}
                sub={c.tr ? `best val ${fmt(c.tr.val_loss?.min)} @ ${fmt(c.tr.val_loss?.argmin_step)}` : "final train loss"} />
              <StatCard tone="green" icon={<Database size={20} />} label="Dataset" value={c.ds ? fmt(c.ds.records) : NA}
                sub={c.ds ? `exact dup ${pct(c.ds.exact_duplicate_rate)} · near ${fmt(c.ds.near_duplicate_pairs)} pairs` : "records"} />
              <StatCard tone="cyan" icon={<Cpu size={20} />} label="Tokenizer" value={c.tkFirst ? fmt(c.tkFirst[1].tokens_per_word, 2) : NA}
                sub={c.tkFirst ? `tokens/word · ${c.tkFirst[0]}` : "tokens per word"} />
              <StatCard tone="amber" icon={<PlayCircle size={20} />} label="Generation" value={c.genFirst ? fmt(c.genFirst[1].distinct_2, 3) : NA}
                sub={c.genFirst ? `distinct-2 · ${c.genFirst[1].degenerate_responses} degenerate` : "distinct-2"} />
            </div>
            {rep.sections.hub?.[0] && <HubCard m={rep.sections.hub[0].metrics as any} />}
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <Panel title="Training curve — loss (lower is better)" tone="cyan">
                {rep.sections.training?.[0]?.series ? (
                  <TimeSeriesChart ariaLabel="Training and validation loss" series={rep.sections.training[0].series as any} showStats={false}
                    defs={[{ key: "train_loss", label: "Train loss", color: "#39FF88" }, { key: "val_loss", label: "Val loss", color: "#FF4DD8" }]} height={250} />
                ) : (
                  <div className="text-muted text-[13px] py-8 text-center">No training log in this experiment.</div>
                )}
              </Panel>
              <Panel title="Alerts & insights" tone="amber" icon={<AlertTriangle size={14} />} bodyClass="p-2">
                {alerts.length === 0 ? <div className="text-muted text-[13px] p-2">No critical or high findings.</div> : (
                  <ul className="space-y-1.5 max-h-[300px] overflow-y-auto pr-1">
                    {alerts.map((f) => (
                      <li key={f.id} className="border border-white/10 p-2 text-[13px] flex gap-2 items-start">
                        <AlertTriangle size={16} className="text-amber flex-none mt-0.5" />
                        <div className="min-w-0"><div>{f.title}</div><div className="flex gap-1.5 mt-1 flex-wrap"><SevChip s={f.severity} /><StatusChip s={f.status} /><span className="text-[11px] text-muted">{f.id} · {f.source}</span></div></div>
                      </li>
                    ))}
                  </ul>
                )}
              </Panel>
            </div>
            <div className="grid gap-3 xl:grid-cols-3">
              <Panel title="Root-cause summary" tone="amber" className="xl:col-span-2">
                <div className="flex gap-4 items-start flex-col sm:flex-row">
                  <img src={mascot} alt="" className="pixelated w-36 flex-none" />
                  <div className="space-y-2 min-w-0 flex-1">
                    <div className="text-amber text-[12px]">TOP HYPOTHESIS (to be tested — not a confirmed cause)</div>
                    {topHyp ? (
                      <>
                        <div className="text-[15px]">{topHyp.statement}</div>
                        <div className="text-[12px] text-muted">{topHyp.id} · supported by {topHyp.supporting_findings.join(", ")}</div>
                      </>
                    ) : <div className="text-muted">No cross-artifact hypothesis was triggered.</div>}
                    <div className="pt-1"><div className="text-phosphor text-[12px] mb-1">RECOMMENDED ACTIONS</div><ExperimentsChecklist items={rep.experiments.slice(0, 3)} /></div>
                  </div>
                </div>
              </Panel>
              <Panel title="Findings by severity" tone="purple">
                <BarsChart ariaLabel="Findings by severity" data={severityCounts(rep.findings)} color="#A255FF" height={200} valueLabel="findings" />
                <div className="flex flex-wrap gap-1.5 mt-2">{rep.analyses_run.map((a) => <Chip key={a} tone="cyan">{a}</Chip>)}</div>
              </Panel>
            </div>
            <div className="grid gap-3 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
              <Panel title="Priority diagnostics"><FindingsTable findings={rep.findings.slice(0, 8)} report={data} compact /></Panel>
              <Panel title="Recent analyses & quick actions" tone="cyan">
                <ul className="space-y-1 text-[12.5px] mb-3">
                  {metas.slice(0, 6).map((m) => (
                    <li key={m.id} className="flex justify-between gap-2 border-b border-white/5 pb-1">
                      <span className="truncate">{m.kind}{m.question ? ` · "${m.question}"` : ""}</span>
                      <span className="text-muted flex-none">{new Date(m.created).toLocaleTimeString()}</span>
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap gap-2">
                  <button className="btn btn-purple btn-sm" onClick={() => nav("/investigate")}><Search size={12} /> Investigate</button>
                  <button className="btn btn-cyan btn-sm" onClick={() => nav("/compare")}><GitCompare size={12} /> Compare</button>
                  <button className="btn btn-amber btn-sm" onClick={() => nav("/reports")}><FileText size={12} /> Reports</button>
                </div>
              </Panel>
            </div>
          </>
        );
      })()}
    </ExperimentGate>
  );
}


// Ficha técnica do repositório do Hugging Face (somente metadados; nada foi baixado).
function HubCard({ m }: { m: any }) {
  const gb = (v: number | null | undefined) => (v == null ? NA : v >= 1 ? `${fmt(v, 2)} GB` : `${fmt(v * 1000, 1)} MB`);
  const count = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(2)} B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} M` : `${(n / 1e3).toFixed(1)} K`);
  const rows: [string, string][] = [
    ["Repository", m.repo_id], ["Architecture", m.architecture ?? NA], ["Parameters", m.parameters_total ? count(m.parameters_total) : NA],
    ["Weights fp16 / int8 / 4-bit", m.memory_gb ? `${gb(m.memory_gb.fp16)} / ${gb(m.memory_gb.int8)} / ${gb(m.memory_gb.int4)}` : NA],
    ["Context length", m.context_length ? fmt(m.context_length) : NA], ["KV cache (fp16)", m.kv_cache_mb_per_1k_tokens ? `${fmt(m.kv_cache_mb_per_1k_tokens)} MB / 1k tokens · ${gb(m.kv_cache_gb_full_context)} full context` : NA],
    ["Layers · heads · KV heads", `${m.layers ?? "?"} · ${m.attention_heads ?? "?"} · ${m.kv_heads ?? "?"}`], ["Vocabulary", m.vocab_size ? fmt(m.vocab_size) : NA],
    ["Chat template", m.chat_template ? "yes" : "no"], ["License", m.license ?? "not declared"],
    ["Weight files", `${m.weights_files?.safetensors ?? 0} safetensors · ${m.weights_files?.pickle ?? 0} pickle · ${m.weights_files?.gguf ?? 0} gguf`],
  ];
  return (
    <Panel title="Hugging Face model card — read without downloading" tone="purple">
      <dl className="grid gap-x-6 gap-y-1 sm:grid-cols-2 text-[13px]">
        {rows.map(([k, v]) => (<div key={k} className="flex gap-2 min-w-0"><dt className="text-muted w-48 flex-none">{k}</dt><dd className="break-all">{v}</dd></div>))}
      </dl>
      <p className="text-[11.5px] text-muted mt-2">Memory covers weights only. Behaviour (quality, hallucination, injection) needs a live probe in Model Lab.</p>
    </Panel>
  );
}
