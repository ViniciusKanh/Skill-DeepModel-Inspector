import { useEffect, useMemo, useState } from "react";
import { Braces, FileCode2, FileDown, Search } from "lucide-react";
import { useApp } from "../app/AppState";
import { Chip, EmptyState, Loader, Panel, StatusChip } from "../components/ui";
import { ExperimentsChecklist, FindingsTable, HypothesesList } from "../features/findings";
import { api } from "../services/api";
import type { FullReport, ReportMeta } from "../types/api";

export default function Reports() {
  const { project, refreshKey, prefs, t } = useApp();
  const [metas, setMetas] = useState<ReportMeta[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [scope, setScope] = useState<"project" | "all">("project");
  const [kind, setKind] = useState("");
  const [qtext, setQ] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [full, setFull] = useState<FullReport | null>(null);

  useEffect(() => {
    setErr(null);
    api.reports(scope === "project" ? project?.id : undefined).then(setMetas).catch((e) => setErr(e.message));
  }, [project?.id, scope, refreshKey]);
  const rows = useMemo(() => (metas ?? []).filter((m) => (!kind || m.kind === kind) &&
    (!qtext || `${m.id} ${m.experiment_name} ${m.question ?? ""} ${m.project_name}`.toLowerCase().includes(qtext.toLowerCase()))), [metas, kind, qtext]);
  useEffect(() => {
    setFull(null);
    if (sel) api.report(sel).then(setFull).catch((e) => setErr(e.message));
  }, [sel]);
  const kinds = [...new Set((metas ?? []).map((m) => m.kind))];
  const rep = full?.report;

  return (
    <div className="space-y-3">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Panel title="Report history" tone="cyan" bodyClass="p-3 space-y-2">
          <div className="flex flex-wrap gap-2">
            <label className="relative flex-1 min-w-[140px]"><Search size={14} className="absolute left-2 top-2.5 text-muted" />
              <input className="field pl-7" placeholder="Search reports" value={qtext} onChange={(e) => setQ(e.target.value)} aria-label="Search reports" /></label>
            <select className="field w-auto" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Filter by kind">
              <option value="">All kinds</option>{kinds.map((k) => <option key={k}>{k}</option>)}
            </select>
            <select className="field w-auto" value={scope} onChange={(e) => setScope(e.target.value as "project" | "all")} aria-label="Scope">
              <option value="project">Selected project</option><option value="all">All projects</option>
            </select>
          </div>
          {err && <div className="text-danger text-[13px]">{err}</div>}
          {!metas && !err && <Loader label="Listing reports" />}
          {metas && rows.length === 0 && <EmptyState small title="No reports" text="Run an audit, a single analysis or an investigation to create reports." />}
          <ul className="space-y-1.5 max-h-[620px] overflow-y-auto pr-1">
            {rows.map((m) => (
              <li key={m.id}>
                <button onClick={() => setSel(m.id)} className={`w-full text-left border-2 p-2 text-[12.5px] ${sel === m.id ? "border-phosphor bg-phosphor/10" : "border-white/10 hover:border-phosphor/50"}`}>
                  <div className="flex justify-between gap-2"><span className="text-cyan">{m.id}</span><span className="text-muted">{new Date(m.created).toLocaleString()}</span></div>
                  <div className="flex flex-wrap gap-1.5 mt-1 items-center">
                    <Chip tone="purple">{m.kind}</Chip>{m.demo && <Chip tone="amber">demo</Chip>}
                    {m.answer_status && <StatusChip s={m.answer_status} />}
                    <span className="truncate">{m.experiment_name ?? "—"}</span>
                  </div>
                  {m.question && <div className="text-muted mt-1 truncate">“{m.question}”</div>}
                  <div className="text-[11px] text-muted mt-1">
                    {["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"].map((s) => `${s[0]}${m.findings_by_severity[s] ?? 0}`).join(" · ")}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="space-y-3 min-w-0">
          {!sel && <Panel tone="purple"><EmptyState title="Select a report" text="Open any analysis to read its executive summary, findings, evidence and recommendations, or download it." /></Panel>}
          {sel && !full && !err && <Loader label="Opening report" />}
          {full && rep && (
            <>
              <Panel title="Executive summary" tone="green" actions={
                <div className="flex gap-1.5">
                  <a className="btn btn-sm" href={api.exportUrl(full.meta.id, "json")} download aria-label="Download JSON"><Braces size={12} /> JSON</a>
                  <a className="btn btn-sm btn-purple" href={api.exportUrl(full.meta.id, "markdown", prefs.lang)} download aria-label="Download Markdown"><FileDown size={12} /> MD</a>
                  <a className="btn btn-sm btn-amber" href={api.exportUrl(full.meta.id, "html", prefs.lang)} download aria-label="Download HTML"><FileCode2 size={12} /> HTML</a>
                </div>}>
                {full.meta.demo && <div className="mb-2"><Chip tone="amber">demo · synthetic data</Chip></div>}
                {rep.question && <div className="mb-2 text-[13px]"><span className="text-purple">Question:</span> {rep.question}<div className="mt-1 flex items-center gap-2"><StatusChip s={rep.answer?.status ?? "INCONCLUSIVE"} /> {rep.answer?.conclusion}</div></div>}
                <div className="text-[13px] grid sm:grid-cols-2 gap-x-6 gap-y-1">
                  <div>Project: <b>{full.meta.project_name}</b></div><div>Experiment: <b>{full.meta.experiment_name ?? "—"}</b></div>
                  <div>Analyses: {rep.analyses_run.join(", ") || "—"}</div><div>Generated: {rep.generated_at}</div>
                </div>
                <ul className="mt-2 text-[13px] list-disc pl-5">{rep.summary.top_findings.map((x) => <li key={x}>{x}</li>)}</ul>
              </Panel>
              <Panel title={t("findings")} tone="amber"><FindingsTable findings={rep.findings} report={full} /></Panel>
              <div className="grid gap-3 2xl:grid-cols-2">
                <Panel title={t("hypotheses")} tone="purple"><HypothesesList hyps={rep.hypotheses} findings={rep.findings} /></Panel>
                <Panel title={t("experiments")} tone="cyan"><ExperimentsChecklist items={rep.experiments} /></Panel>
              </div>
              <Panel title={t("limitations")} tone="muted">
                <ul className="text-[12.5px] text-muted list-disc pl-5 space-y-1">{rep.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
              </Panel>
              <p className="text-[11.5px] text-muted">Exports: JSON, Markdown and static HTML are generated by the engine renderer. PDF export is not implemented.</p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
