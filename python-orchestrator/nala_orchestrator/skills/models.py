"""Skill model definitions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Skill:
    """A reusable agent workflow recipe."""
    name: str
    description: str
    when_to_use: str
    tools: list[str] = field(default_factory=list)
    output_contract: str = ""
    prompt_template: str = ""

    def build_prompt(self, **kwargs: str) -> str:
        """Expand the template with keyword arguments."""
        prompt = self.prompt_template
        for key, value in kwargs.items():
            prompt = prompt.replace(f"{{{key}}}", value)
        return prompt
