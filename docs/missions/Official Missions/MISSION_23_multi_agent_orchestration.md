# Mission 23: Multi-Agent Orchestration Engine

## Objective

Build the multi-agent orchestration system that lets Nala coordinate multiple AI agents working on different parts of a codebase simultaneously. Each agent operates in its own context window with its own memory, and they coordinate through a shared task list, file locking, and message passing. This is how Nala scales from "one developer talking to one agent" to "one developer directing a team of agents."

## Why This Matters

Single-agent workflows hit a hard ceiling. One agent, one context window, one task at a time. When you need to analyze an entire codebase from six perspectives, or refactor three modules simultaneously, or run a security audit while also writing tests, a single agent bottlenecks everything.

Claude Code's Agent Teams (launched with Opus 4.6) proved that multi-agent orchestration works in practice: a team lead coordinates teammates, each with their own context window, communicating via shared task lists and direct messages. Cursor 2.0 supports up to 8 parallel agents using git worktrees. The orchestration tools from the community (Conductor, Gas Town, Multiclaude) show that developers want this capability badly enough to build it themselves.

Nala's advantage is that it already has the code graph, the metrics, the session memory, and the analysis perspectives. It can decompose work intelligently because it understands the codebase's structure. Instead of the user manually assigning "you work on auth, you work on API, you work on tests," Nala can look at the dependency graph and figure out which modules can be worked on independently without conflicts.

## Architecture

### Roles

**Lead Agent**: The primary agent that the user interacts with directly. It plans work, decomposes tasks, assigns them to worker agents, and synthesizes results. The lead maintains the master view.

**Worker Agent**: A specialized agent that handles a specific task in its own context window. Workers have limited scope (specific files or modules), limited tools (read-only for analysis, read-write for refactoring), and their own memory. Workers report results back to the lead.

**Observer Agent** (optional): A passive agent that monitors the work of other agents for quality. It reviews proposed changes from workers before they are applied. This is the CodeRabbit-style review layer applied to agent-generated code.

### Communication

Agents communicate through three mechanisms:
1. **Shared Task List**: A structured list of tasks with status (pending, in_progress, completed, blocked), assignments, and dependencies
2. **Message Bus**: Agents can send targeted messages to each other (e.g., "I found that the auth module uses a custom session store, you'll need to account for this in the API layer")
3. **File Lock Registry**: Agents claim files before modifying them. If two agents need the same file, one waits or they coordinate through the lead.

## Implementation Steps

### Step 1: Task decomposition engine (agents/decomposer.py)

Build a `TaskDecomposer` that takes a high-level objective and breaks it into independent sub-tasks:

1. Analyze the objective against the code graph to identify which modules/files are involved
2. Use the dependency graph to find natural boundaries (modules that do not depend on each other can be worked on independently)
3. Assign each sub-task a scope (list of files), an objective, and a tool permission set
4. Identify dependencies between tasks (e.g., "the API task depends on the schema task completing first")
5. Return a `TaskPlan` with ordered, parallelizable task groups

Example:
```
User: "Run a full analysis and fix all critical findings"

TaskPlan:
  Wave 1 (parallel):
    Task A: Analyze complexity in src/auth/ (read-only)
    Task B: Analyze complexity in src/api/ (read-only)
    Task C: Analyze dependencies across all modules (read-only)
  
  Wave 2 (parallel, after Wave 1):
    Task D: Fix critical complexity in src/auth/login.rs (read-write, locked)
    Task E: Fix critical complexity in src/api/handler.rs (read-write, locked)
  
  Wave 3 (sequential, after Wave 2):
    Task F: Review all changes from Wave 2 (read-only, observer)
    Task G: Run tests and verify fixes (read-only)
```

### Step 2: Agent spawner (agents/spawner.py)

Build an `AgentSpawner` that creates worker agent instances:

Each worker agent gets:
- Its own LLM session (separate API call with its own context window)
- A scoped system prompt that defines its role and boundaries
- A subset of the codebase context (only the files relevant to its task)
- Access to specific tools (read-only for analysis, read-write for modifications)
- Its own short-term memory (conversation history within its context)

