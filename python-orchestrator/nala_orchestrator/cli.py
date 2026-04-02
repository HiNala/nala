"""
Nala Python IPC server.

Spawned by the Rust TUI as a subprocess. Reads JSON-lines requests from
stdin and writes JSON-lines responses to stdout.

Full protocol (JSON-lines over stdin/stdout):

  ── LLM ───────────────────────────────────────────────────────────────────
  Request:  {"id":"1","type":"query","text":"..."}
  Response: {"id":"1","type":"chunk","text":"..."}   (0..N)
            {"id":"1","type":"done"}
            {"id":"1","type":"error","text":"..."}

  ── Analysis ──────────────────────────────────────────────────────────────
  Request:  {"id":"2","type":"run_perspectives","perspective":"all"}
  Response: (same chunk/done/error pattern as query)

  ── Sessions ──────────────────────────────────────────────────────────────
  Request:  {"id":"3","type":"list_sessions"}
  Response: {"id":"3","type":"sessions","sessions":[...]}

  Request:  {"id":"4","type":"new_session"}
  Response: {"id":"4","type":"session_created","session_id":"...","summary":"..."}

  Request:  {"id":"5","type":"load_session","session_id":"20250101_120000"}
  Response: {"id":"5","type":"session_loaded","session_id":"...","turn_count":12}

  Request:  {"id":"6","type":"session_summary"}
  Response: {"id":"6","type":"session_summary","text":"..."}

  Request:  {"id":"6b","type":"session_compare","older_session_id":"...","newer_session_id":"..."}
  Response: {"id":"6b","type":"session_compare","text":"..."}

  ── Mission generation ────────────────────────────────────────────────────
  Request:  {"id":"7","type":"generate_mission","focus":""}
  Response: (same chunk/done/error pattern — streams the markdown)

  ── Housekeeping ──────────────────────────────────────────────────────────
  ── Inline actions ────────────────────────────────────────────────────────
  Request:  {"id":"A","type":"query_with_actions","text":"..."}
  Response: (chunk/done like query, then…)
            {"id":"A","type":"proposed_action","action_id":"abc","action_type":"edit","description":"…","preview":"…"}

  Request:  {"id":"B","type":"apply_action","action_id":"abc"}
  Response: {"id":"B","type":"action_applied","action_id":"abc",
             "success":true,"message":"Edited src/foo.py"}

  Request:  {"id":"C","type":"skip_action","action_id":"abc"}
  Response: {"id":"C","type":"ok"}

  ── Multi-agent team ──────────────────────────────────────────────────────
  Request:  {"id":"T","type":"team_start","objective":"..."}
  Response: (chunk/done streaming progress + final summary)

  Request:  {"id":"T","type":"team_status"}
  Response: (chunk/done with task list + lock status)

  Request:  {"id":"T","type":"team_cancel"}
  Response: {"id":"T","type":"ok","text":"Team cancelled."}

  ── Housekeeping ──────────────────────────────────────────────────────────
  Request:  {"id":"8","type":"index_context","total_files":10,"total_symbols":50}
  Response: {"id":"8","type":"ok"}

  Request:  {"id":"9","type":"ping"}
  Response: {"id":"9","type":"pong","version":"0.1.0"}

Usage (from Rust):
    Command::new("python")
        .args(["-m", "nala_orchestrator.cli", "--root", "/path/to/project"])
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped()).stdout(Stdio::piped()).spawn()?;
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

from .agent_runtime.manager import AgentManager
from .agents.action_executor import ActionExecutor
from .agents.action_extractor import extract_actions
from .agents.actions import Action
from .agents.orchestrator import AgentOrchestrator
from .chunking.embedder import Embedder
from .chunking.splitter import ChunkSplitter, Symbol
from .config import Config
from .git_ops import branch_info, diff_summary, full_status
from .handoff.reader import HandoffReader
from .handoff.writer import HandoffWriter
from .memory.knowledge import KnowledgeBase
from .memory.session_memory import SessionMemory
from .multi_agent.lead import LeadAgent
from .perspectives.engine import PerspectivesEngine, format_results_as_text
from .sessions.manager import SessionManager
from .sessions.missions import MissionDocument, MissionGenerator
from .sessions.report import AuditReport, Finding, ReportGenerator
from .startup import gather_startup_intelligence
from .tasks.ledger import TaskLedger

logging.basicConfig(
    level=logging.DEBUG if os.environ.get("NALA_DEBUG") else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("nala.cli")

_pending_actions: dict[str, Action] = {}
_action_executor: ActionExecutor | None = None

# Project-level embedder (built lazily on first index_context with symbols).
_embedder: Embedder | None = None

# Task ledger — created on IPC startup, persists within the session.
_task_ledger: TaskLedger | None = None

# Singleton lead agent — created on first team_start, reused for status/cancel.
_lead_agent: LeadAgent | None = None

# Agent runtime manager — central control plane for /agent runs.
_agent_manager: AgentManager | None = None

# Flush immediately — Rust reads line-by-line
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

VERSION = "0.1.0"

_write_lock = threading.Lock()


def write_response(data: dict) -> None:
    """Write a JSON-lines response to stdout (thread-safe)."""
    line = json.dumps(data)
    with _write_lock:
        print(line, flush=True)


def _ensure_brain_scaffold(root: Path) -> None:
    """Create durable Brain Mode artifacts if they do not exist yet."""
    brain_dir = root / ".nala" / "brain"
    scopes_dir = brain_dir / "scopes"
    brain_dir.mkdir(parents=True, exist_ok=True)
    scopes_dir.mkdir(parents=True, exist_ok=True)

    project_brief = brain_dir / "project-brief.md"
    if not project_brief.exists():
        project_brief.write_text(
            (
                "# Project Brief\n\n"
                "## Architecture\n"
                "- Fill in core modules and boundaries.\n\n"
                "## Canonical Commands\n"
                "- Build:\n"
                "- Test:\n"
                "- Lint:\n\n"
                "## Definitions of Done\n"
                "- Tests pass\n"
                "- Lint clean\n"
                "- User-visible behavior verified\n\n"
                "## Risky Areas\n"
                "- Fill in critical subsystems and constraints.\n"
            ),
            encoding="utf-8",
        )

    if (root / "rust-core").exists():
        rust_scope = scopes_dir / "rust-core.md"
        if not rust_scope.exists():
            rust_scope.write_text(
                (
                    "# Scope: rust-core\n\n"
                    "- Keep TUI interactions low-latency.\n"
                    "- Prefer minimal rendering-side allocations.\n"
                    "- Validate with `cargo check` before shipping changes.\n"
                ),
                encoding="utf-8",
            )

    if (root / "python-orchestrator").exists():
        py_scope = scopes_dir / "python-orchestrator.md"
        if not py_scope.exists():
            py_scope.write_text(
                (
                    "# Scope: python-orchestrator\n\n"
                    "- Preserve IPC responsiveness (never block event loop).\n"
                    "- Keep request handlers deterministic and explicit.\n"
                    "- Validate with `ruff check` and targeted smoke tests.\n"
                ),
                encoding="utf-8",
            )

    if (root / "dashboard").exists():
        dashboard_scope = scopes_dir / "dashboard.md"
        if not dashboard_scope.exists():
            dashboard_scope.write_text(
                (
                    "# Scope: dashboard\n\n"
                    "- Keep startup lightweight and resilient.\n"
                    "- Prefer read-only operations unless explicitly requested.\n"
                    "- Verify route health before release.\n"
                ),
                encoding="utf-8",
            )


def _get_action_executor(root: Path, *, reset: bool = False) -> ActionExecutor:
    """Return the shared action executor for the active coding session."""
    global _action_executor
    if reset or _action_executor is None:
        _action_executor = ActionExecutor(root)
    return _action_executor


def _stream_text(req_id: str, text: str, chunk_size: int = 200) -> None:
    """Stream a long text string as successive chunk messages, then done.

    Uses character-level slicing (not byte-level) to avoid splitting
    multi-byte Unicode codepoints.
    """
    offset = 0
    while offset < len(text):
        end = min(offset + chunk_size, len(text))
        write_response({"id": req_id, "type": "chunk", "text": text[offset:end]})
        offset = end
    write_response({"id": req_id, "type": "done"})


def _normalise_severity(value: object) -> str:
    severity = str(value or "medium").lower()
    if severity in {"critical", "high", "medium", "low"}:
        return severity
    return "medium"


def _finding_from_dict(data: dict, perspective_name: str) -> Finding:
    """Reconstruct a report Finding from serialised findings.json data."""
    start_line = data.get("start_line", 1)
    try:
        start_line = int(start_line)
    except (TypeError, ValueError):
        start_line = 1

    return Finding(
        title=str(data.get("title", "Untitled finding")),
        description=str(data.get("description", "")),
        file_path=str(data.get("file_path", "")),
        start_line=max(1, start_line),
        severity=_normalise_severity(data.get("severity")),
        perspective=str(data.get("perspective") or perspective_name or "unknown"),
        suggestion=(str(data["suggestion"]) if data.get("suggestion") else None),
        code_snippet=(str(data["code_snippet"]) if data.get("code_snippet") else None),
    )


def _audit_report_from_findings(session: SessionManager, findings_raw: list[dict]) -> AuditReport:
    """Build an AuditReport from the session's saved findings.json payload."""
    meta = session.current_meta
    findings: list[Finding] = []
    perspectives_run: list[str] = []
    summary_lines: list[str] = []

    for perspective_data in findings_raw:
        perspective_name = str(perspective_data.get("perspective_name", "unknown"))
        if perspective_name not in perspectives_run:
            perspectives_run.append(perspective_name)

        summary = str(perspective_data.get("summary", "")).strip()
        if summary:
            summary_lines.append(f"- **{perspective_name}**: {summary}")

        for finding_data in perspective_data.get("findings", []):
            if isinstance(finding_data, dict):
                findings.append(_finding_from_dict(finding_data, perspective_name))

    return AuditReport(
        project_name=meta.project_name if meta else session.project_root.name,
        session_id=meta.session_id if meta else "unknown",
        total_files=meta.total_files if meta else 0,
        total_symbols=meta.total_symbols if meta else 0,
        findings=findings,
        perspectives_run=perspectives_run,
        summary="\n".join(summary_lines),
    )


