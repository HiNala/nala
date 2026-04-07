from __future__ import annotations

from .models import VerifiedFinding


def generate_prompt(finding: VerifiedFinding) -> str:
    """
    Produces actionable text for an LLM agent.
    Example:
    Verify each finding against the current code and only fix it if needed.
    In @apps/mobile/app/(tabs)/discover.tsx at line 102, The callbacks...
    """

    desc = finding.enriched_description or finding.description

    if finding.start_line == finding.end_line:
        line_ref = f"at line {finding.start_line}"
    else:
        line_ref = f"around lines {finding.start_line}-{finding.end_line}"

    idents = ""
    if finding.identifiers:
        idents = f" (Targets: {', '.join(finding.identifiers)})"

    return (
        f"Verify each finding against the current code and only fix it if needed.\n\n"
        f"In @{finding.file_path} {line_ref}, {desc}\n\n"
        f"Action: {finding.instruction}{idents}\n"
    )


def generate_all_prompts(findings: list[VerifiedFinding]) -> str:
    if not findings:
        return "No findings to report."

    parts: list[str] = []
    for finding in findings:
        parts.append(generate_prompt(finding))
        parts.append("-" * 40)

    return "\n".join(parts)
