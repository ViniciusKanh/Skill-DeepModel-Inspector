import { useState } from "react";
import { Cpu, Scissors, Split, Type } from "lucide-react";
import { ExperimentGate } from "../components/layout";
import { BarsChart } from "../components/charts";
import { Chip, EmptyState, Hint, Loader, Panel, StatCard, fmt, pct } from "../components/ui";
import { AuditBar, SingleRunBar } from "../features/analysis";
import { FindingsTable } from "../features/findings";
import { useLatestReport } from "../hooks/useAnalysis";

const ROWS: [string, string, (v: any) => string, string][] = [
  ["tokens_per_word", "Tokens / word", (v) => fmt(v, 3), "Fertility: real tokens divided by \\w+ words."],
  ["tokens_per_char", "Tokens / char", (v) => fmt(v, 4), ""],
  ["chars_per_token", "Chars / token", (v) => fmt(v, 3), ""],
  ["fragmentation_rate", "Fragmentation", pct, "Words split into ≥2 tokens (needs Ġ/▁ word markers)."],
  ["unk_rate", "Unknown tokens", pct, ""],
  ["byte_fallback_rate", "Byte fallback", pct, "<0xNN> byte tokens."],
  ["padding_rate", "Padding", pct, ""],
  ["truncation_rate", "Truncated sequences", pct, "Sequences reaching max_length."],
  ["mean_unused_context", "Unused context", pct, "Mean (max_length − length)/max_length."],
  ["distinct_tokens_observed", "Distinct tokens", (v) => fmt(v), ""],
  ["observed_vocab_coverage", "Observed vocab coverage", pct, "Distinct observed / vocab_size (needs vocab size)."],
];

export default function Tokenizer() {
  const { data, loading } = useLatestReport("tokenizer");
  const block = data?.report.sections.tokenizer?.[0];
  const [maxLen, setMaxLen] = useState("");
  const [vocab, setVocab] = useState("");
  const groups = Object.entries((block?.metrics.groups ?? {}) as Record<string, any>);
  const comp = block?.metrics.comparison;
  const findings = (data?.report.findings ?? []).filter((f) => block?.finding_ids.includes(f.id));
  const g0 = groups[0]?.[1];
  return (
    <ExperimentGate>
      <AuditBar report={data} />
      <Panel title="Analyze provided tokenizations" tone="muted">
        <SingleRunBar kind="tokenizer" label="JSONL with text + tokens / token_ids" fileKinds={["tokenized"]}
          extraParams={{ max_length: maxLen || null, vocab_size: vocab || null }}>
          <label className="text-[11px] text-muted flex flex-col gap-1 w-32">max_length
            <input className="field" inputMode="numeric" value={maxLen} onChange={(e) => setMaxLen(e.target.value.replace(/\D/g, ""))} placeholder="e.g. 2048" />
          </label>
          <label className="text-[11px] text-muted flex flex-col gap-1 w-32">vocab_size
            <input className="field" inputMode="numeric" value={vocab} onChange={(e) => setVocab(e.target.value.replace(/\D/g, ""))} placeholder="optional" />
          </label>
        </SingleRunBar>
        <p className="text-[11.5px] text-muted mt-2">The engine never simulates a tokenizer: export <code>tokens</code> or <code>token_ids</code> from your tokenizer into the JSONL.</p>
      </Panel>
      {loading && <Loader label="Loading tokenizer metrics" />}
      {!loading && !block && <Panel tone="purple"><EmptyState title="No tokenization analyzed" text="Provide a JSONL with text and tokens produced by your tokenizer." small /></Panel>}
      {block && (
        <>
          {g0?.unavailable ? (
            <Panel title="Metrics not computable" tone="amber">
              <p className="text-[13px] mb-2">No tokens were provided, so only text statistics exist ({fmt(g0.chars)} chars, {fmt(g0.words)} words). Unavailable:</p>
              <div className="flex flex-wrap gap-1.5">{g0.unavailable.map((u: string) => <Chip key={u} tone="muted">{u}</Chip>)}</div>
            </Panel>
          ) : (
            <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
              <StatCard tone="cyan" icon={<Type size={20} />} label="Tokens / word" value={fmt(g0?.tokens_per_word, 3)} sub={groups[0]?.[0]} />
              <StatCard tone="purple" icon={<Split size={20} />} label="Fragmentation" value={g0?.fragmentation_rate == null ? "n/a" : pct(g0.fragmentation_rate)} sub="words split into ≥2 tokens" />
              <StatCard tone="amber" icon={<Cpu size={20} />} label="Byte fallback / UNK" value={`${pct(g0?.byte_fallback_rate)}`} sub={`unk ${pct(g0?.unk_rate)}`} />
              <StatCard tone="danger" icon={<Scissors size={20} />} label="Truncation" value={g0?.truncation_rate == null ? "n/a" : pct(g0.truncation_rate)} sub={g0?.truncation_rate == null ? "set max_length" : `${fmt(g0.truncated_records)} sequences`} />
            </div>
          )}
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Panel title="Tokenizer comparison" tone="cyan">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead><tr><th>Metric</th>{groups.map(([g]) => <th key={g}>{g}</th>)}</tr></thead>
                  <tbody>
                    {ROWS.map(([k, label, f, hint]) => (
                      <tr key={k}><td>{label} {hint && <Hint text={hint} />}</td>{groups.map(([g, m]) => <td key={g} className="tabular-nums">{m[k] == null ? "—" : f(m[k])}</td>)}</tr>
                    ))}
                    <tr><td>Tokens / record (mean · p95)</td>{groups.map(([g, m]) => <td key={g}>{fmt(m.tokens_per_record?.mean, 1)} · {fmt(m.tokens_per_record?.p95)}</td>)}</tr>
                  </tbody>
                </table>
              </div>
              {comp && <p className="text-[12px] text-muted mt-2">Most efficient: <span className="text-phosphor">{comp.most_efficient}</span> · same texts: {String(comp.same_texts)}</p>}
            </Panel>
            <Panel title="Relative cost (tokens/word)" tone="purple">
              {groups.some(([, m]) => m.tokens_per_word) ? (
                <BarsChart ariaLabel="Tokens per word by tokenizer" color="#00E5FF" valueLabel="tokens/word"
                  data={groups.filter(([, m]) => m.tokens_per_word).map(([g, m]) => ({ label: g, value: m.tokens_per_word }))} />
              ) : <div className="text-muted text-[13px]">No tokenization to compare.</div>}
            </Panel>
          </div>
          <Panel title="Findings & recommendations" tone="amber">
            <FindingsTable findings={findings} report={data} emptyText="No tokenizer rule fired at the documented thresholds." />
            {block.limitations && block.limitations.length > 0 && <ul className="mt-2 text-[12px] text-muted list-disc pl-5">{block.limitations.map((l) => <li key={l}>{l}</li>)}</ul>}
          </Panel>
        </>
      )}
    </ExperimentGate>
  );
}
