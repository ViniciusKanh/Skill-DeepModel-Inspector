// Assistente de conexão em 3 passos: onde está o modelo → credenciais/modelo → testar e salvar.
// Pensado para usuários não técnicos: detecta servidores locais e lista modelos automaticamente.
import { useEffect, useState } from "react";
import { Boxes, CheckCircle2, ChevronLeft, Cloud, ExternalLink, FileSearch, Laptop, Loader2, RefreshCw, Search, XCircle } from "lucide-react";
import { useApp } from "../app/AppState";
import { api } from "../services/api";
import type { Job, Target } from "../types/api";
import { useJobRunner } from "../hooks/useAnalysis";
import { Chip } from "../components/ui";

interface LocalServer { id: string; label: string; port: number; base_url: string; help: string; running?: boolean; models?: string[] }
interface Provider { id: string; label: string; base_url: string; key_hint: string; key_url: string; example_model: string }

const isLocalUrl = (u: string) => /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:|\/|$)/i.test(u.trim());

export function ConnectWizard({ onCreated, onHub }: { onCreated: (t: Target) => void; onHub?: (j: Job) => void }) {
  const { notify } = useApp();
  const [step, setStep] = useState<"where" | "local" | "online" | "hf" | "details">("where");
  const [repo, setRepo] = useState("");
  const [hfToken, setHfToken] = useState("");
  const [hfStatus, setHfStatus] = useState<{ session_token: boolean; env_token: boolean } | null>(null);
  const hubJob = useJobRunner();
  const [catalog, setCatalog] = useState<{ local: LocalServer[]; online: Provider[] } | null>(null);
  const [found, setFound] = useState<LocalServer[] | null>(null);
  const [scanning, setScanning] = useState(false);
  const [baseUrl, setBaseUrl] = useState("");
  const [label, setLabel] = useState("");
  const [key, setKey] = useState("");
  const [keyEnv, setKeyEnv] = useState("");
  const [provider, setProvider] = useState<Provider | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("");
  const [consent, setConsent] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const remote = baseUrl !== "" && !isLocalUrl(baseUrl);

  useEffect(() => { api.connectCatalog().then(setCatalog).catch(() => setCatalog({ local: [], online: [] })); }, []);
  const scan = async () => {
    setScanning(true);
    try { setFound(await api.discover()); } catch (e) { notify("error", (e as Error).message); } finally { setScanning(false); }
  };
  const loadModels = async (url = baseUrl) => {
    setLoadingModels(true); setMsg(null);
    try {
      const r = await api.connectModels({ base_url: url, api_key: key || undefined, api_key_env: keyEnv || undefined, allow_remote: consent });
      if (r.ok) { setModels(r.models); setModel((m) => m || r.models[0] || ""); setMsg({ ok: true, text: `${r.models.length} models available.` }); }
      else setMsg({ ok: false, text: r.error ?? "Could not list models." });
    } catch (e) { setMsg({ ok: false, text: (e as Error).message }); } finally { setLoadingModels(false); }
  };
  const pickLocal = (s: LocalServer) => {
    setBaseUrl(s.base_url); setLabel(s.label); setProvider(null); setModels(s.models ?? []); setModel(s.models?.[0] ?? "");
    setMsg(s.models?.length ? { ok: true, text: `${s.models.length} models found on ${s.label}.` } : null); setStep("details");
  };
  const pickOnline = (p: Provider) => {
    setProvider(p); setBaseUrl(p.base_url); setLabel(p.label.split(" (")[0]); setModels([]); setModel(p.example_model.startsWith("<") ? "" : p.example_model);
    setMsg(null); setStep("details");
  };
  const save = async () => {
    setSaving(true);
    try {
      const t = await api.createTarget({ name: `${label} · ${model}`, base_url: baseUrl, model, api_key: key || undefined,
        api_key_env: keyEnv || undefined, allow_remote: consent });
      const test = await api.testTarget(t.id);
      if (test.ok) notify("success", `Connected to ${model}: answered in ${Math.round(test.latency_ms ?? 0)} ms.`);
      else notify("error", `Saved, but the test failed: ${test.error}`);
      setKey("");
      setStep("where");
      onCreated(t);
    } catch (e) { notify("error", (e as Error).message); } finally { setSaving(false); }
  };

  const repoOk = /^[A-Za-z0-9][\w.-]{0,95}\/[\w.-]{1,96}$/.test(repo.trim());
  const openHf = () => { setStep("hf"); api.hubToken().then(setHfStatus).catch(() => setHfStatus(null)); };
  const keepHfToken = async () => {
    try { await api.setHubToken(hfToken.trim()); setHfToken(""); setHfStatus(await api.hubToken()); notify("success", "Hugging Face token kept in memory for this session."); }
    catch (e) { notify("error", (e as Error).message); }
  };
  const inspectHub = () => hubJob.run({ kind: "hub", params: { repo_id: repo.trim() } }, (j) => onHub?.(j));
  const runOnHf = () => {
    const p = catalog?.online.find((x) => x.id === "huggingface");
    if (p) { pickOnline(p); setModel(repo.trim()); }
  };

  const back = (to: typeof step) => (
    <button type="button" className="text-[12px] text-muted hover:text-cyan flex items-center gap-1 mb-2" onClick={() => setStep(to)}><ChevronLeft size={14} /> back</button>
  );

  if (step === "where") return (
    <div className="space-y-2">
      <p className="text-[13px] text-muted">Where is the model you want to inspect?</p>
      <button className="w-full text-left border-2 border-phosphor/50 hover:border-phosphor hover:bg-phosphor/5 p-3 flex gap-3 items-center"
        onClick={() => { setStep("local"); scan(); }}>
        <Laptop className="text-phosphor flex-none" /><span><b className="text-[14px]">On this computer</b>
          <span className="block text-[12px] text-muted">Ollama, LM Studio, llama.cpp, vLLM, Jan… detected automatically. Nothing leaves your machine.</span></span>
      </button>
      <button className="w-full text-left border-2 border-amber/50 hover:border-amber hover:bg-amber/5 p-3 flex gap-3 items-center" onClick={() => setStep("online")}>
        <Cloud className="text-amber flex-none" /><span><b className="text-[14px]">Online service</b>
          <span className="block text-[12px] text-muted">OpenAI, Anthropic, Gemini, Groq, OpenRouter, Mistral, Azure or any OpenAI-compatible API. Needs the provider's API key.</span></span>
      </button>
      <button className="w-full text-left border-2 border-purple/50 hover:border-purple hover:bg-purple/5 p-3 flex gap-3 items-center" onClick={openHf}>
        <Boxes className="text-purple flex-none" /><span><b className="text-[14px]">Hugging Face model</b>
          <span className="block text-[12px] text-muted">Inspect any repo WITHOUT downloading it (no token for public models), or run it online through HF Inference Providers (free HF token).</span></span>
      </button>
    </div>
  );

  if (step === "hf") return (
    <div className="space-y-2 text-[13px]">
      {back("where")}
      <label className="text-[11px] text-muted flex flex-col gap-1">Repository id
        <input className="field" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="Qwen/Qwen2.5-0.5B-Instruct" aria-label="Hugging Face repository" />
      </label>
      <button className="btn btn-primary w-full justify-center" disabled={!repoOk || hubJob.busy} onClick={inspectHub}>
        {hubJob.busy ? <Loader2 size={12} className="animate-spin" /> : <FileSearch size={12} />} Inspect files (no download)
      </button>
      <p className="text-[11.5px] text-muted">Reads only the model card metadata, config, tokenizer settings and safetensors headers (a few KB): size, memory per quantization, context, KV cache, chat template, license, pickle/remote-code risks. Behaviour needs a run ↓</p>
      {hubJob.job?.status === "failed" && <div className="text-[12px] border border-danger text-danger px-2 py-1" role="status">{hubJob.job.error}</div>}
      <button className="btn btn-sm btn-purple w-full justify-center" disabled={!repoOk} onClick={runOnHf}>
        <Cloud size={12} /> Run it online (HF Inference Providers) and probe behaviour
      </button>
      <details className="text-[12px]">
        <summary className="cursor-pointer text-muted">Private or gated repo? Hugging Face token {hfStatus?.session_token ? "· kept for this session" : hfStatus?.env_token ? "· HF_TOKEN env var found" : ""}</summary>
        <div className="flex gap-2 mt-1">
          <input className="field flex-1" type="password" autoComplete="off" value={hfToken} onChange={(e) => setHfToken(e.target.value)} placeholder="hf_…" aria-label="Hugging Face token" />
          <button className="btn btn-sm" disabled={hfToken.trim().length < 8} onClick={keepHfToken}>Keep in memory</button>
        </div>
        <a className="text-cyan inline-flex items-center gap-1 mt-1" href="https://huggingface.co/settings/tokens" target="_blank" rel="noreferrer">Create a free read token <ExternalLink size={11} /></a>
      </details>
    </div>
  );

  if (step === "local") return (
    <div className="space-y-2">
      {back("where")}
      <div className="flex items-center gap-2 text-[13px]"><Search size={14} className="text-cyan" /> Looking for model servers on this computer…
        <button className="ml-auto btn btn-sm" onClick={scan} disabled={scanning}><RefreshCw size={12} /> Scan again</button></div>
      {scanning && <div className="text-[12px] text-muted flex items-center gap-2"><Loader2 size={14} className="animate-spin" /> scanning ports…</div>}
      <ul className="space-y-1.5">
        {(found ?? catalog?.local ?? []).map((s) => (
          <li key={s.id} className={`border-2 p-2 text-[12.5px] ${s.running ? "border-phosphor/70" : "border-white/10"}`}>
            <div className="flex items-center gap-2">
              {s.running ? <CheckCircle2 size={15} className="text-phosphor" /> : <XCircle size={15} className="text-muted" />}
              <b>{s.label}</b><span className="text-muted">:{s.port}</span>
              {s.running ? <Chip>{s.models?.length ?? 0} models</Chip> : <Chip tone="muted">not running</Chip>}
              {s.running && <button className="ml-auto btn btn-sm btn-primary" onClick={() => pickLocal(s)}>Use</button>}
            </div>
            {!s.running && found && <div className="text-[11.5px] text-muted mt-1">{s.help}</div>}
          </li>
        ))}
      </ul>
      {found && !found.some((s) => s.running) && (
        <div className="border-2 border-amber/60 bg-amber/10 p-2 text-[12.5px] text-amber">
          No local model server is running. The easiest option: install <b>Ollama</b>, open it, then run <code>ollama pull llama3.2</code> and press <b>Scan again</b>.
        </div>
      )}
    </div>
  );

  if (step === "online") return (
    <div className="space-y-2">
      {back("where")}
      <div className="grid sm:grid-cols-2 gap-1.5">
        {catalog?.online.map((p) => (
          <button key={p.id} className="text-left border-2 border-white/10 hover:border-amber p-2 text-[12.5px]" onClick={() => pickOnline(p)}>
            <b>{p.label}</b><span className="block text-[11px] text-muted truncate">{p.base_url || "enter the base URL"}</span>
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-2 text-[13px]">
      {back(provider ? "online" : "local")}
      <div className="font-semibold">{label}</div>
      <label className="text-[11px] text-muted flex flex-col gap-1">Address (base URL)
        <input className="field" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} aria-label="Base URL" placeholder="https://…/v1" />
      </label>
      {provider && (
        <>
          <label className="text-[11px] text-muted flex flex-col gap-1">API key
            <input className="field" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={provider.key_hint} aria-label="API key" />
          </label>
          <div className="flex items-center gap-2 text-[11.5px] text-muted">
            {provider.key_url && <a className="text-cyan inline-flex items-center gap-1" href={provider.key_url} target="_blank" rel="noreferrer">Get a key <ExternalLink size={11} /></a>}
            <span>Kept in memory only — or use an environment variable:</span>
            <input className="field w-40 py-0.5" value={keyEnv} onChange={(e) => setKeyEnv(e.target.value.replace(/[^A-Za-z0-9_]/g, ""))} placeholder="OPENAI_API_KEY" aria-label="API key environment variable" />
          </div>
        </>
      )}
      {remote && (
        <label className="flex gap-2 items-start border-2 border-amber/70 bg-amber/10 p-2 text-[12px] text-amber">
          <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5" />
          <span>I agree that test prompts are sent to <b>{baseUrl}</b> (and billed by the provider). My datasets and logs are never sent.</span>
        </label>
      )}
      <div className="flex gap-2 items-end">
        <label className="text-[11px] text-muted flex flex-col gap-1 flex-1">Model
          {models.length ? (
            <select className="field" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">{models.map((m) => <option key={m}>{m}</option>)}</select>
          ) : (
            <input className="field" value={model} onChange={(e) => setModel(e.target.value)} placeholder={provider?.example_model || "model name"} aria-label="Model" />
          )}
        </label>
        <button className="btn btn-sm btn-cyan" disabled={!baseUrl || loadingModels || (remote && !consent)} onClick={() => loadModels()}>
          {loadingModels ? <Loader2 size={12} className="animate-spin" /> : <RefreshCw size={12} />} Load models
        </button>
      </div>
      {msg && <div className={`text-[12px] border px-2 py-1 ${msg.ok ? "border-phosphor/60 text-phosphor" : "border-danger text-danger"}`} role="status">{msg.text}</div>}
      <button className="btn btn-primary w-full justify-center" disabled={!baseUrl || !model || saving || (remote && !consent)} onClick={save}>
        {saving ? "Connecting…" : "Connect & test"}
      </button>
    </div>
  );
}
