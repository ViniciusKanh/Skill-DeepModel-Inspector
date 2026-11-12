"""Modelos Pydantic de entrada e saída da API local do DeepModel Inspector."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

AnalysisKind = Literal[
    "audit",
    "investigate",
    "train",
    "dataset",
    "leakage",
    "tokenizer",
    "generation",
    "compare",
    "checkpoint",
    "probe",
    "monitor",
    "hub",
]
JobState = Literal["queued", "running", "done", "failed", "cancelled"]


class Capability(BaseModel):
    kind: str
    command: str
    description: str
    inputs: str


class StatusOut(BaseModel):
    app: str = "DeepModel Inspector"
    app_version: str
    engine_version: str
    python: str
    platform: str
    workspace: str
    allowed_roots: list[str]
    capabilities: list[Capability]
    limitations: list[str]
    demo_available: bool


class SettingsModel(BaseModel):
    allowed_roots: list[str] = Field(default_factory=list)
    reports_dir: str = ""
    max_records: int = Field(200_000, ge=100, le=5_000_000)
    max_mb: float = Field(200.0, gt=0, le=4096)


class InventoryItem(BaseModel):
    path: str
    name: str
    kind: str
    split: str | None = None
    note: str | None = None
    error: str | None = None


class Experiment(BaseModel):
    id: str
    name: str
    items: list[str]
    created: str


class Project(BaseModel):
    id: str
    name: str
    root: str
    demo: bool = False
    created: str
    experiments: list[Experiment] = Field(default_factory=list)
    inventory: list[InventoryItem] = Field(default_factory=list)


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    root: str = Field(min_length=1, max_length=1024)


class ExperimentIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    items: list[str] = Field(min_length=1, max_length=500)


class JobIn(BaseModel):
    project_id: str | None = None
    experiment_id: str | None = None
    kind: AnalysisKind
    question: str | None = Field(None, max_length=500)
    params: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    id: str
    kind: str
    status: JobState
    created: str
    project_id: str
    experiment_id: str | None = None
    progress_done: int | None = None
    progress_total: int | None = None
    message: str = ""
    report_id: str | None = None
    error: str | None = None
    log: list[str] = Field(default_factory=list)


class ReportMeta(BaseModel):
    id: str
    created: str
    kind: str
    project_id: str
    project_name: str
    experiment_id: str | None = None
    experiment_name: str | None = None
    question: str | None = None
    demo: bool = False
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    findings_by_status: dict[str, int] = Field(default_factory=dict)
    analyses_run: list[str] = Field(default_factory=list)
    answer_status: str | None = None
    target_id: str | None = None
    target_name: str | None = None
    simulated: bool = False


class FileInspectIn(BaseModel):
    project_id: str
    path: str = Field(min_length=1, max_length=1024)


class TargetIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(None, max_length=500)
    api_key_env: str | None = Field(None, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    allow_remote: bool = False
    timeout: float = Field(60.0, ge=1, le=600)


class TargetOut(BaseModel):
    id: str
    name: str
    base_url: str
    model: str
    local: bool
    simulated: bool = False
    api_key_env: str | None = None
    has_session_key: bool = False
    timeout: float = 60.0
    created: str
    project_id: str | None = None
    experiment_id: str | None = None
    folder: str | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ModelsIn(BaseModel):
    base_url: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(None, max_length=500)
    api_key_env: str | None = Field(None, max_length=100, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    allow_remote: bool = False


class HubTokenIn(BaseModel):
    """Token do Hugging Face mantido apenas em memória durante a sessão."""

    token: str = Field(..., min_length=8, max_length=200, pattern=r"^[A-Za-z0-9_\-]+$")
