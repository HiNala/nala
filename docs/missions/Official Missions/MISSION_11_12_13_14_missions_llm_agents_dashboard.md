# Mission 11: Mission Document Auto-Generation

## Objective

Build the mission generator that takes analysis findings and automatically produces a series of self-contained mission documents, each describing a specific remediation task with clear objectives, context, acceptance criteria, and implementation guidance. These missions are designed to be handed to a coding agent like Claude Code or tackled by a human developer.

## Why This Matters

Analysis without action is just noise. The mission generator closes the gap between "we know what is wrong" and "here is exactly how to fix it." This is the workflow Brian uses with Beam and Igniwave: structured mission documents that coding agents can consume and execute. By automating the generation of these missions, Nala becomes a self-sustaining improvement loop.

## Implementation Steps

### Step 1: Mission template (sessions/missions.py)

Define a `MissionDocument` dataclass:
- mission_number (int)
- title (str)
- objective (str): One paragraph explaining what this mission accomplishes
- why_it_matters (str): Why this fix is important
- context (str): Background information, related findings, affected files
- implementation_steps (list[str]): Numbered plain-English steps
- acceptance_criteria (list[str]): How to verify the fix is correct
- affected_files (list[str]): File paths involved
- estimated_complexity (str): Low/Medium/High
- priority (str): Critical/High/Medium/Low

### Step 2: Mission generation logic

Create a `generate_missions(analysis_result: AnalysisResult) -> list[MissionDocument]` function that:

1. Groups findings by file or by logical unit (functions that call each other should be in the same mission)
2. Prioritizes by severity (Critical findings become missions first)
3. Merges related findings into single missions (if a function is both too complex AND untested, that is one mission, not two)
4. Generates plain-English implementation steps for each mission
5. Generates acceptance criteria from the finding details
6. Caps at a configurable maximum (default 20 missions per run, to avoid overwhelming the user)

### Step 3: LLM-enhanced mission generation (optional)

If an LLM provider is configured, pass the raw findings to the LLM to generate richer, more specific implementation guidance. The LLM receives the finding data plus relevant code snippets and produces more nuanced steps than rule-based generation alone. If no LLM is configured, the rule-based generator still produces useful missions.

### Step 4: Save missions to the session directory

Save each mission as a separate markdown file in the session directory:
- `.nala/sessions/<timestamp>/missions/MISSION_01_reduce_complexity_auth_module.md`
- `.nala/sessions/<timestamp>/missions/MISSION_02_remove_dead_code_utils.md`
- etc.

Also save an index file: `missions/INDEX.md` that lists all missions with their priority and status.

### Step 5: Wire into the TUI

After mission generation completes, display:
```
Generated 8 missions from 23 findings:
  [Critical] Mission 01: Reduce complexity in auth/login.rs (CC: 28)
  [High]     Mission 02: Break circular dependency between api/ and models/
  [High]     Mission 03: Add test coverage for payment processing
  ...

Missions saved to .nala/sessions/2026-03-31/missions/
```

## Acceptance Criteria

- Missions are generated from findings with correct priority ordering
- Related findings are merged into single missions (no redundant missions)
- Each mission is a complete, self-contained markdown document
- Missions can be read and executed by a coding agent without additional context
- No source file exceeds 400 lines

---

# Mission 12: LLM Provider Integration

## Objective

Build the LLM provider abstraction that lets Nala call AI models for deeper analysis, natural language queries, and intelligent mission generation. Support Anthropic (Claude), OpenAI, Google (Gemini), and local models via Ollama. The user picks their provider and model.

## Why This Matters

The LLM is what makes Nala an AI-powered tool rather than just a static analysis tool. With an LLM, Nala can explain why a piece of code is risky, suggest specific refactoring strategies, answer natural language questions about the codebase, and generate nuanced implementation guidance for missions. Without it, Nala is still useful (static analysis perspectives work without AI), but with it, Nala becomes transformative.

## Implementation Steps

### Step 1: Provider abstraction (llm/provider.py)

Create an abstract `LLMProvider` class:
- `name: str`
- `model: str`
- `complete(prompt: str, system: str, max_tokens: int) -> str`: Send a completion request
- `stream(prompt: str, system: str, max_tokens: int) -> Iterator[str]`: Stream a response (for TUI display)

### Step 2: Anthropic provider (llm/anthropic_provider.py)

Implement the provider using the `anthropic` Python SDK. Support Claude Sonnet and Claude Opus models. Use the Messages API. Handle rate limits with exponential backoff. Pass API key from config or ANTHROPIC_API_KEY env var.

### Step 3: OpenAI provider (llm/openai_provider.py)

Implement using the `openai` Python SDK. Support GPT-4o and newer models. Same interface as Anthropic.

### Step 4: Ollama provider (llm/ollama_provider.py)

Implement using HTTP requests to Ollama's local API (http://localhost:11434). Support any model installed locally. This is the fully-offline option for developers who do not want to send code to external APIs.

### Step 5: Provider factory

Create a `get_provider(config: NalaConfig) -> LLMProvider` factory function that returns the correct provider based on config.llm_provider.

### Step 6: System prompts for code analysis

