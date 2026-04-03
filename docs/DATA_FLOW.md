# Nala: Data Flow and Integration Patterns

This document traces the major data flows through the Nala system, from user
input to rendered output, and describes the integration patterns used to connect
the Rust core, Python orchestration layer, Neo4j graph, LLM providers, model
registry, settings system, and mission-driven orchestrator.

---

## Flow 1: Boot and Initial Indexing

```
nala (CLI)
  │  parse --root arg
  ▼
nala-tui::App::new()
  │  create bg_tx/bg_rx channel pair
  │  set mode = Booting
  ▼
python_bridge::spawn()
  │  Command::new("python") -m nala_orchestrator.cli --root <path>
  │  pipe stdin / stdout
  │  wait for {"type":"ready"} line
  ▼
nala_orchestrator.cli.run_ipc_loop()
  │  Config.load()  ← .env → env vars → defaults
  │  AgentOrchestrator(config)
  │  SessionManager.new_session()
  │  HandoffReader.get_startup_injection()  ← .nala/memory/handoffs/
  │  SessionMemory.get_startup_injection()  ← .nala/memory/sessions/
  │  KnowledgeBase.load_for_context()       ← .nala/memory/knowledge/
  │  inject_system() × 3
  │  → {"type":"ready","has_llm":true/false,"version":"..."}
  ▼
App::handle_background_event(BridgeReady)
  │  set llm_available
  │  update status bar
  ▼
App::start_background_index()  [tokio::spawn]
  │  nala_indexer::index_project(root)
  │    Scanner → walkdir, collect file paths
  │    Hasher → SHA-256 per file (Rayon parallel)
  │    Cache → SQLite diff: changed / new / deleted
  │    Parser → Tree-sitter parallel parse (changed files only)
  │    SymbolExtractor → functions, classes, imports, calls
  │    MetricsEngine → cyclomatic / cognitive / Halstead
  │  → IndexResult { symbols, counts, duration }
  ▼
BackgroundEvent::IndexComplete { files, symbols }
  │  update status bar
  │  push system message
  ▼
TUI renders Ready state
```

**Key properties:**
- First boot: full parse of all files
- Subsequent boots: only re-parse files whose SHA-256 changed
- Python bridge starts in parallel with indexing (both on tokio tasks)

---

## Flow 2: Natural Language Query

```
User types message → Enter
  ▼
App::submit_input()
  │  if starts with "/" → handle_slash_command()
  │  else → send_query() or send_action_query() (/act mode)
  ▼
PythonBridge::query(text, project_root)
  │  → {"id":"N","type":"query","text":"..."}  via subprocess stdin
  ▼
nala_orchestrator.cli.handle_request()
  │  req_type == "query"
  │  agent.stream_query(text)
  │    context.build_system_prompt()  ← system injections + KB + handoff
  │    ConversationContext.add_user_message(text)
  │    if embedder → retrieve_relevant_chunks(text) → inject as system
  │    LLM provider.stream(messages)
  │      Anthropic / OpenAI / Google / Ollama API call
  │    for each token: yield chunk
  ▼
IPC: {"id":"N","type":"chunk","text":"token..."}  × many
     {"id":"N","type":"done"}
  ▼
handle_response() → BackgroundEvent::AssistantChunk(chunk)
                  → BackgroundEvent::AssistantDone
  ▼
App: streaming_response accumulates chunks
     on Done: push_message(assistant) + mode = Ready
```

**Context injection order (highest priority first):**
1. Handoff document (cross-session continuity)
2. Session memory (recent facts from past sessions)
3. Knowledge base (persistent project facts)
4. RAG chunks (relevant code context for this query)
5. Base system prompt (role + project stats)

---

## Flow 3: Analysis Perspective Run

