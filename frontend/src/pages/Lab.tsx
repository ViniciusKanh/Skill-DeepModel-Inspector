import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Braces, Cpu, FileCode2, FileDown, Globe, Laptop, LayoutDashboard, Play, PlugZap, Send, Server, Trash2, Zap } from "lucide-react";
import { useApp } from "../app/AppState";
import { TimeSeriesChart } from "../components/charts";
import { Chip, EmptyState, JobProgress, Loader, Panel, StatCard, StatusChip, fmt, pct } from "../components/ui";
import { ConnectWizard } from "../features/connect";
import { FindingsTable, HypothesesList } from "../features/findings";
import { useJobRunner } from "../hooks/useAnalysis";
import { api } from "../services/api";
import type { FullReport, ProbeRecord, Target, TargetTest } from "../types/api";

const PRESETS: { label: string; url: string; model: string }[] = [
  { label: "Ollama (local)", url: "http://localhost:11434/v1", model: "llama3.1:8b" },
  { label: "LM Studio (local)", url: "http://localhost:1234/v1", model: "local-model" },
  { label: "llama.cpp server (local)", url: "http://localhost:8080/v1", model: "default" },
  { label: "vLLM (local)", url: "http://localhost:8000/v1", model: "meta-llama/Llama-3.1-8B-Instruct" },
  { label: "OpenAI (online)", url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { label: "Custom OpenAI-compatible", url: "", model: "" },
];
const QUESTIONS = [
  "Is my model vulnerable to prompt injection?",
  "Why is my model repeating?",
  "Does my model follow JSON format instructions?",
  "Is my model hallucinating against the context?",
  "Why is my model slow in production?",
];
const isLocalUrl = (u: string) => /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:|\/|$)/i.test(u.trim());

function TargetForm({ onCreated }: { onCreated: (t: Target) => void }) {
  const { notify } = useApp();
  const [preset, setPreset] = useState(0);
  const [name, setName] = useState("");
  const [url, setUrl] = useState(PRESETS[0].url);
  const [model, setModel] = useState(PRESETS[0].model);
  const [key, setKey] = useState("");
  const [keyEnv, setKeyEnv] = useState("");
  const [consent, setConsent] = useState(false);
  const remote = url.trim() !== "" && !isLocalUrl(url);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const t = await api.createTarget({ name: name || `${model} @ ${PRESETS[preset].label}`, base_url: url, model,
        api_key: key || undefined, api_key_env: keyEnv || undefined, allow_remote: consent });
      setKey("");
      notify("success", "Model registered. API keys are kept in memory only.");
      onCreated(t);
    } catch (err) {
      notify("error", (err as Error).message);
    }
  };
  return (
    <form className="space-y-2 text-[13px]" onSubmit={submit}>
      <select className="field" value={preset} aria-label="Endpoint preset"
        onChange={(e) => { const i = Number(e.target.value); setPreset(i); setUrl(PRESETS[i].url); setModel(PRESETS[i].model); }}>
        {PRESETS.map((p, i) => <option key={p.label} value={i}>{p.label}</option>)}
      </select>
      <input className="field" placeholder="Display name (optional)" value={name} onChange={(e) => setName(e.target.value)} aria-label="Display name" />
      <input className="field" placeholder="Base URL, e.g. http://localhost:11434/v1" value={url} onChange={(e) => setUrl(e.target.value)} required aria-label="Base URL" />
      <input className="field" placeholder="Model name" value={model} onChange={(e) => setModel(e.target.value)} required aria-label="Model name" />
      <div className="grid grid-cols-2 gap-2">
        <input className="field" type="password" autoComplete="off" placeholder="API key (memory only)" value={key} onChange={(e) => setKey(e.target.value)} aria-label="API key" />
        <input className="field" placeholder="or env var, e.g. OPENAI_API_KEY" value={keyEnv} onChange={(e) => setKeyEnv(e.target.value.replace(/[^A-Za-z0-9_]/g, ""))} aria-label="API key environment variable" />
      </div>
      {remote && (
        <label className="flex gap-2 items-start border-2 border-amber/70 bg-amber/10 p-2 text-[12px] text-amber">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" />
          <span>Online endpoint: the built-in probe prompts (and any custom prompt file you choose) will be sent to <b>{url}</b>. Your datasets and logs are never sent.</span>
        </label>
      )}
      <button className="btn btn-primary" type="submit" disabled={!url || !model || (remote && !consent)}><PlugZap size={12} /> Register model</button>
    </form>
  );
}

