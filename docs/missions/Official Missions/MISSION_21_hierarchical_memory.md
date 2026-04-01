# Mission 21: Hierarchical Memory System

## Objective

Build a three-tier memory system (short-term, medium-term, long-term) that gives Nala's agents persistent knowledge across sessions, survives context compaction, and gets smarter over time. After this mission, when a developer starts a new session, Nala already knows their project's architecture, coding conventions, previous analysis findings, and what they were working on last time.

## Why This Matters

LLMs are stateless. Every API call starts from zero. Without a memory system, every session begins with "who am I and what is this project?" That is a waste of tokens, a waste of time, and a frustrating experience. Claude Code solved this partially with CLAUDE.md (manual) and Session Memory (automatic). But a purpose-built coding analysis tool like Nala can do much better because it already has structured data about the codebase (the graph, the metrics, the session history) that can be compressed into memory artifacts far more efficiently than raw conversation logs.

The research is clear: hierarchical memory (short/medium/long term, each with different retention and compression characteristics) outperforms flat memory. A GitHub issue documenting 59 compaction events over 26 days demonstrated that without persistent memory, critical context is lost repeatedly and the user must re-teach the agent the same things over and over. Nala eliminates this problem.

## Architecture

### Layer 1: Short-Term Memory (Working Context)

This is the current conversation history plus injected codebase context. It lives entirely in the LLM's context window. It is the highest fidelity (verbatim text) but the shortest lived (lost on compaction or session end). The context window management system from Mission 20 handles this layer.

### Layer 2: Medium-Term Memory (Session Memory)

This is a structured summary of each session that persists to disk. It is created automatically during and at the end of each session. It contains compressed but accurate representations of: what was done, what decisions were made, what files were touched, what the agent learned, and what comes next.

Storage location: `.nala/memory/sessions/`
Format: Structured markdown files, one per session
Retention: Keep the last 30 sessions. Older sessions are archived into long-term memory.

### Layer 3: Long-Term Memory (Project Knowledge)

This is accumulated knowledge about the project that transcends any single session. It is built by extracting facts from medium-term session memories and from Nala's own analysis results. It includes: project architecture patterns, coding conventions, known tech debt areas, recurring issues, developer preferences, and historical analysis trends.

Storage location: `.nala/memory/knowledge/`
Format: Structured TOML or markdown files organized by topic
Retention: Indefinite, with periodic consolidation to merge related facts and remove outdated ones.

## Implementation Steps

### Step 1: Short-term memory manager (memory/short_term.py)

This wraps the context window management from Mission 20 and provides a clean API for the agent to query "what do I currently know?"

Methods:
- `get_current_context() -> dict`: Returns the current working context organized by category (system, conversation, codebase, tools)
- `inject_context(content: str, category: str)`: Adds content to the working context
- `get_relevant_context(query: str) -> str`: Given a natural language query, returns the most relevant content from the current context. Uses keyword matching and recency weighting.

### Step 2: Medium-term session memory (memory/session_memory.py)

Build a `SessionMemory` class that runs in the background during every agent session:

**Background Summarizer**: After every 3-5 conversation turns, update a running session summary. The summary is structured:

```markdown
## Session: 2026-03-31 14:30

### Objective
Refactor the authentication module to reduce cyclomatic complexity

### Completed
- Analyzed src/auth/login.rs: CC=28, 4 high-complexity functions identified
- Split process_login() into validate_credentials(), create_session(), send_welcome()
- Updated 3 test files to cover new functions

### Key Decisions
- Chose to keep session tokens in Redis rather than JWTs (performance reasons)
- Error handling uses Result<T, AuthError> pattern consistently

### Current State
- File src/auth/login.rs is saved with changes
- Tests passing: 47/47
- Remaining: process_logout() still needs refactoring (CC=15)

### Open Questions
- Should we extract the email service into its own module?

### Developer Preferences Observed
- Prefers explicit error types over anyhow
- Likes small functions (< 30 lines)
- Runs tests after every change
```

**Session Save**: At session end (or before compaction), save the summary to `.nala/memory/sessions/<timestamp>.md`.

**Session Recall**: At session start, load the most recent session summary (or the most relevant one based on what the user says) into the context. This gives the agent continuity: "Last session, you were refactoring the auth module. process_logout() still needs work."

