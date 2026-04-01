# Mission 22: Session Handoff and Continuity Protocol

## Objective

Build the session handoff system that ensures zero-loss continuity when a context window fills up or a session ends. Before compaction or session close, Nala writes a structured handoff document that captures exactly where things stand, what was in progress, what files are dirty, and what the next steps are. When the next session (or compacted context) picks up, it reads this handoff and resumes seamlessly. The developer should never have to re-explain what they were doing.

## Why This Matters

The most frustrating moment in AI-assisted coding is when the agent "forgets" what it was doing. You have been working for an hour, making steady progress on a complex refactor, and then the context compacts or the session ends. The next interaction starts with the agent acting like it has never seen your project before. Every developer who has used Claude Code, Cursor, or any long-session AI tool has experienced this.

Claude Code's approach (CLAUDE.md + Session Memory + /compact with focus) is good but manual. The developer has to remember to compact with the right focus, maintain their CLAUDE.md, and hope the auto-summary captures the right details. Nala automates the entire handoff process, treating it as a first-class system concern rather than an afterthought.

The pattern is inspired by how engineering teams do shift handoffs: the outgoing shift writes a structured status report that the incoming shift reads before touching anything. Nala does this between its own sessions automatically.

## Implementation Steps

### Step 1: Handoff document format (handoff/schema.py)

Define the `HandoffDocument` data structure:

```python
@dataclass
class HandoffDocument:
    timestamp: str               # When this handoff was created
    session_id: str              # Which session created it
    trigger: str                 # "compaction" | "session_end" | "manual" | "threshold"
    
    # What was the user trying to accomplish?
    objective: str               # Plain English description of the current goal
    
    # What is done?
    completed_actions: list[str] # List of things that were finished
    
    # What is in progress right now?
    in_progress: InProgressState # The critical "do not lose this" section
    
    # What files were touched?
    modified_files: list[ModifiedFile]  # path, change_description, saved (bool)
    
    # What decisions were made?
    decisions: list[Decision]    # decision text, rationale, affected files
    
    # What should happen next?
    next_steps: list[str]        # Ordered list of what to do next
    
    # What context is needed?
    critical_context: list[str]  # Key facts the next session MUST know
    
    # What should NOT be done?
    constraints: list[str]       # Rules, warnings, things to avoid

@dataclass
class InProgressState:
    current_task: str            # What the agent was actively doing
    current_file: str            # Which file was being worked on
    current_function: str        # Which function, if applicable
    pending_changes: list[str]   # Changes planned but not yet applied
    blocking_issues: list[str]   # Anything that was blocking progress

@dataclass
class ModifiedFile:
    path: str
    change_summary: str
    is_saved: bool
    has_tests: bool              # Were tests updated for this change?

@dataclass
class Decision:
    text: str
    rationale: str
    affected_files: list[str]
```

### Step 2: Pre-compaction handoff writer (handoff/writer.py)

Build a `HandoffWriter` that is called automatically before any compaction or session end:

1. Analyze the current conversation to extract the handoff fields
2. Use the background summary from Mission 20 as a starting point
3. Enrich with file modification tracking (which files were read, which were written)
4. Enrich with the current task state from the agent orchestrator
5. Write the handoff document to `.nala/memory/handoffs/<timestamp>.json` and a human-readable `.md` version

The writer should work even if called during an unexpected crash or interrupt. It saves incrementally, so even a partial handoff is better than none.

### Step 3: Post-compaction handoff reader (handoff/reader.py)

Build a `HandoffReader` that is called at the start of every new session or after every compaction:

1. Find the most recent handoff document
2. Parse it into structured data
3. Construct a concise context injection that tells the agent:
   - "You were working on X"
   - "You completed A, B, C"
   - "You were in the middle of D in file E"
   - "The key decisions so far are F and G"
   - "Next steps are H, I, J"
4. Inject this as a high-priority message at the start of the new context
5. If the handoff indicates unsaved changes, alert the user immediately

The injected context should be as compact as possible (target under 2,000 tokens for a typical handoff) while preserving all critical information.

### Step 4: Automatic handoff triggers

Wire the handoff writer to trigger automatically at these points:
- Before any context compaction (Mission 20 calls the handoff writer before compacting)
- When the user types `/quit` or Ctrl+C
- When the session has been idle for more than 10 minutes (save a handoff just in case)
- When the user manually types `/handoff` to force a save
- At the hard threshold (80% context utilization), write a handoff preemptively

### Step 5: Handoff quality validation

After writing a handoff, run a quick self-check:
- Does the handoff mention at least one objective?
- Does it list at least one completed action or in-progress task?
- Are all modified files accounted for?
- Is the handoff under 3,000 tokens? (If over, compress it)

If the handoff fails validation, log a warning but save it anyway (a bad handoff is better than no handoff).

### Step 6: Cross-session continuity chain

Maintain a chain of handoffs so that a long multi-session project has a traceable history:

`.nala/memory/handoffs/chain.json` contains an ordered list of handoff references with their objectives and outcomes. This lets Nala display a project timeline:

```
Project History:
  Session 1 (Mon 10am): Set up auth module structure ✓
  Session 2 (Mon 2pm):  Implement login flow ✓  
  Session 3 (Tue 9am):  Refactor complexity in login [in progress]
    └─ Compaction 1: Completed validate_credentials extraction
    └─ Compaction 2: Completed create_session extraction  
    └─ Current: Working on process_logout refactor
```

### Step 7: Wire into the TUI

Add commands:
- `/handoff`: Manually create a handoff document
- `/handoff show`: Display the most recent handoff
- `/handoff history`: Show the continuity chain

Show on session start:
```
Resuming from handoff (2 hours ago):
  Objective: Refactor auth module complexity
  Last action: Extracted create_session() from process_login()
  Next step: Refactor process_logout() (CC: 15)
  Modified files: src/auth/login.rs (saved ✓), tests/auth_test.rs (saved ✓)
```

### Step 8: Write tests

- Simulate a 20-turn conversation, trigger a handoff, and verify all fields are populated
- Write a handoff, simulate a new session, and verify the reader injects the correct context
- Test the continuity chain across 5 simulated sessions
- Test handoff under crash conditions (partial write)
- Test that handoff injection stays under 2,000 tokens

## Acceptance Criteria

- Handoffs capture all critical state (objective, progress, files, decisions, next steps)
- Post-compaction sessions resume coherently without the user repeating themselves
- The continuity chain provides accurate project history
- Handoff injection uses fewer than 2,000 tokens
- Automatic triggers fire at all the right moments
- No source file exceeds 400 lines

## Estimated Complexity

High. The challenge is extracting structured handoff data from an unstructured conversation accurately. The "in progress" detection (knowing the agent is mid-task) requires integration with the agent orchestrator from Mission 13.
