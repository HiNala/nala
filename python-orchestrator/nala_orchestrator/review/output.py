from __future__ import annotations

from dataclasses import asdict
import json

from .models import VerifiedFinding
from .prompt_generator import generate_all_prompts


def format_review_output(findings: list[VerifiedFinding], format_type: str) -> str:
    if format_type == "json":
        return json.dumps([asdict(finding) for finding in findings], indent=2)
    if format_type == "markdown":
        lines = ["# Review Findings\n"]
        for finding in findings:
            sev_badge = f"**[{finding.severity.upper()}]**"
            lines.append(f"### {sev_badge} `{finding.file_path}:{finding.start_line}`")
            lines.append(f"**Rule**: `{finding.rule_name}`")
            desc = finding.enriched_description or finding.description
            lines.append(f"{desc}")
            lines.append(f"> **Action**: {finding.instruction}\n")
        return "\n".join(lines)

    return generate_all_prompts(findings)