Workers run as async tasks using Python's asyncio, allowing true parallelism across API calls.

### Step 3: Shared task list (agents/task_list.py)

Build a `SharedTaskList` backed by a SQLite table (or a JSON file with file locking):

```python
@dataclass
class Task:
    id: str
    objective: str
    assigned_to: str          # agent ID
    status: str               # pending, in_progress, completed, blocked, failed
    scope: list[str]          # file paths this task operates on
    dependencies: list[str]   # task IDs that must complete first
    result_summary: str       # filled in when completed
    created_at: str
    completed_at: str
```

Methods:
- `claim_task(agent_id, task_id)`: Mark task as in_progress
- `complete_task(agent_id, task_id, result)`: Mark task as completed with result
- `block_task(agent_id, task_id, reason)`: Mark task as blocked
- `get_available_tasks(agent_id)`: Get tasks that are pending and have all dependencies met
- `get_all_tasks()`: Full task list for the lead to review

### Step 4: File lock registry (agents/file_locks.py)

Build a `FileLockRegistry` that prevents two agents from modifying the same file simultaneously:

- `acquire_lock(agent_id, file_path) -> bool`: Returns True if lock acquired, False if already locked
- `release_lock(agent_id, file_path)`: Release a lock
- `get_locks() -> dict[str, str]`: Map of locked files to agent IDs
- Locks auto-expire after 5 minutes of inactivity (prevents deadlocks from crashed agents)

### Step 5: Message bus (agents/messages.py)

Build a simple message passing system:

- `send_message(from_agent, to_agent, content)`: Send a message
- `get_messages(agent_id) -> list[Message]`: Get unread messages for an agent
- `broadcast(from_agent, content)`: Send a message to all agents

Messages are injected into the recipient agent's context at the start of its next turn. This is how agents share discoveries without needing shared context windows.

### Step 6: Lead agent orchestrator (agents/lead.py)

Build the `LeadAgent` that coordinates everything:

1. Receives the user's high-level objective
2. Calls the TaskDecomposer to create a TaskPlan
3. Presents the plan to the user for approval (or modification)
4. Spawns worker agents for each task wave
5. Monitors progress through the shared task list
6. Handles blocked tasks (reassign, modify scope, or escalate to user)
7. Collects results from completed tasks
8. Synthesizes a final summary for the user
9. Manages the handoff document (Mission 22) for the entire orchestration

### Step 7: Wire into the TUI

Add commands:
- `/team start <objective>`: Decompose the objective and start a multi-agent session
- `/team status`: Show the current task list with agent assignments and progress
- `/team pause`: Pause all worker agents
- `/team resume`: Resume paused agents
- `/team cancel`: Cancel all in-progress tasks

Show agent activity in the TUI:
```
Agent Team: Full codebase analysis and fixes
  Lead:     Planning complete, monitoring workers
  Worker A: [████████░░] Analyzing src/auth/ (65%)
  Worker B: [██████████] Analyzing src/api/ ✓ (3 critical findings)
  Worker C: [███░░░░░░░] Analyzing dependencies (30%)
  
  Tasks: 3/7 completed | 3 in progress | 1 pending
  Files locked: src/api/handler.rs (Worker B)
```

### Step 8: Write tests

- Test task decomposition produces valid, non-overlapping task scopes
- Test file locking prevents concurrent modifications
- Test message passing delivers messages to correct agents
- Test that worker agents respect their scope boundaries
- Test graceful handling of worker agent failures (timeout, API error)
- Simulate a 3-agent parallel workflow end-to-end

## Acceptance Criteria

- Tasks are decomposed intelligently using the code graph
- Worker agents run in parallel without file conflicts
- The shared task list accurately tracks progress
- File locks prevent concurrent modifications
- Agent failures are handled gracefully (retry, reassign, or report)
- The TUI shows real-time agent status
- Results are synthesized into a coherent summary
- No source file exceeds 400 lines

## Estimated Complexity

Very High. Multi-agent orchestration is one of the hardest problems in AI engineering. The task decomposition must be smart enough to avoid creating dependent tasks that deadlock. Worker agent failures must be handled without crashing the entire system. The message passing system must be reliable.
