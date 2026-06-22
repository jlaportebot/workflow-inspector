"""Data models for GitHub Actions workflow analysis."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkflowStatus(str, Enum):
    """GitHub Actions workflow run status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"
    PENDING = "pending"


class WorkflowConclusion(str, Enum):
    """GitHub Actions workflow run conclusion."""
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    ACTION_REQUIRED = "action_required"
    STARTUP_FAILURE = "startup_failure"


class JobStatus(str, Enum):
    """GitHub Actions job status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    WAITING = "waiting"


class JobConclusion(str, Enum):
    """GitHub Actions job conclusion."""
    SUCCESS = "success"
    FAILURE = "failure"
    NEUTRAL = "neutral"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"


class StepConclusion(str, Enum):
    """GitHub Actions step conclusion."""
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


class WorkflowRun(BaseModel):
    """A GitHub Actions workflow run."""
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    head_branch: str
    head_sha: str
    run_number: int
    event: str
    status: WorkflowStatus
    conclusion: Optional[WorkflowConclusion] = None
    workflow_id: int
    url: str
    html_url: str
    created_at: datetime
    updated_at: datetime
    run_started_at: Optional[datetime] = None
    run_attempt: int = 1
    run_duration_ms: Optional[int] = None
    repository_id: int
    head_repository_id: Optional[int] = None


class Job(BaseModel):
    """A GitHub Actions job within a workflow run."""
    model_config = ConfigDict(extra="ignore")

    id: int
    run_id: int
    run_url: str
    name: str
    status: JobStatus
    conclusion: Optional[JobConclusion] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    steps: list["Step"] = Field(default_factory=list)
    runner_id: Optional[int] = None
    runner_name: Optional[str] = None
    runner_group_id: Optional[int] = None
    runner_group_name: Optional[str] = None


class Step(BaseModel):
    """A step within a GitHub Actions job."""
    model_config = ConfigDict(extra="ignore")

    name: str
    number: int
    status: str
    conclusion: Optional[StepConclusion] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class WorkflowFile(BaseModel):
    """A workflow YAML file from the repository."""
    model_config = ConfigDict(extra="ignore")

    path: str
    name: Optional[str] = None
    on: dict = Field(default_factory=dict)
    jobs: dict = Field(default_factory=dict)
    permissions: Optional[dict] = None
    env: Optional[dict] = None
    defaults: Optional[dict] = None
    concurrency: Optional[dict] = None


class CostBreakdown(BaseModel):
    """Cost breakdown for a workflow run or period."""
    total_minutes: float = 0.0
    linux_minutes: float = 0.0
    windows_minutes: float = 0.0
    macos_minutes: float = 0.0
    ubuntu_latest_minutes: float = 0.0
    ubuntu_latest_arm_minutes: float = 0.0
    windows_latest_minutes: float = 0.0
    macos_latest_minutes: float = 0.0
    estimated_cost_usd: float = 0.0

    # Per-runner multipliers (GitHub hosted runner pricing)
    LINUX_MULTIPLIER: float = 1.0
    WINDOWS_MULTIPLIER: float = 2.0
    MACOS_MULTIPLIER: float = 10.0

    def add_minutes(self, runner_label: str, minutes: float) -> None:
        """Add minutes to the appropriate runner category."""
        self.total_minutes += minutes
        label_lower = runner_label.lower()

        if "ubuntu" in label_lower or "linux" in label_lower:
            if "arm" in label_lower or "arm64" in label_lower:
                self.ubuntu_latest_arm_minutes += minutes
            else:
                self.ubuntu_latest_minutes += minutes
            self.linux_minutes += minutes
        elif "windows" in label_lower:
            self.windows_latest_minutes += minutes
            self.windows_minutes += minutes
        elif "macos" in label_lower or "mac" in label_lower:
            self.macos_latest_minutes += minutes
            self.macos_minutes += minutes
        else:
            # Default to linux
            self.ubuntu_latest_minutes += minutes
            self.linux_minutes += minutes

    def calculate_cost(self, linux_rate: float = 0.008, windows_rate: float = 0.016, macos_rate: float = 0.08) -> float:
        """Calculate estimated cost in USD."""
        self.estimated_cost_usd = (
            self.linux_minutes * linux_rate +
            self.windows_minutes * windows_rate +
            self.macos_minutes * macos_rate
        )
        return self.estimated_cost_usd


class PerformanceMetrics(BaseModel):
    """Performance metrics for a workflow run."""
    total_duration_seconds: float = 0.0
    queue_time_seconds: float = 0.0
    setup_time_seconds: float = 0.0
    execution_time_seconds: float = 0.0
    job_count: int = 0
    step_count: int = 0
    parallel_jobs: int = 0
    longest_job_name: Optional[str] = None
    longest_job_duration: float = 0.0
    cache_hit_rate: Optional[float] = None
    cache_size_mb: Optional[float] = None


class SecurityFinding(BaseModel):
    """A security finding in a workflow file."""
    severity: str  # "critical", "high", "medium", "low", "info"
    category: str  # "permissions", "pinning", "secrets", "injection", "supply_chain"
    title: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    remediation: Optional[str] = None
    cwe_id: Optional[str] = None


class OptimizationSuggestion(BaseModel):
    """An optimization suggestion for a workflow."""
    category: str  # "caching", "parallelism", "matrix", "runner", "dependencies", "structure"
    title: str
    description: str
    impact: str  # "high", "medium", "low"
    effort: str  # "low", "medium", "high"
    file_path: str
    line_number: Optional[int] = None
    example: Optional[str] = None


class AnalysisReport(BaseModel):
    """Complete analysis report for a repository."""
    repository: str
    analyzed_at: datetime = Field(default_factory=datetime.now)
    period_days: int = 30
    workflow_runs_analyzed: int = 0
    total_cost_usd: float = 0.0
    cost_breakdown: CostBreakdown = Field(default_factory=CostBreakdown)
    performance_summary: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    security_findings: list[SecurityFinding] = Field(default_factory=list)
    optimization_suggestions: list[OptimizationSuggestion] = Field(default_factory=list)
    top_workflows_by_cost: list[dict] = Field(default_factory=list)
    top_workflows_by_duration: list[dict] = Field(default_factory=list)
    failure_rate: float = 0.0
    most_common_failures: list[dict] = Field(default_factory=list)


# Forward references
Job.model_rebuild()
Step.model_rebuild()