Create a set of system prompts optimized for code analysis tasks:
- General analysis: "You are a senior software engineer analyzing code quality..."
- Refactoring advice: "Given the following function and its complexity metrics..."
- Mission generation: "Generate a clear, actionable mission document..."
- Codebase Q&A: "You have access to the following codebase context..."

### Step 7: Wire into the TUI

Free-text input in the command bar (anything not starting with `/`) is sent to the LLM with relevant codebase context. The response streams into the main area token-by-token, just like Claude Code and OpenCode.

Context injection: When the user asks a question, Nala automatically includes relevant symbols, metrics, and graph data based on the question. If the user asks about a specific function, include that function's code, its metrics, its callers, and its dependencies.

## Acceptance Criteria

- At least two LLM providers work correctly (Anthropic + one other)
- Streaming responses display in the TUI without blocking
- API keys are loaded from config/env vars securely
- LLM-enhanced mission generation produces better results than rule-based alone
- Missing API keys show a helpful message, not a crash
- No source file exceeds 400 lines

---

# Mission 13: Inline Agent Actions

## Objective

Build the agent action system that lets users invoke code modifications directly from the TUI. The user selects a finding or types a request, and the agent generates and applies changes, with explicit user confirmation before any file is modified.

## Why This Matters

This closes the loop from analysis to fix. Instead of reading a mission document, opening a separate editor, and manually making changes, the user can say "fix this" right inside Nala. The key differentiator from Cursor or Claude Code is that Nala's agent actions are informed by the full analysis context: it knows the complexity metrics, the dependency graph, the test coverage gaps, and can make smarter suggestions.

## Implementation Steps

### Step 1: Agent orchestrator (agents/orchestrator.py)

Create an `AgentOrchestrator` that:
- Takes an action request (e.g., "refactor this function to reduce complexity")
- Gathers relevant context (the function code, its metrics, its callers/callees from the graph, test coverage)
- Constructs a prompt with context and sends it to the LLM
- Parses the LLM's response to extract proposed code changes (in diff format or full replacement)
- Presents the proposed changes to the user for review

### Step 2: Change preview and confirmation

Before any file is modified, show the proposed changes in the TUI:
```
Proposed changes to src/auth/login.rs:

  - Lines 45-89: Refactored process_login() into three functions
    + validate_credentials() (lines 45-58)
    + create_session() (lines 60-72)
    + send_welcome_email() (lines 74-82)

  Apply changes? [y/n/edit]
```

The user must explicitly confirm. If they choose "edit," open the diff in their configured editor.

### Step 3: Batch actions

Support batch operations for findings:
- "Fix all low-complexity issues in src/utils/" runs the agent on each finding in sequence
- Each change still requires individual confirmation (no auto-apply without user awareness)

### Step 4: Action history

Save all applied actions to the session directory so changes are traceable. Each action records: timestamp, file_path, original_code, new_code, prompt, finding_reference.

## Acceptance Criteria

- Agent generates reasonable code change proposals
- No file is modified without explicit user confirmation
- Changes are saved to action history for traceability
- Batch operations work for multiple findings
- No source file exceeds 400 lines

---

# Mission 14: Optional Web Dashboard

## Objective

Build a lightweight web dashboard that visualizes the Neo4j code graph in a browser. The dashboard runs on localhost and is launched with `nala dashboard` or `/dashboard` from the TUI. It provides interactive graph exploration, perspective overlays, and session history visualization.

## Why This Matters

The terminal is Nala's home, but some data is genuinely better viewed visually. A dependency graph with 200 nodes is impossible to understand as text. A treemap of complexity hotspots communicates risk at a glance. The dashboard supplements the TUI without replacing it.

## Implementation Steps

### Step 1: FastAPI server (dashboard/server.py)

Create a FastAPI app with these endpoints:
- `GET /` serves the main dashboard HTML page
- `GET /api/graph` returns the full code graph as JSON (nodes and edges)
- `GET /api/graph/module/{name}` returns a subgraph for a specific module
- `GET /api/perspectives/{name}` returns findings for a specific perspective
- `GET /api/sessions` returns session history
- `GET /api/stats` returns project-wide statistics

### Step 2: Frontend (dashboard/static/)

Build a single-page HTML/JS application using D3.js for graph visualization:
- Force-directed graph layout showing modules as nodes and dependencies as edges
- Node size based on SLOC, node color based on complexity (green/yellow/red)
- Click a node to see its details (functions, metrics, findings)
- Filter by perspective (show only complexity hotspots, show only dependency issues)
- Zoom, pan, and search

Keep the frontend simple. One HTML file, one JS file, one CSS file. No build tools, no React, no npm. Just plain D3.js loaded from CDN.

### Step 3: Launch from TUI

Add a `/dashboard` command that starts the FastAPI server in the background and opens the browser to localhost:3000. Add a `/dashboard stop` command to shut it down.

### Step 4: Serve from CLI

Add a `nala dashboard` CLI command that launches the dashboard without the full TUI.

## Acceptance Criteria

- Dashboard starts on localhost and renders the code graph
- Nodes are clickable and show details
- Perspective filters work
- Dashboard stops cleanly when requested
- Frontend has no build dependencies (pure HTML/JS/CSS)
- No source file exceeds 400 lines
