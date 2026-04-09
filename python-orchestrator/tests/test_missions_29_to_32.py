"""Tests for Missions 29-32: project detector, shell bus, classifier, planner, synthesizer."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Mission 30: Project detector ──────────────────────────────────────────

class TestProjectDetector:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def _file(self, name: str, content: str = "") -> None:
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        (self.root / name).write_text(content, encoding="utf-8")

    def test_detects_rust(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        self._file("Cargo.toml", '[package]\nname = "my_crate"\nversion = "0.1.0"\n')
        info = ProjectDetector(self.root).detect()
        assert info.is_project
        assert info.project_type == "rust"
        assert info.project_name == "my_crate"

    def test_detects_python(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        self._file("pyproject.toml", '[project]\nname = "my_pkg"\n')
        info = ProjectDetector(self.root).detect()
        assert info.is_project
        assert "python" in info.languages

    def test_detects_node(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        self._file("package.json", json.dumps({"name": "my-app", "dependencies": {"react": "^18"}}))
        info = ProjectDetector(self.root).detect()
        assert info.is_project
        assert info.project_type == "node"
        assert "react" in info.frameworks

    def test_detects_multi_project(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        (self.root / "proj_a").mkdir()
        (self.root / "proj_a" / "Cargo.toml").write_text('[package]\nname="a"\n', encoding="utf-8")
        (self.root / "proj_b").mkdir()
        (self.root / "proj_b" / "package.json").write_text('{"name":"b"}', encoding="utf-8")
        info = ProjectDetector(self.root).detect()
        assert not info.is_project
        assert info.project_type == "multi"
        assert len(info.sub_projects) >= 2

    def test_detects_unknown(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        info = ProjectDetector(self.root).detect()
        assert not info.is_project
        assert info.project_type == "unknown"

    def test_detects_git_branch(self):
        from nala_orchestrator.core.project_detector import ProjectDetector
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        self._file("Cargo.toml", '[package]\nname="x"\n')
        info = ProjectDetector(self.root).detect()
        assert info.has_git
        assert info.git_branch == "main"

    def test_lsp_availability(self):
        from nala_orchestrator.core.project_detector import (
            ProjectDetector, lsp_availability, lsp_install_hint
        )
        self._file("Cargo.toml", '[package]\nname="x"\n')
        info = ProjectDetector(self.root).detect()
        avail = lsp_availability(info)
        assert "rust" in avail
        hint = lsp_install_hint("rust")
        assert "rust-analyzer" in hint.lower() or "rustup" in hint.lower()


# ── Mission 31: Shell message bus ─────────────────────────────────────────

class TestShellMessageBus:
    def setup_method(self):
        self.tmp = tempfile.mkdtemp()
        self.nala_dir = Path(self.tmp) / ".nala"
        self.nala_dir.mkdir()

    def _bus(self):
        from nala_orchestrator.shell.message_bus import ShellMessageBus
        return ShellMessageBus(self.nala_dir)

    def test_post_and_replay(self):
        bus = self._bus()
        bus.post_text("nala", "Hello from nala")
        bus.post_text("security", "Found a bug")
        msgs = bus.replay()
        assert len(msgs) == 2
        assert msgs[0].source == "nala"
        assert msgs[1].content == "Found a bug"

    def test_approval_pending(self):
        bus = self._bus()
        mid = bus.post_approval("refactor", "Apply changes?", options=["y", "n"])
        pending = bus.get_pending_approvals()
        assert any(p.message_id == mid for p in pending)

    def test_respond_clears_pending(self):
        bus = self._bus()
        mid = bus.post_approval("refactor", "Apply?")
        bus.respond(mid, "y")
        pending = bus.get_pending_approvals()
        assert not any(p.message_id == mid for p in pending)

    def test_message_serialization(self):
        from nala_orchestrator.shell.message_bus import ShellMessage
        msg = ShellMessage(source="nala", content="test", message_type="status")
        restored = ShellMessage.from_json(msg.to_json())
        assert restored.source == "nala"
        assert restored.content == "test"
        assert restored.message_type == "status"


# ── Mission 31: Input router ───────────────────────────────────────────────

class TestInputRouter:
    def _router(self):
        from nala_orchestrator.shell.router import InputRouter
        return InputRouter()

    def _ctx(self, pending_id=None):
        from nala_orchestrator.shell.router import ShellContext
        return ShellContext(pending_approval_id=pending_id)

    def test_routes_approval_response(self):
        from nala_orchestrator.shell.router import RouteToApproval
        router = self._router()
        ctx = self._ctx(pending_id="abc123")
        result = router.route("y", ctx)
        assert isinstance(result, RouteToApproval)
        assert result.response == "y"
        assert result.message_id == "abc123"

    def test_routes_mention(self):
        from nala_orchestrator.shell.router import RouteToAgent
        router = self._router()
        result = router.route("@security check the tokens", self._ctx())
        assert isinstance(result, RouteToAgent)
        assert result.agent_id == "security"
        assert "tokens" in result.message

    def test_routes_command(self):
        from nala_orchestrator.shell.router import RouteToSystem
        router = self._router()
        result = router.route("/review --diff", self._ctx())
        assert isinstance(result, RouteToSystem)
        assert result.command == "/review --diff"

    def test_routes_free_text(self):
        from nala_orchestrator.shell.router import RouteToMainAgent
        router = self._router()
        result = router.route("how does auth work?", self._ctx())
        assert isinstance(result, RouteToMainAgent)
        assert "auth" in result.message

    def test_stop_detection(self):
        router = self._router()
        assert router.is_stop_command("/stop")
        assert router.is_stop_command("/cancel")
        assert not router.is_stop_command("/review")


# ── Mission 32: Task classifier ───────────────────────────────────────────

class TestTaskClassifier:
    def _classifier(self):
        from nala_orchestrator.orchestrator.classifier import TaskClassifier
        return TaskClassifier()

    def test_simple_question(self):
        c = self._classifier()
        t = c.classify("how does the auth flow work?")
        assert t.intent == "question"
        assert t.complexity == "simple"
        assert not t.needs_sub_agents

    def test_single_file_fix(self):
        c = self._classifier()
        t = c.classify("fix the bug in src/auth/login.rs")
        assert t.intent == "fix"
        assert t.complexity in {"single_file", "multi_file"}

    def test_multi_file_review(self):
        c = self._classifier()
        t = c.classify("review src/auth/ for security issues")
        assert t.intent == "review"
        assert t.needs_sub_agents

    def test_full_codebase(self):
        c = self._classifier()
        t = c.classify("review the entire codebase")
        assert t.complexity == "full_codebase"
        assert t.needs_sub_agents
        assert t.estimated_agents >= 3

    def test_review_slash_command(self):
        c = self._classifier()
        t = c.classify("/review")
        assert t.needs_sub_agents

    def test_explain_intent(self):
        c = self._classifier()
        t = c.classify("explain what this module does")
        assert t.intent in {"explain", "question"}
        assert not t.needs_sub_agents

    def test_plan_needed_for_large(self):
        c = self._classifier()
        t = c.classify("refactor the entire codebase")
        assert t.plan_needed


# ── Mission 32: Task planner ──────────────────────────────────────────────

class TestTaskPlanner:
    def _planner(self):
        from nala_orchestrator.orchestrator.planner import TaskPlanner
        return TaskPlanner()

    def _classify(self, text):
        from nala_orchestrator.orchestrator.classifier import TaskClassifier
        return TaskClassifier().classify(text)

    def test_full_review_plan(self):
        p = self._planner()
        task = self._classify("review the entire codebase")
        plan = p.plan(task)
        assert len(plan.waves) >= 1
        assert plan.total_tasks >= 2

    def test_multi_file_review_plan(self):
        p = self._planner()
        task = self._classify("review src/auth/ for issues")
        plan = p.plan(task)
        assert len(plan.waves) >= 1
        wave_tasks = plan.waves[0].tasks
        assert any(t.specialist_type in {"reviewer", "security"} for t in wave_tasks)

    def test_wave_dependencies(self):
        p = self._planner()
        task = self._classify("fix and refactor the entire codebase")
        plan = p.plan(task)
        # Waves after wave 1 should have depends_on set
        for wave in plan.waves[1:]:
            assert wave.depends_on is not None

    def test_plan_summary_non_empty(self):
        p = self._planner()
        task = self._classify("review src/")
        plan = p.plan(task)
        summary = plan.summary()
        assert len(summary) > 10

    def test_single_file_no_approval(self):
        p = self._planner()
        task = self._classify("explain src/main.py")
        plan = p.plan(task)
        assert not plan.requires_user_approval


# ── Mission 32: Result synthesizer ────────────────────────────────────────

class TestResultSynthesizer:
    def _synth(self):
        from nala_orchestrator.orchestrator.synthesizer import ResultSynthesizer
        return ResultSynthesizer()

    def _result(self, agent_id, findings=None, success=True):
        from nala_orchestrator.orchestrator.synthesizer import AgentResult
        return AgentResult(
            agent_id=agent_id,
            specialist_type="reviewer",
            success=success,
            summary=f"{agent_id} done",
            findings=findings or [],
            files_touched=["src/main.py"],
        )

    def test_basic_synthesis(self):
        s = self._synth()
        results = [
            self._result("r1", [{"severity": "high", "description": "issue", "file_path": "a.py", "start_line": 1}]),
            self._result("r2", [{"severity": "critical", "description": "bug", "file_path": "b.py", "start_line": 5}]),
        ]
        summary = s.synthesize(1, "Analysis", results)
        assert summary.successful == 2
        assert summary.findings_by_severity.get("high", 0) >= 1
        assert summary.findings_by_severity.get("critical", 0) >= 1

    def test_deduplication(self):
        s = self._synth()
        dup_finding = {"severity": "high", "file_path": "x.py", "start_line": 10, "rule_name": "R1", "description": "d"}
        results = [
            self._result("r1", [dup_finding]),
            self._result("r2", [dup_finding]),  # same finding from different agent
        ]
        summary = s.synthesize(1, "Analysis", results)
        # Should be deduplicated to 1
        assert sum(summary.findings_by_severity.values()) == 1

    def test_conflict_detection(self):
        s = self._synth()
        from nala_orchestrator.orchestrator.synthesizer import AgentResult
        r1 = AgentResult("a1", "refactor", True, "done", files_touched=["shared.py"])
        r2 = AgentResult("a2", "security", True, "done", files_touched=["shared.py"])
        synthesis = s.merge_waves("test", [], [r1, r2])
        assert "shared.py" in synthesis.conflicts

    def test_wave_persistence(self):
        s = self._synth()
        with tempfile.TemporaryDirectory() as tmp:
            nala_dir = Path(tmp)
            results = [self._result("r1")]
            out = s.save_wave_results(nala_dir, 1, results)
            assert out.exists()
            context = s.load_wave_context(nala_dir, 1)
            assert "reviewer" in context

    def test_format_for_display(self):
        s = self._synth()
        results = [self._result("r1", [{"severity": "critical", "description": "sec issue", "file_path": "f.py", "start_line": 1}])]
        summary = s.synthesize(1, "Wave 1", results)
        synthesis = s.merge_waves("test obj", [summary], results)
        display = synthesis.format_for_display()
        assert "critical" in display.lower() or "1" in display
