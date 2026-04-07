from pathlib import Path

from nala_orchestrator.context.compactor import Compactor
from nala_orchestrator.context.config import CompactionConfig
from nala_orchestrator.context.counter import TokenCounter
from nala_orchestrator.context.detector import OpportunityDetector, Priority
from nala_orchestrator.memory.knowledge import KnowledgeBase


def test_compaction_config_loads_from_project_file(tmp_path: Path) -> None:
    nala_dir = tmp_path / ".nala"
    nala_dir.mkdir()
    (nala_dir / "config.toml").write_text(
        (
            "[context]\n"
            "soft_threshold = 0.5\n"
            "hard_threshold = 0.75\n"
            "critical_threshold = 0.88\n"
            "keep_recent_turns = 3\n"
        ),
        encoding="utf-8",
    )

    config = CompactionConfig.from_project_root(tmp_path)

    assert config.soft_threshold == 0.5
    assert config.hard_threshold == 0.75
    assert config.critical_threshold == 0.88
    assert config.keep_recent_turns == 3
    assert config.level_for(88.0) == "critical"


def test_opportunity_detector_respects_custom_thresholds_and_breakpoints() -> None:
    detector = OpportunityDetector()
    cfg = CompactionConfig(soft_threshold=0.5, hard_threshold=0.7, critical_threshold=0.9)
    detector.mark_user_message("Review auth middleware")
    detector.mark_user_message("Refactor session cache")
    detector.mark_subtask_complete()

    opp = detector.evaluate(
        utilization_pct=72.0,
        history_len=6,
        min_turns=4,
        config=cfg,
        latest_user_message="Refactor session cache",
    )

    assert opp is not None
    assert opp.priority == Priority.HIGH
    assert "Sub-task completed" in opp.reason
    assert opp.safe is True


def test_compactor_preserves_focus_relevant_turns() -> None:
    history = [
        {"role": "user", "content": "Look at auth middleware and session cache"},
        {"role": "assistant", "content": "Investigating auth middleware behavior"},
        {"role": "user", "content": "Also review billing webhooks"},
        {"role": "assistant", "content": "Billing webhook path is separate"},
        {"role": "user", "content": "Need final recommendation"},
        {"role": "assistant", "content": "Summarizing current findings"},
    ]

    compacted, result = Compactor(keep_recent=2).compact(history, focus="auth middleware")
    preserved_text = "\n".join(str(msg["content"]) for msg in compacted)

    assert len(compacted) >= 3
    assert "auth middleware" in preserved_text.lower()
    assert "Preserved" in result.summary


def test_token_counter_separates_context_history_and_tool_outputs() -> None:
    counter = TokenCounter(model="default")
    tool_output = "\n".join([
        *(f"line {idx}" for idx in range(1, 21)),
        "stderr: warning output",
    ])
    history = [
        {"role": "user", "content": "Please inspect the login flow."},
        {"role": "assistant", "content": "I found the issue in auth.py and can fix it."},
        {"role": "tool", "content": tool_output},
    ]

    usage = counter.measure_conversation(
        system_prompt="You are Nala.",
        history=history,
        retrieved_context="def login():\n    return authenticate()",
    )

    assert usage.system_tokens > 0
    assert usage.context_tokens > 0
    assert usage.history_tokens > 0
    assert usage.tool_output_tokens > 0
    assert usage.total_tokens == (
        usage.system_tokens
        + usage.context_tokens
        + usage.history_tokens
        + usage.tool_output_tokens
    )


def test_knowledge_base_rebuilds_from_recent_session_memory(tmp_path: Path) -> None:
    session_dir = tmp_path / ".nala" / "memory" / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / "session-a.md").write_text(
        (
            "## Session: session-a\n\n"
            "### Completed\n"
            "- Implemented auth retry policy in the API service\n\n"
            "### Key Decisions\n"
            "- Prefer explicit service boundaries for auth components\n"
        ),
        encoding="utf-8",
    )

    kb = KnowledgeBase(tmp_path)
    refreshed = kb.rebuild_from_session_dir(session_dir, limit=5)
    summary = kb.get_summary()
    loaded = kb.load_for_context("auth service architecture", max_chars=2000)

    assert refreshed == 1
    assert "Total: 2 facts" in summary
    assert "auth retry policy" in loaded.lower() or "service boundaries" in loaded.lower()
