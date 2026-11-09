import { useEffect, useState } from "react";
import { Save, Plus, Trash2 } from "lucide-react";
import logo from "../assets/brand/logo.png";
import { useApp } from "../app/AppState";
import { Chip, KeyValues, Loader, Panel } from "../components/ui";
import { api } from "../services/api";
import type { ServerSettings } from "../types/api";

function Toggle({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex items-center justify-between gap-3 border border-white/10 px-3 py-2 cursor-pointer">
      <span><span className="text-[13px]">{label}</span>{hint && <span className="block text-[11.5px] text-muted">{hint}</span>}</span>
      <button type="button" role="switch" aria-checked={checked} aria-label={label} onClick={() => onChange(!checked)}
        className={`w-12 h-6 border-2 relative flex-none ${checked ? "border-phosphor bg-phosphor/20" : "border-[#4b5578]"}`}>
        <span className={`absolute top-0.5 w-4 h-4 transition-all ${checked ? "left-6 bg-phosphor" : "left-0.5 bg-[#4b5578]"}`} />
      </button>
    </label>
  );
}

export default function SettingsPage() {
  const { prefs, setPrefs, status, online, notify } = useApp();
  const [srv, setSrv] = useState<ServerSettings | null>(null);
  const [newRoot, setNewRoot] = useState("");
  useEffect(() => {
    if (online) api.settings().then(setSrv).catch((e) => notify("error", e.message));
  }, [online]);
  const save = async (s: ServerSettings) => {
    try {
      setSrv(await api.saveSettings(s));
      notify("success", "Settings saved.");
    } catch (e) {
      notify("error", (e as Error).message);
    }
  };
  return (
    <div className="grid gap-3 xl:grid-cols-2">
      <Panel title="Visual preferences" tone="purple" bodyClass="p-3 space-y-2">
        <Toggle label="CRT effects (scanlines, glow)" checked={prefs.crt} onChange={(v) => setPrefs({ crt: v })} hint="Disable for maximum legibility." />
        <Toggle label="Animations" checked={prefs.motion} onChange={(v) => setPrefs({ motion: v })} hint="Also respects the operating system 'reduce motion' setting." />
        <Toggle label="Collapsed sidebar" checked={prefs.sidebarCollapsed} onChange={(v) => setPrefs({ sidebarCollapsed: v })} />
        <label className="flex items-center justify-between gap-3 border border-white/10 px-3 py-2">
          <span className="text-[13px]">Interface language<span className="block text-[11.5px] text-muted">Navigation and labels. Engine findings and reports text are in English; report headings support PT.</span></span>
          <select className="field w-36" value={prefs.lang} onChange={(e) => setPrefs({ lang: e.target.value as "en" | "pt" })} aria-label="Interface language">
            <option value="en">English</option><option value="pt">Português</option>
          </select>
        </label>
      </Panel>
      <Panel title="Data access & limits (local API)" tone="green" bodyClass="p-3 space-y-3">
        {!srv ? <Loader label={online ? "Loading settings" : "Backend offline"} /> : (
          <>
            <div>
              <div className="text-[12px] text-cyan mb-1">AUTHORIZED ROOTS (read-only access)</div>
              <ul className="space-y-1">{srv.allowed_roots.map((r) => (
                <li key={r} className="flex items-center gap-2 text-[12.5px] border border-white/10 px-2 py-1">
                  <span className="flex-1 break-all">{r}</span>
                  <button aria-label={`Remove ${r}`} disabled={srv.allowed_roots.length === 1} className="text-muted hover:text-danger disabled:opacity-30"
                    onClick={() => save({ ...srv, allowed_roots: srv.allowed_roots.filter((x) => x !== r) })}><Trash2 size={14} /></button>
                </li>))}
              </ul>
              <form className="flex gap-2 mt-2" onSubmit={(e) => { e.preventDefault(); save({ ...srv, allowed_roots: [...srv.allowed_roots, newRoot] }).then(() => setNewRoot("")); }}>
                <input className="field" placeholder="C:\\path\\to\\experiments" value={newRoot} onChange={(e) => setNewRoot(e.target.value)} aria-label="New authorized root" />
                <button className="btn btn-sm" disabled={!newRoot} type="submit"><Plus size={12} /> Add</button>
              </form>
            </div>
            <form className="grid sm:grid-cols-3 gap-2 items-end" onSubmit={(e) => { e.preventDefault(); save(srv); }}>
              <label className="text-[11px] text-muted flex flex-col gap-1 sm:col-span-3">Reports directory (inside a root or the app workspace)
                <input className="field" value={srv.reports_dir} onChange={(e) => setSrv({ ...srv, reports_dir: e.target.value })} aria-label="Reports directory" />
              </label>
              <label className="text-[11px] text-muted flex flex-col gap-1">Max records / file
                <input className="field" type="number" min={100} value={srv.max_records} onChange={(e) => setSrv({ ...srv, max_records: Number(e.target.value) })} />
              </label>
              <label className="text-[11px] text-muted flex flex-col gap-1">Max MB / file
                <input className="field" type="number" min={1} value={srv.max_mb} onChange={(e) => setSrv({ ...srv, max_mb: Number(e.target.value) })} />
              </label>
              <button className="btn btn-primary" type="submit"><Save size={12} /> Save</button>
            </form>
          </>
        )}
      </Panel>
      <Panel title="Version & backend status" tone="cyan">
        <div className="flex gap-4 items-start flex-col sm:flex-row">
          <img src={logo} alt="DeepModel Inspector official logo" className="w-40 flex-none" />
          <div className="flex-1 w-full">
            <KeyValues rows={[
              ["Backend", online ? <Chip key="on">online</Chip> : <Chip key="off" tone="danger">offline</Chip>],
              ["App version", status?.app_version], ["Engine version", status?.engine_version], ["Python", status?.python],
              ["Platform", status?.platform], ["Workspace", <span key="w" className="break-all text-[11.5px]">{status?.workspace}</span>],
              ["Network", "localhost only · no external calls"],
            ]} />
          </div>
        </div>
      </Panel>
      <Panel title="Capabilities & compatibility" tone="amber">
        <ul className="text-[12.5px] space-y-1 mb-3">{status?.capabilities.map((c) => <li key={c.kind}><Chip tone="cyan">{c.kind}</Chip> {c.description} <span className="text-muted">— {c.inputs}</span></li>)}</ul>
        <div className="text-[12.5px] text-muted">Python 3.11+ engine (standard library) · FastAPI local API · modern Chromium/Firefox/Edge. Tested on Linux; Windows engine tests passed (Python 3.13).</div>
      </Panel>
      <Panel title="Known limitations" tone="muted" className="xl:col-span-2">
        <ul className="text-[12.5px] text-muted list-disc pl-5 grid md:grid-cols-2 gap-x-6 gap-y-1">{status?.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Panel>
    </div>
  );
}
