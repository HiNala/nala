# Mission 13: Inline Agent Actions

## Objective

Enable Nala to not just analyse and suggest, but to act: apply code transformations, generate new files, run shell commands, and confirm with the user before making changes. After this mission, a developer can say "refactor the `authenticate()` function to use the repository pattern" and Nala will produce a diff and apply it on confirmation.

## Why This Matters

The gap between "here's what you should do" and "I've done it" is enormous in developer productivity. Cursor, Claude Code, and Aider all demonstrate that AI-applied edits dramatically outperform AI-only suggestions. Nala closing this gap makes it a first-class coding assistant rather than a smart linter.

The key design constraint: **never apply changes without explicit user confirmation**. Every proposed change is shown as a diff in the TUI. The user presses `y` to apply or `n` to skip. This is non-negotiable.

## Context

Inline actions are implemented as a new `ActionExecutor` in the Python orchestration layer. The Rust TUI adds a `Confirming` mode that displays diffs and awaits confirmation. The IPC protocol gets new message types for proposing and confirming actions.

## Implementation Steps

### Step 1: Action schema

Define the action types the AI can propose:

```python
@dataclass
class EditAction:
    type: str = "edit"
    file_path: str
    old_content: str          # exact text to replace
    new_content: str          # replacement text
    description: str          # human-readable summary of the change

@dataclass
class CreateAction:
    type: str = "create"
    file_path: str
    content: str
    description: str

@dataclass
class DeleteAction:
    type: str = "delete"
    file_path: str
    description: str

@dataclass
class ShellAction:
    type: str = "shell"
    command: str
    description: str
    working_dir: str = "."
```

### Step 2: ActionExtractor (agents/action_extractor.py)

When the LLM produces a response, scan it for structured action blocks. Use a simple format that the LLM is prompted to produce:

````
<action type="edit" file="src/auth.py">
<old>
def authenticate(user, password):
    return hashlib.md5(password).hexdigest() == user.hash
</old>
<new>
def authenticate(user, password):
    return bcrypt.checkpw(password.encode(), user.password_hash)
</new>
<description>Replace MD5 with bcrypt for password verification</description>
</action>
````

The `ActionExtractor` parses these blocks from the LLM response text and returns a list of `Action` objects alongside the cleaned response text (with action blocks removed for display).

### Step 3: ActionExecutor (agents/action_executor.py)

```python
class ActionExecutor:
    def __init__(self, project_root: Path):
        self.root = project_root

    def preview(self, action: Action) -> str:
        """Return a human-readable diff/preview of what will change."""

    def apply(self, action: Action) -> ActionResult:
        """Apply the action. Returns success/failure with details."""

    def _apply_edit(self, action: EditAction) -> ActionResult:
        """Find old_content in file and replace with new_content."""

    def _apply_create(self, action: CreateAction) -> ActionResult:
        """Write new file. Fail if file already exists (no silent overwrites)."""

    def _apply_shell(self, action: ShellAction) -> ActionResult:
        """Run shell command with timeout (30s). Capture stdout/stderr."""
```

For `_apply_edit`: read the file, find the exact `old_content` string, replace with `new_content`, write back. If `old_content` is not found, return a `ActionResult(success=False, error="old content not found in file")` — never apply a partial match.

### Step 4: IPC protocol additions

New message types in `cli.py`:

- `query_with_actions` — same as `query` but the LLM is prompted to produce action blocks; response includes extracted actions
- `apply_action {"action_id": "..."}` — apply a previously proposed action
- `skip_action {"action_id": "..."}` — mark action as skipped

Response types:
- `proposed_action {"action_id": "...", "type": "...", "preview": "...", "description": "..."}` — sent after streaming the text response
- `action_applied {"action_id": "...", "success": true/false, "message": "..."}` — sent after apply

### Step 5: Rust TUI — Confirming mode

Add `AppMode::Confirming` to the enum. When a `proposed_action` event arrives:
1. Switch to `Confirming` mode
2. Display the action preview (diff format) in the message area
3. Show a confirmation prompt: `[y] Apply  [n] Skip  [a] Apply all  [q] Skip all`

Key bindings in `Confirming` mode:
- `y` / `Enter` — apply current action, move to next
- `n` — skip current action, move to next
- `a` — apply all remaining actions without further prompts
- `q` / `Esc` — skip all remaining actions

### Step 6: Diff rendering (ui/diff.rs)

Create `nala-tui/src/ui/diff.rs` to render a unified diff in the TUI:
- Removed lines: red background with `-` prefix
- Added lines: green background with `+` prefix
- Context lines: default styling
- File header: bold with file path

Use Ratatui's `Text` and `Span` with style modifiers. Cap the preview at 40 lines (show `... N more lines` if longer).

### Step 7: Safety constraints

Hard limits on inline actions (non-negotiable):
- Never delete files without confirmation
- Never execute shell commands outside the project root
- Shell commands time out after 30 seconds
- Shell commands are never run as root/admin
- A session has a maximum of 50 applied actions (prevents runaway loops)
- Action history is saved to the session for audit

### Step 8: Action prompting

Update `SYSTEM_PROMPT_TEMPLATE` in `AgentOrchestrator` to instruct the LLM on how to produce action blocks. The prompt must be precise about the exact XML format, when to produce actions (only when asked to make changes, not for analysis queries), and that the user will review before applying.

## Acceptance Criteria

- Edit actions correctly replace exact text in files
- Create actions refuse to overwrite existing files
- Shell actions are sandboxed to the project directory
- Diff preview renders correctly in the TUI
- User confirmation is required before any file is modified
- Action history is saved to the session
- No file exceeds 400 lines

## Estimated Complexity

High. The action extraction, safe application, and TUI confirmation flow all have correctness requirements that are critical to user trust.
