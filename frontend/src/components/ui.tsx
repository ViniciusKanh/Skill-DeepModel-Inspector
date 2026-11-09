// Componentes visuais reutilizáveis do design system "Retro AI Lab".
import { useEffect, useRef, type ReactNode } from "react";
import { Info, X } from "lucide-react";
import mascot from "../assets/brand/mascot.png";
import type { FindingStatus, Job, Severity } from "../types/api";

export type Tone = "green" | "cyan" | "purple" | "amber" | "danger" | "muted";
const toneClass: Record<Tone, string> = {
  green: "", cyan: "panel-cyan", purple: "panel-purple", amber: "panel-amber", danger: "panel-danger", muted: "panel-muted",
};
export const toneColor: Record<Tone, string> = {
  green: "#39FF88", cyan: "#00E5FF", purple: "#A255FF", amber: "#FFB000", danger: "#FF4D8D", muted: "#6b7aa8",
};

export function Panel(props: {
  title?: ReactNode; tone?: Tone; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string;
  bodyClass?: string; id?: string;
}) {
  const { title, tone = "green", icon, actions, children, className = "", bodyClass = "p-3", id } = props;
  return (
    <section id={id} className={`panel ${toneClass[tone]} flex flex-col ${className}`} aria-label={typeof title === "string" ? title : undefined}>
      {title && (
        <header className="flex items-center gap-2 px-3 pt-2.5 pb-2 border-b border-white/5 min-w-0">
          <span className="bullet" aria-hidden />
          {icon && <span style={{ color: toneColor[tone] }} className="flex-none">{icon}</span>}
          <h2 className="panel-title truncate">{title}</h2>
          <span className="hatch hidden sm:block" aria-hidden />
          <div className="ml-auto flex items-center gap-2 flex-none">{actions}</div>
        </header>
      )}
      <div className={`${bodyClass} min-w-0 flex-1`}>{children}</div>
    </section>
  );
}

export function StatCard(props: { label: string; value: ReactNode; sub?: ReactNode; tone?: Tone; icon?: ReactNode; hint?: string }) {
  const { label, value, sub, tone = "green", icon, hint } = props;
  return (
    <div className={`panel ${toneClass[tone]} px-3 py-2.5 flex gap-3 items-start`} title={hint}>
      {icon && <div style={{ color: toneColor[tone] }} className="mt-0.5 flex-none">{icon}</div>}
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wide" style={{ color: toneColor[tone] }}>{label}</div>
        <div className="kv-value text-ink truncate">{value}</div>
        {sub && <div className="text-[11px] text-muted mt-0.5 truncate">{sub}</div>}
      </div>
    </div>
  );
}

const sevTone: Record<string, Tone> = { CRITICAL: "danger", HIGH: "danger", MEDIUM: "amber", LOW: "cyan", INFO: "muted" };
const statusTone: Record<string, Tone> = { CONFIRMED: "green", POTENTIAL: "amber", INCONCLUSIVE: "muted" };

export function SevChip({ s }: { s: Severity | string }) {
  return <span className="chip" style={{ ["--c" as any]: toneColor[sevTone[s] ?? "muted"] }}>{s}</span>;
}
export function StatusChip({ s }: { s: FindingStatus | string }) {
  return <span className="chip" style={{ ["--c" as any]: toneColor[statusTone[s] ?? "muted"] }}>{s}</span>;
}
export function Chip({ children, tone = "green", title }: { children: ReactNode; tone?: Tone; title?: string }) {
  return <span className="chip" title={title} style={{ ["--c" as any]: toneColor[tone] }}>{children}</span>;
}

export function Hint({ text }: { text: string }) {
  return (
    <span className="inline-flex text-muted hover:text-cyan cursor-help align-middle" title={text} aria-label={text} tabIndex={0}>
      <Info size={13} />
    </span>
  );
}

export function EmptyState(props: { title: string; text?: ReactNode; action?: ReactNode; small?: boolean }) {
  return (
    <div className={`flex ${props.small ? "flex-row text-left gap-4 py-3" : "flex-col items-center text-center gap-3 py-8"} items-center px-4`}>
      <img src={mascot} alt="" className={`pixelated rounded ${props.small ? "w-20" : "w-40"}`} />
      <div className="space-y-2">
        <div className="pixel-title text-[11px] leading-5">{props.title}</div>
        {props.text && <div className="text-muted text-[13px] max-w-xl">{props.text}</div>}
        {props.action && <div className="pt-1">{props.action}</div>}
      </div>
    </div>
  );
}

export function Loader({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-3 py-6 justify-center font-term text-xl text-phosphor" role="status" aria-live="polite">
      <span>&gt; {label}</span>
      <span className="blink">█</span>
    </div>
  );
}

/** Progresso: barra determinada somente quando o backend informa etapas reais. */
export function JobProgress({ job, onCancel }: { job: Job | null; onCancel?: () => void }) {
  if (!job) return null;
  const active = job.status === "queued" || job.status === "running";
  const known = job.progress_total != null && job.progress_total > 0 && job.progress_done != null;
  const pct = known ? Math.round((100 * (job.progress_done as number)) / (job.progress_total as number)) : 0;
  return (
    <div className="flex items-center gap-3 min-w-0" role="status" aria-live="polite">
      <div className={`progress-pixel w-40 flex-none ${active && !known ? "progress-indeterminate" : ""}`} aria-hidden>
        <div style={{ width: known ? `${pct}%` : active ? undefined : "100%" }} />
      </div>
      <span className="text-[12px] text-muted truncate">
        {job.status.toUpperCase()}
        {known ? ` · ${job.progress_done}/${job.progress_total}` : ""} · {job.error ?? job.message}
      </span>
      {active && onCancel && (
        <button className="btn btn-sm btn-danger" onClick={onCancel}>Cancel</button>
      )}
    </div>
  );
}

export function Modal(props: { open: boolean; title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!props.open) return;
    const k = (e: KeyboardEvent) => e.key === "Escape" && props.onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [props.open, props.onClose]);
  if (!props.open) return null;
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-3" onMouseDown={props.onClose}>
      <div
        ref={ref}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={props.title}
        className={`panel panel-cyan w-full ${props.wide ? "max-w-5xl" : "max-w-2xl"} max-h-[88vh] flex flex-col bg-navy`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-2 px-4 py-3 border-b border-white/10">
          <span className="bullet" />
          <h2 className="panel-title">{props.title}</h2>
          <button className="ml-auto text-muted hover:text-ink" onClick={props.onClose} aria-label="Close"><X size={18} /></button>
        </header>
        <div className="overflow-auto p-4">{props.children}</div>
      </div>
    </div>
  );
}

export function KeyValues({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1.5 text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted truncate">{k}</dt>
          <dd className="font-semibold text-right tabular-nums">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export const fmt = (v: unknown, digits = 4): string => {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return String(v);
    if (Number.isInteger(v)) return v.toLocaleString("en-US");
    return Math.abs(v) < 1e-3 && v !== 0 ? v.toExponential(2) : Number(v.toFixed(digits)).toString();
  }
  return String(v);
};
export const pct = (v: unknown) => (typeof v === "number" ? `${(v * 100).toFixed(2)}%` : "—");

export function DemoBanner({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 border-2 border-amber text-amber bg-amber/10 text-[12px] font-semibold" role="note">
      <span className="font-pixel text-[9px]">DEMO</span>
      <span className="truncate">{text}</span>
    </div>
  );
}
