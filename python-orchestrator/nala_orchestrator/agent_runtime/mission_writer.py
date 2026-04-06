"""Generate structured mission .md files from an LLM-produced plan.

The MissionWriter takes raw planning output (a structured list of mission
descriptions) and writes individual .md files into the run's mission
directory at ``.nala/agent/missions/<run_id>/``.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from .state import MissionFile, MissionStatus

log = logging.getLogger("nala.agent_runtime.mission_writer")

MISSIONS_ROOT = ".nala/agent/missions"


class MissionWriter:
    """Write and read mission files for an agent run."""

    def __init__(self, project_root: Path, run_id: str) -> None:
        self._root = project_root
        self._run_id = run_id
        self._dir = project_root / MISSIONS_ROOT / run_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._manifest_path = self._dir / "manifest.json"

    @property
    def missions_dir(self) -> Path:
        return self._dir

    def write_missions(self, missions: list[MissionFile]) -> list[Path]:
        """Write all missions to disk as .md files and persist a manifest."""
        paths: list[Path] = []
        for i, mission in enumerate(missions, 1):
            filename = f"MISSION_{i:02d}_{_slugify(mission.title)}.md"
            md_path = self._dir / filename
            md_path.write_text(mission.to_markdown(), encoding="utf-8")
            paths.append(md_path)
        self._write_manifest(missions)
        log.info("Wrote %d mission files to %s", len(missions), self._dir)
        return paths

    def load_missions(self) -> list[MissionFile]:
        """Load missions from the manifest."""
        if not self._manifest_path.exists():
            return []
        try:
            data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            return [_mission_from_dict(m) for m in data]
        except Exception as exc:
            log.warning("Failed to load manifest: %s", exc)
            return []

    def update_mission_status(
        self, mission_id: str, status: MissionStatus, summary: str = ""
    ) -> None:
        """Update a single mission's status in the manifest."""
        missions = self.load_missions()
        for m in missions:
            if m.id == mission_id:
                m.status = status
                if summary:
                    m.result_summary = summary
                break
        self._write_manifest(missions)

    def _write_manifest(self, missions: list[MissionFile]) -> None:
        payload = []
        for m in missions:
            d = asdict(m)
            d["status"] = m.status.value
            payload.append(d)
        self._manifest_path.write_text(
            json.dumps(payload, indent=2), encoding="utf-8"
        )

    # ── Parsing LLM output ────────────────────────────────────────────

    @staticmethod
    def parse_plan_output(raw_text: str) -> list[MissionFile]:
        """Parse structured LLM planning output into MissionFile objects.

        Handles three formats (tried in order):
        1. JSON array, optionally inside a ```json ... ``` code fence
        2. Bare JSON array anywhere in the text
        3. Best-effort markdown mission list parsing
        """
        missions: list[MissionFile] = []

        # Strip markdown code fences first (models often wrap JSON in ```json)
        stripped = raw_text
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw_text)
        if fence_match:
            stripped = fence_match.group(1).strip()

        # Try to find and parse a JSON array in the (possibly stripped) text
        for candidate in (stripped, raw_text):
            json_match = re.search(r"\[[\s\S]*\]", candidate)
            if not json_match:
                continue
            try:
                items = json.loads(json_match.group())
                if isinstance(items, list):
                    parsed = [
                        _mission_from_dict(item, index=i + 1)
                        for i, item in enumerate(items)
                        if isinstance(item, dict)
                    ]
                    if parsed:
                        log.info("Parsed %d missions from JSON", len(parsed))
                        return parsed
            except json.JSONDecodeError:
                pass

        missions = _parse_markdown_missions(raw_text)
        if missions:
            log.info("Parsed %d missions from markdown fallback", len(missions))
        return missions


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", text.lower()).strip("_")
    return slug[:60]


def _mission_from_dict(d: dict, index: int = 0) -> MissionFile:
    mid = d.get("id") or f"mission-{index or 1}"
    return MissionFile(
        id=mid,
        title=d.get("title", f"Mission {index}"),
        objective=d.get("objective", ""),
        task_type=d.get("task_type", "code"),
        model_preference=d.get("model_preference", ""),
        dependencies=d.get("dependencies", []),
        parallel_group=d.get("parallel_group", "sequential"),
        scope=d.get("scope", []),
        steps=d.get("steps", []),
        verification=d.get("verification", ""),
        acceptance_criteria=d.get("acceptance_criteria", []),
        status=MissionStatus(d.get("status", "pending")),
        result_summary=d.get("result_summary", ""),
    )


def _parse_markdown_missions(text: str) -> list[MissionFile]:
    """Best-effort parse when LLM returns markdown instead of JSON."""
    missions: list[MissionFile] = []
    blocks = re.split(r"(?=^#{1,2}\s+Mission[\s:])", text, flags=re.MULTILINE)
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        title_match = re.match(r"^#{1,2}\s+Mission[:\s]*(.+)", block)
        title = title_match.group(1).strip() if title_match else f"Mission {i + 1}"

        obj_match = re.search(
            r"(?:^|\n)#{2,3}\s+Objective\s*\n([\s\S]*?)(?=\n#{2,3}\s|\Z)",
            block,
        )
        objective = obj_match.group(1).strip() if obj_match else ""

        task_match = re.search(
            r"(?:^|\n)#{2,3}\s+Task\s+Type\s*\n\s*(\S+)", block
        )
        task_type = task_match.group(1).strip() if task_match else "code"

        deps_match = re.search(
            r"(?:^|\n)#{2,3}\s+Dependencies\s*\n([\s\S]*?)(?=\n#{2,3}\s|\Z)",
            block,
        )
        deps: list[str] = []
        if deps_match:
            raw_deps = deps_match.group(1).strip()
            if raw_deps.lower() not in ("none", "n/a", "-"):
                deps = [d.strip().lstrip("- ") for d in raw_deps.splitlines() if d.strip()]

        group_match = re.search(
            r"(?:^|\n)#{2,3}\s+Parallel\s+Group\s*\n\s*(\S+)", block
        )
        parallel_group = group_match.group(1).strip() if group_match else "sequential"

        steps_match = re.search(
            r"(?:^|\n)#{2,3}\s+Steps\s*\n([\s\S]*?)(?=\n#{2,3}\s|\Z)",
            block,
        )
        steps: list[str] = []
        if steps_match:
            for line in steps_match.group(1).strip().splitlines():
                cleaned = re.sub(r"^\d+\.\s*", "", line.strip())
                if cleaned:
                    steps.append(cleaned)

        ac_match = re.search(
            r"(?:^|\n)#{2,3}\s+Acceptance\s+Criteria\s*\n([\s\S]*?)(?=\n#{2,3}\s|\Z)",
            block,
        )
        criteria: list[str] = []
        if ac_match:
            for line in ac_match.group(1).strip().splitlines():
                cleaned = re.sub(r"^-\s*\[.\]\s*", "", line.strip())
                if cleaned:
                    criteria.append(cleaned)

        missions.append(
            MissionFile(
                id=f"mission-{i + 1}",
                title=title,
                objective=objective,
                task_type=task_type,
                dependencies=deps,
                parallel_group=parallel_group,
                steps=steps,
                acceptance_criteria=criteria,
            )
        )
    return missions
