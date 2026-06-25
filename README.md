# Workflow Inspector

Analyze and optimize GitHub Actions workflows — cost tracking, performance bottlenecks, security linting, and optimization suggestions.

[![PyPI](https://img.shields.io/pypi/v/workflow-inspector.svg)](https://pypi.org/project/workflow-inspector/)
[![Python](https://img.shields.io/pypi/pyversions/workflow-inspector.svg)](https://pypi.org/project/workflow-inspector/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- **Cost Analysis** — Track GitHub Actions minutes and estimate costs across Linux, Windows, and macOS runners
- **Performance Analysis** — Identify slow workflows, queue times, parallelization opportunities, cache hit rates
- **Security Linting** — Detect hardcoded secrets, unpinned actions, overly permissive permissions, command injection risks, supply chain issues
- **Optimization Suggestions** — Get actionable recommendations for caching, parallelization, matrix strategies, runner selection, dependency caching, workflow structure, and action versions

## Installation

```bash
pip install workflow-inspector
```

Or with [uv](https://github.com/astral-sh/uv):

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

1. Environment variable: `export GITHUB_TOKEN=***`
2. GitHub CLI: `gh auth login` (token will be fetched automatically)

## Analysis Details

### Cost Analysis

- Breaks down minutes by runner type (Linux, Windows, macOS)
- Calculates estimated cost using GitHub's published rates ($0.008/min Linux, $0.016/min Windows, $0.08/min macOS)
- Identifies most expensive workflows
- Estimates monthly cost projection

### Performance Analysis

- Total duration, queue time, and execution time
- Job parallelism estimation
- Cache hit rate detection
- Failure rate and common failure patterns
- Top workflows by duration

### Security Analysis

- **Hardcoded secrets** — API keys, AWS credentials, GitHub tokens, Docker credentials, Slack/NPM tokens
- **Action pinning** — Verifies actions are pinned to commit SHA (not mutable tags)
- **Permissions** — Detects overly permissive permissions (write-all, admin, contents: write)
- **Command injection** — Detects untrusted GitHub context interpolation in shell commands
- **Supply chain** — Flags third-party actions from unverified publishers
- **Workflow permissions** — Checks job-level permissions for least-privilege

### Optimization Suggestions

| Category | Checks |
|----------|--------|
| **Caching** | Missing `actions/cache`, cache keys without `hashFiles`, dependency caching for npm/pip/cargo/maven/gradle/go/composer/nuget |
| **Parallelism** | Sequential jobs that could run in parallel |
| **Matrix** | `runs-on` list vs matrix strategy, `fail-fast: true` default |
| **Runner** | Outdated runners (ubuntu-18.04, ubuntu-20.04, windows-2019, macos-11/12), bare `self-hosted` |
| **Dependencies** | Package manager detection without caching |
| **Structure** | Missing concurrency, defaults, env vars |
| **Action versions** | Outdated common actions (checkout v3→v4, cache v3→v4, etc.) |

## Output Formats

```bash
# Table output (default)
workflow-inspector analyze owner/repo

# JSON output for CI/CD
workflow-inspector analyze owner/repo --format json

# Save to file
workflow-inspector analyze owner/repo --output report.json
```

## Example Output

```bash
$ workflow-inspector analyze myorg/myrepo

📊 Workflow Inspector — myorg/myrepo (last 30 days)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 COST ANALYSIS
  Linux:   1,234 min  ($9.87)
  Windows:   567 min  ($9.07)
  macOS:     89 min  ($7.12)
  ────────────────────────────────────────────
  Total:   1,890 min  ($26.06)
  Monthly projection: $260.60

  Top workflows by cost:
  1. CI Pipeline          $15.23 (45 runs)
  2. Deploy Production    $8.45  (12 runs)
  3. Integration Tests    $2.38  (28 runs)

⚡ PERFORMANCE ANALYSIS
  Avg duration: 4m 32s  |  Queue: 45s  |  Execution: 3m 47s
  Parallelism: 3.2 jobs avg  |  Cache hit rate: 68%

  Top slow workflows:
  1. Integration Tests     12m 14s  (28 runs)
  2. E2E Tests             8m 8m 56s  (15 runs)

  Failure rate: 12% (18/150 runs)
  Common failures: npm install (6), flaky e2e test (4), timeout (3)

🔒 SECURITY ANALYSIS
  ✓ No hardcoded secrets found
  ✓ All actions pinned to commit SHA
  ✓ Permissions properly restricted
  ⚠ 2 workflows lack explicit permissions
  ⚠ 1 action pinned to mutable tag (actions/checkout@v3)

🔧 OPTIMIZATION SUGGESTIONS
  HIGH IMPACT:
  • CI Pipeline: No dependency caching for npm (add actions/cache)
  • Deploy: All jobs sequential - test & build can run in parallel
  • CI Pipeline: Uses ubuntu-20.04 (upgrade to ubuntu-22.04)
  • Deploy: No concurrency control - enable cancel-in-progress

  MEDIUM IMPACT:
  • CI Pipeline: Matrix uses fail-fast: true (default)
  • Integration Tests: Uses runs-on list instead of matrix

  LOW IMPACT:
  • Multiple actions on older versions (checkout v3→v4, cache v3→v4)
```

## Configuration

### Custom Optimization Policies

Create a `workflow-inspector.yaml` to customize analysis:

```yaml
rules:
  - name: "No self-hosted runners"
    category: "runner"
    severity: "high"
    check_type: "step_uses"
    pattern: "self-hosted"
    suggestion: "Use GitHub-hosted runners instead"
    estimated_savings_percent: 0.0

  - name: "Require npm caching"
    category: "caching"
    severity: "medium"
    check_type: "job_steps"
    pattern: "npm"
    suggestion: "Add actions/cache for ~/.npm"
```

Load policies:
```bash
workflow-inspector analyze owner/repo --policy-dir /path/to/policies
```

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

# Type check
uv run ty check src/
```

## Architecture

```
workflow-inspector/
├── workflow_inspector/
│   ├── __init__.py           # Package metadata
│   ├── cli.py                # Click CLI entry point
│   ├── client.py             # GitHub API client (REST + GraphQL)
│   ├── models.py             # Pydantic models for runs, jobs, steps, findings
│   ├── cost.py               # Cost analysis engine
│   ├── performance.py        # Performance analysis engine
│   ├── security.py           # Security linting engine
│   ├── optimization.py       # Optimization suggestion engine
│   └── policies/             # Custom policy definitions
├── tests/
├── pyproject.toml
└── README.md
```

## License

MIT