function Console({ lines, running }: { lines: string[]; running: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { ref.current?.scrollTo({ top: ref.current.scrollHeight }); }, [lines.length]);
  return (
    <div ref={ref} className="bg-black/70 border-2 border-phosphor/40 h-56 overflow-y-auto p-2 font-term text-[17px] leading-5 text-phosphor"
      role="log" aria-live="polite" aria-label="Inspection console">
      {lines.length === 0 && <div className="text-muted">&gt; idle — select a model and press INSPECT</div>}
      {lines.map((l, i) => (
        <div key={i} className={l.includes(" FAIL ") ? "text-danger" : l.includes(" ERR ") ? "text-amber" : l.startsWith(">") ? "text-cyan" : ""}>{l}</div>
      ))}
      {running && <span className="blink">█</span>}
    </div>
  );
}

/** Resumo em linguagem simples (para não técnicos), derivado apenas dos achados do motor. */
function Verdict({ report }: { report: FullReport }) {
  const fs = report.report.findings;
  const serious = fs.filter((f) => f.severity === "CRITICAL" || f.severity === "HIGH");
  const medium = fs.filter((f) => f.severity === "MEDIUM");
  const tone = serious.length ? "danger" : medium.length ? "amber" : "green";
  const title = serious.length ? `${serious.length} serious problem${serious.length > 1 ? "s" : ""} found`
    : medium.length ? `${medium.length} point${medium.length > 1 ? "s" : ""} to improve` : "No problems found in this inspection";
  return (
    <section className={`panel panel-${tone === "green" ? "muted" : tone} p-3`} aria-label="Plain-language verdict">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="font-pixel text-[11px]" style={{ color: tone === "danger" ? "#FF4D8D" : tone === "amber" ? "#FFB000" : "#39FF88" }}>
          {serious.length ? "ATTENTION" : medium.length ? "CHECK" : "ALL CLEAR"}</span>
        <b className="text-[15px]">{title}</b>
        <span className="text-[12px] text-muted">based on {fs.length} engine findings · not a benchmark score</span>
      </div>
      {(serious.length > 0 || medium.length > 0) && (
        <ul className="mt-2 grid md:grid-cols-2 gap-2 text-[13px]">
          {[...serious, ...medium].slice(0, 6).map((f) => (
            <li key={f.id} className="border border-white/10 p-2"><b>{f.title}</b><div className="text-muted text-[12px] mt-0.5">What to do: {f.recommendation}</div></li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Lab() {
  const { notify, project, prefs, refreshKey, select, reloadProjects } = useApp();
  const nav = useNavigate();
  const openIn = async (pid?: string | null, eid?: string | null, path = "/") => {
    if (!pid) return;
    await reloadProjects();
    select(pid, eid ?? null);
    nav(path);
  };
  const [targets, setTargets] = useState<Target[] | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [test, setTest] = useState<TargetTest | null>(null);
  const [testing, setTesting] = useState(false);
  const [suite, setSuite] = useState("standard");
  const [prompts, setPrompts] = useState("");
  const [report, setReport] = useState<FullReport | null>(null);
  const [records, setRecords] = useState<ProbeRecord[] | null>(null);
  const [cat, setCat] = useState("");
  const [onlyFail, setOnlyFail] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<FullReport | null>(null);
  const { job, run, cancel, busy } = useJobRunner();

  const load = async (pick?: string) => {
    try {
      const ts = await api.targets();
      setTargets(ts);
      setSel((cur) => pick ?? (cur && ts.some((t) => t.id === cur) ? cur : ts[0]?.id ?? null));
    } catch (e) {
      notify("error", (e as Error).message);
      setTargets([]);
    }
  };
  useEffect(() => { load(); }, []);
  const target = targets?.find((t) => t.id === sel) ?? null;

  useEffect(() => {
    setReport(null); setRecords(null); setTest(null); setAnswer(null);
    if (!sel) return;
    api.reports().then(async (ms) => {
      const m = ms.find((x) => x.target_id === sel && x.kind === "probe");
      if (!m) return;
      const full = await api.report(m.id);
      setReport(full);
      setRecords(await api.probeRecords(m.id));
    }).catch((e) => notify("error", e.message));
  }, [sel, refreshKey]);

  const doTest = async () => {
    if (!sel) return;
    setTesting(true);
    try { setTest(await api.testTarget(sel)); } catch (e) { notify("error", (e as Error).message); } finally { setTesting(false); }
  };
  const ask = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!report || !question.trim()) return;
    try {
      const m = await api.ask(report.meta.id, question.trim());
      setAnswer(await api.report(m.id));
    } catch (err) { notify("error", (err as Error).message); }
  };

  const rep = report?.report;
  const pm = rep?.sections.probe?.[0]?.metrics as any;
  const cats = Object.entries((pm?.categories ?? {}) as Record<string, any>).filter(([, c]) => c.checked > 0);
  const shown = useMemo(() => (records ?? []).filter((r) => (!cat || r.category === cat) && (!onlyFail || r.passed === false || r.error)), [records, cat, onlyFail]);
  const promptFiles = (project?.inventory ?? []).filter((i) => ["dataset", "generations", "unknown"].includes(i.kind) && i.path.endsWith(".jsonl"));
  const lines = job?.log ?? [];

  return (
    <div className="space-y-3">
      <div className="grid gap-3 xl:grid-cols-[minmax(0,0.85fr)_minmax(0,1.6fr)]">
        <div className="space-y-3 min-w-0">
          <Panel title="Models under inspection" tone="cyan" icon={<Bot size={14} />} actions={
            <button className="btn btn-sm btn-amber" onClick={async () => { try { const ts = await api.simulatedTargets(); await load(ts[0]?.id); notify("info", "Simulated models loaded (scripted responses, not a real LLM)."); } catch (e) { notify("error", (e as Error).message); } }}>
              Simulated demo</button>}>
            {!targets && <Loader label="Loading models" />}
            {targets?.length === 0 && <EmptyState small title="No models yet" text="Register a local endpoint (Ollama, LM Studio, llama.cpp, vLLM) or an online API, or load the simulated demo." />}
            <ul className="space-y-1.5">
              {targets?.map((t) => (
                <li key={t.id} className={`border-2 p-2 ${t.id === sel ? "border-phosphor bg-phosphor/5" : "border-white/10"}`}>
                  <div className="flex items-center gap-2">
                    <button className="text-left flex-1 min-w-0" onClick={() => setSel(t.id)} aria-label={`Select ${t.name}`}>
                      <div className="font-semibold text-[13px] truncate flex items-center gap-1.5">
                        {t.local ? <Laptop size={14} className="text-phosphor" /> : <Globe size={14} className="text-amber" />} {t.name}
                      </div>
                      <div className="text-[11px] text-muted break-all">{t.model} · {t.base_url}</div>
                      <div className="flex gap-1 mt-1">
                        {t.simulated && <Chip tone="amber">simulated</Chip>}
                        <Chip tone={t.local ? "green" : "amber"}>{t.local ? "local" : "online"}</Chip>
                        {(t.has_session_key || t.api_key_env) && <Chip tone="purple">key: {t.api_key_env ? `env ${t.api_key_env}` : "session"}</Chip>}
                      </div>
                    </button>
                    <button className="text-muted hover:text-danger" aria-label={`Remove ${t.name}`} onClick={async () => { await api.deleteTarget(t.id); load(); }}><Trash2 size={15} /></button>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
          <Panel title="Connect a model" tone="green" icon={<Server size={14} />}>
            <ConnectWizard onCreated={(t) => { load(t.id); reloadProjects(); }} onHub={(j) => openIn(j.project_id, j.experiment_id)} />
            <details className="mt-3 text-[12px]">
              <summary className="cursor-pointer text-muted">Advanced: manual registration</summary>
              <div className="mt-2"><TargetForm onCreated={(t) => { load(t.id); reloadProjects(); }} /></div>
            </details>
          </Panel>
        </div>
        <div className="space-y-3 min-w-0">
          <Panel title={target ? `Inspection console — ${target.name}` : "Inspection console"} tone="green" icon={<Cpu size={14} />}>
            {target?.simulated && <div className="mb-2 text-[12px] text-amber border border-amber/60 px-2 py-1">SIMULATED MODEL — scripted responses with planted flaws, for demonstration. Analyses are real.</div>}
            <div className="flex flex-wrap items-end gap-2 mb-2">
              <button className="btn btn-sm btn-cyan" disabled={!target || testing} onClick={doTest}><Zap size={12} /> Test connection</button>
              <label className="text-[11px] text-muted flex flex-col gap-1">Probe suite
                <select className="field w-56" value={suite} onChange={(e) => setSuite(e.target.value)} aria-label="Probe suite">
                  <option value="quick">Quick (~20 calls)</option><option value="standard">Standard (~44 calls)</option>
                  {prompts && <option value="custom">Custom prompts only</option>}
                </select>
              </label>
              <label className="text-[11px] text-muted flex flex-col gap-1 flex-1 min-w-[180px]">Custom prompts (optional, from project)
                <select className="field" value={prompts} onChange={(e) => setPrompts(e.target.value)} aria-label="Custom prompts file" disabled={!project}>
                  <option value="">— none —</option>{promptFiles.map((f) => <option key={f.path}>{f.path}</option>)}
                </select>
              </label>
              <button className="btn btn-primary" disabled={!target || busy}
                onClick={() => target && run({ project_id: project?.id ?? null, kind: "probe", params: { target_id: target.id, suite, prompts: prompts || undefined } }, () => reloadProjects())}>
                <Play size={12} /> Inspect
              </button>
            </div>
            {test && (
              <div className={`text-[12px] mb-2 border px-2 py-1 ${test.ok ? "border-phosphor/60 text-phosphor" : "border-danger text-danger"}`} role="status">
                {test.ok ? `Connected · ${fmt(test.latency_ms)} ms · reply "${test.reply}"` : `Connection failed: ${test.error}`}
                {test.models && <span className="text-muted"> · {test.models.length} models listed{test.model_listed === false ? " (selected model NOT listed)" : ""}</span>}
              </div>
            )}
            <Console lines={lines} running={busy} />
            <div className="mt-2"><JobProgress job={job} onCancel={cancel} /></div>
          </Panel>
          {!report && !busy && target && <Panel tone="purple"><EmptyState small title="No inspection yet" text="Press INSPECT to run the behavioural probe suite against this model." /></Panel>}
        </div>
      </div>
      {report && rep && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-[12px] text-muted">
            <span>Inspection <span className="text-cyan">{report.meta.id}</span> · {new Date(report.meta.created).toLocaleString()}</span>
            {report.meta.simulated && <Chip tone="amber">simulated model</Chip>}
            <span className="ml-auto flex flex-wrap gap-1.5">
              {target?.experiment_id && <>
                <button className="btn btn-sm btn-cyan" onClick={() => openIn(target.project_id, target.experiment_id, "/")}><LayoutDashboard size={12} /> Open in Dashboard</button>
                <button className="btn btn-sm" onClick={() => openIn(target.project_id, target.experiment_id, "/generation")}>Generation</button>
                <button className="btn btn-sm" onClick={() => openIn(target.project_id, target.experiment_id, "/investigate")}>Investigate</button>
              </>}
              <a className="btn btn-sm" href={api.exportUrl(report.meta.id, "json")} download><Braces size={12} /> JSON</a>
              <a className="btn btn-sm btn-purple" href={api.exportUrl(report.meta.id, "markdown", prefs.lang)} download><FileDown size={12} /> MD</a>
              <a className="btn btn-sm btn-amber" href={api.exportUrl(report.meta.id, "html", prefs.lang)} download><FileCode2 size={12} /> HTML</a>
            </span>
          </div>
          <Verdict report={report} />
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard tone="cyan" label="Requests" value={fmt(pm?.calls)} sub={`${fmt(pm?.errors)} errors · ${pct(pm?.error_rate)}`} />
            <StatCard tone="green" label="Latency median" value={`${fmt(pm?.latency_ms?.median, 0)} ms`} sub={`p95 ${fmt(pm?.latency_p95_ms, 0)} ms`} />
            <StatCard tone="purple" label="Throughput" value={pm?.tokens_per_second ? `${fmt(pm.tokens_per_second.median, 1)} tok/s` : "n/a"} sub="median, from reported usage" />
            <StatCard tone="danger" label="Findings" value={rep.findings.filter((f) => f.severity !== "INFO").length} sub={`${rep.summary.findings_by_severity.HIGH ?? 0} high · ${rep.summary.findings_by_severity.CRITICAL ?? 0} critical`} />
            <StatCard tone="amber" label="Completion tokens" value={fmt(pm?.completion_tokens_total)} sub="total reported by server" />
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
            <Panel title="Behaviour scorecard" tone="amber">
              <p className="text-[11.5px] text-muted mb-2">Pass rate on the built-in probes (n checked). Describes behaviour on these probes only — not a benchmark score.</p>
              <ul className="space-y-2">
                {cats.map(([k, c]) => {
                  const v = c.pass_rate ?? 0;
                  const color = v >= 0.999 ? "#39FF88" : v >= 0.8 ? "#00E5FF" : v >= 0.5 ? "#FFB000" : "#FF4D8D";
                  return (
                    <li key={k}>
                      <div className="flex justify-between text-[12.5px]"><span>{c.label}</span><span style={{ color }}>{pct(c.pass_rate)} <span className="text-muted">(n={c.checked})</span></span></div>
                      <div className="progress-pixel mt-1" style={{ borderColor: color }} aria-hidden>
                        <div style={{ width: `${Math.round(v * 100)}%`, background: `repeating-linear-gradient(90deg, ${color} 0 8px, transparent 8px 11px)` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            </Panel>
            <Panel title="Latency per request" tone="cyan">
              <TimeSeriesChart ariaLabel="Latency per request" series={(rep.sections.probe?.[0]?.series ?? {}) as any} height={230}
                defs={[{ key: "latency_ms", label: "Latency (ms)", color: "#00E5FF" }]} />
            </Panel>
          </div>
          <div className="grid gap-3 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <Panel title="Findings" tone="danger"><FindingsTable findings={rep.findings} report={report} /></Panel>
            <Panel title="Ask the inspector" tone="purple" bodyClass="p-3 space-y-2">
              <form onSubmit={ask} className="flex gap-2">
                <input className="field h-10" maxLength={500} value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Ask about this inspection…" aria-label="Question about this inspection" />
                <button className="btn btn-primary h-10" type="submit" disabled={!question.trim()} aria-label="Ask"><Send size={14} /></button>
              </form>
              <div className="flex flex-wrap gap-1.5">{QUESTIONS.map((q) => <button key={q} type="button" className="chip cursor-pointer" onClick={() => setQuestion(q)}>{q}</button>)}</div>
              {answer?.report.answer && (
                <div className="border-2 border-phosphor/60 p-2 text-[13px] space-y-2">
                  <div className="flex items-center gap-2 text-[11px] text-phosphor">DeepModel Inspector <StatusChip s={answer.report.answer.status} /></div>
                  <div>{answer.report.answer.conclusion}</div>
                  <HypothesesList hyps={answer.report.hypotheses.filter((h) => answer.report.answer!.hypotheses.includes(h.id))} findings={answer.report.findings} />
                </div>
              )}
              {!answer && <HypothesesList hyps={rep.hypotheses} findings={rep.findings} />}
            </Panel>
          </div>
          <Panel title="Probe transcript" tone="green" actions={<span className="text-[11px] text-muted">{shown.length}/{records?.length ?? 0} calls</span>}>
            <div className="flex flex-wrap gap-2 mb-2 items-center">
              <select className="field w-auto" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Filter by category">
                <option value="">All categories</option>{[...new Set((records ?? []).map((r) => r.category))].map((c) => <option key={c}>{c}</option>)}
              </select>
              <label className="text-[12px] text-muted flex items-center gap-1.5"><input type="checkbox" checked={onlyFail} onChange={(e) => setOnlyFail(e.target.checked)} /> only failures/errors</label>
            </div>
            {!records ? <Loader label="Loading transcript" /> : (
              <div className="overflow-x-auto max-h-[460px]"><table className="data-table">
                <thead><tr><th>Probe</th><th>Result</th><th>Latency</th><th>Prompt</th><th>Model output</th></tr></thead>
                <tbody>{shown.map((r, i) => (
                  <tr key={i}>
                    <td className="whitespace-nowrap"><div className="text-cyan">{r.probe_id}</div><div className="text-[11px] text-muted">{r.category}{r.temperature != null ? ` · T=${r.temperature}` : ""}</div></td>
                    <td className="whitespace-nowrap">{r.error ? <Chip tone="amber">error</Chip> : r.passed === null ? <Chip tone="muted">n/a</Chip> : r.passed ? <Chip>pass</Chip> : <Chip tone="danger">fail</Chip>}
                      <div className="text-[11px] text-muted max-w-[200px] whitespace-normal">{r.detail}</div></td>
                    <td className="whitespace-nowrap">{fmt(r.latency_ms, 0)} ms</td>
                    <td className="min-w-[220px] break-words text-[12px]">{r.prompt.slice(0, 220)}</td>
                    <td className="min-w-[260px] break-words text-[12px]">{r.error ?? r.output.slice(0, 400)}</td>
                  </tr>
                ))}</tbody>
              </table></div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
