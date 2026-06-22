"""Optimization suggestions for GitHub Actions workflows."""

from .models import OptimizationSuggestion, WorkflowFile


class OptimizationAnalyzer:
    """Analyze workflows for optimization opportunities."""

    def __init__(self) -> None:
        self.suggestions: list[OptimizationSuggestion] = []

    def analyze_workflow(self, workflow: WorkflowFile, path: str) -> list[OptimizationSuggestion]:
        self.suggestions = []
        self._check_caching(workflow, path)
        self._check_parallelism(workflow, path)
        self._check_matrix_strategy(workflow, path)
        self._check_runner_selection(workflow, path)
        self._check_dependency_caching(workflow, path)
        self._check_workflow_structure(workflow, path)
        self._check_action_versions(workflow, path)
        return self.suggestions

    def _check_caching(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs:
            return

        has_cache_action = False
        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict):
                    continue
                uses = step.get("uses", "")
                if "actions/cache" in uses:
                    has_cache_action = True
                    with_ = step.get("with", {})
                    key = with_.get("key", "")
                    if key and "${{ hashFiles(" not in key:
                        self.suggestions.append(
                            OptimizationSuggestion(
                                category="caching",
                                title="Cache key could use hashFiles for better invalidation",
                                description=(
                                    f"Cache key in job '{job_name}' doesn't use "
                                    "hashFiles for automatic invalidation."
                                ),
                                impact="medium",
                                effort="low",
                                file_path=path,
                                example=(
                                    "key: ${{ runner.os }}-${{ hashFiles('**/package-lock.json') }}"
                                ),
                            )
                        )

        if not has_cache_action:
            self.suggestions.append(
                OptimizationSuggestion(
                    category="caching",
                    title="No caching configured",
                    description=(
                        "Workflow doesn't use actions/cache. Adding caching can "
                        "significantly reduce build times."
                    ),
                    impact="high",
                    effort="medium",
                    file_path=path,
                    example=(
                        "- uses: actions/cache@v4\n"
                        "  with:\n"
                        "    path: ~/.npm\n"
                        "    key: ${{ runner.os }}-node-${{ "
                        "hashFiles('**/package-lock.json') }}\n"
                        "    restore-keys: |\n"
                        "      ${{ runner.os }}-node-"
                    ),
                )
            )

    def _check_parallelism(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs or len(workflow.jobs) <= 1:
            return

        dependent_jobs = 0
        for job_config in workflow.jobs.values():
            if not isinstance(job_config, dict):
                continue
            needs = job_config.get("needs", [])
            if needs:
                dependent_jobs += 1

        if dependent_jobs == len(workflow.jobs) - 1:
            self.suggestions.append(
                OptimizationSuggestion(
                    category="parallelism",
                    title="All jobs run sequentially - consider parallelization",
                    description=(
                        "All jobs have explicit dependencies, running sequentially. "
                        "Independent jobs can run in parallel."
                    ),
                    impact="high",
                    effort="medium",
                    file_path=path,
                    example=(
                        "jobs:\n  build:\n    # no needs\n  test:\n    # no needs\n  deploy:\n"
                        "    needs: [build, test]  # only deploy waits"
                    ),
                )
            )

    def _check_matrix_strategy(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs:
            return

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            strategy = job_config.get("strategy", {})
            matrix = strategy.get("matrix", {})

            if not matrix:
                runs_on = job_config.get("runs-on", "")
                if isinstance(runs_on, list) and len(runs_on) > 1:
                    self.suggestions.append(
                        OptimizationSuggestion(
                            category="matrix",
                            title=f"Job '{job_name}' uses runs-on list instead of matrix",
                            description=(
                                "Using a list for runs-on runs jobs sequentially. "
                                "Matrix strategy runs in parallel."
                            ),
                            impact="high",
                            effort="low",
                            file_path=path,
                            example=(
                                "strategy:\n  matrix:\n    os: [ubuntu-latest, "
                                "windows-latest, macos-latest]\n  fail-fast: false\n"
                                "runs-on: ${{ matrix.os }}"
                            ),
                        )
                    )
            else:
                fail_fast = strategy.get("fail-fast", True)
                if fail_fast and len(matrix) > 1:
                    self.suggestions.append(
                        OptimizationSuggestion(
                            category="matrix",
                            title=f"Job '{job_name}' has fail-fast enabled (default)",
                            description=(
                                "fail-fast: true cancels other matrix jobs on first "
                                "failure. Set to false for full results."
                            ),
                            impact="medium",
                            effort="low",
                            file_path=path,
                            example=("strategy:\n  fail-fast: false\n  matrix:\n    ..."),
                        )
                    )

    def _check_runner_selection(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs:
            return

        outdated_runners = {
            "ubuntu-18.04": "ubuntu-22.04",
            "ubuntu-20.04": "ubuntu-24.04",
            "windows-2019": "windows-2022",
            "macos-11": "macos-14",
            "macos-12": "macos-14",
        }

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            runs_on = job_config.get("runs-on", "")

            if isinstance(runs_on, str):
                for old, new in outdated_runners.items():
                    if old in runs_on:
                        self.suggestions.append(
                            OptimizationSuggestion(
                                category="runner",
                                title=f"Job '{job_name}' uses outdated runner: {runs_on}",
                                description=(
                                    f"Runner '{runs_on}' is deprecated or outdated. "
                                    "Consider upgrading."
                                ),
                                impact="medium",
                                effort="low",
                                file_path=path,
                                example=f"runs-on: {new}",
                            )
                        )

                if "self-hosted" in runs_on and runs_on == "self-hosted":
                    self.suggestions.append(
                        OptimizationSuggestion(
                            category="runner",
                            title=f"Job '{job_name}' uses bare 'self-hosted' runner",
                            description=(
                                "Using 'self-hosted' without labels can route to any "
                                "self-hosted runner. Add specific labels."
                            ),
                            impact="low",
                            effort="low",
                            file_path=path,
                            example="runs-on: [self-hosted, linux, x64]",
                        )
                    )

    def _check_dependency_caching(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs:
            return

        cache_patterns = {
            "npm": ["package-lock.json", "yarn.lock", "pnpm-lock.yaml"],
            "pip": ["requirements.txt", "pyproject.toml", "poetry.lock", "uv.lock"],
            "maven": ["pom.xml"],
            "gradle": ["build.gradle", "build.gradle.kts", "gradle.lockfile"],
            "cargo": ["Cargo.lock"],
            "go": ["go.sum"],
            "composer": ["composer.lock"],
            "nuget": ["packages.lock.json", "*.csproj"],
        }

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            step_names = [s.get("name", "").lower() for s in steps if isinstance(s, dict)]
            step_uses = [s.get("uses", "") for s in steps if isinstance(s, dict)]

            for pm, lockfiles in cache_patterns.items():
                has_pm_step = (
                    any(pm in name for name in step_names)
                    or any(f"actions/setup-{pm}" in u for u in step_uses)
                    or any(f"setup-{pm}" in u for u in step_uses)
                )
                has_cache = any("actions/cache" in u for u in step_uses)

                if has_pm_step and not has_cache:
                    self.suggestions.append(
                        OptimizationSuggestion(
                            category="dependencies",
                            title=f"Job '{job_name}' uses {pm} but no dependency caching",
                            description=(
                                f"Dependency caching for {pm} can significantly speed up builds."
                            ),
                            impact="high",
                            effort="low",
                            file_path=path,
                            example=self._get_cache_example(pm, lockfiles[0]),
                        )
                    )

    def _get_cache_example(self, pm: str, lockfile: str) -> str:
        examples = {
            "npm": (
                "      - uses: actions/cache@v4\n"
                "        with:\n"
                "          path: ~/.npm\n"
                "          key: ${ runner.os }-node-${ "
                f"hashFiles('**/{lockfile}') }}\n"
                "          restore-keys: |\n"
                "            ${ runner.os }-node-"
            ),
            "pip": (
                "      - uses: actions/cache@v4\n"
                "        with:\n"
                "          path: ~/.cache/pip\n"
                "          key: ${ runner.os }-pip-${ "
                f"hashFiles('**/{lockfile}') }}\n"
                "          restore-keys: |\n"
                "            ${ runner.os }-pip-"
            ),
            "cargo": (
                "      - uses: actions/cache@v4\n"
                "        with:\n"
                "          path: |\n"
                "            ~/.cargo/bin\n"
                "            ~/.cargo/registry/index\n"
                "            ~/.cargo/registry/cache\n"
                "            ~/.cargo/git/db\n"
                "            target/\n"
                "          key: ${ runner.os }-cargo-${ "
                f"hashFiles('**/{lockfile}') }}\n"
                "          restore-keys: |\n"
                "            ${ runner.os }-cargo-"
            ),
        }
        return examples.get(pm, f"# Add caching for {pm}")

    def _check_workflow_structure(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.concurrency:
            self.suggestions.append(
                OptimizationSuggestion(
                    category="structure",
                    title="No concurrency control configured",
                    description=(
                        "Without concurrency control, multiple workflow runs can "
                        "queue up for the same branch/PR."
                    ),
                    impact="medium",
                    effort="low",
                    file_path=path,
                    example=(
                        "concurrency:\n  group: ${{ github.workflow }}-${{ github.ref }}\n"
                        "  cancel-in-progress: true"
                    ),
                )
            )

        if not workflow.defaults:
            self.suggestions.append(
                OptimizationSuggestion(
                    category="structure",
                    title="No defaults configured",
                    description=(
                        "Setting defaults for shell, working-directory can reduce repetition."
                    ),
                    impact="low",
                    effort="low",
                    file_path=path,
                    example=("defaults:\n  run:\n    shell: bash\n    working-directory: ./src"),
                )
            )

        if not workflow.env:
            self.suggestions.append(
                OptimizationSuggestion(
                    category="structure",
                    title="No workflow-level environment variables",
                    description=("Common environment variables can be defined at workflow level."),
                    impact="low",
                    effort="low",
                    file_path=path,
                    example="env:\n  NODE_ENV: production\n  PYTHON_VERSION: '3.11'",
                )
            )

    def _check_action_versions(self, workflow: WorkflowFile, path: str) -> None:
        if not workflow.jobs:
            return

        latest_versions = {
            "actions/checkout": "v4",
            "actions/setup-node": "v4",
            "actions/setup-python": "v5",
            "actions/setup-go": "v5",
            "actions/setup-java": "v4",
            "actions/cache": "v4",
            "actions/upload-artifact": "v4",
            "actions/download-artifact": "v4",
            "actions/github-script": "v7",
            "docker/build-push-action": "v5",
            "docker/login-action": "v3",
            "docker/setup-buildx-action": "v3",
        }

        for job_config in workflow.jobs.values():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict) or "uses" not in step:
                    continue

                uses = step["uses"]
                for action, latest in latest_versions.items():
                    if uses.startswith(action + "@"):
                        version = uses.split("@")[-1].split("/")[0]
                        if not version.startswith(latest):
                            self.suggestions.append(
                                OptimizationSuggestion(
                                    category="dependencies",
                                    title=f"Action {action} uses older version {version}",
                                    description=(
                                        f"Latest major version is {latest}. Newer "
                                        "versions may have performance improvements "
                                        "and bug fixes."
                                    ),
                                    impact="low",
                                    effort="low",
                                    file_path=path,
                                    example=f"{action}@{latest}",
                                )
                            )