### Step 3: Long-term project knowledge (memory/knowledge.py)

Build a `KnowledgeBase` class that accumulates project-level knowledge:

**Fact Extraction**: After each session, extract durable facts from the session memory and store them in the knowledge base. Facts are categorized:

- `architecture.md`: High-level project structure, key patterns, technology choices
- `conventions.md`: Coding style, naming conventions, error handling patterns, testing approach
- `tech_debt.md`: Known issues, complexity hotspots, areas needing refactoring
- `developer_prefs.md`: How this developer likes to work (preferences observed across sessions)
- `analysis_history.md`: Trend data from analysis sessions (is complexity going up or down?)

**Fact Consolidation**: Periodically (every 10 sessions), review the knowledge base for:
- Duplicates (merge them)
- Contradictions (keep the newer fact, note the change)
- Outdated facts (mark as potentially stale if the related code has changed significantly)

**Knowledge Loading**: At session start, load relevant knowledge based on what the user is working on. If they open the auth module, load architecture facts about auth and any tech debt notes related to auth. Do not load everything; load only what is relevant. This is the "just-in-time context retrieval" pattern.

### Step 4: Memory compression using Smart Strip (memory/compression.py)

Implement a "Smart Strip" compression technique (inspired by Erold) that reduces memory artifacts to their essential facts:

1. Classify every fact as either self-identifying (bare values like file paths, function names, error codes that are unambiguous on their own) or context-dependent (values that need one disambiguating word)
2. Strip all conversational filler, hedging, and redundancy
3. Preserve the exact names, paths, numbers, and decisions
4. Produce output that survives re-compression without drift (compressing an already-compressed summary produces the same output)

Example:
- Before: "We decided that it would probably be best to use the Result<T, AuthError> pattern for error handling in the auth module because it gives us more explicit control over error types compared to using anyhow, which was the other option we considered."
- After: "Auth module: Result<T, AuthError> for errors (explicit types, not anyhow)"

Target 60-70% token reduction while preserving 100% of the factual content.

### Step 5: Memory-aware session startup

When a new session begins, Nala assembles the agent's starting context from all three memory layers:

1. **System prompt** (fixed): Nala's personality, capabilities, and rules
2. **Long-term knowledge** (from knowledge base): Architecture, conventions, preferences relevant to the current working directory
3. **Medium-term recall** (from session memory): The most recent session summary, plus any other recent sessions working on the same files
4. **Short-term context** (from indexer): Current file structure, recent changes, any pending tasks from the last session

This assembled context replaces the blank-slate startup that most tools suffer from.

### Step 6: Wire into the TUI

Add commands:
- `/memory`: Show what Nala remembers about this project (knowledge base summary)
- `/memory sessions`: List recent sessions with one-line summaries
- `/memory forget <topic>`: Remove specific knowledge (privacy/correction)
- `/memory refresh`: Re-extract knowledge from recent sessions

Show in the boot sequence:
```
Nala v0.1.0 | Loading project: beam/
  ✓ Loaded project knowledge (12 facts)
  ✓ Recalled last session: "Auth module refactoring" (2 hours ago)
  ✓ Indexed 1,247 files (0 changed since last session)

Ready. Last time you were working on process_logout() in src/auth/login.rs.
```

### Step 7: Write tests

- Test that session memory accurately captures key decisions from a simulated conversation
- Test that Smart Strip compression preserves all facts while reducing token count
- Test that knowledge extraction correctly categorizes facts
- Test that re-compression produces stable output (no drift)
- Test that session recall loads the right session based on working directory
- Test that knowledge consolidation merges duplicates correctly

## Acceptance Criteria

- New sessions start with relevant context from previous sessions (no blank slate)
- Session summaries accurately capture decisions, changes, and next steps
- Smart Strip compression achieves 60%+ token reduction without fact loss
- Knowledge base grows over time and remains accurate
- Re-compression is stable (no hallucination drift)
- Memory commands work in the TUI
- No source file exceeds 400 lines

## Estimated Complexity

Very High. The fact extraction and knowledge consolidation logic is the hardest part. Extracting structured facts from unstructured conversation requires either careful heuristics or LLM-assisted extraction (which itself consumes tokens). The Smart Strip compression needs careful testing to ensure it truly preserves all facts.
