# Workflow Inspector

Analyze and optimize GitHub Actions workflows — cost tracking, performance bottlenecks, security linting, and optimization suggestions.

## Features

- **Cost Analysis**: Track GitHub Actions minutes and estimate costs across Linux, Windows, and macOS runners
- **Performance Analysis**: Identify slow workflows, queue times, and parallelization opportunities
- **Security Linting**: Detect hardcoded secrets, unpinned actions, overly permissive permissions, and command injection risks
- **Optimization Suggestions**: Get actionable recommendations for caching, matrix strategies, runner selection, and workflow structure

## Installation

```bash
pip install workflow-inspector
```

Or with uv:

```bash
uv add workflow-inspector
```

## Usage

### Analyze a Repository

```bash
# Analyze last 30 days of workflow runs
workflow-inspector analyze owner/repo

# Analyze last 7 days
workflow-inspector analyze owner/repo --days 7

# Output as JSON
workflow-inspector analyze owner/repo --format json

# Save report to file
workflow-inspector analyze owner/repo --output report.json
```

### Authentication

The tool requires a GitHub token. Provide it via:

1. Environment variable: `export GITHUB_TOKEN=your_token`
2. GitHub CLI: `gh auth login` (token will be fetched automatically)

## Analysis Details

### Cost Analysis
- Breaks down minutes by runner type (Linux, Windows, macOS)
- Calculates estimated cost using GitHub's published rates
- Identifies most expensive workflows

### Performance Analysis
- Total duration, queue time, and execution time
- Job parallelism estimation
- Cache hit rate detection
- Failure rate and common failure patterns

### Security Analysis
- Hardcoded secrets detection
- Action pinning verification (commit SHA vs tags)
- Permissions auditing (least privilege)
- Command injection risk detection
- Supply chain risk (unverified action publishers)

### Optimization Suggestions
- Missing dependency caching
- Parallelization opportunities
- Matrix strategy improvements
- Outdated runner versions
- Missing concurrency control
- Outdated action versions

## Development

```bash
# Clone and setup
git clone https://github.com/jlaportebot/workflow-inspector
cd workflow-inspector
uv sync --all-groups

# Run tests
uv run pytest

# Run linting
uv run ruff check .
uv run ruff format --check .
uv run ty check src/
```

## License

MIT