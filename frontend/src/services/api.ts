// Cliente HTTP da API local. Toda a análise acontece no backend Python; aqui só há transporte.
import type {
  HistoryPoint, ProbeRecord, Target, TargetTest,
  Experiment, FsEntry, FullReport, Job, Project, RecordRow, ReportMeta, SeriesResponse, ServerSettings, Status,
} from "../types/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...init });
  } catch {
    throw new ApiError(0, "Backend unreachable. Start the local API (scripts/Start-DeepModel.ps1).");
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d: any) => d.msg).join("; ") : `HTTP ${res.status}`;
    throw new ApiError(res.status, msg);
  }
  return body as T;
}

const q = (o: Record<string, string | number | undefined | null>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "") as [string, string][]).toString();

export const api = {
  status: () => req<Status>("/api/status"),
  settings: () => req<ServerSettings>("/api/settings"),
  saveSettings: (s: ServerSettings) => req<ServerSettings>("/api/settings", { method: "PUT", body: JSON.stringify(s) }),
  projects: () => req<Project[]>("/api/projects"),
  createProject: (name: string, root: string) => req<Project>("/api/projects", { method: "POST", body: JSON.stringify({ name, root }) }),
  deleteProject: (id: string) => req<void>(`/api/projects/${id}`, { method: "DELETE" }),
  scan: (id: string) => req<Project>(`/api/projects/${id}/scan`, { method: "POST" }),
  createExperiment: (pid: string, name: string, items: string[]) =>
    req<Experiment>(`/api/projects/${pid}/experiments`, { method: "POST", body: JSON.stringify({ name, items }) }),
  deleteExperiment: (pid: string, eid: string) => req<void>(`/api/projects/${pid}/experiments/${eid}`, { method: "DELETE" }),
  demo: () => req<Project>("/api/demo", { method: "POST" }),
  fsList: (path: string) => req<{ path: string; parent: string | null; entries: FsEntry[] }>(`/api/fs/list?${q({ path })}`),
  targets: () => req<Target[]>("/api/targets"),
  createTarget: (body: { name: string; base_url: string; model: string; api_key?: string; api_key_env?: string; allow_remote: boolean; timeout?: number }) =>
    req<Target>("/api/targets", { method: "POST", body: JSON.stringify(body) }),
  deleteTarget: (id: string) => req<void>(`/api/targets/${id}`, { method: "DELETE" }),
  testTarget: (id: string) => req<TargetTest>(`/api/targets/${id}/test`, { method: "POST" }),
  connectCatalog: () => req<{ local: any[]; online: any[] }>("/api/connect/catalog"),
  discover: () => req<any[]>("/api/connect/discover"),
  connectModels: (body: { base_url: string; api_key?: string; api_key_env?: string; allow_remote: boolean }) =>
    req<{ ok: boolean; models: string[]; error: string | null }>("/api/connect/models", { method: "POST", body: JSON.stringify(body) }),
  hubToken: () => req<{ session_token: boolean; env_token: boolean }>("/api/hub/token"),
  setHubToken: (token: string) => req<void>("/api/hub/token", { method: "POST", body: JSON.stringify({ token }) }),
  clearHubToken: () => req<void>("/api/hub/token", { method: "DELETE" }),
  simulatedTargets: () => req<Target[]>("/api/targets/simulated", { method: "POST" }),
  probeRecords: (rid: string) => req<ProbeRecord[]>(`/api/reports/${rid}/probe-records`),
  history: (id: string) => req<HistoryPoint[]>(`/api/targets/${id}/history`),
  ask: (reportId: string, question: string) => req<ReportMeta>(`/api/reports/${reportId}/ask`, { method: "POST", body: JSON.stringify({ question }) }),
  submitJob: (body: { project_id?: string | null; experiment_id?: string | null; kind: string; question?: string; params?: Record<string, unknown> }) =>
    req<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  jobs: () => req<Job[]>("/api/jobs"),
  cancelJob: (id: string) => req<Job>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  reports: (project_id?: string, experiment_id?: string) => req<ReportMeta[]>(`/api/reports?${q({ project_id, experiment_id })}`),
  report: (id: string) => req<FullReport>(`/api/reports/${id}`),
  exportUrl: (id: string, format: "json" | "markdown" | "html", lang = "en") => `/api/reports/${id}/export?${q({ format, lang })}`,
  series: (project_id: string, path: string) => req<SeriesResponse>(`/api/data/series?${q({ project_id, path })}`),
  lengths: (project_id: string, path: string) =>
    req<{ records: number; bins: { label: string; count: number }[] }>(`/api/data/lengths?${q({ project_id, path })}`),
  records: (project_id: string, path: string, indices?: number[], limit = 25) =>
    req<{ total_records: number; rows: RecordRow[]; malformed: number }>(
      `/api/data/records?${q({ project_id, path, indices: indices?.join(","), limit })}`,
    ),
};
