"""
Mission document auto-generator.

Takes audit findings and generates structured mission documents — self-contained
task specifications that can be handed to a coding agent (like Claude Code) or
tackled by a human developer.

Each mission covers one distinct actionable area identified in the audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .report import AuditReport, Finding


@dataclass
class MissionDocument:
    """A generated mission document."""

    number: int
    title: str
    objective: str
    context: str
    findings: list[Finding]
    acceptance_criteria: list[str]
    implementation_steps: list[str]
    estimated_complexity: str  # "Low" | "Medium" | "High"


class MissionGenerator:
    """Generates mission documents from audit findings."""

    def generate_all(self, report: AuditReport) -> list[MissionDocument]:
        """Generate a set of missions from an audit report.

        Groups related findings into missions. Critical + high severity
        findings each get their own mission. Medium findings are grouped
        by perspective. Low findings are bundled into a cleanup mission.
        """
        missions: list[MissionDocument] = []
        n = 1

        # Critical findings — each gets its own mission
        for finding in [f for f in report.findings if f.severity == "critical"]:
            missions.append(self._finding_to_mission(n, finding))
            n += 1

        # High findings — each gets its own mission
        for finding in [f for f in report.findings if f.severity == "high"]:
            missions.append(self._finding_to_mission(n, finding))
            n += 1

        # Medium findings — grouped by perspective
        medium = [f for f in report.findings if f.severity == "medium"]
        if medium:
            missions.append(self._group_to_mission(n, medium, "medium"))
            n += 1

        # Low findings — one cleanup mission
        low = [f for f in report.findings if f.severity == "low"]
        if low:
            missions.append(self._group_to_mission(n, low, "low"))

        return missions

    def render(self, mission: MissionDocument) -> str:
        """Render a mission as a markdown string."""
        lines = []
        lines.append(f"# Mission {mission.number:02d}: {mission.title}")
        lines.append(f"\n## Objective\n\n{mission.objective}")
        lines.append(f"\n## Context\n\n{mission.context}")

        if mission.findings:
            lines.append("\n## Findings\n")
            for f in mission.findings:
                lines.append(f"- **{f.title}** — `{f.file_path}:{f.start_line}` ({f.severity})")

        lines.append("\n## Implementation Steps\n")
        for i, step in enumerate(mission.implementation_steps, 1):
            lines.append(f"{i}. {step}")

        lines.append("\n## Acceptance Criteria\n")
        for criterion in mission.acceptance_criteria:
            lines.append(f"- [ ] {criterion}")

        lines.append(f"\n## Estimated Complexity\n\n{mission.estimated_complexity}")
        return "\n".join(lines)

    # ── Private ────────────────────────────────────────────────────────────

    def _finding_to_mission(self, n: int, finding: Finding) -> MissionDocument:
        return MissionDocument(
            number=n,
            title=finding.title,
            objective=finding.description,
            context=(
                f"This issue was identified by the {finding.perspective} perspective "
                f"in `{finding.file_path}` at line {finding.start_line}."
            ),
            findings=[finding],
            acceptance_criteria=[
                f"The issue at `{finding.file_path}:{finding.start_line}` is resolved",
                "All tests pass after the fix",
                "No new issues introduced",
            ],
            implementation_steps=[
                f"Open `{finding.file_path}` and navigate to line {finding.start_line}",
                finding.suggestion or "Review and fix the identified issue",
                "Write or update tests to cover the changed code",
                "Run the full test suite to verify no regressions",
            ],
            estimated_complexity="Medium" if finding.severity == "high" else "High",
        )

    def _group_to_mission(self, n: int, findings: list[Finding], severity: str) -> MissionDocument:
        perspectives = sorted({f.perspective for f in findings})
        title = f"Address {severity.capitalize()}-Severity Findings ({', '.join(perspectives)})"
        return MissionDocument(
            number=n,
            title=title,
            objective=(
                f"Resolve all {severity}-severity findings identified across "
                f"{len(findings)} locations."
            ),
            context=(
                f"These {len(findings)} findings were grouped together because they share similar "
                f"severity ({severity}) and can be addressed in a single pass. "
                f"Perspectives involved: {', '.join(perspectives)}."
            ),
            findings=findings,
            acceptance_criteria=[
                f"All {len(findings)} findings are resolved or have accepted rationale",
                "All tests pass",
                "No regressions introduced",
            ],
            implementation_steps=[
                f"Review each of the {len(findings)} findings listed above",
                "Address them in order of most to least impactful",
                "Test each change before moving to the next",
                "Update documentation if behaviour changes",
            ],
            estimated_complexity="Medium",
        )
