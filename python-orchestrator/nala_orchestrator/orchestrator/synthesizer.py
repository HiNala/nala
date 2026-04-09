"""Mission 32: Result synthesizer — merges output from multiple agent waves.

Deduplicates overlapping findings, resolves file-level conflicts, and
produces a user-facing summary ready to post to the interpreter shell.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# ── Data classes ──────────────────────────────────────────────────────────

@dataclass
class AgentResult:
    agent_id: str
    specialist_type: str
    success: bool
    summary: str
    findings: list[dict] = field(default_factory=list)    # raw finding dicts
    files_touched: list[str] = field(default_factory=list)
    partial: bool = False    # True if agent failed mid-way


@dataclass
class WaveSummary:
    wave_number: int
    description: str
    total_agents: int
    successful: int
    failed: int
    findings_by_severity: dict[str, int] = field(default_factory=dict)
    files_touched: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class Synthesis:
    """Unified summary of all wave results."""
    objective: str
    wave_summaries: list[WaveSummary]
    total_findings: int
    critical_count: int
    high_count: int
    conflicts: list[str]          # Files where agents proposed conflicting changes
    recommended_actions: list[str]

    def format_for_display(self) -> str:
        lines: list[str] = []
        for ws in self.wave_summaries:
            sev = ws.findings_by_severity
            lines.append(f"Wave {ws.wave_number} ({ws.description}):")
            if sev:
                counts = ", ".join(f"{k}: {v}" for k, v in sorted(sev.items()))
                lines.append(f"  Findings: {counts}")
            for h in ws.highlights[:3]:
                lines.append(f"  • {h}")
            if ws.failed:
                lines.append(f"  {ws.failed} agent(s) failed")

        lines.append("")
        if self.critical_count or self.high_count:
            lines.append(
                f"Total: {self.total_findings} findings "
                f"({self.critical_count} critical, {self.high_count} high)"
            )
        if self.conflicts:
            lines.append(f"Conflicts in {len(self.conflicts)} file(s) — manual review needed")
        for action in self.recommended_actions[:3]:
            lines.append(f"  → {action}")
        return "\n".join(lines)


# ── Synthesizer ────────────────────────────────────────────────────────────

class ResultSynthesizer:
    """Merges results from multiple agent tasks into a coherent summary."""

    def synthesize(
        self,
        wave_number: int,
        wave_description: str,
        results: list[AgentResult],
    ) -> WaveSummary:
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful

        all_findings: list[dict] = []
        all_files: list[str] = []
        for r in results:
            all_findings.extend(r.findings)
            all_files.extend(r.files_touched)

        deduped = self._deduplicate(all_findings)
        by_severity = self._count_by_severity(deduped)
        highlights = self._extract_highlights(results, deduped)

        return WaveSummary(
            wave_number=wave_number,
            description=wave_description,
            total_agents=len(results),
            successful=successful,
            failed=failed,
            findings_by_severity=by_severity,
            files_touched=list(dict.fromkeys(all_files)),
            highlights=highlights,
        )

    def merge_waves(
        self,
        objective: str,
        summaries: list[WaveSummary],
        all_results: list[AgentResult],
    ) -> Synthesis:
        total_findings = sum(
            sum(s.findings_by_severity.values()) for s in summaries
        )
        critical = sum(s.findings_by_severity.get("critical", 0) for s in summaries)
        high = sum(s.findings_by_severity.get("high", 0) for s in summaries)

        conflicts = self._detect_conflicts(all_results)
        actions = self._recommend_actions(summaries, conflicts)

        return Synthesis(
            objective=objective,
            wave_summaries=summaries,
            total_findings=total_findings,
            critical_count=critical,
            high_count=high,
            conflicts=conflicts,
            recommended_actions=actions,
        )

    def save_wave_results(
        self,
        nala_dir: Path,
        wave_number: int,
        results: list[AgentResult],
    ) -> Path:
        """Persist wave results to disk for cross-wave context injection."""
        out_dir = nala_dir / "orchestrator"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"wave_{wave_number}_results.json"
        data = [
            {
                "agent_id": r.agent_id,
                "specialist_type": r.specialist_type,
                "success": r.success,
                "summary": r.summary,
                "findings": r.findings[:50],  # cap to keep context manageable
                "files_touched": r.files_touched,
            }
            for r in results
        ]
        out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return out_file

    def load_wave_context(self, nala_dir: Path, up_to_wave: int) -> str:
        """Load previous wave results as a context string for the next wave."""
        lines: list[str] = []
        for i in range(1, up_to_wave + 1):
            path = nala_dir / "orchestrator" / f"wave_{i}_results.json"
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                lines.append(f"## Wave {i} Results")
                for agent in data:
                    lines.append(f"- {agent['specialist_type']}: {agent['summary']}")
                    for f_item in agent.get("findings", [])[:5]:
                        sev = f_item.get("severity", "?")
                        msg = f_item.get("description", str(f_item))[:120]
                        lines.append(f"  [{sev}] {msg}")
            except Exception as e:
                log.debug("Failed to load wave %d context: %s", i, e)
        return "\n".join(lines)

    # ── Private ────────────────────────────────────────────────────────────

    def _deduplicate(self, findings: list[dict]) -> list[dict]:
        seen: set[str] = set()
        unique: list[dict] = []
        for f in findings:
            # Key on (file, line, rule) — same finding from multiple agents → keep one
            key = (
                f.get("file_path", ""),
                str(f.get("start_line", "")),
                f.get("rule_name", f.get("type", "")),
            )
            if key not in seen:
                seen.add(key)
                unique.append(f)
        return unique

    def _count_by_severity(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    def _extract_highlights(
        self,
        results: list[AgentResult],
        findings: list[dict],
    ) -> list[str]:
        highlights: list[str] = []
        # Critical findings first
        for f in findings:
            if f.get("severity") == "critical":
                fp = f.get("file_path", "")
                desc = f.get("description", "")[:80]
                highlights.append(f"CRITICAL in {fp}: {desc}")
        # Agent summaries as fallback
        if not highlights:
            for r in results:
                if r.success and r.summary:
                    highlights.append(f"{r.specialist_type}: {r.summary[:80]}")
        return highlights[:5]

    def _detect_conflicts(self, results: list[AgentResult]) -> list[str]:
        """Files where more than one agent proposed changes."""
        file_agents: dict[str, list[str]] = {}
        for r in results:
            for f in r.files_touched:
                file_agents.setdefault(f, []).append(r.agent_id)
        return [f for f, agents in file_agents.items() if len(agents) > 1]

    def _recommend_actions(
        self,
        summaries: list[WaveSummary],
        conflicts: list[str],
    ) -> list[str]:
        actions: list[str] = []
        critical = sum(s.findings_by_severity.get("critical", 0) for s in summaries)
        high = sum(s.findings_by_severity.get("high", 0) for s in summaries)
        if critical:
            actions.append(f"Address {critical} critical finding(s) immediately")
        if high:
            actions.append(f"Review {high} high-severity finding(s)")
        if conflicts:
            actions.append(f"Manually resolve conflicts in {len(conflicts)} file(s)")
        return actions
