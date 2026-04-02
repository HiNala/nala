from pathlib import Path

from nala_orchestrator.sessions.manager import SessionManager


def test_compare_sessions_reports_new_and_resolved_findings(tmp_path: Path) -> None:
    session = SessionManager(tmp_path)

    first = session.new_session()
    session.write_file(
        "findings.json",
        """
[
  {
    "perspective_name": "complexity",
    "findings": [
      {
        "title": "High complexity: alpha",
        "file_path": "src/a.py",
        "start_line": 10,
        "severity": "high"
      }
    ]
  }
]
""".strip(),
    )

    second = session.new_session()
    session.write_file(
        "findings.json",
        """
[
  {
    "perspective_name": "complexity",
    "findings": [
      {
        "title": "High complexity: beta",
        "file_path": "src/b.py",
        "start_line": 20,
        "severity": "critical"
      }
    ]
  }
]
""".strip(),
    )

    diff = session.compare_sessions(first.session_id, second.session_id)

    assert "Session comparison" in diff
    assert "New findings: 1" in diff
    assert "Resolved findings: 1" in diff
    assert "High complexity: beta" in diff
    assert "High complexity: alpha" in diff
