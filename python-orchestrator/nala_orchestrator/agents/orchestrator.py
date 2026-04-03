"""
Agent orchestrator — routes natural language queries to the LLM.

This is the core of the coding assistant experience. When the user types
a question in the TUI, it comes here. The orchestrator:

  1. Builds context from the indexed codebase (relevant files, symbols, metrics)
  2. Constructs a system prompt explaining Nala's capabilities and the project
  3. Sends the conversation to the configured LLM provider
  4. Streams the response back to the caller (the TUI)
  5. Logs every turn to the active session (conversation.jsonl)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nala_orchestrator.chunking.embedder import Embedder
    from nala_orchestrator.config import Config
    from nala_orchestrator.graph.context import GraphContextProvider
    from nala_orchestrator.memory.knowledge import KnowledgeBase
    from nala_orchestrator.sessions.manager import SessionManager

from ..context.background_summary import BackgroundSummary
from ..context.compactor import Compactor
from ..context.config import CompactionConfig
from ..context.counter import TokenCounter, TokenUsage
from ..context.detector import OpportunityDetector
from ..llm.provider import LLMMessage, create_provider, create_provider_for
from .action_extractor import extract_actions

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """\
You are **Nala**, an expert AI coding assistant embedded inside a terminal-first
IDE. You have **full indexed access** to the project's source code. Every answer
you give should be grounded in the actual code shown below under "Retrieved
context". Cite specific **file paths, function names, and line numbers** when
referencing code.

## Project overview
- **Name:** {project_name}
- **Root:** {project_root}
- **Files indexed:** {total_files}
- **Symbols extracted:** {total_symbols}
- **Primary language:** {primary_language}

{project_brief}

## What you can do right now
- Answer questions about architecture, data flow, and dependencies using the
  indexed code chunks provided below.
- Explain what any function, class, or module does — cite exact locations.
- Identify bugs, risks, complexity hotspots, dead code, and missing tests.
- Suggest refactoring plans with specific file paths and line numbers.
- When the user uses `/act`, propose concrete file edits with diff-style actions.
- When the user uses `/agent <objective>`, you can read/write/edit files,
  run shell commands, search the codebase, and navigate directories using
  function-calling tools.

## How context works
The "Retrieved context" section below contains the most relevant code chunks
retrieved from the indexed codebase based on the user's current question. Use
this as your primary source of truth. If the retrieved context does not contain
enough information to answer confidently, say so and suggest which files or
commands the user should look at.

## Response style
- **Be specific** — always cite `file_path:line_number` when referencing code.
- **Be concise** — the developer is experienced; skip basic explanations.
- Use markdown: **bold**, `inline code`, ```code blocks```, headings, bullets.
- Structure longer answers with `##` headings.
- When you don't know something, say so rather than guessing.

## Project structure
{file_tree}

## Retrieved context
{retrieved_context}
"""

# Extra instructions appended when the user explicitly requests actions
ACTION_PROMPT_EXTENSION = """
## Structured Action Response

When the user asks you to *make a change*, *fix*, *refactor*, or *create* something,
respond in this exact order:

### Step 1 — Plan (always output this first)
Start your response with a brief plan:
- What files will be changed and why
- What the intended outcome is
- Any risks or side effects to be aware of
- What verification the user should run afterward (tests, lints, etc.)

### Step 2 — Action blocks
After the plan, emit structured action blocks using this exact XML format:

<action type="edit" file="relative/path/to/file.py">
<old>
exact existing text to replace (must be verbatim — the executor does a literal string match)
</old>
<new>
replacement text
</new>
<description>One-sentence summary of what this change does</description>
</action>

<action type="create" file="relative/path/to/new_file.py">
<new>
full content of the new file
</new>
<description>Why this file is being created</description>
</action>

<action type="shell">
<command>pip install bcrypt</command>
<description>Install required dependency</description>
</action>

### Step 3 — Verification summary
End with a "Verify" section listing the exact commands to run
(e.g. `cargo test`, `pytest`, `ruff check`) to confirm the changes work.

