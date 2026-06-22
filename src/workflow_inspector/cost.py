"""Cost analysis for GitHub Actions workflows."""


from .client import GitHubClient
from .models import CostBreakdown, Job, WorkflowRun


class CostAnalyzer:
    """Analyze costs of GitHub Actions workflow runs."""

    # GitHub hosted runner rates (USD per minute) as of 2024
    LINUX_RATE = 0.008      # $0.008/min for Linux
    WINDOWS_RATE = 0.016    # $0.016/min for Windows
    MACOS_RATE = 0.08       # $0.08/min for macOS

    # Runner label to rate mapping
    RUNNER_RATES = {
        "ubuntu-latest": LINUX_RATE,
        "ubuntu-24.04": LINUX_RATE,
        "ubuntu-22.04": LINUX_RATE,
        "ubuntu-20.04": LINUX_RATE,
        "ubuntu-latest-arm": LINUX_RATE,
        "ubuntu-24.04-arm": LINUX_RATE,
        "ubuntu-22.04-arm": LINUX_RATE,
        "windows-latest": WINDOWS_RATE,
        "windows-2022": WINDOWS_RATE,
        "windows-2019": WINDOWS_RATE,
        "macos-latest": MACOS_RATE,
        "macos-14": MACOS_RATE,
        "macos-13": MACOS_RATE,
        "macos-12": MACOS_RATE,
    }

    def __init__(self, client: GitHubClient):
        self.client = client

    def analyze_run_cost(self, run: WorkflowRun, jobs: list[Job]) -> CostBreakdown:
        """Calculate cost breakdown for a single workflow run."""
        breakdown = CostBreakdown()

        if run.run_duration_ms:
            total_minutes = run.run_duration_ms / 60000.0
            # We don't know the runner from the run alone, use jobs
            for job in jobs:
                job_minutes = self._get_job_minutes(job)
                runner_label = job.runner_name or job.runner_group_name or "ubuntu-latest"
                breakdown.add_minutes(runner_label, job_minutes)
        else:
            # Fallback: estimate from jobs
            for job in jobs:
                job_minutes = self._get_job_minutes(job)
                runner_label = job.runner_name or job.runner_group_name or "ubuntu-latest"
                breakdown.add_minutes(runner_label, job_minutes)

        breakdown.calculate_cost(self.LINUX_RATE, self.WINDOWS_RATE, self.MACOS_RATE)
        return breakdown

    def _get_job_minutes(self, job: Job) -> float:
        """Calculate job duration in minutes."""
        if job.started_at and job.completed_at:
            duration = job.completed_at - job.started_at
            return duration.total_seconds() / 60.0

        # Fallback: estimate from steps
        total_seconds = 0.0
        for step in job.steps:
            if step.started_at and step.completed_at:
                total_seconds += (step.completed_at - step.started_at).total_seconds()

        return total_seconds / 60.0 if total_seconds > 0 else 1.0  # Minimum 1 minute

    def analyze_period_cost(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
    ) -> CostBreakdown:
        """Calculate cost breakdown for a period across multiple runs."""
        total_breakdown = CostBreakdown()

        for run in runs:
            jobs = jobs_by_run.get(run.id, [])
            run_breakdown = self.analyze_run_cost(run, jobs)
            total_breakdown.total_minutes += run_breakdown.total_minutes
            total_breakdown.linux_minutes += run_breakdown.linux_minutes
            total_breakdown.windows_minutes += run_breakdown.windows_minutes
            total_breakdown.macos_minutes += run_breakdown.macos_minutes
            total_breakdown.ubuntu_latest_minutes += run_breakdown.ubuntu_latest_minutes
            total_breakdown.ubuntu_latest_arm_minutes += run_breakdown.ubuntu_latest_arm_minutes
            total_breakdown.windows_latest_minutes += run_breakdown.windows_latest_minutes
            total_breakdown.macos_latest_minutes += run_breakdown.macos_latest_minutes

        total_breakdown.calculate_cost(self.LINUX_RATE, self.WINDOWS_RATE, self.MACOS_RATE)
        return total_breakdown

    def get_top_workflows_by_cost(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
        limit: int = 10,
    ) -> list[dict]:
        """Get top workflows by cost."""
        workflow_costs: dict[str, float] = {}
        workflow_counts: dict[str, int] = {}

        for run in runs:
            jobs = jobs_by_run.get(run.id, [])
            breakdown = self.analyze_run_cost(run, jobs)
            name = run.name
            workflow_costs[name] = workflow_costs.get(name, 0.0) + breakdown.estimated_cost_usd
            workflow_counts[name] = workflow_counts.get(name, 0) + 1

        sorted_workflows = sorted(
            workflow_costs.items(), key=lambda x: x[1], reverse=True
        )

        return [
            {
                "name": name,
                "total_cost_usd": round(cost, 4),
                "run_count": workflow_counts[name],
                "avg_cost_usd": round(cost / workflow_counts[name], 4),
            }
            for name, cost in sorted_workflows[:limit]
        ]

    def estimate_monthly_cost(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
        period_days: int = 30,
    ) -> float:
        """Estimate monthly cost based on analyzed period."""
        if not runs:
            return 0.0

        breakdown = self.analyze_period_cost(runs, jobs_by_run)
        daily_cost = breakdown.estimated_cost_usd / period_days
        return daily_cost * 30
