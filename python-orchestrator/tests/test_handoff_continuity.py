import json
from pathlib import Path

from nala_orchestrator.handoff import HandoffDocument, HandoffReader, HandoffWriter


_DEF_HISTORY = [
    {"role": "user", "content": "Implement context window compaction for auth."},
    {
        "role": "assistant",
        "content": "Implemented auth compaction flow\nNext: add continuity tests",
    },
]


def test_handoff_reader_skips_corrupt_latest_file(tmp_path: Path) -> None:
    handoff_dir = tmp_path / ".nala" / "memory" / "handoffs"
    handoff_dir.mkdir(parents=True)

    valid_doc = HandoffDocument.create("session-ok", "manual")
    valid_doc.objective = "Recover latest valid handoff"
    valid_doc.completed_actions = ["Implemented resilient handoff load"]
    (handoff_dir / "2026-01-01_10-00-00.json").write_text(valid_doc.to_json(), encoding="utf-8")
    (handoff_dir / "2026-01-02_10-00-00.json").write_text("{broken json", encoding="utf-8")

    reader = HandoffReader(tmp_path)
    loaded = reader.load_latest()

    assert loaded is not None
    assert loaded.session_id == "session-ok"
    assert loaded.objective == "Recover latest valid handoff"



def test_handoff_reader_returns_empty_chain_for_invalid_shape(tmp_path: Path) -> None:
    handoff_dir = tmp_path / ".nala" / "memory" / "handoffs"
    handoff_dir.mkdir(parents=True)
    (handoff_dir / "chain.json").write_text(json.dumps({"unexpected": True}), encoding="utf-8")

    reader = HandoffReader(tmp_path)

    assert reader.get_continuity_chain() == []



def test_handoff_writer_deduplicates_chain_entries(tmp_path: Path) -> None:
    writer = HandoffWriter(tmp_path)
    doc = HandoffDocument.create("session-1", "manual")
    doc.timestamp = "2026-01-01T10:00:00"
    doc.objective = "Verify deduplication"
    doc.completed_actions = ["Implemented duplicate guard"]

    writer._update_chain(doc)
    writer._update_chain(doc)

    chain_path = tmp_path / ".nala" / "memory" / "handoffs" / "chain.json"
    chain = json.loads(chain_path.read_text(encoding="utf-8"))

    assert len(chain) == 1
    assert chain[0]["session_id"] == "session-1"



def test_handoff_writer_and_reader_round_trip_startup_injection(tmp_path: Path) -> None:
    writer = HandoffWriter(tmp_path)
    writer.write("session-rt", "manual", _DEF_HISTORY, modified_files=["src/auth.py"])

    reader = HandoffReader(tmp_path)
    injection = reader.get_startup_injection()

    assert "RESUMING FROM HANDOFF" in injection
    assert "Objective:" in injection
    assert "src/auth.py" in injection