def _match_mission_focus(mission: MissionDocument, focus: str) -> bool:
    if not focus:
        return True
    needle = focus.lower()
    haystacks = [
        mission.title,
        mission.objective,
        mission.context,
        *(f.title for f in mission.findings),
        *(f.description for f in mission.findings),
        *(f.file_path for f in mission.findings),
        *(f.perspective for f in mission.findings),
    ]
    return any(needle in text.lower() for text in haystacks if text)


# ── Request handlers ───────────────────────────────────────────────────────

async def handle_request(
    req: dict,
    agent: AgentOrchestrator,
    root: Path,
    config: Config,
) -> None:
    """Dispatch one request and write response(s) to stdout."""
    req_id = req.get("id", "0")
    req_type = req.get("type", "")

    # ── Ping ──────────────────────────────────────────────────────────────
    if req_type == "ping":
        write_response({"id": req_id, "type": "pong", "version": VERSION})

    # ── Index context update ───────────────────────────────────────────────
    elif req_type == "index_context":
        total_files = req.get("total_files", 0)
        total_symbols = req.get("total_symbols", 0)

        symbols_raw_all: list[dict] = req.get("symbols", [])
        lang_counts: dict[str, int] = {}
        for s in symbols_raw_all:
            lang = s.get("language", "")
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
        primary_lang = (
            max(lang_counts, key=lang_counts.get, default="unknown")  # type: ignore[arg-type]
            if lang_counts
            else "unknown"
        )

        agent.update_index_context(
            total_files=total_files,
            total_symbols=total_symbols,
            primary_language=primary_lang,
        )

        write_response({"id": req_id, "type": "ok"})

        global _embedder
        symbols_raw: list[dict] = req.get("symbols", [])
        if symbols_raw:
            normalised_symbols: list[dict] = []
            for s in symbols_raw:
                copied = dict(s)
                copied["kind"] = str(s.get("kind", "")).lower()
                normalised_symbols.append(copied)

            syms = [
                Symbol(
                    name=s.get("name", ""),
                    kind=s.get("kind", ""),
                    start_line=s.get("start_line", 1),
                    end_line=s.get("end_line", 1),
                    file_path=s.get("file_path", ""),
                )
                for s in normalised_symbols
            ]

            async def _background_build(
                root_str: str,
                syms_list: list,
                total: int,
                normalised: list[dict],
            ) -> None:
                global _embedder
                import time as _t

                if _embedder is not None and not _embedder.needs_rebuild(total):
                    return

                _t0 = _t.monotonic()
                log.warning(
                    "index_context: building chunks for %d symbols (background)",
                    len(syms_list),
                )
                try:
                    def _do_build() -> Embedder:
                        t1 = _t.monotonic()
                        emb = Embedder(root_str)
                        splitter = ChunkSplitter()
                        chunks = splitter.split_all(root_str, syms_list)
                        t2 = _t.monotonic()
                        log.warning(
                            "split_all: %d chunks in %.1fs",
                            len(chunks), t2 - t1,
                        )
                        emb.build(chunks, source_file_count=total)
                        t3 = _t.monotonic()
                        log.warning(
                            "embedder.build: %.1fs (total %.1fs)",
                            t3 - t2, t3 - t1,
                        )
                        return emb

                    emb = await asyncio.wait_for(
                        asyncio.to_thread(_do_build),
                        timeout=120,
                    )
                    _embedder = emb
                    agent.set_embedder(emb)
                    elapsed = _t.monotonic() - _t0
                    log.warning(
                        "index_context: chunks built in %.1fs", elapsed,
                    )
                    msg = (
                        f"Context ready: {emb.chunk_count} code chunks"
                        f" indexed in {elapsed:.1f}s."
                    )
                    write_response({
                        "id": req_id,
                        "type": "system_message",
                        "text": msg,
                    })
                except TimeoutError:
                    log.error(
                        "index_context: chunk build timed out (120s)",
                    )
                except Exception as e:
                    log.error("index_context: chunk build failed: %s", e)

                try:
                    from .graph.builder import GraphBuilder
                    from .graph.connection import GraphConnection

                    conn = GraphConnection(config)
                    if conn.connect():
                        builder = GraphBuilder(conn)
                        builder.ensure_schema()
                        await asyncio.to_thread(
                            builder.populate_from_index,
                            json.dumps(
                                {"symbols": normalised},
                                separators=(",", ":"),
                            ),
                        )
                        conn.close()
                except Exception as e:
                    log.debug("Graph sync skipped: %s", e)

            asyncio.create_task(
                _background_build(
                    str(root), syms, total_files, normalised_symbols,
                ),
            )

    # ── Natural language query (streaming) ────────────────────────────────
    elif req_type == "query":
        text = req.get("text", "").strip()
        if not text:
            write_response({"id": req_id, "type": "error", "text": "Empty query"})
            return
        import time as _time
        _t0 = _time.monotonic()
        log.warning("QUERY START id=%s text=%r", req_id, text[:60])
        try:
            got_chunk = False
            async for chunk in agent.stream_query(text):
                got_chunk = True
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
            _elapsed = _time.monotonic() - _t0
            log.warning(
                "QUERY DONE id=%s chunks=%s elapsed=%.1fs",
                req_id, got_chunk, _elapsed,
            )
        except TimeoutError:
            log.error("QUERY TIMEOUT id=%s", req_id)
            write_response({
                "id": req_id, "type": "error",
                "text": "LLM request timed out. Check your network and API key.",
            })
        except Exception as e:
            log.exception("QUERY ERROR id=%s: %s", req_id, e)
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Run perspectives (streaming formatted report) ─────────────────────
    elif req_type == "run_perspectives":
        project_root_str = req.get("project_root") or str(root)
        perspective_name = req.get("perspective", "all")
        graph_conn = None
        try:
            try:
                from .graph.connection import GraphConnection

                graph_conn = GraphConnection(config)
                graph_conn.connect()
            except Exception as e:
                log.debug("Graph unavailable for perspectives: %s", e)
                graph_conn = None

            engine = PerspectivesEngine(config, graph=graph_conn)
            if perspective_name == "all":
                results = await engine.run_all(project_root_str)
            elif perspective_name == "quick":
                quick_names = ("complexity", "security", "dependency")
                collected = []
                for name in quick_names:
                    one = await engine.run_one(name, project_root_str)
                    if one:
                        collected.append(one)
                results = collected
            else:
                result = await engine.run_one(perspective_name, project_root_str)
                results = [result] if result else []

            session = agent.ensure_session()
            session.save_findings(results)
            findings_raw = session.load_findings_raw()
            audit_report = _audit_report_from_findings(session, findings_raw)
            report_md = ReportGenerator().generate(audit_report)
            report_path = session.write_report("report", report_md)
            try:
                report_rel = report_path.relative_to(root)
                report_label = str(report_rel)
            except ValueError:
                report_label = str(report_path)

            rendered = format_results_as_text(results)
            rendered += f"\n\nSaved audit report: {report_label}"
            _stream_text(req_id, rendered)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Analysis error: {e}"})
        finally:
            if graph_conn is not None:
                graph_conn.close()

    # ── Generate mission document (streaming) ─────────────────────────────
    elif req_type == "generate_mission":
        focus = req.get("focus", "").strip()
        try:
            session = agent.ensure_session()
            findings_raw = session.load_findings_raw()
            if not findings_raw:
                write_response({
                    "id": req_id,
                    "type": "error",
                    "text": "No findings available yet. Run /analyze before generating a mission.",
                })
                return

            audit_report = _audit_report_from_findings(session, findings_raw)

            if not config.has_llm():
                generator = MissionGenerator()
                missions = generator.generate_all(audit_report)
                missions = [m for m in missions if _match_mission_focus(m, focus)]
                if not missions:
                    write_response({
                        "id": req_id,
                        "type": "error",
                        "text": (
                            f"No generated mission matched focus '{focus}'."
                            if focus else
                            "No mission could be generated from the current findings."
                        ),
                    })
                    return

                mission_md = generator.render(missions[0])
                _stream_text(req_id, mission_md)
                existing = (
                    list(session.current_dir.glob("missions/MISSION_*.md"))
                    if session.current_dir
                    else []
                )
                session.write_mission(len(existing) + 1, mission_md)
                return

            # Build the prompt from saved findings
            prompt = _build_mission_prompt(findings_raw, focus, agent)

            full_text: list[str] = []
            async for chunk in agent.stream_query(prompt):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
                full_text.append(chunk)
            write_response({"id": req_id, "type": "done"})

            # Save the generated mission to the session
            if full_text:
                mission_md = "".join(full_text)
                existing = (
                    list(session.current_dir.glob("missions/MISSION_*.md"))
                    if session.current_dir
                    else []
                )
                n = len(existing) + 1
                session.write_mission(n, mission_md)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Generation error: {e}"})

    # ── Session: list ──────────────────────────────────────────────────────
    elif req_type == "list_sessions":
        try:
            sm = SessionManager(root)
            sessions = sm.list_sessions()
            session_list = [
                {
                    "session_id": s.session_id,
                    "created_at": s.created_at,
                    "project_name": s.project_name,
                    "status": s.status,
                    "total_turns": s.total_turns,
                    "perspectives_run": s.perspectives_run,
                }
                for s in sessions[:20]
            ]
            write_response({"id": req_id, "type": "sessions", "sessions": session_list})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Session: new ──────────────────────────────────────────────────────
    elif req_type == "new_session":
        try:
            sm = SessionManager(root)
            meta = sm.new_session()
            agent.set_session(sm)
            # Clear in-memory conversation history and pending actions
            agent.context.messages.clear()
            _pending_actions.clear()
            _get_action_executor(root, reset=True)
            write_response({
                "id": req_id,
                "type": "session_created",
                "session_id": meta.session_id,
                "summary": f"New session {meta.session_id} created.",
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Session: load ─────────────────────────────────────────────────────
    elif req_type == "load_session":
        session_id = req.get("session_id", "")
        if not session_id:
            write_response({"id": req_id, "type": "error", "text": "Missing session_id"})
            return
        try:
            sm = SessionManager(root)
            meta = sm.load_session(session_id)
            if meta is None:
                write_response(
                    {
                        "id": req_id,
                        "type": "error",
                        "text": f"Session {session_id!r} not found",
                    }
                )
                return
            agent.context.messages.clear()
            agent.restore_history(sm)
            _pending_actions.clear()
            _get_action_executor(root, reset=True)
            turns = sm.get_conversation_history()
            write_response({
                "id": req_id,
                "type": "session_loaded",
                "session_id": session_id,
                "turn_count": len(turns),
                "summary": sm.summary_text(),
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Query with inline actions (streaming + action extraction) ─────────
    elif req_type == "query_with_actions":
        text = req.get("text", "").strip()
        if not text:
            write_response({"id": req_id, "type": "error", "text": "Empty query"})
            return
        try:
            full_text: list[str] = []
            async for chunk in agent.stream_query_with_actions(text):
                full_text.append(chunk)
                write_response({
                    "id": req_id, "type": "chunk", "text": chunk,
                })

            assembled = "".join(full_text)
            _cleaned, actions = extract_actions(assembled)
            write_response({"id": req_id, "type": "done"})
            for action in actions:
                _pending_actions[action.action_id] = action
                executor = _get_action_executor(root)
                preview = executor.preview(action)
                write_response({
                    "id": req_id,
                    "type": "proposed_action",
                    "action_id": action.action_id,
                    "action_type": action.type,
                    "description": action.description,
                    "preview": preview,
                })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Apply a proposed action ────────────────────────────────────────────
    elif req_type == "apply_action":
        action_id = req.get("action_id", "")
        action = _pending_actions.get(action_id)
        if action is None:
            write_response(
                {
                    "id": req_id,
                    "type": "error",
                    "text": f"Unknown action_id: {action_id}",
                }
            )
            return
        try:
            executor = _get_action_executor(root)
            result = executor.apply(action)
            # Persist to session audit log
            session = agent.ensure_session()
            session.append_turn(
                "action",
                json.dumps({
                    "action_id": result.action_id,
                    "success": result.success,
                    "message": result.message,
                }),
            )
            write_response({
                "id": req_id,
                "type": "action_applied",
                "action_id": result.action_id,
                "success": result.success,
                "message": result.message,
                "output": result.output,
            })
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Skip a proposed action (acknowledge, no file changes) ─────────────
    elif req_type == "skip_action":
        action_id = req.get("action_id", "")
        _pending_actions.pop(action_id, None)
        write_response({"id": req_id, "type": "ok"})

    # ── Handoff: manual save ──────────────────────────────────────────────
    elif req_type == "handoff_save":
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session and agent._session.current_meta else "manual")
            writer = HandoffWriter(root)
            doc = writer.write(sid, "manual", history)
            _stream_text(req_id, f"Handoff saved.\n\n{doc.to_markdown()}")
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Handoff: show latest ───────────────────────────────────────────────
    elif req_type == "handoff_show":
        reader = HandoffReader(root)
        doc = reader.load_latest()
        if doc:
            _stream_text(req_id, doc.to_markdown())
        else:
            _stream_text(req_id, "No handoff document found.")

    # ── Handoff: history chain ─────────────────────────────────────────────
    elif req_type == "handoff_history":
        reader = HandoffReader(root)
        _stream_text(req_id, reader.format_history())

    # ── Memory: project knowledge summary ────────────────────────────────
    elif req_type == "memory_summary":
        kb = KnowledgeBase(root)
        sm_mem = SessionMemory(root)
        kb_text = kb.get_summary()
        recent = sm_mem.list_sessions(5)
        sessions_text = "\n".join(
            f"  {s['session_id']}: {s['summary']}" for s in recent
        ) or "  (no sessions yet)"
        text = f"{kb_text}\n\nRecent sessions:\n{sessions_text}"
        _stream_text(req_id, text)

    # ── Memory: list sessions ─────────────────────────────────────────────
    elif req_type == "memory_sessions":
        sm_mem = SessionMemory(root)
        sessions = sm_mem.list_sessions(30)
        write_response({"id": req_id, "type": "memory_sessions", "sessions": sessions})

    # ── Memory: forget a topic ─────────────────────────────────────────────
    elif req_type == "memory_forget":
        target = req.get("target", "").strip()
        if not target:
            write_response({"id": req_id, "type": "error", "text": "Missing target"})
        else:
            kb = KnowledgeBase(root)
            count = kb.remove_fact(target)
            write_response({"id": req_id, "type": "ok",
                            "text": f"Removed {count} fact(s) matching '{target}'"})

    # ── Context: usage breakdown ──────────────────────────────────────────
    elif req_type == "context_usage":
        usage = agent.get_context_usage()
        breakdown = usage.get_usage_breakdown()
        write_response({
            "id": req_id,
            "type": "context_usage",
            "display": bool(req.get("display", True)),
            "text": agent.get_context_breakdown_text(),
            "breakdown": breakdown,
        })

    # ── Context: manual compaction (writes handoff first) ────────────────
    elif req_type == "compact_context":
        focus = req.get("focus", "").strip()
        # Write a handoff before compacting so context is never lost.
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session and agent._session.current_meta else "compact")
            HandoffWriter(root).write(sid, "compaction", history)
        except Exception as e:
            log.warning("Pre-compaction handoff failed: %s", e)
        summary_msg = agent.compact_now(focus=focus)
        _stream_text(req_id, f"Compaction complete.\n{summary_msg}")

    # ── Session: summary ──────────────────────────────────────────────────
    elif req_type == "session_summary":
        session = agent._session
        if session:
            text = session.summary_text()
        else:
            text = "No active session. Run a query or /analyze to start one."
        write_response({"id": req_id, "type": "session_summary", "text": text})

    elif req_type == "session_compare":
        older_session_id = req.get("older_session_id", "").strip()
        newer_session_id = req.get("newer_session_id", "").strip()
        if not older_session_id or not newer_session_id:
            write_response({
                "id": req_id,
                "type": "error",
                "text": "Usage: session_compare requires older_session_id and newer_session_id",
            })
            return

        sm = SessionManager(root)
        try:
            text = sm.compare_sessions(older_session_id, newer_session_id)
            write_response({"id": req_id, "type": "session_compare", "text": text})
        except FileNotFoundError as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    # ── Graph: stats summary ──────────────────────────────────────────────
    elif req_type == "graph_stats":
        from .graph.connection import GraphConnection
        from .graph.queries import find_most_imported_modules
        conn = GraphConnection(config)
        if not conn.connect():
            _stream_text(
                req_id,
                "Neo4j is not connected. Run `neo4j start` to enable graph features.",
            )
            return
        try:
            def _fetch_graph_stats() -> str:
                def _count(query: str) -> int:
                    rows = conn.run(query)
                    return rows[0].get("n", 0) if rows else 0

                files = _count("MATCH (f:File) RETURN count(f) AS n")
                fns = _count("MATCH (f:Function) RETURN count(f) AS n")
                classes = _count("MATCH (c:Class) RETURN count(c) AS n")
                mods = _count("MATCH (m:Module) RETURN count(m) AS n")
                rels = _count("MATCH ()-[r]->() RETURN count(r) AS n")
                cypher, params = find_most_imported_modules()
                top = conn.run(cypher, **params)[:5]
                top_lines = "\n".join(
                    f"  {i+1}. {r.get('module','?')} — imported {r.get('import_count',0)}x"
                    for i, r in enumerate(top)
                ) or "  (no data)"
                return (
                    f"Graph statistics:\n"
                    f"  Files:     {files}\n"
                    f"  Functions: {fns}\n"
                    f"  Classes:   {classes}\n"
                    f"  Modules:   {mods}\n"
                    f"  Relations: {rels}\n\n"
                    f"Top 5 most imported modules:\n{top_lines}"
                )

            text = await asyncio.to_thread(_fetch_graph_stats)
            conn.close()
            _stream_text(req_id, text)
        except Exception as e:
            conn.close()
            write_response({"id": req_id, "type": "error", "text": f"Graph query error: {e}"})

    # ── Multi-agent: start a team run (streaming progress) ───────────────
    elif req_type == "team_start":
        objective = req.get("objective", "").strip()
        if not objective:
            write_response({"id": req_id, "type": "error", "text": "Missing objective"})
            return
        global _lead_agent
        _lead_agent = LeadAgent(config, root)
        try:
            async for chunk in _lead_agent.stream_run(objective):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Team run error: {e}"})

    # ── Multi-agent: status of running/last team ──────────────────────────
    elif req_type == "team_status":
        if _lead_agent is None:
            _stream_text(req_id, "No team run active.")
        else:
            _stream_text(req_id, _lead_agent.get_status())

    # ── Multi-agent: cancel / reset ───────────────────────────────────────
    elif req_type == "team_cancel":
        if _lead_agent is not None:
            _lead_agent._task_list.clear()
            _lead_agent._bus.clear()
        _lead_agent = None
        write_response({"id": req_id, "type": "ok", "text": "Team cancelled."})

    # ── Git operations ────────────────────────────────────────────────────
    elif req_type == "git_diff":
        try:
            text = diff_summary(root)
            _stream_text(req_id, text)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Git error: {e}"})

    elif req_type == "git_branch":
        try:
            text = branch_info(root)
            _stream_text(req_id, text)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Git error: {e}"})

    elif req_type == "git_status":
        try:
            text = full_status(root)
            _stream_text(req_id, text)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": f"Git error: {e}"})

    # ── Task ledger ─────────────────────────────────────────────────────
    elif req_type == "task_create":
        global _task_ledger
        objective = req.get("objective", "").strip()
        if not objective:
            write_response({"id": req_id, "type": "error", "text": "Missing task objective"})
            return
        if _task_ledger is None:
            sessions_dir = root / ".nala" / "sessions"
            _task_ledger = TaskLedger(sessions_dir)
        task = _task_ledger.create_task(objective)
        msg = f"Created task [{task.task_id}]: {task.objective}\nStatus: {task.status.value}"
        _stream_text(req_id, msg)

    elif req_type == "task_status":
        if _task_ledger is None:
            _stream_text(req_id, "No active task. Use /task <objective> to start one.")
        else:
            _stream_text(req_id, _task_ledger.status_text())

    elif req_type == "task_list":
        if _task_ledger is None or not _task_ledger.list_tasks():
            _stream_text(req_id, "No tasks in this session.")
        else:
            lines = []
            for t in _task_ledger.list_tasks():
                lines.append(f"[{t.task_id}] {t.status.value:12s}  {t.objective}")
            _stream_text(req_id, "\n".join(lines))

    elif req_type == "task_done":
        if _task_ledger is None:
            _stream_text(req_id, "No active task.")
        else:
            summary = req.get("summary", "")
            task = _task_ledger.complete_current(summary)
            if task:
                _stream_text(req_id, f"Completed task [{task.task_id}]: {task.objective}")
            else:
                _stream_text(req_id, "No active task to complete.")

    # ── Undo last action batch ──────────────────────────────────────────
    elif req_type == "undo_actions":
        if _action_executor is None or not _action_executor.has_rollback:
            _stream_text(req_id, "Nothing to undo.")
        else:
            messages = _action_executor.rollback_last_batch()
            _stream_text(req_id, "\n".join(messages) if messages else "Rollback complete.")

    # ── Startup intelligence (on-demand refresh) ────────────────────────
    elif req_type == "startup_intelligence":
        try:
            intel = gather_startup_intelligence(
                root,
                file_count=req.get("file_count", 0),
                symbol_count=req.get("symbol_count", 0),
            )
            intel["id"] = req_id
            write_response(intel)
        except Exception as e:
            err = f"Startup intelligence error: {e}"
            write_response({"id": req_id, "type": "error", "text": err})

    # ── Agent runtime requests ──────────────────────────────────────────
    elif req_type == "agent_start":
        objective = req.get("objective", "").strip()
        if not objective:
            write_response({"id": req_id, "type": "error", "text": "Empty objective"})
            return
        if _agent_manager is None:
            write_response({"id": req_id, "type": "error", "text": "Agent runtime not ready"})
            return
        try:
            async for chunk in _agent_manager.handle_objective(objective):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_status":
        if _agent_manager is None:
            _stream_text(req_id, "Agent runtime not initialised.")
        else:
            _stream_text(req_id, _agent_manager.status())

    elif req_type == "agent_plan":
        topic = req.get("topic", "").strip()
        if _agent_manager is None:
            write_response({"id": req_id, "type": "error", "text": "Agent runtime not ready"})
            return
        try:
            async for chunk in _agent_manager.plan(topic):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_run":
        if _agent_manager is None:
            write_response({"id": req_id, "type": "error", "text": "Agent runtime not ready"})
            return
        try:
            async for chunk in _agent_manager.run_execution():
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_review":
        if _agent_manager is None:
            _stream_text(req_id, "Agent runtime not ready.")
            return
        try:
            text = await _agent_manager.review()
            _stream_text(req_id, text)
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_verify":
        if _agent_manager is None:
            write_response({"id": req_id, "type": "error", "text": "Agent runtime not ready"})
            return
        try:
            async for chunk in _agent_manager.verify():
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_hotspot":
        if _agent_manager is None:
            write_response({"id": req_id, "type": "error", "text": "Agent runtime not ready"})
            return
        try:
            async for chunk in _agent_manager.hotspot():
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    elif req_type == "agent_stop":
        if _agent_manager is None:
            _stream_text(req_id, "No agent runtime.")
        else:
            msg = _agent_manager.stop()
            _stream_text(req_id, msg)

    elif req_type == "agent_resume":
        if _agent_manager is None:
            _stream_text(req_id, "Agent runtime not ready.")
        else:
            msg = _agent_manager.resume()
            _stream_text(req_id, msg)

    else:
        write_response({"id": req_id, "type": "error", "text": f"Unknown type: {req_type}"})


# ── Mission prompt builder ─────────────────────────────────────────────────

def _build_mission_prompt(
    findings_raw: list[dict],
    focus: str,
    agent: AgentOrchestrator,
) -> str:
    """Build the LLM prompt for mission generation from saved findings."""
    project_name = Path(agent.context.project_root).name

    # Summarise findings
    finding_lines: list[str] = []
    for perspective_data in findings_raw:
        p_name = perspective_data.get("perspective_name", "unknown")
        findings = perspective_data.get("findings", [])
        if not findings:
            continue
        finding_lines.append(f"\n### {p_name} ({len(findings)} findings)")
        severity_order = ["critical", "high", "medium", "low", "info"]
        sorted_findings = sorted(
            findings,
            key=lambda f: severity_order.index(f.get("severity", "info"))
            if f.get("severity") in severity_order else 99
        )
        for f in sorted_findings[:5]:
            sev = f.get("severity", "?").upper()
            title = f.get("title", "Untitled")
            fp = f.get("file_path", "")
            line = f.get("start_line", 0)
            loc = f" ({fp}:{line})" if fp else ""
            finding_lines.append(f"- [{sev}] {title}{loc}")

    findings_section = "\n".join(finding_lines) or "No findings recorded."
    focus_line = f"\nFocus specifically on: {focus}" if focus else ""

    return f"""You are a senior software engineer performing a code review of **{project_name}**.
You have just completed an automated analysis. Generate a detailed, actionable improvement mission.

## Findings Summary
{findings_section}

## Project Context
Location: {agent.context.project_root}
Files: {agent.context.total_files} | Symbols: {agent.context.total_symbols}
{focus_line}

Generate a mission document in EXACTLY this format:

# Mission: [descriptive title]

## Objective
[1–2 sentences: what will be fixed and why]

## Why This Matters
[2–3 sentences: business/engineering impact]

## Implementation Steps
[Numbered list with enough detail to act on. Reference actual file names and line numbers.]

## Acceptance Criteria
- [ ] [verifiable outcome]
- [ ] [verifiable outcome]

## Estimated Complexity
[Low / Medium / High with 1-sentence justification]

Rules:
- Reference actual file names from the findings (not generic placeholders)
- Each step must be specific enough to implement without guessing
- Do not invent findings not present in the analysis above
"""


# ── IPC loop ───────────────────────────────────────────────────────────────

async def run_ipc_loop(project_root: str | None = None) -> None:
    """
    Main IPC loop: read JSON-lines from stdin, write responses to stdout.
    Runs until stdin closes (Rust process exits or sends EOF).
    """
    root = Path(project_root) if project_root else Path.cwd()
    _ensure_brain_scaffold(root)
    config = Config.load(project_root=root)
    agent = AgentOrchestrator(config)

    # Auto-create a session on startup so the first query is always logged
    sm = SessionManager(root)
    sm.new_session()
    agent.set_session(sm)
    _get_action_executor(root, reset=True)

    # Initialise the embedder (BM25 works offline; vector index is lazy).
    global _embedder
    _embedder = Embedder(str(root))
    agent.set_embedder(_embedder)

    # Inject handoff + memory context so the agent resumes seamlessly.
    handoff_reader = HandoffReader(root)
    session_mem = SessionMemory(root)
    knowledge_base = KnowledgeBase(root)

    handoff_ctx = handoff_reader.get_startup_injection()
    session_ctx = session_mem.get_startup_injection()
    kb_ctx = knowledge_base.load_for_context(max_chars=2000)

    if handoff_ctx:
        agent.context.inject_system(handoff_ctx)
    elif session_ctx:
        agent.context.inject_system(session_ctx)
    if kb_ctx:
        agent.context.inject_system(f"[PROJECT KNOWLEDGE]\n{kb_ctx}\n[END KNOWLEDGE]")

    # Initialise the task ledger for this session.
    global _task_ledger
    sessions_dir = root / ".nala" / "sessions"
    _task_ledger = TaskLedger(sessions_dir)

    # Initialise the agent runtime manager.
    global _agent_manager
    _agent_manager = AgentManager(
        config, root,
        orchestrator=agent,
        task_ledger=_task_ledger,
    )

    # Signal ready
    write_response({
        "type": "ready",
        "has_llm": config.has_llm(),
        "provider": config.llm_provider,
        "model": config.active_model(),
        "version": VERSION,
    })

    # Send proactive startup intelligence immediately after ready.
    try:
        intel = gather_startup_intelligence(root)
        write_response(intel)
    except Exception:
        log.debug("Startup intelligence gathering failed", exc_info=True)

    while True:
        try:
            line = await asyncio.to_thread(sys.stdin.buffer.readline)
            if not line:
                break  # EOF — Rust side closed stdin
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            req = json.loads(line)
            log.warning("IPC RECV type=%s id=%s", req.get("type"), req.get("id"))
            await handle_request(req, agent, root, config)
        except json.JSONDecodeError as e:
            write_response({"type": "error", "text": f"JSON parse error: {e}"})
        except Exception as e:
            log.exception("IPC handler error")
            write_response({"type": "error", "text": f"IPC error: {e}"})

    # Graceful shutdown — write handoff, save memory, mark session complete.
    if agent._session:
        try:
            history = [{"role": m.role, "content": m.content}
                       for m in agent.context.messages]
            sid = (agent._session.current_meta.session_id
                   if agent._session.current_meta else "unknown")
            if history:
                # Write handoff document for continuity
                writer = HandoffWriter(root)
                writer.write(sid, "session_end", history)
                # Save session memory and extract knowledge
                session_mem = SessionMemory(root)
                record = session_mem.build_and_save(sid, history)
                knowledge_base = KnowledgeBase(root)
                knowledge_base.extract_from_session(record.to_markdown())
        except Exception as e:
            log.debug("Shutdown handoff/memory save failed: %s", e)
        agent._session.complete()


def main() -> None:
    """Entry point: parse optional --root arg and run the IPC loop."""
    import argparse
    parser = argparse.ArgumentParser(description="Nala Python IPC server")
    parser.add_argument("--root", default=None, help="Project root directory")
    args = parser.parse_args()
    asyncio.run(run_ipc_loop(args.root))


if __name__ == "__main__":
    main()
