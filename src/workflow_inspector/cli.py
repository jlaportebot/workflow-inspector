"""CLI entry point for Workflow Inspector."""

import asyncio
import os
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .client import GitHubClient
from .models import AnalysisReport
from .cost import CostAnalyzer
from .performance import PerformanceAnalyzer
from .security import SecurityAnalyzer
from .optimization import OptimizationAnalyzer

console = Console()


def get_token() -> str:
    """Get GitHub token from environment or gh CLI."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token

    # Try to get from gh CLI
    import subprocess
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise click.ClickException(
            "GitHub token not found. Set GITHUB_TOKEN env var or run 'gh auth login'"
        )


@click.group()
@click.version_option(version="0.1.0")
def main() -> None:
    """Workflow Inspector - Analyze and optimize GitHub Actions workflows."""
    pass


@main.command()
@click.argument("repository", required=True)
@click.option("--days", "-d", default=30, help="Number of days to analyze")
@click.option("--output", "-o", type=click.Path(), help="Output report to file")
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def analyze(repository: str, days: int, output: Optional[str], format: str) -> None:
    """Analyze a repository's GitHub Actions workflows."""
    if "/" not in repository:
        raise click.ClickException("Repository must be in format 'owner/repo'")

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
            from datetime import datetime, timedelta, timezone
            since = datetime.now(timezone.utc) - timedelta(days=days)

        console.print(f"[blue]Fetching workflow runs for {owner}/{repo}...[/blue]")
        runs = await client.get_workflow_runs(owner, repo, since=since)

        console.print(f"[green]Found {len(runs)} workflow runs[/green]")

        # Fetch jobs for each run
        jobs_by_run = {}
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

        # Fetch workflow files
        console.print("[blue]Fetching workflow files...[/blue]")
        workflows = await client.get_workflows(owner, repo)

        # Analyze
        console.print("[blue]Analyzing...[/blue]")

        report = AnalysisReport(
            repository=f"{owner}/{repo}",
            period_days=days,
            workflow_runs_analyzed=len(runs),
        )

        # Cost analysis
        report.cost_breakdown = cost_analyzer.analyze_period_cost(runs, jobs_by_run)
        report.total_cost_usd = report.cost_breakdown.estimated_cost_usd
        report.top_workflows_by_cost = cost_analyzer.get_top_workflows_by_cost(
            runs, jobs_by_run
        )

        # Performance analysis
        report.performance_summary = perf_analyzer.analyze_period_performance(
            runs, jobs_by_run
        )
        report.top_workflows_by_duration = perf_analyzer.get_top_workflows_by_duration(
            runs, jobs_by_run
        )
        report.failure_rate, report.most_common_failures = (
            perf_analyzer.get_failure_analysis(runs, jobs_by_run)
        )

        # Security analysis
        for wf in workflows:
            findings = security_analyzer.analyze_workflow(wf, wf.path)
            report.security_findings.extend(findings)

        # Optimization analysis
        for wf in workflows:
            suggestions = opt_analyzer.analyze_workflow(wf, wf.path)
            report.optimization_suggestions.extend(suggestions)

        await client.close()
        return report

    report = asyncio.run(run_analysis())

    # Output
    if format == "json":
        import json
        output_data = report.model_dump(mode="json")
        if output:
            Path(output).write_text(json.dumps(output_data, indent=2, default=str))
            console.print(f"[green]Report saved to {output}[/green]")
        else:
            console.print(json.dumps(output_data, indent=2, default=str))
    else:
        _print_table_report(report, console)
        if output:
            import json
            Path(output).write_text(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
            console.print(f"[green]Report saved to {output}[/green]")


def _print_table_report(report: AnalysisReport, console: Console) -> None:
    """Print analysis report as tables."""
    console.print(f"\n[bold]Workflow Analysis Report: {report.repository}[/bold]")
    console.print(f"Period: {report.period_days} days | Runs analyzed: {report.workflow_runs_analyzed}")
    console.print(f"Total estimated cost: ${report.total_cost_usd:.4f}")
    console.print(f"Failure rate: {report.failure_rate:.1%}")

    # Cost breakdown
    if report.cost_breakdown.total_minutes > 0:
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

    # Top workflows by cost
    if report.top_workflows_by_cost:
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

    # Top workflows by duration
    if report.top_workflows_by_duration:
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

    # Security findings
    if report.security_findings:
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

    # Optimization suggestions
    if report.optimization_suggestions:
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