```
User: /analyze [perspective]
  ▼
PythonBridge::run_perspectives(root, "all" | name)
  │  → {"type":"run_perspectives","project_root":"...","perspective":"all"}
  ▼
nala_orchestrator.cli  →  PerspectivesEngine(config, graph=None)
  │  for each perspective:
  │    ComplexityPerspective.analyze(files)    ← nala-indexer metrics
  │    SecurityPerspective.analyze(files)      ← regex pattern matching
  │    DependencyPerspective.analyze(files)    ← graph queries (if Neo4j)
  │    DeadCodePerspective.analyze(files)      ← graph CALLS/IMPORTS
  │    DuplicationPerspective.analyze(files)   ← token hash similarity
  │    TestCoveragePerspective.analyze(files)  ← lcov / coverage.py JSON
  │  collect PerspectiveResult[]
  │  session.save_findings(results)            ← .nala/sessions/<id>/
  ▼
stream findings as formatted text
  ▼
App: accumulate chunks → push assistant message
User: /generate  →  MissionGenerator.generate_missions(analysis_result)
                    save MISSION_NN_*.md per finding group
```

---

## Flow 4: Agent Action (/act)

```
User: /act refactor process_login to reduce complexity
  ▼
PythonBridge::query_with_actions(text, root)
  │  → {"type":"query_with_actions","text":"..."}
  ▼
agent.stream_query_with_actions(text)
  │  LLM responds with tagged action blocks:
  │    <nala:action type="edit" file="...">...</nala:action>
  ▼
extract_actions(response_text)
  │  ActionExtractor parses <nala:action> blocks
  │  returns list[ProposedAction]
  ▼
for each action:
  ActionExecutor.preview(action) → unified diff string
  IPC: {"type":"proposed_action","action_id":"...","preview":"..."}
  ▼
BackgroundEvent::ProposedAction → App::show_next_pending_action()
  │  mode = Confirming
  │  TUI renders diff panel
  ▼
User presses y / n / a (apply-all) / q (quit)
  │  y → PythonBridge::apply_action(action_id)
  │       ActionExecutor.apply() → write file
  │       session.append_turn("action", result_json)
  │  n → PythonBridge::skip_action(action_id)
  ▼
BackgroundEvent::ActionApplied → push result message
show_next_pending_action() → next diff or back to Ready
```

---

## Flow 5: Multi-Agent Team Run

```
User: /team <objective>
  ▼
PythonBridge::team_start(objective)
  │  → {"type":"team_start","objective":"..."}
  ▼
LeadAgent(config, root).stream_run(objective)
  │  TaskDecomposer.decompose(objective)
  │    detect intent (analyze | fix | both)
  │    _discover_modules()  ← walk project dirs
  │    build Wave 1 (analyze), Wave 2 (fix), Wave 3 (synthesise)
  │  yield plan summary
  │
  │  for each wave:
  │    SharedTaskList.add_task() × N         ← SQLite .nala/multi_agent/
  │    AgentSpawner.run_wave(tasks)
  │      asyncio.Semaphore(max_concurrent=3)
  │      asyncio.gather(*[run_one(task) for task in wave])
  │        WorkerAgent._execute()
  │          AgentOrchestrator(config)
  │          inject scope + inbox messages
  │          agent.query(task.objective)
  │          → WorkerResult(summary, success)
  │      broadcast findings to MessageBus
  │
  │  LeadAgent._synthesise()  → final summary
  │  yield final summary
  ▼
IPC chunks → App streaming_response → push assistant message
```

---

## Flow 6: Session Shutdown and Handoff

```
App exits (Ctrl+C or /quit)
  ▼
Python bridge stdin closed  →  run_ipc_loop() exits while loop
  ▼
shutdown sequence:
  HandoffWriter.write(session_id, "session_end", history)
    │  extract: objective, decisions, modified_files, next_steps
    │  save: .nala/memory/handoffs/<timestamp>.json + .md
    │  update: .nala/memory/handoffs/chain.json
  SessionMemory.build_and_save(session_id, history)
    │  _extract() keyword matching over conversation
    │  save: .nala/memory/sessions/<session_id>.md
  KnowledgeBase.extract_from_session(session_markdown)
    │  scan for facts → _classify() → append to category files
    │  consolidate() → deduplicate + trim oversized categories
  SessionManager.complete()
    │  update session.json status = "complete"
```

