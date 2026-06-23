"""CLI entry point for Workflow Inspector."""

import asyncio
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .client import GitHubClient
from .cost import CostAnalyzer
from .models import AnalysisReport
from .optimization import OptimizationAnalyzer
from .performance import PerformanceAnalyzer
from .security import SecurityAnalyzer

console = Console()

GH_TOKEN_ERROR = "GitHub token not found. Set GITHUB_TOKEN env var or run 'gh auth login'"  # noqa: S105
REPO_FORMAT_ERROR = "Repository must be in format 'owner/repo'"


def get_token() -> str:
    """Get GitHub token from environment or gh CLI."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # Try to get from gh CLI
    gh_path = shutil.which("gh")
    if gh_path is None:
        raise click.ClickException(GH_TOKEN_ERROR)

    try:
        result = subprocess.run(  # noqa: S603
            [gh_path, "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise click.ClickException(GH_TOKEN_ERROR) from exc


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Workflow Inspector - Analyze and optimize GitHub Actions workflows."""


@main.command()
@click.argument("repository", required=True)
@click.option("--days", "-d", default=30, help="Number of days to analyze")
@click.option("--output", "-o", type=click.Path(), help="Output report to file")
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
)
def analyze(repository: str, days: int, output: Optional[str], output_format: str) -> None:
    """Analyze a repository's GitHub Actions workflows."""
    if "/" not in repository:
        raise click.ClickException(REPO_FORMAT_ERROR)

    owner, repo = repository.split("/", 1)

    async def run_analysis() -> AnalysisReport:
        token = get_token()
        client = GitHubClient(token=token)
        cost_analyzer = CostAnalyzer(client)
        perf_analyzer = PerformanceAnalyzer(client)
        security_analyzer = SecurityAnalyzer()
        opt_analyzer = OptimizationAnalyzer()

        # Fetch workflow runs
        since = None
        if days > 0:
            since = datetime.now(UTC) - timedelta(days=days)

        console.print(f"[blue]Fetching workflow runs for {owner}/{repo}...[/blue]")
        runs = await client.get_workflow_runs(owner, repo, since=since)

        console.print(f"[green]Found {len(runs)} workflow runs[/green]")

        # Fetch jobs for each run
        jobs_by_run = await _fetch_jobs_for_runs(client, owner, repo, runs)

        # Fetch workflow files
        console.print("[blue]Fetching workflow files...[/blue]")
        workflows = await client.get_workflows(owner, repo)

        # Analyze
        console.print("[blue]Analyzing...[/blue]")

        report = _analyze_data(
            owner,
            repo,
            days,
            runs,
            jobs_by_run,
            workflows,
            cost_analyzer,
            perf_analyzer,
            security_analyzer,
            opt_analyzer,
        )

        await client.close()
        return report

    report = asyncio.run(run_analysis())

    # Output
    if output_format == "json":
        _output_json(report, output)
    else:
        _print_table_report(report, console)
        if output:
            _output_json(report, output)


async def _fetch_jobs_for_runs(
    client: GitHubClient, owner: str, repo: str, runs: list
) -> dict[int, list]:
    """Fetch jobs for all runs with progress indicator."""
    jobs_by_run: dict[int, list] = {}
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching job details...", total=len(runs))
        for run in runs:
            jobs = await client.get_workflow_run_jobs(owner, repo, run.id)
            jobs_by_run[run.id] = jobs
            progress.advance(task)
    return jobs_by_run


def _analyze_data(
    owner: str,
    repo: str,
    days: int,
    runs: list,
    jobs_by_run: dict[int, list],
    workflows: list,
    cost_analyzer: CostAnalyzer,
    perf_analyzer: PerformanceAnalyzer,
    security_analyzer: SecurityAnalyzer,
    opt_analyzer: OptimizationAnalyzer,
) -> AnalysisReport:
    """Analyze all data and build report."""
    report = AnalysisReport(
        repository=f"{owner}/{repo}",
        period_days=days,
        workflow_runs_analyzed=len(runs),
    )

    # Cost analysis
    report.cost_breakdown = cost_analyzer.analyze_period_cost(runs, jobs_by_run)
    report.total_cost_usd = report.cost_breakdown.estimated_cost_usd
    report.top_workflows_by_cost = cost_analyzer.get_top_workflows_by_cost(runs, jobs_by_run)

    # Performance analysis
    report.performance_summary = perf_analyzer.analyze_period_performance(runs, jobs_by_run)
    report.top_workflows_by_duration = perf_analyzer.get_top_workflows_by_duration(
        runs, jobs_by_run
    )
    report.failure_rate, report.most_common_failures = perf_analyzer.get_failure_analysis(
        runs, jobs_by_run
    )

    # Security analysis
    for wf in workflows:
        findings = security_analyzer.analyze_workflow(wf, wf.path)
        report.security_findings.extend(findings)

    # Optimization analysis
    for wf in workflows:
        suggestions = opt_analyzer.analyze_workflow(wf, wf.path)
        report.optimization_suggestions.extend(suggestions)

    return report


