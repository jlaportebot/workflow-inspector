"""Security analysis for GitHub Actions workflows."""

import re

from .models import SecurityFinding, WorkflowFile


class SecurityAnalyzer:
    """Analyze security issues in GitHub Actions workflow files."""

    # Patterns for detecting secrets and sensitive data
    SECRET_PATTERNS = [
        (re.compile(r"(?i)(api[_-]?key|apikey|secret|password|token|auth[_-]?key)\s*[:=]\s*[\"']?([a-zA-Z0-9_\-]{20,})[\"']?"), "hardcoded_secret"),
        (re.compile(r"(?i)(aws[_-]?access[_-]?key|aws[_-]?secret[_-]?key)\s*[:=]\s*[\"']?([A-Z0-9]{20,})[\"']?"), "aws_credentials"),
        (re.compile(r"(?i)(github[_-]?token|gh[_-]?token|ghp_[a-zA-Z0-9]{36})"), "github_token"),
        (re.compile(r"(?i)(slack[_-]?token|xoxb-[a-zA-Z0-9\-]+)"), "slack_token"),
        (re.compile(r"(?i)(npm[_-]?token|npm_[a-zA-Z0-9]{36})"), "npm_token"),
        (re.compile(r"(?i)(docker[_-]?password|docker[_-]?token)"), "docker_credentials"),
    ]

    # Patterns for command injection vulnerabilities
    INJECTION_PATTERNS = [
        (re.compile(r"\$\{\{\s*(github\.event\.(issue|pull_request|comment|release|repository)\.[^}]+)\s*\}\}"), "github_event_injection"),
        (re.compile(r"\$\{\{\s*(github\.event\.[^}]+)\s*\}\}"), "github_context_injection"),
        (re.compile(r"run:\s*\|\s*\n\s*\$\{\{\s*[^}]+\s*\}\}"), "shell_injection"),
    ]

    def __init__(self):
        self.findings: list[SecurityFinding] = []

    def analyze_workflow(self, workflow: WorkflowFile, path: str) -> list[SecurityFinding]:
        """Analyze a workflow file for security issues."""
        self.findings = []

        # Convert workflow to YAML string for pattern matching
        import yaml
        content = yaml.dump(workflow.model_dump(exclude_none=True))

        self._check_hardcoded_secrets(content, path)
        self._check_permissions(workflow, path)
        self._check_action_pinning(workflow, path)
        self._check_command_injection(content, path)
        self._check_supply_chain(workflow, path)
        self._check_workflow_permissions(workflow, path)

        return self.findings

    def _check_hardcoded_secrets(self, content: str, path: str) -> None:
        """Check for hardcoded secrets in workflow."""
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pattern, category in self.SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    severity = "critical" if category in ("aws_credentials", "github_token") else "high"
                    self.findings.append(SecurityFinding(
                        severity=severity,
                        category="secrets",
                        title=f"Potential hardcoded {category.replace('_', ' ')}",
                        description=f"Possible secret detected in workflow file: {match.group()[:50]}",
                        file_path=path,
                        line_number=line_num,
                        remediation="Use GitHub Secrets (${{ secrets.SECRET_NAME }}) instead of hardcoding values.",
                        cwe_id="CWE-798",
                    ))

    def _check_permissions(self, workflow: WorkflowFile, path: str) -> None:
        """Check for overly permissive permissions."""
        if workflow.permissions is None:
            self.findings.append(SecurityFinding(
                severity="medium",
                category="permissions",
                title="Missing explicit permissions",
                description="Workflow does not define explicit permissions. Defaults to read-all for contents.",
                file_path=path,
                remediation="Add explicit permissions block with minimal required scopes.",
            ))
        elif isinstance(workflow.permissions, dict):
            # Check for write-all or admin permissions
            for key, value in workflow.permissions.items():
                if value in ("write-all", "admin") or (isinstance(value, str) and "write" in value and key == "contents"):
                    self.findings.append(SecurityFinding(
                        severity="high",
                        category="permissions",
                        title=f"Overly permissive {key} permission",
                        description=f"Workflow grants '{value}' permission for {key}.",
                        file_path=path,
                        remediation=f"Restrict {key} permission to minimal required scope (e.g., 'read').",
                        cwe_id="CWE-250",
                    ))

    def _check_action_pinning(self, workflow: WorkflowFile, path: str) -> None:
        """Check if actions are pinned to commit SHA."""
        if not workflow.jobs:
            return

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict) or "uses" not in step:
                    continue

                uses = step["uses"]
                if "@" not in uses:
                    self.findings.append(SecurityFinding(
                        severity="medium",
                        category="pinning",
                        title=f"Action not pinned: {uses}",
                        description=f"Action '{uses}' is not pinned to a specific version or commit SHA.",
                        file_path=path,
                        remediation=f"Pin action to commit SHA: {uses}@<sha>",
                        cwe_id="CWE-829",
                    ))
                else:
                    version = uses.split("@")[-1]
                    # Check if pinned to tag (mutable) instead of SHA (immutable)
                    if not re.match(r"^[a-f0-9]{40}$", version):
                        self.findings.append(SecurityFinding(
                            severity="low",
                            category="pinning",
                            title=f"Action pinned to mutable tag: {uses}",
                            description=f"Action '{uses}' is pinned to tag '{version}' which can be moved.",
                            file_path=path,
                            remediation=f"Pin to commit SHA instead of tag: {uses.split('@')[0]}@<sha>",
                            cwe_id="CWE-829",
                        ))

    def _check_command_injection(self, content: str, path: str) -> None:
        """Check for potential command injection via GitHub context interpolation."""
        lines = content.split("\n")
        for line_num, line in enumerate(lines, 1):
            for pattern, category in self.INJECTION_PATTERNS:
                match = pattern.search(line)
                if match:
                    self.findings.append(SecurityFinding(
                        severity="high",
                        category="command_injection",
                        title="Potential command injection via context interpolation",
                        description=f"Untrusted GitHub context interpolated into shell command: {match.group()[:100]}",
                        file_path=path,
                        line_number=line_num,
                        remediation="Avoid interpolating untrusted input into shell commands. Use action inputs instead of shell interpolation.",
                        cwe_id="CWE-78",
                    ))

    def _check_supply_chain(self, workflow: WorkflowFile, path: str) -> None:
        """Check for supply chain security issues."""
        if not workflow.jobs:
            return

        trusted_owners = {
            "actions", "github", "docker", "aws-actions", "azure",
            "google-github-actions", "hashicorp", "pypa"
        }

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            steps = job_config.get("steps", [])
            for step in steps:
                if not isinstance(step, dict) or "uses" not in step:
                    continue

                uses = step["uses"]
                if "/" in uses:
                    owner, action = uses.split("/", 1)
                    if owner not in trusted_owners:
                        self.findings.append(SecurityFinding(
                            severity="low",
                            category="supply_chain",
                            title=f"Third-party action: {uses}",
                            description=f"Action from '{owner}' is not a verified publisher.",
                            file_path=path,
                            remediation="Verify the action source, pin to commit SHA, and consider using trusted alternatives.",
                            cwe_id="CWE-829",
                        ))

    def _check_workflow_permissions(self, workflow: WorkflowFile, path: str) -> None:
        """Check job-level permissions."""
        if not workflow.jobs:
            return

        for job_name, job_config in workflow.jobs.items():
            if not isinstance(job_config, dict):
                continue

            permissions = job_config.get("permissions")
            if permissions is None:
                continue

            if isinstance(permissions, dict):
                for key, value in permissions.items():
                    if value in ("write-all", "admin") or (isinstance(value, str) and "write" in value and key == "contents"):
                        self.findings.append(SecurityFinding(
                            severity="medium",
                            category="permissions",
                            title=f"Job '{job_name}' has overly permissive {key} permission",
                            description=f"Job grants '{value}' permission for {key}.",
                            file_path=path,
                            remediation=f"Restrict {key} permission to minimal required scope.",
                            cwe_id="CWE-250",
                        ))
