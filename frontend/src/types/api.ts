// Tipos espelhando os modelos da API local (backend/schemas/models.py) e o JSON do motor.

export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";
export type FindingStatus = "CONFIRMED" | "POTENTIAL" | "INCONCLUSIVE";
export type JobState = "queued" | "running" | "done" | "failed" | "cancelled";

export interface Capability { kind: string; command: string; description: string; inputs: string }

export interface Status {
  app: string; app_version: string; engine_version: string; python: string; platform: string;
  workspace: string; allowed_roots: string[]; capabilities: Capability[]; limitations: string[];
  demo_available: boolean;
}

export interface ServerSettings { allowed_roots: string[]; reports_dir: string; max_records: number; max_mb: number }

export interface InventoryItem { path: string; name: string; kind: string; split?: string | null; note?: string | null; error?: string | null }
export interface Experiment { id: string; name: string; items: string[]; created: string }
export interface Project {
  id: string; name: string; root: string; demo: boolean; created: string;
  experiments: Experiment[]; inventory: InventoryItem[];
}

export interface Job {
  id: string; kind: string; status: JobState; created: string; project_id: string; experiment_id?: string | null;
  progress_done?: number | null; progress_total?: number | null; message: string; report_id?: string | null; error?: string | null;
}

export interface ReportMeta {
  id: string; created: string; kind: string; project_id: string; project_name: string;
  experiment_id?: string | null; experiment_name?: string | null; question?: string | null; demo: boolean;
  findings_by_severity: Record<string, number>; findings_by_status: Record<string, number>;
  analyses_run: string[]; answer_status?: string | null;
}

export interface Finding {
  id: string; rule: string; category: string; severity: Severity; status: FindingStatus; title: string;
  evidence: Record<string, unknown>; source: string; explanation: string; recommendation: string;
  confirmation?: string; analysis?: string;
}

export interface Hypothesis {
  id: string; rule: string; status: FindingStatus; statement: string; supporting_findings: string[];
  counter_evidence: string; experiment: string; priority_rank: number;
}

export interface SectionBlock {
  source: string; metrics: Record<string, any>; series?: Record<string, [number, number][]> | null;
  finding_ids: string[]; limitations?: string[];
}

export interface Answer {
  intents: string[]; relevant_findings: string[]; hypotheses: string[];
  missing_artifacts: { intent: string; provide: string }[]; conclusion: string; status: FindingStatus;
}

export interface Report {
  tool: string; version: string; generated_at: string; inventory: InventoryItem[]; analyses_run: string[];
  sections: Record<string, SectionBlock[]>; findings: Finding[]; hypotheses: Hypothesis[];
  experiments: { for: string; experiment: string; priority: number }[];
  summary: { findings_by_severity: Record<string, number>; findings_by_status: Record<string, number>; top_findings: string[] };
  limitations: string[]; question?: string; answer?: Answer;
}

export interface FullReport { meta: ReportMeta; report: Report }

export interface SeriesResponse {
  series: Record<string, [number, number | null][]>; perplexity_source: string | null; rows: number;
}
export interface RecordRow {
  index: number; format: string; input: string; target: string; output: string; words: number;
  repetition_rate: number | null; meta: Record<string, unknown>;
}
export interface FsEntry { name: string; path: string; dir: boolean; size: number | null; supported: boolean }
