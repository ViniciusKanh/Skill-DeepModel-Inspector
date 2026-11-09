import { useEffect, useMemo, useState } from "react";
import { Activity, Gauge, TrendingDown, Zap } from "lucide-react";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { TimeSeriesChart } from "../components/charts";
import { Chip, EmptyState, Hint, KeyValues, Loader, Panel, StatCard, StatusChip, fmt, pct } from "../components/ui";
import { AuditBar, SingleRunBar } from "../features/analysis";
import { FindingsTable } from "../features/findings";
import { sourcePath, useLatestReport } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { Finding, SeriesResponse } from "../types/api";

const CHECKS: { label: string; rules: string[]; needs?: string; hint: string }[] = [
  { label: "Divergence / NaN", rules: ["TRN.NONFINITE", "TRN.DIVERGENCE"], hint: "Non-finite values or loss ending above its start (TRN.NONFINITE, TRN.DIVERGENCE)." },
  { label: "Overfitting", rules: ["TRN.OVERFIT", "TRN.VAL_BELOW_TRAIN"], needs: "TRN.NO_VALIDATION", hint: "Eval loss rising ≥5% after its minimum while train loss falls." },
  { label: "Plateau", rules: ["TRN.PLATEAU"], hint: "≥10% overall improvement but <1% over the last third." },
  { label: "Underfitting", rules: ["TRN.UNDERFIT"], hint: "<10% improvement between first and last windows." },
  { label: "Unstable learning", rules: ["TRN.INSTABILITY", "TRN.LR_HIGH"], hint: "Repeated spikes vs. rolling median; association with peak LR." },
  { label: "Gradient health", rules: ["TRN.GRAD_EXPLOSION", "TRN.GRAD_VANISH"], needs: "grad", hint: "Only evaluated when grad_norm is logged." },
];

function checkState(findings: Finding[], limitations: string[], c: (typeof CHECKS)[number]) {
  const hit = findings.find((f) => c.rules.includes(f.rule));
  if (hit) return { label: hit.status, f: hit };
  if (c.needs === "grad" && limitations.some((l) => l.includes("Gradient norm not logged"))) return { label: "NOT EVALUATED" };
  if (c.needs && findings.some((f) => f.rule === c.needs)) return { label: "NOT EVALUATED" };
  if (limitations.some((l) => l.includes("fewer than"))) return { label: "NOT EVALUATED" };
  return { label: "NOT DETECTED" };
}

