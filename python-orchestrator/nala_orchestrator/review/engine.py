from __future__ import annotations

import glob
from pathlib import Path
from typing import TYPE_CHECKING

from .diff import get_changed_files
from .enricher import Enricher
from .learnings import LearningsDB
from .models import RawFinding, ReviewRequest, ReviewResult, VerifiedFinding
from .rules import ALL_RULES
from .verifier import Verifier

if TYPE_CHECKING:
    from nala_orchestrator.graph.connection import GraphConnection
    from nala_orchestrator.llm.provider import LLMProvider


_LANGUAGE_ALIASES = {
    ".py": {"py", "python"},
    ".ts": {"ts", "typescript"},
    ".tsx": {"tsx", "typescript"},
    ".js": {"js", "javascript"},
    ".jsx": {"jsx", "javascript"},
    ".rs": {"rs", "rust"},
    ".go": {"go", "golang"},
}


class ReviewEngine:
    def __init__(
        self,
        root_dir: str,
        provider: LLMProvider | None = None,
        graph: GraphConnection | None = None,
    ):
        self.root_dir = Path(root_dir)
        self.provider = provider
        self.graph = graph
        self.verifier = Verifier(str(self.root_dir), self.graph)
        self.enricher = Enricher(self.provider)
        self.learnings = LearningsDB(self.root_dir / ".nala")

    def _resolve_targets(self, req: ReviewRequest) -> list[str]:
        target_files: set[str] = set()
        if req.mode == "diff":
            target_files.update(get_changed_files(str(self.root_dir)))
        elif req.mode == "full":
            for p in self.root_dir.rglob("*"):
                if p.is_file() and not any(part.startswith(".") for part in p.parts):
                    if p.suffix in _LANGUAGE_ALIASES:
                        target_files.add(str(p))
        else:
            for target in req.targets:
                if "*" in target:
                    matched = glob.glob(str(self.root_dir / target), recursive=True)
                    target_files.update([m for m in matched if Path(m).is_file()])
                else:
                    p = self.root_dir / target
                    if p.is_file():
                        target_files.add(str(p))
        return sorted(target_files)

    @staticmethod
    def _file_languages(file_path: str) -> set[str]:
        return _LANGUAGE_ALIASES.get(Path(file_path).suffix.lower(), set())

    def _selected_rules(self, req: ReviewRequest) -> list:
        if not req.perspectives:
            return list(ALL_RULES)

        selected = {item.lower() for item in req.perspectives}
        return [
            rule for rule in ALL_RULES
            if rule.category.lower() in selected or rule.name.lower() in selected
        ]

    async def run_review(self, req: ReviewRequest) -> ReviewResult:
        targets = self._resolve_targets(req)
        rules = self._selected_rules(req)
        all_raw_findings: list[RawFinding] = []
        files_scanned = 0

        # 1. Execute rules
        for file_path in targets:
            try:
                content = Path(file_path).read_text(encoding="utf-8")
                files_scanned += 1
                file_languages = self._file_languages(file_path)
                for rule in rules:
                    if rule.languages and not file_languages.intersection(rule.languages):
                        continue
                    findings = await rule.check(file_path, content, self.graph)
                    all_raw_findings.extend(findings)
            except Exception:
                continue

        # Filter by severity
        severity_map = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        threshold = severity_map.get(req.severity_threshold.lower(), 1)

        filtered_raw = [
            f for f in all_raw_findings
            if severity_map.get(f.severity.lower(), 1) >= threshold
        ]

        verified_findings: list[VerifiedFinding] = []
        disproven_count = 0

        for raw in filtered_raw:
            # Check false positives learnings DB
            content_snippet = ""
            try:
                lines = Path(raw.file_path).read_text(encoding="utf-8").split("\n")
                if raw.start_line <= len(lines):
                    content_snippet = lines[raw.start_line - 1]
            except Exception:
                pass

            if self.learnings.is_dismissed(raw.rule_name, raw.file_path, content_snippet):
                disproven_count += 1
                continue

            # 2. Verify
            verified = await self.verifier.verify(raw)
            if not verified:
                disproven_count += 1
                continue

            # 3. Enrich
            file_content = ""
            try:
                file_content = Path(raw.file_path).read_text(encoding="utf-8")
            except Exception:
                pass
            enriched = await self.enricher.enrich(verified, file_content)
            
            # Make file path relative to root to make prompts cleaner
            try:
                enriched.file_path = str(Path(enriched.file_path).relative_to(self.root_dir))
            except ValueError:
                pass

            verified_findings.append(enriched)

        return ReviewResult(
            target=",".join(req.targets) if req.targets else req.mode,
            findings=verified_findings,
            files_scanned=files_scanned,
            rules_run=len(rules),
            disproven_count=disproven_count,
        )
