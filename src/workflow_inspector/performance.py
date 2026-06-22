"""Performance analysis for GitHub Actions workflows."""

from collections import defaultdict
from typing import Optional

from .client import GitHubClient
from .models import Job, PerformanceMetrics, WorkflowRun


class PerformanceAnalyzer:
    """Analyze performance of GitHub Actions workflow runs."""

    def __init__(self, client: GitHubClient):
        self.client = client

    def analyze_run_performance(self, run: WorkflowRun, jobs: list[Job]) -> PerformanceMetrics:
        """Calculate performance metrics for a single workflow run."""
        metrics = PerformanceMetrics()

        if run.run_started_at and run.created_at:
            metrics.queue_time_seconds = (run.run_started_at - run.created_at).total_seconds()

        if run.run_duration_ms:
            metrics.total_duration_seconds = run.run_duration_ms / 1000.0
        elif run.run_started_at and run.updated_at:
            metrics.total_duration_seconds = (run.updated_at - run.run_started_at).total_seconds()

        metrics.job_count = len(jobs)
        metrics.step_count = sum(len(job.steps) for job in jobs)

        # Analyze job parallelism and durations
        job_durations = []
        for job in jobs:
            if job.started_at and job.completed_at:
                duration = (job.completed_at - job.started_at).total_seconds()
                job_durations.append((job.name, duration))
                if duration > metrics.longest_job_duration:
                    metrics.longest_job_duration = duration
                    metrics.longest_job_name = job.name

        # Estimate parallelism by checking overlapping jobs
        if job_durations:
            metrics.parallel_jobs = self._estimate_parallelism(job_durations)

        # Calculate execution time (total - queue)
        metrics.execution_time_seconds = max(0, metrics.total_duration_seconds - metrics.queue_time_seconds)

        # Check for cache usage in steps
        metrics.cache_hit_rate, metrics.cache_size_mb = self._analyze_cache_usage(jobs)

        return metrics

    def _estimate_parallelism(self, job_durations: list[tuple[str, float]]) -> int:
        """Estimate number of jobs running in parallel."""
        # Simple heuristic: if multiple jobs have similar start times, they run in parallel
        # For now, return the number of jobs as upper bound
        # A more sophisticated approach would need actual start times
        return len(job_durations)

    def _analyze_cache_usage(self, jobs: list[Job]) -> tuple[Optional[float], Optional[float]]:
        """Analyze cache hit/miss from job steps."""
        cache_hits = 0
        cache_misses = 0
        total_cache_size = 0.0

        for job in jobs:
            for step in job.steps:
                step_name = step.name.lower()
                if "cache" in step_name:
                    if step.conclusion and step.conclusion.value == "success":
                        # Check step output for cache hit/miss
                        # This would need log parsing, simplified here
                        cache_hits += 1
                    else:
                        cache_misses += 1

        total = cache_hits + cache_misses
        if total > 0:
            return cache_hits / total, total_cache_size if total_cache_size > 0 else None

        return None, None

    def analyze_period_performance(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
    ) -> PerformanceMetrics:
        """Aggregate performance metrics across a period."""
        total_metrics = PerformanceMetrics()
        run_count = 0

        for run in runs:
            jobs = jobs_by_run.get(run.id, [])
            if not jobs:
                continue

            metrics = self.analyze_run_performance(run, jobs)
            total_metrics.total_duration_seconds += metrics.total_duration_seconds
            total_metrics.queue_time_seconds += metrics.queue_time_seconds
            total_metrics.execution_time_seconds += metrics.execution_time_seconds
            total_metrics.job_count += metrics.job_count
            total_metrics.step_count += metrics.step_count
            total_metrics.parallel_jobs = max(total_metrics.parallel_jobs, metrics.parallel_jobs)
            if metrics.longest_job_duration > total_metrics.longest_job_duration:
                total_metrics.longest_job_duration = metrics.longest_job_duration
                total_metrics.longest_job_name = metrics.longest_job_name
            run_count += 1

        if run_count > 0:
            total_metrics.cache_hit_rate = None  # Would need per-run aggregation

        return total_metrics

    def get_top_workflows_by_duration(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
        limit: int = 10,
    ) -> list[dict]:
        """Get top workflows by average duration."""
        workflow_durations: dict[str, list[float]] = defaultdict(list)

        for run in runs:
            jobs = jobs_by_run.get(run.id, [])
            metrics = self.analyze_run_performance(run, jobs)
            workflow_durations[run.name].append(metrics.total_duration_seconds)

        avg_durations = {
            name: sum(durations) / len(durations)
            for name, durations in workflow_durations.items()
        }

        sorted_workflows = sorted(
            avg_durations.items(), key=lambda x: x[1], reverse=True
        )

        return [
            {
                "name": name,
                "avg_duration_seconds": round(avg_dur, 1),
                "avg_duration_minutes": round(avg_dur / 60, 1),
                "run_count": len(workflow_durations[name]),
            }
            for name, avg_dur in sorted_workflows[:limit]
        ]

    def get_failure_analysis(
        self,
        runs: list[WorkflowRun],
        jobs_by_run: dict[int, list[Job]],
    ) -> tuple[float, list[dict]]:
        """Analyze failure rates and common failure patterns."""
        total_runs = len(runs)
        failed_runs = 0
        failure_reasons: dict[str, int] = defaultdict(int)

        for run in runs:
            if run.conclusion == "failure":
                failed_runs += 1
                jobs = jobs_by_run.get(run.id, [])
                for job in jobs:
                    if job.conclusion == "failure":
                        for step in job.steps:
                            if step.conclusion and step.conclusion.value == "failure":
                                failure_reasons[step.name] += 1
                                break

        failure_rate = failed_runs / total_runs if total_runs > 0 else 0.0

        common_failures = [
            {"step": step, "count": count}
            for step, count in sorted(failure_reasons.items(), key=lambda x: x[1], reverse=True)
        ][:10]

        return failure_rate, common_failures
