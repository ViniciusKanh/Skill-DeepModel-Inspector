// Estrutura da aplicação: sidebar, cabeçalho com seleção de projeto/experimento, placa inferior e notificações.
import { type ReactNode } from "react";
import { Link, NavLink, useNavigate } from "react-router-dom";
import {
  BarChart3, ChevronsLeft, ChevronsRight, Cpu, Database, FileText, FolderKanban, GitCompare, LayoutGrid, PlayCircle,
  Search, Settings, X,
} from "lucide-react";
import logoIcon from "../assets/brand/logo-icon.png";
import { useApp } from "../app/AppState";
import type { I18nKey } from "../app/i18n";
import { api } from "../services/api";
import { DemoBanner, EmptyState } from "./ui";

export const NAV: { to: string; key: I18nKey; icon: ReactNode }[] = [
  { to: "/", key: "dashboard", icon: <LayoutGrid size={18} /> },
  { to: "/training", key: "training", icon: <BarChart3 size={18} /> },
  { to: "/dataset", key: "dataset", icon: <Database size={18} /> },
  { to: "/tokenizer", key: "tokenizer", icon: <Cpu size={18} /> },
  { to: "/generation", key: "generation", icon: <PlayCircle size={18} /> },
  { to: "/compare", key: "compare", icon: <GitCompare size={18} /> },
  { to: "/investigate", key: "investigate", icon: <Search size={18} /> },
  { to: "/reports", key: "reports", icon: <FileText size={18} /> },
  { to: "/projects", key: "projects", icon: <FolderKanban size={18} /> },
  { to: "/settings", key: "settings", icon: <Settings size={18} /> },
];

export function Sidebar() {
  const { prefs, setPrefs, t } = useApp();
  const c = prefs.sidebarCollapsed;
  return (
    <nav aria-label="Main navigation" className={`panel flex-none flex flex-col gap-1 p-2 ${c ? "w-[62px]" : "w-[252px]"} transition-[width] duration-150 max-lg:w-[62px]`}>
      <Link to="/" className="flex items-center gap-2 px-1 py-2 mb-1" aria-label="DeepModel Inspector home">
        <img src={logoIcon} alt="DeepModel Inspector logo" className="w-11 flex-none drop-shadow-[0_0_6px_rgba(57,255,136,0.35)]" />
        {!c && (
          <span className="max-lg:hidden leading-tight">
            <span className="block font-pixel text-[10px] text-phosphor">DeepModel</span>
            <span className="block font-pixel text-[10px] text-[#f5e6c8]">Inspector</span>
          </span>
        )}
      </Link>
      <div className={`flex items-center gap-2 px-1 pb-1 ${c ? "hidden" : "max-lg:hidden"}`}>
        <span className="bullet" /><span className="panel-title">Navigation</span><span className="hatch" />
      </div>
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} title={t(n.key)}>
          <span className="flex-none">{n.icon}</span>
          {!c && <span className="truncate max-lg:hidden">{t(n.key)}</span>}
        </NavLink>
      ))}
      <button className="nav-item mt-auto max-lg:hidden" onClick={() => setPrefs({ sidebarCollapsed: !c })} aria-label={c ? "Expand sidebar" : "Collapse sidebar"}>
        {c ? <ChevronsRight size={18} /> : <><ChevronsLeft size={18} /> <span className="text-[12px] text-muted">Collapse</span></>}
      </button>
    </nav>
  );
}

