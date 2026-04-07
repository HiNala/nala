"""Security review rules.

Detects hardcoded credentials, exposed tokens, clipboard hazards,
and missing input validation at critical boundaries.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..models import RawFinding
from .base import ReviewRule

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection

# Patterns that signal a credential value (high-entropy, long enough to be real)
_SECRET_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{20,})["\']'),
        "API key",
    ),
    (
        re.compile(r'(?i)(secret[_-]?key|secret)\s*[:=]\s*["\']([a-zA-Z0-9_\-]{16,})["\']'),
        "secret key",
    ),
    (
        re.compile(r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']([^"\']{6,})["\']'),
        "password",
    ),
    (
        re.compile(
            r'(?i)(token|access[_-]?token|auth[_-]?token)\s*[:=]\s*["\']([a-zA-Z0-9_.\-]{20,})["\']'
        ),
        "auth token",
    ),
    (
        re.compile(r'(?i)(private[_-]?key)\s*[:=]\s*["\']([a-zA-Z0-9+/=]{20,})["\']'),
        "private key",
    ),
    # AWS / GCP / common cloud provider key patterns
    (re.compile(r'\b(AKIA[0-9A-Z]{16})\b'), "AWS access key"),
    (re.compile(r'\b(sk-[a-zA-Z0-9]{32,})\b'), "OpenAI secret key"),
    (re.compile(r'\b(ghp_[a-zA-Z0-9]{36,})\b'), "GitHub PAT"),
]

# Values that look like placeholders — verified.py handles most; we skip early
_PLACEHOLDER_RE = re.compile(
    r'(?i)(your[_-][a-z\-]+|xxx+|placeholder|changeme|example|test-key|fake|dummy|mock)',
)

# Comment prefixes — if the whole line is a comment, skip
_COMMENT_RE = re.compile(r'^\s*(#|//|\*|/\*)')


class HardcodedSecretRule(ReviewRule):
    name = "hardcoded-secret"
    category = "security"
    severity = "critical"
    languages = ["python", "typescript", "tsx", "rust", "javascript", "jsx", "go"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()
        seen: set[int] = set()  # deduplicate multi-pattern hits on same line

        for i, line in enumerate(lines, 1):
            if i in seen:
                continue
            if _COMMENT_RE.match(line):
                continue  # Comment lines handled by verifier; skip pre-scan

            for pattern, secret_type in _SECRET_PATTERNS:
                m = pattern.search(line)
                if not m:
                    continue
                # Skip obvious placeholders
                if _PLACEHOLDER_RE.search(line):
                    continue
                seen.add(i)
                ident = secret_type
                if "=" in m.group(0):
                    ident = m.group(0).split("=")[0].strip().strip('"\'')
                findings.append(
                    RawFinding(
                        rule_name=self.name,
                        category=self.category,
                        severity=self.severity,
                        file_path=file_path,
                        start_line=i,
                        end_line=i,
                        description=f"Potential hardcoded {secret_type} detected on line {i}.",
                        instruction=(
                            f"Replace the hardcoded {secret_type} with an environment "
                            f"variable. Use `os.getenv('{ident.upper()}')` in Python or "
                            f"`process.env.{ident.upper().replace('-', '_')}` in TypeScript."
                        ),
                        identifiers=[ident],
                    )
                )
                break  # One finding per line

        return findings


class ClipboardWithoutWarningRule(ReviewRule):
    """Flags clipboard write operations that have no user-visible confirmation."""

    name = "clipboard-no-warning"
    category = "security"
    severity = "medium"
    languages = ["typescript", "tsx", "javascript", "jsx"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        if "writeText" not in file_content and "clipboard" not in file_content.lower():
            return findings

        lines = file_content.splitlines()
        for i, line in enumerate(lines, 1):
            if re.search(r"clipboard\.writeText|navigator\.clipboard", line, re.IGNORECASE):
                # Look for a toast/alert/confirm in the surrounding 5 lines
                window = "\n".join(lines[max(0, i - 3):i + 3])
                if not re.search(r"toast|alert|confirm|notify|snackbar", window, re.IGNORECASE):
                    findings.append(
                        RawFinding(
                            rule_name=self.name,
                            category=self.category,
                            severity=self.severity,
                            file_path=file_path,
                            start_line=i,
                            end_line=i,
                            description=(
                                "Clipboard write with no visible user confirmation "
                                "(no toast/alert nearby)."
                            ),
                            instruction=(
                                "Add a toast notification after the clipboard.writeText "
                                "call so users know their data was copied and what was "
                                "placed in the clipboard."
                            ),
                            identifiers=["clipboard.writeText"],
                        )
                    )
        return findings


class MissingInputValidationRule(ReviewRule):
    """Detects user inputs (query params, form fields) used without validation."""

    name = "missing-input-validation"
    category = "security"
    severity = "high"
    languages = ["typescript", "tsx", "javascript", "jsx", "python"]

    async def check(
        self,
        file_path: str,
        file_content: str,
        graph: GraphConnection | None,
    ) -> list[RawFinding]:
        del graph
        findings: list[RawFinding] = []
        lines = file_content.splitlines()
        for i, line in enumerate(lines, 1):
            # Detect direct use of router params / form values without validation
            if re.search(r'req\.params\.|req\.query\.|request\.args\.get\(', line):
                # Check the next 3 lines for any validation (typeof, parseInt, schema, zod, etc.)
                window = "\n".join(lines[i:min(len(lines), i + 3)])
                if not re.search(
                    r"parseInt|parseFloat|Number\(|zod|schema|validate|typeof|isNaN",
                    window,
                ):
                    findings.append(
                        RawFinding(
                            rule_name=self.name,
                            category=self.category,
                            severity=self.severity,
                            file_path=file_path,
                            start_line=i,
                            end_line=i,
                            description=(
                                "User-controlled input used without visible type "
                                "validation or schema check."
                            ),
                            instruction=(
                                "Validate and sanitize the input before use. Use "
                                "parseInt/Number() for numeric params or a Zod/"
                                "Pydantic schema for objects."
                            ),
                            identifiers=re.findall(
                                r"req\.\w+\.\w+|args\.get\(['\"]?\w+",
                                line,
                            ),
                        )
                    )
        return findings


security_rules = [
    HardcodedSecretRule(),
    ClipboardWithoutWarningRule(),
    MissingInputValidationRule(),
]
