"""
Agent orchestrator — routes natural language queries to the LLM.

This is the core of the coding assistant experience. When the user types
a question in the TUI, it comes here. The orchestrator:

  1. Builds context from the indexed codebase (relevant files, symbols, metrics)
  2. Constructs a system prompt explaining Nala's capabilities and the project
  3. Sends the conversation to the configured LLM provider
  4. Streams the response back to the caller (the TUI)

The context window is managed carefully. Large codebases can have millions
of tokens of source code — we select the most relevant context rather than
dumping everything in.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, AsyncIterator, Optional

if TYPE_CHECKING:
    from nala_orchestrator.config import Config

from ..llm.provider import LLMMessage, create_provider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are Nala, a terminal-first AI coding assistant with deep understanding
of the project you are analysing.

Project: {project_name}
Location: {project_root}
Files indexed: {total_files}
Symbols found: {total_symbols}
Primary language: {primary_language}

Your role is to:
- Answer questions about the codebase concisely and accurately
- Suggest specific improvements with file:line references
- Generate actionable refactoring suggestions
- Explain complex code in plain English
- Identify risks, bugs, and architectural issues

When referencing code, always include file paths and line numbers.
Keep responses focused and actionable. The developer is experienced — skip basics.
"""


@dataclass
class ConversationContext:
    """Tracks the conversation history for one session."""

    messages: list[LLMMessage] = field(default_factory=list)
    project_root: str = ""
    total_files: int = 0
    total_symbols: int = 0
    primary_language: str = "unknown"

    def add_user(self, text: str) -> None:
        self.messages.append(LLMMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(LLMMessage(role="assistant", content=text))

    def trim_to_limit(self, max_messages: int = 20) -> None:
        """Keep only the most recent messages to avoid context overflow."""
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]


class AgentOrchestrator:
    """Routes user queries to the LLM with codebase context."""

    def __init__(self, config: "Config") -> None:
        self.config = config
        self.context = ConversationContext(
            project_root=str(config.project_root),
        )
        self._provider = None

    def _get_provider(self):
        if self._provider is None:
            self._provider = create_provider(self.config)
        return self._provider

    def build_system_prompt(self) -> str:
        """Build the system prompt with current project context."""
        return SYSTEM_PROMPT_TEMPLATE.format(
            project_name=Path(self.context.project_root).name,
            project_root=self.context.project_root,
            total_files=self.context.total_files,
            total_symbols=self.context.total_symbols,
            primary_language=self.context.primary_language,
        )

    def update_index_context(self, total_files: int, total_symbols: int) -> None:
        """Update the context with fresh index data."""
        self.context.total_files = total_files
        self.context.total_symbols = total_symbols

    async def query(self, user_message: str) -> str:
        """Send a query and return the complete response."""
        if not self.config.has_llm():
            return (
                "No LLM provider configured. "
                "Add ANTHROPIC_API_KEY (or OPENAI_API_KEY, GOOGLE_API_KEY) to your .env file."
            )

        self.context.add_user(user_message)
        self.context.trim_to_limit()

        try:
            provider = self._get_provider()
            response = await provider.chat(
                messages=self.context.messages,
                system_prompt=self.build_system_prompt(),
            )
            self.context.add_assistant(response.content)
            return response.content
        except Exception as e:
            logger.error("LLM query failed: %s", e)
            return f"Error: {e}"

    async def stream_query(self, user_message: str) -> AsyncIterator[str]:
        """Stream a response token by token."""
        if not self.config.has_llm():
            yield (
                "No LLM provider configured. "
                "Add your API key to .env and restart Nala.\n"
                "Supported: ANTHROPIC_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY\n"
                "Example .env:\n  LLM_PROVIDER=anthropic\n  ANTHROPIC_API_KEY=sk-ant-..."
            )
            return

        self.context.add_user(user_message)
        self.context.trim_to_limit()

        full_response = []
        try:
            provider = self._get_provider()
            async for chunk in provider.stream_chat(
                messages=self.context.messages,
                system_prompt=self.build_system_prompt(),
            ):
                full_response.append(chunk)
                yield chunk
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            yield f"\n\nError: {e}"

        if full_response:
            self.context.add_assistant("".join(full_response))
