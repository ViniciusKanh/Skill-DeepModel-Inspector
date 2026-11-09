import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Braces, FileCode2, FileDown, Microscope, Send, Trophy, User } from "lucide-react";
import logoIcon from "../assets/brand/logo-icon.png";
import { useApp } from "../app/AppState";
import { ExperimentGate } from "../components/layout";
import { Chip, EmptyState, JobProgress, Loader, Panel, SevChip, StatusChip, fmt } from "../components/ui";
import { ExperimentsChecklist, FindingModal } from "../features/findings";
import { useJobRunner, useLatestReport } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { Finding, FullReport } from "../types/api";

const SUGGESTIONS = [
  "Why is my model repeating the same responses?",
  "Why is validation loss increasing?",
  "My fine-tuning results are worse than before.",
  "Is my fine-tuning dataset contaminated?",
  "Meu modelo está apresentando overfitting?",
  "Is my tokenizer inefficient for Portuguese?",
];

function numericEvidence(f: Finding): [string, string][] {
  return Object.entries(f.evidence)
    .filter(([, v]) => typeof v === "number")
    .slice(0, 3)
    .map(([k, v]) => [k.replace(/_/g, " "), fmt(v)]);
}

export default function Investigate() {
  const { project, experiment, prefs, t } = useApp();
  const { metas } = useLatestReport(undefined, ["investigate"]);
  const history = useMemo(() => metas.filter((m) => m.kind === "investigate").slice().reverse(), [metas]);
  const [selected, setSelected] = useState<string | null>(null);
  const [current, setCurrent] = useState<FullReport | null>(null);
  const [loadingRep, setLoadingRep] = useState(false);
  const [question, setQuestion] = useState("");
  const [fresh, setFresh] = useState(false);
  const [open, setOpen] = useState<Finding | null>(null);
  const { job, run, cancel, busy } = useJobRunner();

  const targetId = selected ?? history[history.length - 1]?.id ?? null;
  useEffect(() => {
    setCurrent(null);
    if (!targetId) return;
    setLoadingRep(true);
    api.report(targetId).then(setCurrent).finally(() => setLoadingRep(false));
  }, [targetId]);
  useEffect(() => setSelected(null), [experiment?.id]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = question.trim();
    if (!q || !project || !experiment) return;
    run({ project_id: project.id, experiment_id: experiment.id, kind: "investigate", question: q, params: { fresh } }, (j) => {
      setQuestion("");
      setSelected(j.report_id ?? null);
    });
  };

  const rep = current?.report;
  const ans = rep?.answer;
  const byId = new Map((rep?.findings ?? []).map((f) => [f.id, f]));
  const relevant = (ans?.relevant_findings ?? []).map((id) => byId.get(id)).filter(Boolean) as Finding[];
  const hyps = (rep?.hypotheses ?? []).filter((h) => ans?.hypotheses.includes(h.id));
  const exps = (rep?.experiments ?? []).filter((x) => hyps.some((h) => h.id === x.for) || relevant.some((f) => f.id === x.for));

  return (
    <ExperimentGate>
      <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
        <span>Investigation ID: <span className="text-cyan">{current?.meta.id ?? "—"}</span></span>
        <span>Created: {current ? new Date(current.meta.created).toLocaleString() : "—"}</span>
        <span>Experiment: <span className="text-ink">{experiment?.name}</span></span>
        {ans && <span className="ml-auto flex items-center gap-2">Answer status <StatusChip s={ans.status} /></span>}
      </div>
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <Panel title="Investigation conversation" tone="green" bodyClass="p-3 flex flex-col gap-3">
          <div className="space-y-3 max-h-[440px] overflow-y-auto pr-1" aria-live="polite">
            {history.length === 0 && !busy && (
              <EmptyState small title="Ask a question" text="The engine answers with rule-based evidence from this experiment's artifacts — it is not a generative chatbot." />
            )}
            {history.map((h) => (
              <div key={h.id} className="space-y-2">
                <div className="flex gap-2 items-start">
                  <div className="w-8 h-8 flex-none border-2 border-purple grid place-items-center text-purple"><User size={16} /></div>
                  <button className={`text-left border-2 ${targetId === h.id ? "border-purple bg-purple/10" : "border-purple/40"} px-3 py-2 text-[13px] max-w-[85%]`}
                    onClick={() => setSelected(h.id)} aria-label={`Open investigation ${h.id}`}>
                    <div className="text-[11px] text-purple mb-0.5">You · {new Date(h.created).toLocaleTimeString()}</div>{h.question}
                  </button>
                </div>
                <div className="flex gap-2 items-start pl-6">
                  <img src={logoIcon} alt="" className="w-8 flex-none" />
                  <div className="border-2 border-phosphor/60 px-3 py-2 text-[13px] flex-1">
                    <div className="text-[11px] text-phosphor mb-1 flex items-center gap-2">DeepModel Inspector <StatusChip s={h.answer_status ?? "INCONCLUSIVE"} /></div>
                    {targetId === h.id && ans ? ans.conclusion : <span className="text-muted">Select to view the full answer.</span>}
                    {targetId === h.id && ans?.missing_artifacts.length ? (
                      <ul className="mt-2 text-amber text-[12px] list-disc pl-4">{ans.missing_artifacts.map((m) => <li key={m.intent}>Provide {m.provide}</li>)}</ul>
                    ) : null}
                  </div>
                </div>
              </div>
            ))}
            {busy && <Loader label="Investigating" />}
          </div>
          <form onSubmit={submit} className="flex gap-2 items-center">
            <input className="field h-10" maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)}
              placeholder={t("ask")} aria-label="Investigation question" disabled={busy} />
            <button className="btn btn-primary h-10" type="submit" disabled={busy || !question.trim()} aria-label="Send question"><Send size={14} /></button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip cursor-pointer hover:bg-phosphor/20" onClick={() => setQuestion(s)} type="button">{s}</button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
            <label className="flex items-center gap-1.5"><input type="checkbox" checked={fresh} onChange={(e) => setFresh(e.target.checked)} /> re-run full audit first</label>
            <JobProgress job={job} onCancel={cancel} />
          </div>
        </Panel>
        <Panel title="Prioritized findings" tone="amber" icon={<Trophy size={14} />}>
          {loadingRep && <Loader label="Loading investigation" />}
          {!rep && !loadingRep && <div className="text-muted text-[13px]">Ask a question to see the evidence ranked by severity.</div>}
          {rep && relevant.length === 0 && <div className="text-muted text-[13px]">{ans?.conclusion}</div>}
          <ol className="space-y-2">
            {relevant.slice(0, 6).map((f, i) => (
              <li key={f.id}>
                <button className="w-full text-left border-2 border-amber/50 hover:border-amber p-2 flex gap-3" onClick={() => setOpen(f)}>
                  <span className="font-pixel text-[10px] text-amber border-2 border-amber px-1.5 py-1 h-fit">#{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="flex flex-wrap gap-1.5 items-center"><b className="text-[13.5px]">{f.title}</b></span>
                    <span className="flex flex-wrap gap-1.5 mt-1"><SevChip s={f.severity} /><StatusChip s={f.status} /><span className="text-[11px] text-muted">{f.id} · {f.source}</span></span>
                    <span className="block text-[11.5px] text-muted mt-1">{numericEvidence(f).map(([k, v]) => `${k}: ${v}`).join(" · ")}</span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        </Panel>
      </div>
      {rep && (
        <div className="grid gap-3 xl:grid-cols-3">
          <Panel title={t("evidence")} tone="green" icon={<Microscope size={14} />}>
            <ul className="space-y-2">
              {relevant.map((f) => (
                <li key={f.id}>
                  <button className="w-full text-left border border-phosphor/40 hover:border-phosphor p-2 text-[12.5px]" onClick={() => setOpen(f)}>
                    <div className="flex justify-between gap-2"><b>{f.id} {f.rule}</b><span className="text-cyan">open ›</span></div>
                    <div className="text-muted break-all">{JSON.stringify(f.evidence).slice(0, 140)}</div>
                  </button>
                </li>
              ))}
              {relevant.length === 0 && <li className="text-muted text-[13px]">No supporting evidence for this question.</li>}
            </ul>
          </Panel>
          <Panel title="Root-cause chain (hypothesis tree)" tone="purple">
            <div className="flex flex-col items-center gap-3">
              <div className="border-2 border-danger px-3 py-2 text-center text-[13px] max-w-sm">
                <div className="text-danger text-[11px]">OBSERVED · {ans?.status}</div>
                {relevant[0]?.title ?? rep.question}
              </div>
              {hyps.length > 0 && <div className="w-px h-4 bg-white/40" />}
              <div className="grid gap-2 w-full" style={{ gridTemplateColumns: `repeat(${Math.min(Math.max(hyps.length, 1), 3)}, minmax(0, 1fr))` }}>
                {hyps.map((h, i) => (
                  <div key={h.id} className="border-2 p-2 text-[12px] [overflow-wrap:anywhere]" style={{ borderColor: ["#FFB000", "#A255FF", "#00E5FF"][i % 3] }}>
                    <div className="flex justify-between gap-1"><b>{h.id}</b><Chip tone="amber">{h.status}</Chip></div>
                    <div className="mt-1">{h.statement}</div>
                    <div className="text-muted mt-1">via {h.supporting_findings.join(", ")}</div>
                  </div>
                ))}
              </div>
              {hyps.length === 0 && <div className="text-muted text-[13px]">No hypothesis triggered for this question.</div>}
            </div>
          </Panel>
          <Panel title={t("experiments")} tone="cyan">
            <ExperimentsChecklist items={exps} />
          </Panel>
        </div>
      )}
      {current && (
        <Panel title="Export report" tone="muted" bodyClass="p-3 flex flex-wrap gap-2 items-center">
          <span className="text-[12px] text-muted mr-auto">Shareable investigation report with findings, evidence, hypotheses and next steps.</span>
          <a className="btn btn-sm" href={api.exportUrl(current.meta.id, "json")} download><Braces size={12} /> JSON</a>
          <a className="btn btn-sm btn-purple" href={api.exportUrl(current.meta.id, "markdown", prefs.lang)} download><FileDown size={12} /> Markdown</a>
          <a className="btn btn-sm btn-amber" href={api.exportUrl(current.meta.id, "html", prefs.lang)} download><FileCode2 size={12} /> HTML</a>
        </Panel>
      )}
      <FindingModal finding={open} report={current} onClose={() => setOpen(null)} />
    </ExperimentGate>
  );
}
