from pathlib import Path

from nala_orchestrator.cli import _audit_report_from_findings, _match_mission_focus
from nala_orchestrator.sessions.manager import SessionManager
from nala_orchestrator.sessions.missions import MissionGenerator


def test_audit_report_from_saved_findings_and_focus_matching(tmp_path: Path) -> None:
    session = SessionManager(tmp_path)
    meta = session.new_session()
    session.update_meta(total_files=12, total_symbols=34)

    findings_raw = [
        {
            "perspective_name": "complexity",
            "summary": "Complex functions were found.",
            "findings": [
                {
                    "title": "High complexity: build_prompt",
                    "description": "This function is difficult to maintain.",
                    "file_path": "src/agent.py",
                    "start_line": 42,
                    "severity": "high",
                    "perspective": "complexity",
                    "suggestion": "Split the function into smaller helpers.",
                }
            ],
        }
    ]

    report = _audit_report_from_findings(session, findings_raw)

    assert report.project_name == meta.project_name
    assert report.session_id == meta.session_id
    assert report.total_files == 12
    assert report.total_symbols == 34
    assert len(report.findings) == 1
    assert report.findings[0].title == "High complexity: build_prompt"
    assert report.perspectives_run == ["complexity"]

    missions = MissionGenerator().generate_all(report)
    assert missions
    assert _match_mission_focus(missions[0], "build_prompt")
    assert _match_mission_focus(missions[0], "src/agent.py")
    assert not _match_mission_focus(missions[0], "database")
