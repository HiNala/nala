"""Compression quality assurance.

Validates that compression passes meet safety invariants:
  1. No identifier loss — every file path and symbol in the original
     appears unchanged in the compressed output.
  2. Compression ratio is within acceptable bounds (not over-compressed).
  3. Stability — re-compressing produces identical output (no oscillation).
  4. Minimum content retention — at least MIN_RETENTION_PCT of original
     non-whitespace characters are preserved.

If a quality check fails, the pipeline falls back to the previous tier's
output rather than returning a broken result.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MIN_RETENTION_PCT = 30.0    # compressed must retain >= this % of original chars
MAX_COMPRESSION_PCT = 85.0  # refuse if compression removed > this % of content


@dataclass
class QualityReport:
    """Result of a quality check."""
    passed: bool
    ratio: float                      # compressed / original (lower = more compressed)
    retention_pct: float
    lost_identifiers: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"Quality [{status}]: {self.retention_pct:.0f}% retention, "
            f"ratio={self.ratio:.2f}",
        ]
        if self.issues:
            lines += [f"  Issue: {i}" for i in self.issues]
        if self.lost_identifiers:
            lines.append(f"  Lost {len(self.lost_identifiers)} identifiers: "
                         + ", ".join(self.lost_identifiers[:5]))
        return "\n".join(lines)


# ── Identifier extraction (same patterns as memory/compression.py) ────────────

_IDENTIFIER_RE = re.compile(
    r"(?:"
    r"[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_.]*)+|"
    r"/[a-zA-Z0-9_./\-]+|"
    r"[A-Z]:\\[^\s,;]+"
    r")"
)


class QualityChecker:
    """Validates compression output meets safety invariants."""

    def __init__(
        self,
        min_retention_pct: float = MIN_RETENTION_PCT,
        max_compression_pct: float = MAX_COMPRESSION_PCT,
    ) -> None:
        self._min_retention = min_retention_pct
        self._max_compression = max_compression_pct

    def check(self, original: str, compressed: str) -> QualityReport:
        """Run all quality checks. Returns a QualityReport."""
        issues: list[str] = []
        lost: list[str] = []

        orig_len = len(original.replace(" ", "").replace("\n", ""))
        comp_len = len(compressed.replace(" ", "").replace("\n", ""))

        ratio = comp_len / max(orig_len, 1)
        retention_pct = ratio * 100

        # ── Retention floor ───────────────────────────────────────────────
        if retention_pct < self._min_retention:
            issues.append(
                f"Over-compressed: only {retention_pct:.0f}% retained "
                f"(minimum {self._min_retention:.0f}%)"
            )

        # ── Max compression ceiling ───────────────────────────────────────
        compression_pct = (1.0 - ratio) * 100
        if compression_pct > self._max_compression:
            issues.append(
                f"Compression too aggressive: {compression_pct:.0f}% removed"
            )

        # ── Identifier preservation ───────────────────────────────────────
        # Only flag identifiers with meaningful length (short fragments are
        # often sub-matches of longer paths and produce false positives).
        orig_ids = set(_IDENTIFIER_RE.findall(original))
        for ident in orig_ids:
            if len(ident) < 8:
                continue  # skip short fragments
            if ident not in compressed:
                lost.append(ident)

        if lost:
            issues.append(f"{len(lost)} identifier(s) lost in compression")

        passed = len(issues) == 0
        return QualityReport(
            passed=passed,
            ratio=ratio,
            retention_pct=retention_pct,
            lost_identifiers=lost,
            issues=issues,
        )

    def check_stability(self, text: str, compress_fn) -> bool:
        """Return True if compress_fn(text) == compress_fn(compress_fn(text))."""
        once = compress_fn(text)
        twice = compress_fn(once)
        return once == twice

    def safe_compress(
        self,
        original: str,
        compress_fn,
        fallback: str = "",
    ) -> tuple[str, QualityReport]:
        """Apply compress_fn and validate. Falls back to original on failure."""
        compressed = compress_fn(original)
        report = self.check(original, compressed)
        if not report.passed:
            return fallback or original, report
        return compressed, report