export function Header({ title }: { title: string }) {
  const { projects, project, experiment, select, online, t } = useApp();
  return (
    <header className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-3 pb-2">
      <h1 className="pixel-title text-[13px] sm:text-[15px] leading-6 mr-auto min-w-0">
        <span className="text-amber mr-2">▶</span>{title}
      </h1>
      <label className="flex items-center gap-2 text-[11px] text-muted max-sm:w-full">
        {t("project").toUpperCase()}
        <select className="field w-44 py-1 max-sm:w-auto max-sm:flex-1 max-sm:min-w-0" value={project?.id ?? ""} onChange={(e) => select(e.target.value || null, null)} aria-label="Select project">
          <option value="">— none —</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.demo ? "◆ " : ""}{p.name}</option>)}
        </select>
      </label>
      <label className="flex items-center gap-2 text-[11px] text-muted max-sm:w-full">
        {t("experiment").toUpperCase()}
        <select className="field w-52 py-1 max-sm:w-auto max-sm:flex-1 max-sm:min-w-0" value={experiment?.id ?? ""} disabled={!project}
          onChange={(e) => select(project?.id ?? null, e.target.value || null)} aria-label="Select experiment">
          <option value="">— none —</option>
          {project?.experiments.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
        </select>
      </label>
      <span className={`chip ${online ? "" : ""}`} style={{ ["--c" as any]: online ? "#39FF88" : "#FF4D8D" }} role="status">
        <span className={`led ${online ? "led-on" : "led-off"}`} /> {online ? t("backendOnline") : t("backendOffline")}
      </span>
    </header>
  );
}

export function Footer() {
  const { status, online } = useApp();
  return (
    <footer className="flex items-center justify-between gap-3 px-3 pt-2 text-[11px] text-muted">
      <div className="hidden sm:flex gap-1.5" aria-hidden>{[0, 1, 2, 3].map((i) => <span key={i} className="w-3 h-5 bg-black/50 border border-white/10" />)}</div>
      <div className="border-2 border-[#5b4560] bg-black/40 px-3 py-1 font-term text-lg text-amber tracking-wider">
        DMI v{status?.app_version ?? "1.0.0"} · engine {status?.engine_version ?? "—"}
      </div>
      <div className="flex items-center gap-2"><span className="hidden md:inline">{status?.platform}</span><span className={`led ${online ? "led-on" : "led-off"}`} /></div>
    </footer>
  );
}

export function Toasts() {
  const { toasts, dismiss } = useApp();
  return (
    <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 max-w-sm" aria-live="assertive">
      {toasts.map((x) => (
        <div key={x.id} className={`panel ${x.kind === "error" ? "panel-danger" : x.kind === "info" ? "panel-cyan" : ""} bg-navy px-3 py-2 flex gap-2 items-start text-[13px]`} role={x.kind === "error" ? "alert" : "status"}>
          <span className="flex-1">{x.text}</span>
          <button onClick={() => dismiss(x.id)} aria-label="Dismiss"><X size={14} /></button>
        </div>
      ))}
    </div>
  );
}

/** Garante projeto/experimento selecionado; caso contrário, convida a importar ou carregar a demo. */
export function ExperimentGate({ children }: { children: ReactNode }) {
  const { project, experiment, t, reloadProjects, select, notify, online } = useApp();
  const nav = useNavigate();
  if (project && experiment) {
    return (
      <div className="space-y-3">
        {project.demo && <DemoBanner text={t("demoBanner")} />}
        {children}
      </div>
    );
  }
  const loadDemo = async () => {
    try {
      const p = await api.demo();
      await reloadProjects();
      select(p.id, p.experiments[0]?.id ?? null);
      notify("success", "Demo lab loaded (synthetic data).");
    } catch (e) {
      notify("error", (e as Error).message);
    }
  };
  return (
    <div className="panel panel-purple">
      <EmptyState
        title={t("noExperiment")}
        text={online ? "Create a local project and an experiment from your files, or load the DEMO lab built from the bundled synthetic datasets." : "The local API is not reachable. Start it with scripts/Start-DeepModel.ps1."}
        action={
          <div className="flex flex-wrap gap-2 justify-center">
            <button className="btn btn-primary" onClick={loadDemo} disabled={!online}>{t("loadDemo")}</button>
            <button className="btn btn-purple" onClick={() => nav("/projects")}>{t("projects")}</button>
          </div>
        }
      />
    </div>
  );
}