def _output_json(report: AnalysisReport, output: Optional[str]) -> None:
    """Output report as JSON."""
    output_data = report.model_dump(mode="json")
    if output:
        Path(output).write_text(json.dumps(output_data, indent=2, default=str))
        console.print(f"[green]Report saved to {output}[/green]")
    else:
        console.print(json.dumps(output_data, indent=2, default=str))


def _print_table_report(report: AnalysisReport, console: Console) -> None:
    """Print analysis report as tables."""
    _print_header(console, report)
    _print_cost_breakdown(console, report)
    _print_top_workflows_by_cost(console, report)
    _print_top_workflows_by_duration(console, report)
    _print_security_findings(console, report)
    _print_optimization_suggestions(console, report)


def _print_header(console: Console, report: AnalysisReport) -> None:
    """Print report header."""
    console.print(f"\n[bold]Workflow Analysis Report: {report.repository}[/bold]")
    console.print(
        f"Period: {report.period_days} days | Runs analyzed: {report.workflow_runs_analyzed}"
    )
    console.print(f"Total estimated cost: ${report.total_cost_usd:.4f}")
    console.print(f"Failure rate: {report.failure_rate:.1%}")


def _print_cost_breakdown(console: Console, report: AnalysisReport) -> None:
    """Print cost breakdown table."""
    if report.cost_breakdown.total_minutes <= 0:
        return

    table = Table(title="Cost Breakdown")
    table.add_column("Runner Type", style="cyan")
    table.add_column("Minutes", justify="right")
    table.add_column("Est. Cost", justify="right")

    cb = report.cost_breakdown
    if cb.linux_minutes > 0:
        table.add_row("Linux", f"{cb.linux_minutes:.1f}", f"${cb.linux_minutes * 0.008:.4f}")
    if cb.windows_minutes > 0:
        table.add_row("Windows", f"{cb.windows_minutes:.1f}", f"${cb.windows_minutes * 0.016:.4f}")
    if cb.macos_minutes > 0:
        table.add_row("macOS", f"{cb.macos_minutes:.1f}", f"${cb.macos_minutes * 0.08:.4f}")

    console.print(table)


def _print_top_workflows_by_cost(console: Console, report: AnalysisReport) -> None:
    """Print top workflows by cost."""
    if not report.top_workflows_by_cost:
        return

    table = Table(title="Top Workflows by Cost")
    table.add_column("Workflow", style="cyan")
    table.add_column("Total Cost", justify="right")
    table.add_column("Runs", justify="right")
    table.add_column("Avg Cost", justify="right")

    for wf in report.top_workflows_by_cost[:10]:
        table.add_row(
            wf["name"],
            f"${wf['total_cost_usd']:.4f}",
            str(wf["run_count"]),
            f"${wf['avg_cost_usd']:.4f}",
        )
    console.print(table)


def _print_top_workflows_by_duration(console: Console, report: AnalysisReport) -> None:
    """Print top workflows by duration."""
    if not report.top_workflows_by_duration:
        return

    table = Table(title="Top Workflows by Duration")
    table.add_column("Workflow", style="cyan")
    table.add_column("Avg Duration", justify="right")
    table.add_column("Runs", justify="right")

    for wf in report.top_workflows_by_duration[:10]:
        table.add_row(
            wf["name"],
            f"{wf['avg_duration_minutes']:.1f} min",
            str(wf["run_count"]),
        )
    console.print(table)


def _print_security_findings(console: Console, report: AnalysisReport) -> None:
    """Print security findings table."""
    if not report.security_findings:
        return

    table = Table(title="Security Findings")
    table.add_column("Severity", style="red")
    table.add_column("Category", style="cyan")
    table.add_column("Title")
    table.add_column("File")

    for finding in report.security_findings[:20]:
        table.add_row(
            finding.severity.upper(),
            finding.category,
            finding.title,
            finding.file_path,
        )
    console.print(table)


def _print_optimization_suggestions(console: Console, report: AnalysisReport) -> None:
    """Print optimization suggestions table."""
    if not report.optimization_suggestions:
        return

    table = Table(title="Optimization Suggestions")
    table.add_column("Category", style="cyan")
    table.add_column("Impact", style="yellow")
    table.add_column("Title")
    table.add_column("File")

    for sugg in report.optimization_suggestions[:20]:
        table.add_row(
            sugg.category,
            sugg.impact,
            sugg.title,
            sugg.file_path,
        )
    console.print(table)


if __name__ == "__main__":
    main()