Rules for inline actions:
- Only emit actions when the user explicitly asks for a change to be made
- Use exact verbatim text for <old> — never paraphrase or reformat
- Explain your reasoning in the plan BEFORE the action blocks
- One action block per logical change; do not batch unrelated changes
- Never emit a delete action unless the user explicitly asks to remove a file
"""


@dataclass
class ConversationContext:
    """Tracks the conversation history for one session."""

    messages: list[LLMMessage] = field(default_factory=list)
    project_root: str = ""
    total_files: int = 0
    total_symbols: int = 0
    primary_language: str = "unknown"
    _system_injections: list[str] = field(default_factory=list)

    def add_user(self, text: str) -> None:
        self.messages.append(LLMMessage(role="user", content=text))

    def add_assistant(self, text: str) -> None:
        self.messages.append(LLMMessage(role="assistant", content=text))

    def inject_system(self, text: str) -> None:
        """Add extra context that is appended to the system prompt."""
        if text and text.strip():
            self._system_injections.append(text.strip())

    def get_system_injections(self) -> str:
        """Return all injected system context as a single block."""
        return "\n\n".join(self._system_injections)

    def trim_to_limit(self, max_messages: int = 20) -> None:
        """Keep only the most recent messages to avoid context overflow."""
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]


class AgentOrchestrator:
    """Routes user queries to the LLM with codebase context."""

    def __init__(
        self,
        config: Config,
        model_override: tuple[str, str] | None = None,
    ) -> None:
        self.config = config
        self._model_override = model_override
        self.context = ConversationContext(
            project_root=str(config.project_root),
        )
        self._provider = None
        self._session: SessionManager | None = None
        self._embedder: Embedder | None = None
        self._graph_ctx: GraphContextProvider | None = None
        self._knowledge_base: KnowledgeBase | None = None
        self._token_counter = TokenCounter(model=getattr(config, "llm_model", "default"))
        self._compaction_cfg = CompactionConfig()
        self._detector = OpportunityDetector()
        self._compactor = Compactor(keep_recent=self._compaction_cfg.keep_recent_turns)
        self._bg_summary = BackgroundSummary()

    # ── File tree ──────────────────────────────────────────────────────────

    def _build_file_tree(self, max_lines: int = 200) -> str:
        """Build a compact directory tree for the system prompt.

        Root-level files are listed first (README, configs, etc.) so the AI
        always knows about them. Then directories are expanded up to depth 2.
        """
        root = Path(self.context.project_root)
        if not root.is_dir():
            return "(project root not found)"

        skip_dirs = {
            ".git", "node_modules", "__pycache__", ".nala", "target",
            "dist", "build", ".next", ".venv", "venv", ".mypy_cache",
            ".ruff_cache", ".pytest_cache", "egg-info",
        }
        try:
            entries = sorted(root.iterdir(), key=lambda e: e.name.lower())
        except PermissionError:
            return "(permission denied)"

        root_files = [
            e for e in entries
            if e.is_file() and not e.name.startswith(".")
        ]
        root_dirs = [
            e for e in entries
            if e.is_dir() and e.name not in skip_dirs and not e.name.startswith(".")
        ]

        lines: list[str] = []

        # Root-level files first — always visible to the AI
        all_root_items = root_files + root_dirs
        for i, f in enumerate(root_files):
            connector = "└── " if i == len(all_root_items) - 1 else "├── "
            lines.append(f"{connector}{f.name}")

        def _walk(p: Path, prefix: str, depth: int) -> None:
            if len(lines) >= max_lines:
                return
            try:
                children = sorted(p.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
            except PermissionError:
                return
            dirs = [
                e for e in children
                if e.is_dir() and e.name not in skip_dirs and not e.name.startswith(".")
            ]
            files = [
                e for e in children
                if e.is_file() and not e.name.startswith(".")
            ]
            items = dirs + files
            for j, entry in enumerate(items):
                if len(lines) >= max_lines:
                    lines.append(f"{prefix}...")
                    return
                connector = "└── " if j == len(items) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
                if entry.is_dir() and depth < 2:
                    extension = "    " if j == len(items) - 1 else "│   "
                    _walk(entry, prefix + extension, depth + 1)

        # Directories after root files
        for i, d in enumerate(root_dirs):
            is_last = (i == len(root_dirs) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{connector}{d.name}/")
            extension = "    " if is_last else "│   "
            _walk(d, extension, 1)

        return "\n".join(lines) if lines else "(empty project)"

    # ── Project brief ─────────────────────────────────────────────────────

    def _load_project_brief(self) -> str:
        """Load project description from brief + README for AI grounding.

        Priority: project-brief.md (if it has real content) + README.md.
        Both are included when available since they serve different purposes.
        """
        root = Path(self.context.project_root)
        parts: list[str] = []

        # Project brief — only use if it has substantive content
        brief_path = root / ".nala" / "agent" / "project-brief.md"
        if brief_path.exists():
            try:
                text = brief_path.read_text(encoding="utf-8", errors="replace").strip()
                # Skip if it's just the default template (< 400 chars of boilerplate)
                if len(text) > 400 and "Fill in" not in text:
                    parts.append(f"## Project brief\n{text[:3000]}")
            except Exception:
                pass

        # README — always include if present (primary project documentation)
        for name in ("README.md", "readme.md", "README.rst", "README.txt", "README"):
            readme = root / name
            if readme.exists():
                try:
                    text = readme.read_text(encoding="utf-8", errors="replace").strip()
                    if text:
                        parts.append(f"## README ({name})\n{text[:5000]}")
                    break
                except Exception:
                    pass

        return "\n\n".join(parts)

    # ── Retrieval ──────────────────────────────────────────────────────────

    def set_embedder(self, embedder: Embedder) -> None:
        """Attach an Embedder so queries are augmented with retrieved context."""
        self._embedder = embedder

    def set_graph_context(self, graph_ctx: GraphContextProvider) -> None:
        """Attach a GraphContextProvider so queries include structural insights."""
        self._graph_ctx = graph_ctx

    def set_knowledge_base(self, kb: KnowledgeBase) -> None:
        """Attach a KnowledgeBase so queries include persistent project knowledge."""
        self._knowledge_base = kb

    def _retrieve_context(self, query: str) -> str:
        """Retrieve the most relevant code chunks for a query."""
        if self._embedder is None or not self._embedder.is_ready():
            return "(index not yet available — try again after 'Index complete' appears)"
        from ..chunking.assembler import ContextAssembler
        chunks = self._embedder.retrieve(query, top_k=40)
        assembled = ContextAssembler().assemble(chunks, token_budget=32_000)
        if assembled.included_chunks == 0:
            return "(no relevant code found for this query)"
        return (
            f"__{assembled.included_chunks} chunks from {assembled.total_chunks} "
            f"candidates (~{assembled.token_estimate} tokens)__\n\n"
            + assembled.text
        )

    # ── Session management ─────────────────────────────────────────────────

    def set_session(self, session_manager: SessionManager) -> None:
        """Attach a SessionManager so turns are logged to disk."""
        self._session = session_manager

    def ensure_session(self) -> SessionManager:
        """Return the current session, creating a new one if needed."""
        if self._session is None:
            from nala_orchestrator.sessions.manager import SessionManager
            sm = SessionManager(Path(self.context.project_root))
            sm.new_session()
            self._session = sm
        return self._session

    def restore_history(self, session_manager: SessionManager) -> None:
        """
        Reload conversation history from a saved session into in-memory context.
        Called when resuming a past session.
        """
        self._session = session_manager
        for turn in session_manager.get_conversation_history():
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                self.context.messages.append(LLMMessage(role="user", content=content))
            elif role == "assistant":
                self.context.messages.append(LLMMessage(role="assistant", content=content))
        # Keep the last 20 turns to avoid context overflow
        self.context.trim_to_limit(max_messages=20)

    # ── LLM interface ──────────────────────────────────────────────────────

    def _get_provider(self):
        if self._provider is None:
            if self._model_override:
                prov_name, model_id = self._model_override
                self._provider = create_provider_for(prov_name, model_id, self.config)
            else:
                self._provider = create_provider(self.config)
        return self._provider

    def build_system_prompt(self, query: str = "") -> str:
        """Build the system prompt with current project context and retrieved chunks."""
        retrieved = self._retrieve_context(query) if query else "(no query provided)"
        file_tree = self._build_file_tree()
        project_brief = self._load_project_brief()
        base = SYSTEM_PROMPT_TEMPLATE.format(
            project_name=Path(self.context.project_root).name,
            project_root=self.context.project_root,
            total_files=self.context.total_files,
            total_symbols=self.context.total_symbols,
            primary_language=self.context.primary_language,
            project_brief=project_brief,
            file_tree=file_tree,
            retrieved_context=retrieved,
        )
        injections = self.context.get_system_injections()
        if injections:
            base = base + "\n\n" + injections

        # Graph context: structural insights from Neo4j (dependencies, call graph)
        if self._graph_ctx and self._graph_ctx.is_available() and query:
            try:
                graph_block = self._graph_ctx.context_for_query(query, max_chars=3000)
                if graph_block:
                    base = base + "\n\n" + graph_block
            except Exception as exc:
                logger.debug("Graph context injection failed: %s", exc)

        # Knowledge base: persistent project facts (refreshed per query)
        if self._knowledge_base and query:
            try:
                kb_block = self._knowledge_base.load_for_context(query, max_chars=2000)
                if kb_block:
                    base = base + "\n\n[PROJECT KNOWLEDGE]\n" + kb_block + "\n[END KNOWLEDGE]"
            except Exception as exc:
                logger.debug("Knowledge base injection failed: %s", exc)

        summary = self._bg_summary.get_summary_text()
        if summary and summary != "(no session summary yet)":
            base = base + "\n\n" + summary
        from ..repo_detect import commands_summary
        cmds = commands_summary(Path(self.context.project_root))
        if cmds:
            base = base + "\n\n" + cmds
        return base

    # ── Context window management ──────────────────────────────────────────

    def get_context_usage(self) -> TokenUsage:
        """Return the current token usage breakdown."""
        system = self.build_system_prompt()
        history = [{"role": m.role, "content": m.content} for m in self.context.messages]
        return self._token_counter.measure_conversation(
            system_prompt=system,
            history=history,
        )

    def get_context_breakdown_text(self) -> str:
        """Return a formatted context breakdown for display."""
        usage = self.get_context_usage()
        return self._token_counter.format_breakdown(usage)

    def compact_now(self, focus: str = "") -> str:
        """Compact the conversation history and return a summary message."""
        msgs = self.context.messages
        history = [{"role": m.role, "content": m.content} for m in msgs]

        new_history, result = self._compactor.compact(
            history,
            token_estimate_fn=lambda t: self._token_counter.count(t),
        )

        # Rebuild message list from compacted history.
        self.context.messages = [
            LLMMessage(role=m["role"], content=m["content"])
            for m in new_history
        ]

        # Force a fresh background summary from the new (shorter) history.
        self._bg_summary.force_rebuild(new_history)

        return result.summary

    def _maybe_compact(self, query: str) -> None:
        """Auto-compact if the detector says it is time."""
        usage = self.get_context_usage()
        should = self._detector.should_compact_now(
            utilization_pct=usage.utilization_pct,
            history_len=len(self.context.messages),
            min_turns=self._compaction_cfg.min_turns_before_compact,
        )
        if should:
            logger.info(
                "Auto-compacting context at %.1f%% utilization",
                usage.utilization_pct,
            )
            self.compact_now()

    def update_index_context(
        self,
        total_files: int,
        total_symbols: int,
        primary_language: str = "",
    ) -> None:
        """Update the context with fresh index data."""
        self.context.total_files = total_files
        self.context.total_symbols = total_symbols
        if primary_language:
            self.context.primary_language = primary_language
        if self._session:
            self._session.update_meta(
                total_files=total_files,
                total_symbols=total_symbols,
            )

    async def query(self, user_message: str) -> str:
        """Send a query and return the complete response."""
        if not self.config.has_llm():
            return (
                "No LLM provider configured. "
                "Add ANTHROPIC_API_KEY (or OPENAI_API_KEY, GOOGLE_API_KEY) to your .env file."
            )

        session = self.ensure_session()
        self._detector.mark_user_message()
        self._maybe_compact(user_message)
        self.context.add_user(user_message)
        self.context.trim_to_limit()
        session.append_turn("user", user_message)

        try:
            provider = self._get_provider()
            response = await provider.chat(
                messages=self.context.messages,
                system_prompt=self.build_system_prompt(user_message),
            )
            self.context.add_assistant(response.content)
            session.append_turn("assistant", response.content)
            self._detector.mark_assistant_response()
            history = [{"role": m.role, "content": m.content} for m in self.context.messages]
            self._bg_summary.on_turn(history)
            return response.content
        except Exception as e:
            logger.error("LLM query failed: %s", e)
            error_msg = f"Error: {e}"
            self.context.add_assistant(error_msg)
            session.append_turn("assistant_error", error_msg)
            return error_msg

    async def stream_query_with_actions(self, user_message: str) -> AsyncIterator[str]:
        """
        Like stream_query but injects action-format instructions into the system
        prompt. The caller is responsible for extracting action blocks from the
        assembled response.
        """
        if not self.config.has_llm():
            yield (
                "No LLM provider configured. "
                "Add your API key to .env and restart Nala.\n"
            )
            return

        session = self.ensure_session()
        self._detector.mark_user_message()
        self._maybe_compact(user_message)
        self.context.add_user(user_message)
        self.context.trim_to_limit()
        session.append_turn("user", user_message)

        action_system = self.build_system_prompt(user_message) + ACTION_PROMPT_EXTENSION
        full_response: list[str] = []
        had_error = False
        try:
            provider = self._get_provider()
            async for chunk in provider.stream_chat(
                messages=self.context.messages,
                system_prompt=action_system,
            ):
                full_response.append(chunk)
                yield chunk
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            had_error = True
            yield f"\n\nError: {e}"

        if full_response:
            assembled = "".join(full_response)
            cleaned, actions = extract_actions(assembled)
            assistant_text = cleaned.strip()
            if not assistant_text and actions:
                assistant_text = (
                    f"Prepared {len(actions)} proposed action(s). "
                    "Review the generated previews before applying them."
                )
            self.context.add_assistant(assistant_text)
            turn_type = "assistant_error" if had_error else "assistant"
            session.append_turn(turn_type, assistant_text)
            self._detector.mark_assistant_response()
            history = [{"role": m.role, "content": m.content} for m in self.context.messages]
            self._bg_summary.on_turn(history)

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

        session = self.ensure_session()
        self._detector.mark_user_message()
        self._maybe_compact(user_message)
        self.context.add_user(user_message)
        self.context.trim_to_limit()
        session.append_turn("user", user_message)

        full_response: list[str] = []
        had_error = False
        try:
            provider = self._get_provider()
            async for chunk in provider.stream_chat(
                messages=self.context.messages,
                system_prompt=self.build_system_prompt(user_message),
            ):
                full_response.append(chunk)
                yield chunk
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            had_error = True
            yield f"\n\nError: {e}"

        if full_response:
            assembled = "".join(full_response)
            self.context.add_assistant(assembled)
            turn_type = "assistant_error" if had_error else "assistant"
            session.append_turn(turn_type, assembled)
            self._detector.mark_assistant_response()
            history = [{"role": m.role, "content": m.content} for m in self.context.messages]
            self._bg_summary.on_turn(history)