---

## Integration Patterns

### PyO3 Bridge: Bulk Data Transfer

All data crossing the Rust→Python boundary is serialised to JSON in a single
call. The `index_project()` function does the full scan→parse→symbol pipeline
in Rust, then returns one large JSON blob. This minimises crossing overhead:

```
Python: json.loads(nala_core.index_project(path))
Rust:   serde_json::to_string(&symbols)  # one allocation, one transfer
```

Never call Rust per-symbol from Python — always batch.

### Async Dispatch: Non-blocking TUI

The TUI main loop never blocks. Every operation that takes >1ms is dispatched
as a `tokio::spawn` task. Results come back via the `BackgroundEvent` channel:

```rust
tokio::spawn(async move {
    let result = bridge.some_operation().await;
    let _ = tx.send(BackgroundEvent::AssistantChunk(result)).await;
});
```

### IPC Protocol: JSON-Lines

All TUI↔Python communication is newline-delimited JSON over stdin/stdout.
Streaming responses use multiple `chunk` messages followed by `done`.
Request IDs allow correlating responses to requests (though the TUI
currently processes responses in arrival order).

### Memory Priority Stack

When injecting context at startup, priority order is:
```
Handoff document  >  Session memory  >  Knowledge base  >  empty
```
Only the highest-priority available source is injected (handoff takes precedence
over session memory to avoid duplication).

---

## Flow 7: Agent Orchestration (Missions 32-36)

The `/agent` command activates a three-layer orchestration model:

```
Interpreter (TUI)         Orchestrator (Python)        Workers (Python)
─────────────────         ───────────────────          ─────────────────
User types /agent ──────► AgentManager.start()
                          │
                          ├─ load project brief
                          ├─ load scoped guidance
                          ├─ detect verification cmds
                          │
                          ├─ plan() ────────────────► LLM generates plan
                          │  └── research (if needed)  └── ResearchService
                          │
                          ├─ AWAITING_APPROVAL ─────► user sees choices
User approves ──────────► approve()
                          │
                          ├─ run_execution() ────────► LeadAgent.run()
                          │  ├─ spawn_worker()          ├── WorkerAgent 1
                          │  ├─ spawn_worker()          ├── WorkerAgent 2
                          │  └─ spawn_worker()          └── WorkerAgent 3
                          │                                  (max 3, no recursion)
                          │
Summary to TUI ◄──────── status broadcast (IPC)
                          │
                          ├─ verify() ───────────────► auto-detect + run checks
                          │
                          ├─ review() ───────────────► git diff + blame
                          │
                          └─ DONE / checkpoint / pause
```

### Human-in-the-Loop Controls

At every phase transition, the orchestrator suggests appropriate next steps:
- `PLANNING` → approve, reject, change mode, pause
- `AWAITING_APPROVAL` → approve, reject, review first
- `EXECUTING` → check status, inspect workers, pause, stop
- `REVIEWING` → verify, checkpoint, research, stop
- `PAUSED` → resume, status, stop
- `BLOCKED` → resume (after fix), check workers, stop

### Notification Priority

The system uses two notification levels:
- **interrupt**: approval needed, safety issues, blocked workers
- **quiet**: progress milestones, phase transitions, worker completion

### Research Flow

```
/agent research <question>
  │
  ▼
ResearchService.research()
  ├─ check cache (disk: .nala/agent/research/*.json)
  ├─ if cached → return immediately
  ├─ else → LLM-powered research prompt
  ├─ parse structured response (summary, facts, citations, uncertainties)
  ├─ persist to cache
  └─ return attributed result to interpreter
```

Research is bounded: max 10 queries per run, max 5 sources per query.
Recent research is automatically injected into planning context.

---

## Flow 8: Settings and Configuration (Phase 7)

