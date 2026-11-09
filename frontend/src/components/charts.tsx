// Gráficos interativos (Recharts): seleção de séries, tooltip, zoom por intervalo (Brush) e estatística do intervalo.
import { useMemo, useState } from "react";
import {
  Bar, BarChart, Brush, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { fmt } from "./ui";

export interface SeriesDef { key: string; label: string; color: string; axis?: "left" | "right" }
type Pts = [number, number | null][];

const tooltipStyle = {
  background: "#0b1839", border: "1.5px solid #00E5FF", borderRadius: 3, fontFamily: "IBM Plex Mono", fontSize: 12,
};

/** Une séries (passo, valor) em linhas por passo para o Recharts. */
export function mergeSeries(series: Record<string, Pts | undefined>, keys: string[]) {
  const map = new Map<number, Record<string, number | null>>();
  for (const k of keys) {
    for (const [x, y] of series[k] ?? []) {
      const row = map.get(x) ?? { step: x };
      row[k] = y;
      map.set(x, row);
    }
  }
  return [...map.values()].sort((a, b) => (a.step as number) - (b.step as number));
}

export function TimeSeriesChart(props: {
  series: Record<string, Pts | undefined>; defs: SeriesDef[]; height?: number; log?: boolean; brush?: boolean;
  showStats?: boolean; ariaLabel: string;
}) {
  const available = props.defs.filter((d) => (props.series[d.key]?.length ?? 0) > 0);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [range, setRange] = useState<{ startIndex?: number; endIndex?: number }>({});
  const data = useMemo(() => mergeSeries(props.series, available.map((d) => d.key)), [props.series, available.length]);
  const visible = available.filter((d) => !hidden.has(d.key));
  const sliced = data.slice(range.startIndex ?? 0, (range.endIndex ?? data.length - 1) + 1);
  const hasRight = visible.some((d) => d.axis === "right");

  if (!available.length) return <div className="text-muted text-sm py-6 text-center">No series available in this log.</div>;
  return (
    <div className="space-y-2" aria-label={props.ariaLabel} role="figure">
      <div className="flex flex-wrap gap-2">
        {available.map((d) => (
          <button
            key={d.key}
            className="chip cursor-pointer"
            style={{ ["--c" as any]: hidden.has(d.key) ? "#4b5578" : d.color }}
            aria-pressed={!hidden.has(d.key)}
            onClick={() => setHidden((h) => {
              const n = new Set(h);
              n.has(d.key) ? n.delete(d.key) : n.add(d.key);
              return n;
            })}
          >
            <span className="w-2.5 h-2.5" style={{ background: hidden.has(d.key) ? "transparent" : d.color }} /> {d.label}
          </button>
        ))}
      </div>
      <div style={{ height: props.height ?? 260 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: hasRight ? 8 : 16, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#1d2a55" strokeDasharray="2 4" />
            <XAxis dataKey="step" stroke="#7d8bb5" tick={{ fontSize: 11 }} type="number" domain={["dataMin", "dataMax"]} />
            <YAxis yAxisId="left" stroke="#7d8bb5" tick={{ fontSize: 11 }} width={54} scale={props.log ? "log" : "auto"}
              domain={props.log ? ["auto", "auto"] : ["auto", "auto"]} allowDataOverflow tickFormatter={(v) => fmt(v, 3)} />
            {hasRight && <YAxis yAxisId="right" orientation="right" stroke="#7d8bb5" tick={{ fontSize: 11 }} width={58} tickFormatter={(v) => fmt(v, 3)} />}
            <Tooltip contentStyle={tooltipStyle} labelFormatter={(v) => `step ${v}`} formatter={(v: number) => fmt(v, 5)} />
            {visible.map((d) => (
              <Line key={d.key} yAxisId={d.axis ?? "left"} type="monotone" dataKey={d.key} name={d.label} stroke={d.color}
                dot={false} strokeWidth={1.8} connectNulls isAnimationActive={false} />
            ))}
            {props.brush !== false && data.length > 10 && (
              <Brush dataKey="step" height={18} stroke="#A255FF" fill="#0b1839" travellerWidth={8}
                onChange={(r: any) => setRange({ startIndex: r.startIndex, endIndex: r.endIndex })} />
            )}
          </LineChart>
        </ResponsiveContainer>
      </div>
      {props.showStats !== false && sliced.length > 0 && (
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Series (selected range)</th><th>Steps</th><th>Min</th><th>Max</th><th>Mean</th><th>First → Last</th></tr>
            </thead>
            <tbody>
              {visible.map((d) => {
                const vals = sliced.map((r) => r[d.key]).filter((v): v is number => typeof v === "number");
                if (!vals.length) return null;
                const mean = vals.reduce((a, b) => a + b, 0) / vals.length;
                return (
                  <tr key={d.key}>
                    <td style={{ color: d.color }}>{d.label}</td>
                    <td>{fmt(sliced[0].step)}–{fmt(sliced[sliced.length - 1].step)}</td>
                    <td>{fmt(Math.min(...vals))}</td><td>{fmt(Math.max(...vals))}</td><td>{fmt(mean)}</td>
                    <td>{fmt(vals[0])} → {fmt(vals[vals.length - 1])}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="text-[11px] text-muted mt-1">Range statistics are descriptive values of the plotted points; diagnostics come from the engine.</p>
        </div>
      )}
    </div>
  );
}

export function BarsChart(props: { data: { label: string; value: number }[]; color?: string; height?: number; ariaLabel: string; valueLabel?: string }) {
  return (
    <div style={{ height: props.height ?? 220 }} role="figure" aria-label={props.ariaLabel}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={props.data} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
          <CartesianGrid stroke="#1d2a55" strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="label" stroke="#7d8bb5" tick={{ fontSize: 10 }} interval={0} />
          <YAxis stroke="#7d8bb5" tick={{ fontSize: 11 }} width={48} />
          <Tooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(57,255,136,0.08)" }} />
          <Legend wrapperStyle={{ display: "none" }} />
          <Bar dataKey="value" maxBarSize={70} name={props.valueLabel ?? "value"} fill={props.color ?? "#39FF88"} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