export default function Training() {
  const { data, loading } = useLatestReport("training");
  const { project } = useApp();
  const blocks = data?.report.sections.training ?? [];
  const [bi, setBi] = useState(0);
  const block = blocks[Math.min(bi, blocks.length - 1)];
  const path = block ? sourcePath(data, block.source) : null;
  const [series, setSeries] = useState<SeriesResponse | null>(null);
  const [serr, setSerr] = useState<string | null>(null);
  const [log, setLog] = useState(false);

  useEffect(() => {
    setSeries(null);
    setSerr(null);
    if (project && path) api.series(project.id, path).then(setSeries).catch((e) => setSerr(e.message));
  }, [project?.id, path]);

  const findings = useMemo(() => (data?.report.findings ?? []).filter((f) => block?.finding_ids.includes(f.id)), [data, block]);
  const m = block?.metrics ?? {};
  const lims = block?.limitations ?? [];

  return (
    <ExperimentGate>
      <AuditBar report={data} />
      <Panel title="Analyze a training log" tone="muted" bodyClass="p-3">
        <SingleRunBar kind="train" label="Training log (CSV / JSONL / trainer_state.json)" fileKinds={["training_log"]} />
      </Panel>
      {loading && <Loader label="Loading training diagnostics" />}
      {!loading && !block && <Panel tone="purple"><EmptyState title="No training log analyzed" text="Run the audit or analyze a training log above." small /></Panel>}
      {block && (
        <>
          {blocks.length > 1 && (
            <div className="flex flex-wrap gap-2">{blocks.map((b, i) => (
              <button key={i} className={`btn btn-sm ${i === bi ? "btn-primary" : ""}`} onClick={() => setBi(i)}>{b.source}</button>
            ))}</div>
          )}
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-6">
            <StatCard icon={<TrendingDown size={20} />} label="Train loss (last)" value={fmt(m.train_loss?.last)} sub={`change ${pct(m.train_loss?.relative_change)}`} />
            <StatCard tone="purple" icon={<TrendingDown size={20} />} label="Val loss (best)" value={fmt(m.val_loss?.min)}
              sub={m.val_loss ? `@ step ${fmt(m.val_loss.argmin_step)} · last ${fmt(m.val_loss.last)}` : "not logged"} />
            <StatCard tone="amber" icon={<Gauge size={20} />} label="Perplexity (val)" value={fmt(m.val_perplexity_derived?.min ?? null, 3)}
              sub={m.perplexity_source ?? "not available"} hint="Derived perplexity assumes mean token cross-entropy in nats." />
            <StatCard tone="cyan" icon={<Activity size={20} />} label="Learning rate" value={m.lr ? fmt(m.lr.max) : "not logged"} sub={m.lr ? `min ${fmt(m.lr.min)} · ρ(lr,loss) ${fmt(m.lr_loss_spearman, 3)}` : ""} />
            <StatCard tone="green" icon={<Zap size={20} />} label="Grad norm" value={m.grad_norm ? fmt(m.grad_norm.median, 3) : "not logged"} sub={m.grad_norm ? `max ${fmt(m.grad_norm.max)} · ${fmt(m.grad_norm_explosions)} explosions` : "median"} />
            <StatCard tone="danger" icon={<Activity size={20} />} label="Loss spikes" value={fmt(m.train_loss_spikes ?? 0)} sub={`${fmt(m.rows)} log rows`} />
          </div>
          <div className="grid gap-3 xl:grid-cols-2">
            <Panel title="Train & validation loss" tone="cyan" actions={
              <label className="text-[11px] text-muted flex items-center gap-1"><input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> log scale</label>}>
              {serr && <div className="text-danger text-[13px]">{serr}</div>}
              {!series && !serr && <Loader label="Reading series" />}
              {series && <TimeSeriesChart ariaLabel="Loss curves" log={log} series={series.series as any}
                defs={[{ key: "train_loss", label: "Train loss", color: "#39FF88" }, { key: "val_loss", label: "Val loss", color: "#FF4DD8" }]} />}
            </Panel>
            <Panel title="Learning rate timeline" tone="cyan">
              {series && <TimeSeriesChart ariaLabel="Learning rate" series={series.series as any} defs={[{ key: "lr", label: "Learning rate", color: "#00E5FF" }]} />}
            </Panel>
            <Panel title="Perplexity trend" tone="amber" actions={series?.perplexity_source ? <Chip tone="amber">{series.perplexity_source}</Chip> : null}>
              {series && <TimeSeriesChart ariaLabel="Perplexity" series={series.series as any} defs={[{ key: "val_ppl", label: "Val perplexity", color: "#FFB000" }]} />}
            </Panel>
            <Panel title="Gradient norm" tone="purple">
              {series && <TimeSeriesChart ariaLabel="Gradient norm" series={series.series as any} defs={[{ key: "grad_norm", label: "Grad norm", color: "#A255FF" }]} />}
            </Panel>
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
            <Panel title="Convergence & stability checks" tone="amber">
              <ul className="space-y-1.5">
                {CHECKS.map((c) => {
                  const st = checkState(findings, lims, c);
                  return (
                    <li key={c.label} className="flex items-center gap-2 border border-white/10 px-2 py-1.5 text-[13px]">
                      <span className="flex-1">{c.label} <Hint text={c.hint} /></span>
                      {st.f ? <StatusChip s={st.label} /> : <Chip tone={st.label === "NOT DETECTED" ? "green" : "muted"}>{st.label}</Chip>}
                    </li>
                  );
                })}
              </ul>
              <div className="mt-3 text-[12px] text-cyan">WINDOW STABILITY (train loss, 4 windows)</div>
              <KeyValues rows={(m.train_loss?.window_mean ?? []).map((v: number, i: number) => [`window ${i + 1} mean ± std`, `${fmt(v)} ± ${fmt(m.train_loss.window_std?.[i])}`])} />
              {m.val_train_gap && <div className="mt-2"><KeyValues rows={[["val − train gap (first → last)", `${fmt(m.val_train_gap.first)} → ${fmt(m.val_train_gap.last)}`]]} /></div>}
            </Panel>
            <Panel title="Diagnostic findings">
              <FindingsTable findings={findings} report={data} emptyText="No training rule fired at the documented thresholds." />
              {lims.length > 0 && <ul className="mt-2 text-[12px] text-muted list-disc pl-5">{lims.map((l) => <li key={l}>{l}</li>)}</ul>}
            </Panel>
          </div>
          <Panel title="Recommended next experiments" tone="purple">
            <ol className="grid md:grid-cols-3 gap-2 text-[13px]">
              {findings.filter((f) => f.confirmation).slice(0, 6).map((f, i) => (
                <li key={f.id} className="border border-purple/50 p-2"><span className="font-pixel text-[9px] text-purple mr-1">{i + 1}</span> {f.confirmation}<div className="text-[11px] text-muted mt-1">for {f.id} · {f.title}</div></li>
              ))}
              {!findings.some((f) => f.confirmation) && <li className="text-muted">No follow-up experiment required by the current findings.</li>}
            </ol>
          </Panel>
        </>
      )}
    </ExperimentGate>
  );
}
