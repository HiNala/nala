# HiNala (Nala)

> Terminal-first AI-powered coding environment. Fast, deep, keyboard-driven.

HiNala combines the speed of NeoVim, the intelligence of Cursor, the code-review depth of CodeRabbit, and the clean SSH-style boot of OpenCode — without Electron, without a browser, without the bloat.

**Status:** Active development. See [docs/missions/](docs/missions/) for the full build plan.

### What works today

- **Instant codebase scanning** — hash-based change detection on 170+ file projects in < 0.05s
- **Full Tree-sitter indexing** — extracts functions, classes, imports across Rust, Python, JS/TS, Go
- **RAG-powered code context** — chunks every indexed file, retrieves relevant code via BM25 (+ optional vector embeddings), injects up to 12k tokens of context per query
- **Real-time streaming** — true token-by-token streaming from OpenAI, Anthropic, Google, and Ollama
- **Markdown rendering** — AI responses display with **bold**, `inline code`, ```code blocks```, headings, bullet points, numbered lists, and horizontal rules
- **Custom TUI** with themed panels, branded top bar, file tree, session history, progress gauge
- **Python AI bridge** — streams LLM responses via IPC with project structure and file tree awareness
- **LSP integration** — go-to-definition, find-references, hover, live diagnostics
- **Analysis perspectives** — security, complexity, churn, performance, dependency audits
- **Session management** — save, resume, and review past analysis sessions
- **Agent workflow** — `/agent` unified autonomous entrypoint: plan, approve, run, review, verify, hotspot
- **Agent workbench** — toggleable panel (`Ctrl+G`) showing phase, objective, plan steps, verification
- **Autonomy levels** — `/agent mode observe|plan|patch|autonomous` controls how far the agent runs
- **Skill system** — built-in skills (triage-hotspots, review-diff, refactor-safely, repair-failures) + user skills in `.nala/agent/skills/`
- **Project brief + scoped guidance** — durable `.nala/agent/project-brief.md` and per-directory scopes auto-loaded into agent context
- **Verification recipes** — auto-detects Rust (`cargo check/test`), Python (`ruff/pytest`), Node (`npm test/lint`) commands
- **Approval workflow** — `/agent approve` / `/agent reject` gates before execution
- **Mission-driven orchestration** — `/agent objective <goal>` runs full research → plan → execute → verify loop with structured `.md` mission files
- **Worker architecture** — interpreter/orchestrator/worker three-layer model with up to 3 parallel workers per run
- **Worker management** — `/agent workers`, `/agent attach`, `/agent message`, `/agent cancel-worker` for full worker control
- **Git integration** — `/agent scm`, `/agent compare`, `/agent blame`, branch comparison, worktree support
- **Worktree isolation** — spawn workers in isolated git worktrees for safe parallel edits
- **Web research** — `/agent research <question>` with citation tracking, caching, and budget limits
- **Pause/checkpoint** — `/agent pause`, `/agent checkpoint`, `/agent restore` for durable run control
- **Human-in-the-loop** — context-appropriate next-step suggestions, notification priority (interrupt vs quiet), checkpoint indicators
- **Action mode** — `/agent <instruction>` to propose file edits with diff preview + y/n confirmation
- **Context window management** — `/context` usage, `/compact` compaction with handoff docs
- **Clipboard paste** — bracketed paste support for pasting text from clipboard into input

### Terminal UI Highlights

- Custom dark theme with semantic color palette (blue-violet accent family)
- Top bar with project name, git branch, LSP status, and mode badge
- **Markdown rendering** in AI responses: bold, code blocks with language labels, headings, bullets, inline code
- Message area with role badges (AI/YOU/SYS/ERR) and word-wrap-aware scrolling
- File tree panel with language-colored icons and scanner-aligned skip rules
- Visual progress gauge during indexing
- Ctrl+Left/Right word jump, Ctrl+W delete-word, mouse click support
- Mouse wheel / `PgUp`/`PgDn` / `Shift+↑`/`↓` message scrolling + `↑`/`↓` prompt history
- Bracketed paste support — paste from clipboard with Ctrl+V
- Live LSP diagnostics (error/warning counts in status bar and top bar)
- Diff confirmation view with color-coded add/remove/context lines

---

## Quick Start

### Prerequisites

