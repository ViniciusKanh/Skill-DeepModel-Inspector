import { useEffect, useMemo, useState } from "react";
import { FolderOpen, FolderPlus, RefreshCw, Trash2, CheckCircle2, FileWarning, Folder, File, ArrowUp } from "lucide-react";
import { useApp } from "../app/AppState";
import { Chip, EmptyState, Loader, Modal, Panel } from "../components/ui";
import { api } from "../services/api";
import type { FsEntry } from "../types/api";

const INVALID = new Set(["unreadable", "unknown", "skipped_sensitive", "skipped_unsafe_format"]);
const KIND_TONE: Record<string, "green" | "cyan" | "purple" | "amber" | "danger" | "muted"> = {
  training_log: "cyan", dataset: "green", tokenized: "purple", generations: "amber", run: "cyan", run_metadata: "muted",
  checkpoint: "purple", unreadable: "danger", unknown: "muted", skipped_sensitive: "danger", skipped_unsafe_format: "danger",
};

function FolderBrowser({ open, onClose, onPick }: { open: boolean; onClose: () => void; onPick: (p: string) => void }) {
  const { status } = useApp();
  const [cur, setCur] = useState<{ path: string; parent: string | null; entries: FsEntry[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const go = (p: string) => api.fsList(p).then((r) => { setCur(r); setErr(null); }).catch((e) => setErr(e.message));
  useEffect(() => {
    if (open && status?.allowed_roots[0]) go(status.allowed_roots[0]);
  }, [open, status?.allowed_roots.join("|")]);
  return (
    <Modal open={open} onClose={onClose} title="Select an authorized folder">
      <div className="space-y-2 text-[13px]">
        <div className="flex flex-wrap gap-1.5">{status?.allowed_roots.map((r) => <button key={r} className="chip cursor-pointer" onClick={() => go(r)}>{r}</button>)}</div>
        {err && <div className="text-danger">{err}</div>}
        {cur && (
          <>
            <div className="flex items-center gap-2"><span className="text-cyan break-all flex-1">{cur.path}</span>
              {cur.parent && <button className="btn btn-sm" onClick={() => go(cur.parent!)}><ArrowUp size={12} /> Up</button>}
              <button className="btn btn-sm btn-primary" onClick={() => { onPick(cur.path); onClose(); }}>Use this folder</button></div>
            <ul className="max-h-80 overflow-y-auto border border-white/10">
              {cur.entries.map((e) => (
                <li key={e.path} className="flex items-center gap-2 px-2 py-1 border-b border-white/5">
                  {e.dir ? <Folder size={14} className="text-amber" /> : <File size={14} className={e.supported ? "text-phosphor" : "text-muted"} />}
                  {e.dir ? <button className="hover:text-cyan text-left flex-1" onClick={() => go(e.path)}>{e.name}/</button> : <span className={`flex-1 ${e.supported ? "" : "text-muted"}`}>{e.name}</span>}
                  {!e.dir && <span className="text-[11px] text-muted">{e.size != null ? `${(e.size / 1024).toFixed(1)} KB` : ""}{e.supported ? "" : " · unsupported"}</span>}
                </li>
              ))}
            </ul>
          </>
        )}
        <p className="text-[11.5px] text-muted">Only folders inside authorized roots (Settings) are reachable. Files are read-only; nothing is executed or uploaded.</p>
      </div>
    </Modal>
  );
}

export default function Projects() {
  const { projects, project, experiment, select, reloadProjects, notify, online } = useApp();
  const [name, setName] = useState("");
  const [root, setRoot] = useState("");
  const [browse, setBrowse] = useState(false);
  const [busy, setBusy] = useState(false);
  const [kindFilter, setKindFilter] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [expName, setExpName] = useState("");
  const [extraItem, setExtraItem] = useState("");

  useEffect(() => setPicked(new Set()), [project?.id]);
  const inv = useMemo(() => (project?.inventory ?? []).filter((i) => !kindFilter || i.kind === kindFilter), [project, kindFilter]);
  const kinds = [...new Set((project?.inventory ?? []).map((i) => i.kind))];
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try {
      await fn();
      await reloadProjects();
      notify("success", ok);
    } catch (e) {
      notify("error", (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-3 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)]">
      <div className="space-y-3 min-w-0">
        <Panel title="Local projects" tone="cyan" actions={
          <button className="btn btn-sm btn-amber" disabled={busy || !online} onClick={() => act(async () => { const p = await api.demo(); select(p.id, p.experiments[0]?.id ?? null); }, "Demo lab loaded.")}>Load demo</button>}>
          {projects.length === 0 && <EmptyState small title="No projects" text="Create one below or load the demo lab." />}
          <ul className="space-y-2">
            {projects.map((p) => (
              <li key={p.id} className={`border-2 p-2 ${project?.id === p.id ? "border-phosphor bg-phosphor/5" : "border-white/10"}`}>
                <div className="flex items-center gap-2">
                  <button className="text-left flex-1 min-w-0" onClick={() => select(p.id, p.experiments[0]?.id ?? null)}>
                    <div className="font-semibold truncate">{p.name} {p.demo && <Chip tone="amber">demo</Chip>}</div>
                    <div className="text-[11px] text-muted break-all">{p.root}</div>
                    <div className="text-[11px] text-muted">{p.experiments.length} experiments · {p.inventory.length} files indexed</div>
                  </button>
                  <button className="text-muted hover:text-danger" title="Remove project registration (files are not touched)" aria-label={`Remove ${p.name}`}
                    onClick={() => act(async () => { await api.deleteProject(p.id); if (project?.id === p.id) select(null); }, "Project removed from registry (files untouched).")}><Trash2 size={16} /></button>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
        <Panel title="New local project" tone="green">
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); act(async () => { const p = await api.createProject(name, root); await api.scan(p.id); select(p.id); setName(""); setRoot(""); }, "Project created and scanned."); }}>
            <input className="field" placeholder="Project name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} aria-label="Project name" />
            <div className="flex gap-2">
              <input className="field" placeholder="Root folder (inside an authorized root)" value={root} onChange={(e) => setRoot(e.target.value)} required aria-label="Project root folder" />
              <button type="button" className="btn btn-sm btn-purple" onClick={() => setBrowse(true)}><FolderOpen size={12} /> Browse</button>
            </div>
            <button className="btn btn-primary" type="submit" disabled={busy || !name || !root}><FolderPlus size={12} /> Create & scan</button>
          </form>
        </Panel>
        <Panel title="Supported inputs" tone="muted">
          <ul className="text-[12.5px] space-y-1">
            <li><Chip tone="cyan">training_log</Chip> CSV / JSONL / trainer_state.json with loss per step</li>
            <li><Chip>dataset</Chip> JSONL text · instruction · messages · prompt/response, CSV, TXT</li>
            <li><Chip tone="purple">tokenized</Chip> JSONL with text + tokens / token_ids</li>
            <li><Chip tone="amber">generations</Chip> JSONL outputs (+ decoding params, reference)</li>
            <li><Chip tone="cyan">run</Chip> folders with config.json / metrics.json / logs</li>
            <li><Chip tone="purple">checkpoint</Chip> safetensors headers + JSON configs (pickle never opened)</li>
          </ul>
        </Panel>
      </div>
      <div className="space-y-3 min-w-0">
        {!project ? <Panel tone="purple"><EmptyState title="Select a project" text="Pick or create a local project to index files and define experiments." /></Panel> : (
          <>
            <Panel title={`Experiments — ${project.name}`} tone="amber">
              {project.experiments.length === 0 && <div className="text-muted text-[13px]">No experiments yet. Select files below to create one.</div>}
              <ul className="grid md:grid-cols-2 gap-2">
                {project.experiments.map((x) => (
                  <li key={x.id} className={`border-2 p-2 text-[12.5px] ${experiment?.id === x.id ? "border-amber bg-amber/10" : "border-white/10"}`}>
                    <div className="flex items-center gap-2">
                      <button className="text-left flex-1 min-w-0" onClick={() => select(project.id, x.id)}>
                        <div className="font-semibold flex items-center gap-1.5">{experiment?.id === x.id && <CheckCircle2 size={14} className="text-amber" />}{x.name}</div>
                        <div className="text-muted break-all">{x.items.join(", ")}</div>
                      </button>
                      <button className="text-muted hover:text-danger" aria-label={`Delete ${x.name}`} onClick={() => act(() => api.deleteExperiment(project.id, x.id), "Experiment removed.")}><Trash2 size={14} /></button>
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
            <Panel title="File inventory" tone="green" actions={
              <button className="btn btn-sm btn-cyan" disabled={busy} onClick={() => act(() => api.scan(project.id), "Inventory refreshed.")}><RefreshCw size={12} /> Scan</button>}>
              <div className="flex flex-wrap gap-2 mb-2 items-center">
                <select className="field w-auto" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} aria-label="Filter by kind">
                  <option value="">All kinds</option>{kinds.map((k) => <option key={k}>{k}</option>)}
                </select>
                <span className="text-[12px] text-muted">{inv.length} items · {picked.size} selected · invalid: {(project.inventory ?? []).filter((i) => INVALID.has(i.kind)).length}</span>
              </div>
              {busy && <Loader label="Working" />}
              <div className="overflow-x-auto max-h-[420px]"><table className="data-table">
                <thead><tr><th></th><th>Path</th><th>Kind</th><th>Split</th><th>Notes</th></tr></thead>
                <tbody>{inv.map((i) => (
                  <tr key={i.path}>
                    <td><input type="checkbox" aria-label={`Select ${i.path}`} disabled={INVALID.has(i.kind)} checked={picked.has(i.path)}
                      onChange={() => setPicked((s) => { const n = new Set(s); n.has(i.path) ? n.delete(i.path) : n.add(i.path); return n; })} /></td>
                    <td className="break-all">{i.path}</td>
                    <td><Chip tone={KIND_TONE[i.kind] ?? "muted"}>{i.kind}</Chip></td>
                    <td>{i.split ?? ""}</td>
                    <td className="text-[11.5px] text-muted">{INVALID.has(i.kind) ? <span className="text-danger flex items-center gap-1"><FileWarning size={12} /> not analyzable</span> : i.error ?? i.note ?? ""}</td>
                  </tr>
                ))}</tbody>
              </table></div>
              <form className="flex flex-wrap gap-2 mt-3 items-end" onSubmit={(e) => {
                e.preventDefault();
                const items = [...picked, ...(extraItem ? [extraItem] : [])];
                act(async () => { const x = await api.createExperiment(project.id, expName, items); select(project.id, x.id); setPicked(new Set()); setExpName(""); setExtraItem(""); }, "Experiment created.");
              }}>
                <input className="field flex-1 min-w-[160px]" placeholder="Experiment name" value={expName} onChange={(e) => setExpName(e.target.value)} required aria-label="Experiment name" />
                <input className="field flex-1 min-w-[160px]" placeholder="optional folder (relative), e.g. runs/" value={extraItem} onChange={(e) => setExtraItem(e.target.value)} aria-label="Optional folder item" />
                <button className="btn btn-primary" disabled={busy || !expName || (picked.size === 0 && !extraItem)} type="submit">Create experiment</button>
              </form>
            </Panel>
          </>
        )}
      </div>
      <FolderBrowser open={browse} onClose={() => setBrowse(false)} onPick={(p) => { setRoot(p); if (!name) setName(p.split(/[\\/]/).pop() ?? ""); }} />
    </div>
  );
}
