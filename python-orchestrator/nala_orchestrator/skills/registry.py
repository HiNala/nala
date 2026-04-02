"""Skill registry — discover, load, and invoke skills."""

from __future__ import annotations

import logging
from pathlib import Path

from .models import Skill

log = logging.getLogger("nala.skills.registry")

BUILTIN_SKILLS: list[Skill] = [
    Skill(
        name="triage-hotspots",
        description="Identify the top code hotspots that need attention.",
        when_to_use="At project start or when prioritising refactoring work.",
        tools=["codebase_index", "git_log", "llm_query"],
        output_contract="Ranked list of hotspots with severity and suggested action.",
        prompt_template=(
            "Analyze the codebase and identify the top 5 hotspots that would "
            "benefit most from improvement. Consider: complexity, code churn, "
            "error-prone patterns, and architectural risks. For each hotspot, "
            "suggest a specific actionable improvement."
        ),
    ),
    Skill(
        name="review-current-diff",
        description="Review the current git diff for issues.",
        when_to_use="Before committing changes or during a review gate.",
        tools=["git_diff", "llm_query"],
        output_contract="Summary of changes with potential issues flagged.",
        prompt_template=(
            "Review the following git diff and identify:\n"
            "1. Potential bugs or regressions\n"
            "2. Style or convention violations\n"
            "3. Missing tests or documentation\n"
            "4. Security concerns\n\n"
            "Diff:\n{diff}"
        ),
    ),
    Skill(
        name="refactor-safely",
        description="Propose a safe refactoring plan for a given target.",
        when_to_use="When code quality needs improvement without behavior change.",
        tools=["codebase_index", "llm_query", "git_status"],
        output_contract="Step-by-step refactoring plan with risk assessment.",
        prompt_template=(
            "Create a safe refactoring plan for: {target}\n"
            "Requirements:\n"
            "- No behavior changes\n"
            "- Each step independently verifiable\n"
            "- Include rollback strategy\n"
            "- List affected files and blast radius"
        ),
    ),
    Skill(
        name="repair-verification-failures",
        description="Diagnose and fix verification failures.",
        when_to_use="After /agent verify reports failures.",
        tools=["shell", "llm_query", "codebase_index"],
        output_contract="Diagnosis + fix patch or escalation.",
        prompt_template=(
            "The following verification commands failed:\n{failures}\n\n"
            "Diagnose the root cause and propose a minimal fix. "
            "If the fix is straightforward, provide the exact changes. "
            "If risky, explain why and suggest manual intervention."
        ),
    ),
    Skill(
        name="prepare-shippable-summary",
        description="Generate a release/PR summary from recent changes.",
        when_to_use="After completing an agent run, before sharing results.",
        tools=["git_diff", "git_log", "llm_query"],
        output_contract="Markdown summary suitable for PR description.",
        prompt_template=(
            "Generate a concise summary of the changes made:\n"
            "- What was the objective?\n"
            "- What files were changed and why?\n"
            "- What verification was run?\n"
            "- Any known risks or follow-ups?\n\n"
            "Format as markdown suitable for a PR description."
        ),
    ),
]


class SkillRegistry:
    """Manages built-in and user-defined skills."""

    def __init__(self, project_root: Path | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in BUILTIN_SKILLS:
            self._skills[skill.name] = skill
        if project_root:
            self._load_user_skills(project_root)

    def _load_user_skills(self, project_root: Path) -> None:
        skills_dir = project_root / ".nala" / "agent" / "skills"
        if not skills_dir.exists():
            return
        for md_file in skills_dir.glob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
                name = md_file.stem
                self._skills[name] = Skill(
                    name=name,
                    description=f"User skill: {name}",
                    when_to_use="User-defined",
                    prompt_template=content,
                )
                log.info("Loaded user skill: %s", name)
            except Exception as e:
                log.warning("Failed to load skill %s: %s", md_file, e)

    def list_skills(self) -> list[str]:
        return sorted(self._skills.keys())

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def resolve(self, name: str, **kwargs: str) -> str | None:
        """Resolve a skill into an expanded prompt."""
        skill = self.get(name)
        if skill is None:
            return None
        return skill.build_prompt(**kwargs)
