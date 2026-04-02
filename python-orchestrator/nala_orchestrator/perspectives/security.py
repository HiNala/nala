"""
Security perspective.

Pattern-based scanning for common vulnerability classes in Python, Rust,
JavaScript, and TypeScript. Does NOT require Neo4j.

Patterns are conservative — we only flag things that are nearly always wrong
or that require a code comment to justify. The goal is zero false positives on
clean codebases, not comprehensive SAST coverage.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from ..sessions.report import Finding
from .base import BasePerspective, PerspectiveResult

if TYPE_CHECKING:
    pass

# ── Pattern definitions ────────────────────────────────────────────────────

@dataclass
class Pattern:
    regex: str
    title: str
    description: str
    severity: str
    suggestion: str
    languages: frozenset[str]  # empty = all languages


# Language sets
_PY   = frozenset({"py"})
_JS   = frozenset({"js", "ts", "jsx", "tsx"})
_RS   = frozenset({"rs"})
_ALL  = frozenset()

PATTERNS: list[Pattern] = [
    # ── Python ────────────────────────────────────────────────────────────
    Pattern(
        regex=r"\beval\s*\(",
        title="Use of eval()",
        description=(
            "`eval()` executes arbitrary Python code. If the input comes from any "
            "external source (user, file, network) this is a remote code execution vulnerability."
        ),
        severity="critical",
        suggestion=(
            "Parse structured data with json.loads(), ast.literal_eval(), "
            "or a proper parser instead."
        ),
        languages=_PY,
    ),
    Pattern(
        regex=r"\bexec\s*\(",
        title="Use of exec()",
        description=(
            "`exec()` executes arbitrary Python code. Same risk as eval()."
        ),
        severity="critical",
        suggestion=(
            "Replace with a structured approach: importlib for dynamic imports, "
            "subprocess for shell commands."
        ),
        languages=_PY,
    ),
    Pattern(
        regex=r"\bpickle\.(loads?|load)\s*\(",
        title="Unsafe pickle deserialisation",
        description=(
            "`pickle.load/loads` can execute arbitrary code during deserialisation. "
            "Never unpickle data from untrusted sources."
        ),
        severity="critical",
        suggestion="Use json, msgpack, or protobuf for data serialisation instead.",
        languages=_PY,
    ),
    Pattern(
        regex=r"subprocess\..*shell\s*=\s*True",
        title="subprocess with shell=True",
        description=(
            "Running a subprocess with `shell=True` passes the command through the shell, "
            "enabling shell injection if any part of the command string is user-controlled."
        ),
        severity="high",
        suggestion="Pass a list of arguments instead: subprocess.run(['cmd', arg1, arg2]).",
        languages=_PY,
    ),
    Pattern(
        regex=r"hashlib\.(md5|sha1)\s*\(",
        title="Weak cryptographic hash",
        description=(
            "MD5 and SHA-1 are cryptographically broken. Do not use them for "
            "security-sensitive purposes (passwords, signatures, integrity checks)."
        ),
        severity="high",
        suggestion="Use hashlib.sha256() or hashlib.sha3_256() instead.",
        languages=_PY,
    ),
    Pattern(
        regex=r"(password|secret|api_key|token|passwd)\s*=\s*[\"'][^\"']{6,}[\"']",
        title="Possible hardcoded secret",
        description=(
            "A string that looks like a hardcoded password, secret, or API key was found. "
            "Hardcoded secrets are exposed in source control and in compiled binaries."
        ),
        severity="critical",
        suggestion="Use environment variables or a secrets manager. Never commit credentials.",
        languages=_ALL,
    ),
    Pattern(
        regex=r"os\.system\s*\(",
        title="os.system() call",
        description=(
            "`os.system()` passes its argument directly to the shell. Shell injection is "
            "possible if any part of the command is user-controlled."
        ),
        severity="high",
        suggestion="Use subprocess.run([...], check=True) with a list of arguments.",
        languages=_PY,
    ),
    Pattern(
        regex=r"yaml\.load\s*\([^)]*\)",
        title="Unsafe YAML load",
        description=(
            "`yaml.load()` without a Loader argument can deserialise Python objects, "
            "leading to arbitrary code execution."
        ),
        severity="high",
        suggestion="Use yaml.safe_load() instead.",
        languages=_PY,
    ),
    Pattern(
        regex=r"\.format\s*\(.*request\.",
        title="Possible SQL/template injection via .format()",
        description=(
            "Building a string with `.format()` using request data is a common injection vector. "
            "If this string is passed to a database or template engine, injection is possible."
        ),
        severity="medium",
        suggestion="Use parameterised queries for SQL; use template auto-escaping for HTML.",
        languages=_PY,
    ),

    # ── JavaScript / TypeScript ───────────────────────────────────────────
    Pattern(
        regex=r"\.innerHTML\s*=",
        title="Direct innerHTML assignment",
        description=(
            "Assigning to `innerHTML` with untrusted content creates XSS vulnerabilities. "
            "The browser will parse and execute any `<script>` tags in the assigned string."
        ),
        severity="high",
        suggestion="Use textContent for plain text, or DOMPurify.sanitize() before assigning HTML.",
        languages=_JS,
    ),
    Pattern(
        regex=r"document\.write\s*\(",
        title="Use of document.write()",
        description=(
            "`document.write()` with user-controlled input is an XSS vector. "
            "It also blocks the HTML parser."
        ),
        severity="high",
        suggestion="Use DOM manipulation methods (createElement, appendChild) instead.",
        languages=_JS,
    ),
    Pattern(
        regex=r"\beval\s*\(",
        title="Use of eval()",
        description=(
            "`eval()` executes arbitrary JavaScript. If the input comes from any external "
            "source this is a code injection vulnerability."
        ),
        severity="critical",
        suggestion=(
            "JSON.parse() for JSON data; no legitimate use case for eval() "
            "in application code."
        ),
        languages=_JS,
    ),
    Pattern(
        regex=r"new\s+Function\s*\(",
        title="Dynamic Function construction",
        description=(
            "`new Function(...)` is equivalent to eval() and has the same injection risks."
        ),
        severity="critical",
        suggestion="Remove dynamic code generation; use callbacks and closures instead.",
        languages=_JS,
    ),

    # ── Rust ─────────────────────────────────────────────────────────────
    Pattern(
        regex=r"\bunsafe\s*\{",
        title="Unsafe block",
        description=(
            "Unsafe blocks bypass Rust's memory safety guarantees. They are sometimes "
            "necessary but must be carefully reviewed for undefined behaviour."
        ),
        severity="medium",
        suggestion="Document why unsafe is required. Prefer safe abstractions where possible.",
        languages=_RS,
    ),
    Pattern(
        regex=r"std::mem::transmute",
        title="mem::transmute",
        description=(
            "`std::mem::transmute` reinterprets the bits of a value as a different type. "
            "This is extremely unsafe and almost always has a safer alternative."
        ),
        severity="high",
        suggestion="Use From/Into traits, bytemuck::cast, or safe reinterpretation helpers.",
        languages=_RS,
    ),
    Pattern(
        regex=r"\.unwrap\(\)",
        title="Unchecked unwrap()",
        description=(
            "`.unwrap()` panics if the value is None or Err, crashing the process. "
            "In a production binary this is poor error handling."
        ),
        severity="low",
        suggestion=(
            'Use .expect("context") for developer clarity, or ? / match for '
            "proper error propagation."
        ),
        languages=_RS,
    ),
]

# Extension → language tag mapping
EXT_LANG: dict[str, str] = {
    "py": "py", "pyw": "py",
    "js": "js", "jsx": "js", "mjs": "js",
    "ts": "ts", "tsx": "tsx",
    "rs": "rs",
}


class SecurityPerspective(BasePerspective):
    """Pattern-based security scanning across Python, JS/TS, and Rust source."""

    @property
    def name(self) -> str:
        return "security"

    @property
    def description(self) -> str:
        return "Flags dangerous patterns: eval, shell injection, hardcoded secrets, XSS vectors"

    async def analyze(self, project_root: str) -> PerspectiveResult:
        start = time.monotonic()
        findings: list[Finding] = []
        root = Path(project_root)

        # Collect source files
        source_files = _collect_source_files(root)

        for file_path, lang in source_files:
            try:
                source = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = str(file_path.relative_to(root))
            findings.extend(_scan_file(source, rel, lang))

        duration_ms = int((time.monotonic() - start) * 1000)
        critical = sum(1 for f in findings if f.severity == "critical")
        high = sum(1 for f in findings if f.severity == "high")

        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=(
                f"Security scan: {len(findings)} findings "
                f"({critical} critical, {high} high) across {len(source_files)} files."
            ),
            duration_ms=duration_ms,
        )


# ── Helpers ────────────────────────────────────────────────────────────────

def _collect_source_files(root: Path) -> list[tuple[Path, str]]:
    """Return (path, lang_tag) for all scannable source files."""
    skip_dirs = {
        "node_modules", "target", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".nala", ".mypy_cache", ".pytest_cache",
    }
    results = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(p in skip_dirs for p in path.parts):
            continue
        ext = path.suffix.lstrip(".")
        lang = EXT_LANG.get(ext)
        if lang:
            results.append((path, lang))
    return results


def _scan_file(source: str, rel_path: str, lang: str) -> list[Finding]:
    """Scan one file's source for all matching patterns."""
    findings = []
    lines = source.splitlines()
    for pattern in PATTERNS:
        # Skip patterns not applicable to this language
        if pattern.languages and lang not in pattern.languages:
            continue
        regex = re.compile(pattern.regex, re.IGNORECASE)
        for lineno, line in enumerate(lines, 1):
            if regex.search(line):
                findings.append(Finding(
                    title=pattern.title,
                    description=pattern.description,
                    file_path=rel_path,
                    start_line=lineno,
                    severity=pattern.severity,
                    perspective="security",
                    suggestion=pattern.suggestion,
                    code_snippet=line.strip()[:200],
                ))
    return findings
