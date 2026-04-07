from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReviewRequest:
    mode: str                # "file" | "glob" | "full" | "diff"
    targets: list[str]       # File paths or glob patterns
    perspectives: list[str]  # Which review lenses to apply (default: all)
    severity_threshold: str  # Minimum severity to report (default: "low")
    output_format: str       # "prompts" | "markdown" | "json" | "clipboard"


@dataclass
class RawFinding:
    rule_name: str
    category: str
    severity: str            # "critical" | "high" | "medium" | "low" | "info"
    file_path: str
    start_line: int
    end_line: int
    description: str         # Plain english explanation of problem
    instruction: str         # Instruction to give to an AI agent
    identifiers: list[str]   # Variables, functions, components involved
    context: dict[str, object] = field(default_factory=dict)


@dataclass
class VerifiedFinding(RawFinding):
    evidence: str = ""       # Why the verification succeeded
    enriched_description: str | None = None
    confidence: float = 1.0


@dataclass
class ReviewResult:
    target: str
    findings: list[VerifiedFinding]
    files_scanned: int
    rules_run: int
    disproven_count: int
