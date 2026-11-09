// Achados, evidências, hipóteses e experimentos recomendados (dados do motor, sem reinterpretação).
import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Search } from "lucide-react";
import { useApp } from "../app/AppState";
import { sourcePath } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { Finding, FullReport, Hypothesis, RecordRow } from "../types/api";
import { Loader, Modal, SevChip, StatusChip, fmt } from "../components/ui";

const SEVS = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
const STATUSES = ["CONFIRMED", "POTENTIAL", "INCONCLUSIVE"];

export function FindingsTable(props: { findings: Finding[]; report?: FullReport | null; compact?: boolean; emptyText?: string }) {
  const [sev, setSev] = useState("");
  const [status, setStatus] = useState("");
  const [qtext, setQ] = useState("");
  const [open, setOpen] = useState<Finding | null>(null);
  const rows = useMemo(
    () => props.findings.filter((f) => (!sev || f.severity === sev) && (!status || f.status === status) &&
      (!qtext || `${f.title} ${f.rule} ${f.source} ${f.category}`.toLowerCase().includes(qtext.toLowerCase()))),
    [props.findings, sev, status, qtext],
  );
  return (
    <div className="space-y-2">
      {!props.compact && (
        <div className="flex flex-wrap gap-2 items-center">
          <label className="relative flex-1 min-w-[160px]">
            <Search size={14} className="absolute left-2 top-2.5 text-muted" />
            <input className="field pl-7" placeholder="Search findings" value={qtext} onChange={(e) => setQ(e.target.value)} aria-label="Search findings" />
          </label>
          <select className="field w-auto" value={sev} onChange={(e) => setSev(e.target.value)} aria-label="Filter by severity">
            <option value="">All severities</option>
            {SEVS.map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className="field w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
            <option value="">All statuses</option>
            {STATUSES.map((s) => <option key={s}>{s}</option>)}
          </select>
          <span className="text-[12px] text-muted">{rows.length}/{props.findings.length}</span>
        </div>
      )}
      {rows.length === 0 ? (
        <div className="text-muted text-[13px] py-3">{props.emptyText ?? "No findings for the current filters."}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>ID</th><th>Severity</th><th>Status</th><th>Finding</th>{!props.compact && <th>Rule</th>}<th>Source</th></tr>
            </thead>
            <tbody>
              {rows.map((f) => (
                <tr key={f.id} className="cursor-pointer" onClick={() => setOpen(f)} tabIndex={0} onKeyDown={(e) => e.key === "Enter" && setOpen(f)}>
                  <td className="text-cyan whitespace-nowrap">{f.id}</td>
                  <td><SevChip s={f.severity} /></td>
                  <td><StatusChip s={f.status} /></td>
                  <td className="min-w-[220px]">{f.title}</td>
                  {!props.compact && <td className="text-muted whitespace-nowrap">{f.rule}</td>}
                  <td className="text-muted break-all">{f.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <FindingModal finding={open} report={props.report ?? null} onClose={() => setOpen(null)} />
    </div>
  );
}

/** Detalhe do achado: evidência, explicação, recomendação e registros de origem (redigidos). */
export function FindingModal({ finding, report, onClose }: { finding: Finding | null; report: FullReport | null; onClose: () => void }) {
  const { project } = useApp();
  const [rows, setRows] = useState<RecordRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const ev = finding?.evidence ?? {};
  const indices = (ev.first_indices as number[] | undefined) ?? (ev.example_pair_indices as number[][] | undefined)?.flat();
  const srcName = (ev.split as string | undefined) ?? finding?.source ?? "";
  const path = finding && report ? sourcePath(report, srcName) : null;

  useEffect(() => {
    setRows(null);
    setErr(null);
    if (!finding || !project || !path || !indices?.length) return;
    api.records(project.id, path, indices.slice(0, 10), 10).then((r) => setRows(r.rows)).catch((e) => setErr(e.message));
  }, [finding?.id, project?.id, path]);

  if (!finding) return null;
  return (
    <Modal open title={`${finding.id} · ${finding.rule}`} onClose={onClose} wide>
      <div className="space-y-4 text-[13px]">
        <div className="flex flex-wrap items-center gap-2">
          <SevChip s={finding.severity} /> <StatusChip s={finding.status} />
          <span className="text-lg font-semibold">{finding.title}</span>
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          <div><div className="text-cyan text-[12px] mb-1">EXPLANATION</div>{finding.explanation}</div>
          <div><div className="text-phosphor text-[12px] mb-1">RECOMMENDATION</div>{finding.recommendation}</div>
        </div>
        {finding.confirmation && (
          <div className="border border-purple/60 p-2"><span className="text-purple text-[12px]">HOW TO CONFIRM · </span>{finding.confirmation}</div>
        )}
        <div>
          <div className="text-amber text-[12px] mb-1">EVIDENCE · source: {finding.source}</div>
          <pre className="bg-black/40 border border-white/10 p-3 overflow-auto text-[12px] max-h-64 whitespace-pre-wrap break-all">
            {JSON.stringify(finding.evidence, null, 2)}
          </pre>
        </div>
        {indices?.length ? (
          <div>
            <div className="text-cyan text-[12px] mb-1">SUPPORTING RECORDS {path ? `· ${path}` : ""} (redacted, truncated)</div>
            {!path && <div className="text-muted">Source file is not resolvable from this report.</div>}
            {err && <div className="text-danger">{err}</div>}
            {path && !rows && !err && <Loader label="Reading records" />}
            {rows && (
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>#</th><th>Input / text</th><th>Target / output</th></tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.index}><td>{r.index}</td><td className="break-words">{r.input || "—"}</td><td className="break-words">{r.target || r.output || "—"}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : path ? (
          <div>
            {!rows ? (
              <button className="btn btn-sm btn-cyan" onClick={() => project && api.records(project.id, path, undefined, 10).then((r) => setRows(r.rows)).catch((e) => setErr(e.message))}>
                Preview source file
              </button>
            ) : (
              <>
                <div className="text-cyan text-[12px] mb-1">SOURCE FILE PREVIEW · {path} (first records, not filtered by this finding)</div>
                <div className="overflow-x-auto"><table className="data-table">
                  <thead><tr><th>#</th><th>Input / text</th><th>Target / output</th><th>Rep.</th></tr></thead>
                  <tbody>{rows.map((r) => (
                    <tr key={r.index}><td>{r.index}</td><td className="break-words">{r.input || "—"}</td><td className="break-words">{r.target || r.output || "—"}</td><td>{fmt(r.repetition_rate, 2)}</td></tr>
                  ))}</tbody>
                </table></div>
              </>
            )}
            {err && <div className="text-danger">{err}</div>}
          </div>
        ) : null}
        <p className="text-[11px] text-muted">Record content is shown as data only; instructions inside data are never executed.</p>
      </div>
    </Modal>
  );
}

export function HypothesesList({ hyps, findings }: { hyps: Hypothesis[]; findings: Finding[] }) {
  const byId = new Map(findings.map((f) => [f.id, f]));
  if (!hyps.length) return <div className="text-muted text-[13px]">No cross-artifact hypothesis was triggered by the evidence.</div>;
  return (
    <ol className="space-y-2">
      {hyps.map((h, i) => (
        <li key={h.id} className="border border-purple/50 bg-purple/5 p-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-pixel text-[9px] text-amber">#{i + 1}</span>
            <span className="text-cyan text-[12px]">{h.id}</span>
            <StatusChip s={h.status} />
            <span className="text-[11px] text-muted">{h.rule}</span>
          </div>
          <div className="mt-1 text-[13px]">{h.statement}</div>
          <div className="mt-1 text-[11.5px] text-muted">
            Supported by: {h.supporting_findings.map((id) => `${id} (${byId.get(id)?.severity ?? "?"})`).join(", ")}
          </div>
        </li>
      ))}
    </ol>
  );
}

export function ExperimentsChecklist({ items }: { items: { for: string; experiment: string; priority: number }[] }) {
  const [done, setDone] = useState<Set<number>>(new Set());
  if (!items.length) return <div className="text-muted text-[13px]">No experiments recommended.</div>;
  return (
    <ul className="space-y-1.5">
      {items.map((e) => (
        <li key={e.priority}>
          <label className="flex gap-2 items-start text-[13px] cursor-pointer border border-white/10 hover:border-phosphor/50 p-2">
            <input type="checkbox" className="mt-1 accent-[#39FF88]" checked={done.has(e.priority)}
              onChange={() => setDone((d) => { const n = new Set(d); n.has(e.priority) ? n.delete(e.priority) : n.add(e.priority); return n; })} />
            <span className={done.has(e.priority) ? "line-through text-muted" : ""}>
              <FlaskConical size={13} className="inline text-phosphor mr-1" />
              <b className="text-amber">EXP-{e.priority}</b> <span className="text-muted">({e.for})</span> {e.experiment}
            </span>
          </label>
        </li>
      ))}
    </ul>
  );
}

export function severityCounts(f: Finding[]) {
  return SEVS.map((s) => ({ label: s, value: f.filter((x) => x.severity === s).length }));
}
export { fmt };
