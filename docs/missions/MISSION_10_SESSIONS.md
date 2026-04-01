# Mission 10: Session Management

## Objective

Build the session management system that saves, loads, and resumes analysis sessions. A session is a time-stamped directory containing: the conversation history, perspective findings, generated mission documents, and project snapshot metadata. After this mission, a developer can close Nala, come back three days later, and pick up exactly where they left off.

## Why This Matters

Code analysis is not a one-shot operation. A developer might spend an hour exploring complexity findings, then need to context-switch. Without persistence, all that context is lost on exit. With sessions, Nala accumulates knowledge about a project over time — findings from last week inform this week's review, and the AI has the full conversation history to reason from.

This is inspired by Claude Code's conversation persistence and OpenCode's session model.

## Context

Sessions are stored in `.nala/sessions/{timestamp}/`. The Python `SessionManager` creates and manages these directories. The Rust TUI exposes `/session list`, `/session load <id>`, and `/session resume` commands. The `AppMode::Viewing` state is used when browsing a past session report.

## Implementation Steps

### Step 1: Session schema

A session directory contains:
```
.nala/sessions/2025-01-15T14-30-00/
├── session.json          # metadata (id, timestamp, project_root, summary)
├── conversation.jsonl    # one JSON object per turn {role, content, timestamp}
├── findings.json         # serialised PerspectiveResult list from last analysis
├── mission.md            # AI-generated mission document (if generated)
└── snapshot.json         # {total_files, total_symbols, git_branch, git_commit}
```

The `session.json` schema:
```json
{
  "id": "2025-01-15T14-30-00",
  "project_root": "/home/user/myproject",
  "created_at": "2025-01-15T14:30:00Z",
  "last_active": "2025-01-15T16:45:00Z",
  "turn_count": 12,
  "summary": "Investigated authentication module complexity..."
}
```

### Step 2: SessionManager (sessions/manager.py)

Create `nala_orchestrator/sessions/manager.py`:

```python
class SessionManager:
    def __init__(self, project_root: Path):
        self.root = project_root
        self.sessions_dir = project_root / ".nala" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._current: Optional[Session] = None

    def create(self) -> "Session":
        """Create a new session with a timestamp-based ID."""

    def load(self, session_id: str) -> "Session":
        """Load a session by ID. Raises SessionNotFoundError if missing."""

    def list_sessions(self, limit: int = 20) -> list[SessionMeta]:
        """Return sessions sorted by last_active desc."""

    def current(self) -> Optional["Session"]:
        return self._current

    def set_current(self, session: "Session") -> None:
        self._current = session
```

### Step 3: Session class (sessions/session.py)

```python
class Session:
    def __init__(self, session_dir: Path, meta: SessionMeta):
        self.dir = session_dir
        self.meta = meta
        self._conversation: list[Turn] = []

    def append_turn(self, role: str, content: str) -> None:
        """Add a turn and immediately flush to conversation.jsonl."""

    def save_findings(self, results: list[PerspectiveResult]) -> None:
        """Serialise and write findings.json."""

    def load_findings(self) -> list[PerspectiveResult]:
        """Deserialise findings from findings.json, or [] if missing."""

    def save_mission(self, content: str) -> None:
        """Write mission.md."""

    def save_snapshot(self, files: int, symbols: int,
                      git_branch: str = "", git_commit: str = "") -> None:
        """Write snapshot.json."""

    def get_conversation_history(self) -> list[Turn]:
        """Load all turns from conversation.jsonl."""

    def update_last_active(self) -> None:
        """Update last_active in session.json to now."""
```

Implement `append_turn` with atomic writes (write to `.tmp` file, then rename) to avoid corruption on crash.

### Step 4: IPC integration

Add session-related request types to `cli.py`:

- `list_sessions` → returns `{id, summary, last_active, turn_count}` for each
- `load_session {"session_id": "..."}` → loads conversation history into agent
- `save_turn {"role": "...", "content": "..."}` → appends to current session
- `new_session` → creates a new session and sets it as current

When `AgentOrchestrator` handles a `query`, it should:
1. Ensure a current session exists (create one if not)
2. Append the user turn before sending to LLM
3. Append the assistant response after streaming completes

### Step 5: Rust TUI integration

Add session commands to `handle_slash_command` in `app.rs`:
- `/session` or `/session list` — request session list, display in message log
- `/session new` — create a new session
- `/session load <id>` — load a past session (switches to `AppMode::Viewing`)

Add a `session_panel` component to `ui/session_panel.rs` (the panel toggled by Ctrl+E) that shows the 10 most recent sessions with their summaries. Clicking (or pressing Enter on) a session loads it.

### Step 6: Session resumption

When loading a past session, the `AgentOrchestrator` reconstructs its `conversation_history` from `conversation.jsonl`. This means the LLM has full context of the previous conversation and can answer follow-up questions ("what did we find in the auth module last time?").

Inject a system message at the start of a resumed session:
```
[Session resumed: {session_id}. Previous conversation had {N} turns. Last active: {date}.]
```

### Step 7: Auto-save on exit

When `App.should_quit` becomes true, send a `close_session` IPC message that triggers `session.update_last_active()` and flushes any pending state. The bridge task should handle this before dropping stdin.

## Acceptance Criteria

- New session is created automatically on first query if none exists
- Session is resumed correctly with full conversation history
- `conversation.jsonl` is never corrupted (atomic writes)
- `/session list` shows sessions sorted by last active
- Session panel (Ctrl+E) renders a scrollable list of recent sessions
- Findings and mission docs persist correctly across restarts
- No file exceeds 400 lines

## Estimated Complexity

Medium. The main challenge is the atomic write pattern and the IPC message roundtrip for session state synchronisation.