- [Rust](https://rustup.rs/) (1.75+)
- [Python](https://python.org) 3.11+
- [Maturin](https://github.com/PyO3/maturin) (`pip install maturin`)

### Setup

```bash
# Clone the repo
git clone https://github.com/HiNala/nala.git
cd nala

# Configure API keys
cp .env.example .env
# Edit .env and set LLM_PROVIDER + API key

# One-command setup + command install
# Linux/macOS:
./scripts/setup.sh
# Windows PowerShell:
.\scripts\setup.ps1
```

### Run

```bash
# Open any project folder and launch directly:
HiNala

# Compatible aliases:
hinala
nala
```

`HiNala` automatically targets the current working directory as `--path`, so you can use it Claude-Code style from any repo root.

If your system `python` is not the one with `nala_orchestrator` installed, set:

```bash
NALA_PYTHON=/absolute/path/to/python
```

### First-run smoke test

```bash
# From any project directory:
hinala scan
hinala index
hinala dashboard --port 3000
```

The dashboard should open on `http://127.0.0.1:3000` and use the current directory as project root.

### Commands inside Nala

Just type a question or instruction to chat with the AI. All slash commands:

**Agent** — autonomous workflow:

| Command | Description |
|---------|-------------|
| `/agent <objective>` | Start an autonomous agent run |
| `/agent objective <goal>` | Full orchestration: research → plan missions → execute → verify |
| `/agent missions` | Show mission plan status |
| `/agent approve-missions` | Approve and execute the generated mission plan |
| `/agent plan [topic]` | Generate a plan |
| `/agent approve` / `reject` | Accept or revise the plan |
| `/agent run` | Execute the approved plan |
| `/agent review` | Review changes and diff |
| `/agent verify` | Run tests and linting |
| `/agent status` | Current run state |
| `/agent stop` / `pause` / `resume` | Control the run |
| `/agent scm` | Git status overview |
| `/agent research <q>` | Look up external docs |
| `/agent next` | Suggested next steps |

**Code:**

| Command | Description |
|---------|-------------|
| `/analyze [quick]` | Run analysis perspectives |
| `/scope <path>` | Focus on a subtree |
| `/read <file>` | Show file contents |
| `/tree` | Project file tree |
| `/diag` | LSP diagnostics |

**Session:**

| Command | Description |
|---------|-------------|
| `/session` | List / create / load sessions |
| `/context` | Context window usage |
| `/compact` | Free tokens by compacting |

**Settings:**

| Command | Description |
|---------|-------------|
| `/settings` | Show all configuration (keys, routing, agent defaults) |
| `/settings set <key> <value>` | Change a setting (persists to `.nala/settings.toml`) |
| `/settings setup` | Guided first-run configuration wizard |
| `/model` | Show current LLM provider/model |
| `/models` | Show all available models + routing table |
| `/doctor` | Environment diagnostics |

**General:**

| Command | Description |
|---------|-------------|
| `/scan` / `/index` | Rescan or reindex project files |
| `/clear` | Clear messages |
| `/help` | Full command reference |
| `/quit` | Exit |

### Key Bindings

| Key | Action |
|-----|--------|
| `Ctrl+B` | Toggle file tree panel |
| `Ctrl+E` | Toggle session panel |
| `Ctrl+G` | Toggle agent workbench panel |
| `Ctrl+←` / `Ctrl+→` | Jump word left/right |
| `Ctrl+W` | Delete word backward |
| `↑` / `↓` | Navigate command history |
| `Shift+↑` / `Shift+↓` | Scroll message area (3 lines) |
| `PgUp` / `PgDn` | Scroll message area (10 lines) |
| Mouse wheel | Scroll message area |
| `Home` / `End` | Jump to start/end of input |
| `Esc` | Cancel analysis / clear input |
| `Ctrl+C` / `Ctrl+Q` | Quit |

---

## Testing on a Codebase

You can point HiNala at **any** project folder and start exploring immediately:

```bash
# Navigate to any project you want to analyze
cd ~/projects/my-app

# Launch HiNala (it auto-targets the current directory)
hinala

# Or specify a path explicitly
hinala -p /path/to/any/project
```

### Recommended first-run workflow

1. Launch the TUI — it auto-scans and indexes on boot
2. Wait for "Index complete" message (usually < 1 second)
3. Type `/model` to verify your LLM connection
4. Ask a question: `What are the main entry points in this project?`
5. Type `/analyze` for a full analysis
6. Type `/agent <goal>` to start an autonomous agent run

### Without the global command

If you haven't run the setup script, you can run the binary directly:

```bash
# Windows
.\rust-core\target\release\nala.exe -p C:\path\to\project

# Linux / macOS
./rust-core/target/release/nala -p /path/to/project
```

---

## Troubleshooting

- **Command not found after setup:** open a **new terminal** so PATH updates are loaded.
- **Wrong Python interpreter:** set `NALA_PYTHON` to your `.venv` Python executable.
- **AI says provider is missing despite `.env`:** restart Nala after key changes. Config resolves `.env` from parent directories automatically.
- **AI responses are generic / don't reference code:** wait for the "Context ready: N code chunks indexed" message. If it never appears, check that your project has parseable source files.
- **Dashboard startup fails:** re-run setup (`scripts/setup.sh` or `scripts/setup.ps1`) to install `fastapi` and `uvicorn`.
- **No symbols after `scan`:** run `/index` (index reparses even when scan cache is warm).
- **Can't paste text:** make sure your terminal supports bracketed paste (Windows Terminal, iTerm2, most modern terminals do).

---

## Architecture

```
nala/
├── rust-core/              Rust workspace
│   ├── nala-cli/           Binary entry point — type `nala` to start
│   ├── nala-tui/           Ratatui terminal user interface
│   │   ├── app.rs          State machine + event loop
│   │   ├── commands.rs     Slash-command dispatch
│   │   ├── lsp_commands.rs LSP go-to-def / refs / hover
│   │   ├── actions.rs      Inline-edit confirmation workflow
│   │   ├── python_bridge.rs IPC bridge to Python orchestrator
│   │   └── ui/             Rendering (layout, markdown, splash, panels, bars)
│   ├── nala-indexer/       Tree-sitter parsing, hashing, SQLite cache
│   ├── nala-lsp/           LSP client (JSON-RPC transport)
│   └── nala-bridge/        PyO3 bindings (Rust → Python)
├── python-orchestrator/    Python package
│   └── nala_orchestrator/
│       ├── config.py       Configuration (loads from .env + settings.toml)
│       ├── settings/       Settings system (.nala/settings.toml)
│       ├── llm/            LLM providers (Anthropic, OpenAI, Google, Ollama)
│       ├── chunking/       Code chunk splitter, BM25/vector embedder, context assembler
│       ├── context/        Token counting, compaction, background summaries
│       ├── memory/         Session memory and knowledge base persistence
│       ├── graph/          Neo4j code knowledge graph
│       ├── perspectives/   Analysis engines (complexity, security, churn, …)
│       ├── sessions/       Session management and report generation
│       ├── agents/         LLM query orchestration, action extraction/execution
│       ├── agent_runtime/  Central control plane: manager, state, toolbox, workers
│       ├── skills/         Reusable agent workflow recipes (built-in + user)
│       ├── research/       Web research service (query, cache, citations)
│       ├── git_ops.py      Git operations (status, diff, blame, worktrees)
│       └── git_review.py   Review flows (branch review, SCM overview)
├── dashboard/              Optional FastAPI + D3.js web dashboard
├── scripts/                Setup and benchmark scripts
└── docs/missions/          Complete build plan (26 missions)
```

See [docs/missions/MISSION_00_MASTER_PLAN.md](docs/missions/MISSION_00_MASTER_PLAN.md) for the full vision.

---

## LLM Providers

Nala supports four providers. Set `LLM_PROVIDER` in `.env`:

| Provider | Env var | Default model |
|----------|---------|--------------|
| `anthropic` | `ANTHROPIC_API_KEY` | claude-sonnet-4-6 |
| `openai` | `OPENAI_API_KEY` | gpt-4o |
| `google` | `GOOGLE_API_KEY` | gemini-2.0-flash |
| `ollama` | *(none)* | codellama:13b |

### Settings File

Nala's canonical configuration file is `.nala/settings.toml`. Use `/settings setup` to create it interactively, or `/settings set <key> <value>` to change individual settings. Environment variables (`.env`) always take precedence.

```toml
[keys]
anthropic_api_key = "sk-ant-..."

[models]
default_provider = "anthropic"
default_model = "claude-sonnet-4-6"

[models.routing]
plan = "anthropic/claude-opus-4-6"
code = "anthropic/claude-sonnet-4-6"
explore = "anthropic/claude-haiku-4-5"

[agent]
autonomy = "guided"
max_workers = 3

[agent.git]
auto_branch = true
auto_commit = true
```

### Multi-Model Routing

When multiple API keys are configured, Nala can route different task types to different models. Use `/models` to see the routing table and available models.

Configure routing in `.nala/settings.toml` (preferred) or via `.env`:

```bash
ROUTE_PLAN=anthropic:claude-opus-4-6      # planning uses flagship
ROUTE_CODE=openai:gpt-4o                  # coding uses GPT-4o
ROUTE_EXPLORE=openai:gpt-4o-mini          # exploration uses cheaper model
ROUTE_SUMMARIZE=google:gemini-2.0-flash   # summaries use fast/cheap
```

| Task Type | Description | Default Tier |
|-----------|-------------|--------------|
| `plan` | Architecture, PRDs, mission writing | Flagship |
| `code` | Implementation, edits, bug fixes | Mid-tier |
| `explore` | Read-only analysis, triage | Cheap/fast |
| `research` | Documentation gathering | Flagship |
| `design` | UI/UX reasoning | Multimodal |
| `review` | Code review, safety audit | Mid-tier |
| `summarize` | Compaction, handoffs | Cheap/fast |

---

## Mission Plan

The build is structured through Mission 26 (and growing). Each mission is in `docs/missions/`.

| Phase | Missions | Focus |
|-------|---------|-------|
| Foundation | 01-06 | Setup, indexing, TUI, LSP, PyO3 |
| Analysis | 07-10 | Neo4j graph, perspectives, reports, sessions |
| Agent Actions | 11-16 | Missions, LLM integration, inline edits, polish |
| Docs | 17-19 | Architecture, data flow, extension docs |
| Context & Memory | 20-24 | Context mgmt, memory, handoff, multi-agent, compression |
| Objective Agent | 25-28 | Objective-driven workflows, command surface, control plane |
| Agent UX | 29-31 | Agent workbench TUI, autonomous loop, skills & memory |
| Multi-Agent & Git | 32-34 | Worker architecture, attach flow, git integration & worktrees |
| Research & HITL | 35-36 | Web research grounding, human-in-the-loop orchestration UX |

---

## License

MIT
