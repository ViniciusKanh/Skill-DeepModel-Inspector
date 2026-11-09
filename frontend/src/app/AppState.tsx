// Estado global: status do backend, projetos, seleção ativa, preferências visuais e notificações.
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../services/api";
import type { Experiment, Project, Status } from "../types/api";
import { translate, type I18nKey, type Lang } from "./i18n";

export interface Prefs { crt: boolean; motion: boolean; lang: Lang; sidebarCollapsed: boolean }
export interface Toast { id: number; kind: "success" | "error" | "info"; text: string }

interface Ctx {
  status: Status | null; online: boolean; projects: Project[]; project: Project | null; experiment: Experiment | null;
  prefs: Prefs; toasts: Toast[]; refreshKey: number;
  setPrefs: (p: Partial<Prefs>) => void; select: (projectId: string | null, experimentId?: string | null) => void;
  reloadProjects: () => Promise<Project[]>; notify: (kind: Toast["kind"], text: string) => void; dismiss: (id: number) => void;
  bump: () => void; t: (k: I18nKey) => string;
}

const AppCtx = createContext<Ctx | null>(null);
const PREFS_KEY = "dmi.prefs";
const SEL_KEY = "dmi.selection";

function load<T>(key: string, fallback: T): T {
  try {
    const v = localStorage.getItem(key);
    return v ? { ...fallback, ...JSON.parse(v) } : fallback;
  } catch {
    return fallback;
  }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [online, setOnline] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [sel, setSel] = useState(() => load<{ p: string | null; e: string | null }>(SEL_KEY, { p: null, e: null }));
  const [prefs, setPrefsState] = useState<Prefs>(() =>
    load<Prefs>(PREFS_KEY, { crt: true, motion: true, lang: "en", sidebarCollapsed: false }),
  );
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts.slice(-3), { id, kind, text }]);
    window.setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), kind === "error" ? 8000 : 4500);
  }, []);
  const dismiss = useCallback((id: number) => setToasts((ts) => ts.filter((x) => x.id !== id)), []);

  const reloadProjects = useCallback(async () => {
    const ps = await api.projects();
    setProjects(ps);
    return ps;
  }, []);

  useEffect(() => {
    let alive = true;
    const ping = async () => {
      try {
        const s = await api.status();
        if (!alive) return;
        setStatus(s);
        setOnline(true);
      } catch {
        if (alive) setOnline(false);
      }
    };
    ping();
    reloadProjects().catch(() => undefined);
    const h = window.setInterval(ping, 15000);
    return () => {
      alive = false;
      window.clearInterval(h);
    };
  }, [reloadProjects]);

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("fx-off", !prefs.crt);
    root.classList.toggle("motion-off", !prefs.motion);
    root.lang = prefs.lang === "pt" ? "pt-BR" : "en";
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch {
      /* armazenamento indisponível: preferências valem apenas nesta sessão */
    }
  }, [prefs]);

  const select = useCallback((p: string | null, e: string | null = null) => {
    setSel({ p, e });
    try {
      localStorage.setItem(SEL_KEY, JSON.stringify({ p, e }));
    } catch {
      /* ignore */
    }
  }, []);

  const project = projects.find((p) => p.id === sel.p) ?? null;
  const experiment = project?.experiments.find((e) => e.id === sel.e) ?? null;

  const value = useMemo<Ctx>(
    () => ({
      status, online, projects, project, experiment, prefs, toasts, refreshKey,
      setPrefs: (p) => setPrefsState((cur) => ({ ...cur, ...p })),
      select, reloadProjects, notify, dismiss, bump: () => setRefreshKey((k) => k + 1),
      t: (k) => translate(prefs.lang, k),
    }),
    [status, online, projects, project, experiment, prefs, toasts, refreshKey, select, reloadProjects, notify, dismiss],
  );
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp outside AppProvider");
  return c;
}