```
User: /settings setup
  │
  ▼
commands.rs::handle_settings_command("setup")
  │  bridge.settings_setup()
  ▼
cli.py → "settings_setup"
  │  SettingsLoader(project_root).load()
  │  └── 1. Read ~/.nala/settings.toml (global)
  │  └── 2. Read .nala/settings.toml (project)
  │  └── 3. Apply env var overrides
  │  SettingsWriter → .nala/settings.toml
  ▼
TUI shows wizard with current state + instructions

User: /settings set keys.anthropic_api_key sk-ant-...
  │
  ▼
cli.py → "settings_set"
  │  SettingsWriter.set_value("keys.anthropic_api_key", "sk-ant-...")
  │  → writes updated .nala/settings.toml
  ▼
Next Config.load() picks up the new value
```

### Settings Priority Chain

```
Highest ─► Environment variables (always win)
         ► .env file (loaded by dotenv)
         ► .nala/settings.toml (project-level)
         ► ~/.nala/settings.toml (global)
Lowest  ─► Built-in defaults
```

---

## Flow 9: Model Registry and Routing (Phase 7)

```
Config.load()
  │  reads model_overrides from settings.toml + ROUTE_* env vars
  ▼
ModelRegistry(config)
  │  ensure_loaded()
  │  ├── try _load_from_disk() (.nala/models/registry.json)
  │  └── fallback: refresh()
  │      ├── _probe_anthropic()  → lightweight API call
  │      ├── _probe_openai()     → models.list()
  │      ├── _probe_google()     → genai.list_models()
  │      └── _probe_ollama()     → HTTP GET /api/tags
  │  _persist() → .nala/models/registry.json
  ▼
ModelRouter(registry, overrides, primary_provider, primary_model)
  │  route(TaskType.CODE)
  │  ├── check user overrides first
  │  ├── score models by strength_score(task)
  │  └── fallback to primary model if no matches
  ▼
Returns RouteResult(provider, model_id, reason)
  │  used by AgentOrchestrator and MissionExecutor
  ▼
create_provider_for(provider, model_id, config) → LLM provider instance
```

---

## Flow 10: Mission-Driven Orchestration (Phase 7)

```
User: /agent objective "build a REST API"
  │
  ▼
commands.rs → agent_dispatch → bridge.agent_objective()
  │
  ▼
cli.py → "agent_objective"
  │  phase_update("starting")
  ▼
AgentManager.start_objective()
  │
  ├── Phase 1: Research
  │   ResearchService.research() → LLM gathers context
  │
  ├── Phase 2: Generate Missions
  │   _build_plan_prompt() → LLM generates JSON mission array
  │   MissionWriter.parse_plan_output() → list[MissionFile]
  │   MissionWriter.write_missions() → .nala/agent/missions/<run_id>/
  │   git: commit_milestone() for the plan
  │
  ├── Phase 3: Await Approval (if autonomy ≠ autonomous)
  │   _transition(AWAITING_APPROVAL)
  │   user → /agent approve-missions
  │
  └── Phase 4: Execute Missions
      MissionExecutor.execute_all()
        ├── _get_ready_missions() → dependency resolution
        ├── _group_parallel() → identify parallel groups
        ├── for each mission:
        │   ├── ModelRouter.route(task_type) → pick model
        │   ├── AgentOrchestrator(model_override) → run LLM
        │   ├── _execute_with_retry() → 1 automatic retry on failure
        │   └── update manifest status
        ├── git: commit_milestone() after completed missions
        └── yield progress text to TUI

      Phase 5: Final Summary
        git_ops.get_run_diff_summary() → show what changed
        _transition(DONE)
```

### Mission File Format

Each mission is written as a `.md` file in `.nala/agent/missions/<run_id>/`:

```
MISSION_01_<slug>.md
MISSION_02_<slug>.md
manifest.json           ← tracks status of all missions
```

### Error Recovery

- **Per-mission failures** are isolated — other missions continue
- **Automatic retry** (1 attempt) before marking FAILED
- **Deadlock detection** when no missions can proceed due to unresolved dependencies
- **Friendly error messages** translate API errors into actionable suggestions
- **No orphaned state** — manifest always reflects current status
