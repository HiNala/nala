# HiNala (Nala)

> Terminal-first AI-powered coding environment. Fast, deep, keyboard-driven.

HiNala combines the speed of NeoVim, the intelligence of Cursor, the code-review depth of CodeRabbit, and the clean SSH-style boot of OpenCode — without Electron, without a browser, without the bloat.

**Status:** Active development. See [docs/missions/](docs/missions/) for the full build plan.

### What works today

- **Instant codebase scanning** — hash-based change detection on 160+ file projects in < 0.05s
- **Full Tree-sitter indexing** — extracts functions, classes, imports across Rust, Python, JS/TS, Go
- **Custom TUI** with themed panels, branded top bar, file tree, session history, progress gauge
- **Python AI bridge** — streams LLM responses (OpenAI, Anthropic, Google, Ollama) via IPC
- **LSP integration** — go-to-definition, find-references, hover, live diagnostics
- **Analysis perspectives** — security, complexity, churn, performance, dependency audits
- **Session management** — save, resume, and review past analysis sessions
- **Action mode** — `/act` to ask AI to propose file edits with diff preview + y/n confirmation
- **Context window management** — `/context` usage, `/compact` compaction with handoff docs

### Terminal UI Highlights

- Custom dark theme with semantic color palette (blue-violet accent family)
- Top bar with project name, git branch, LSP status, and mode badge
- Message area with role badges (YOU/AI/SYS/ERR), separators, and scrollbar
- File tree panel with language-colored icons and scanner-aligned skip rules
- Visual progress gauge during indexing
- Ctrl+Left/Right word jump, Ctrl+W delete-word, mouse click support
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

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/scan` | Scan project files (fast, hash-only) |
| `/index` | Full index: parse + symbol extraction |
| `/analyze` | Run analysis perspectives |
| `/scope` | Show or set analysis scope |
| `/scope <path>` | Analyze a specific subtree |
| `/scope clear` | Reset scope to full project |
| `/lsp status` | Show LSP runtime status |
| `/def <file>:<line>:<col>` | Go-to-definition lookup |
| `/refs <file>:<line>:<col>` | Find references lookup |
| `/hover <file>:<line>:<col>` | Hover information lookup |
| `/diag` | Show LSP diagnostics summary (errors/warnings) |
| `/session` | List past sessions |
| `/quit` | Exit |
| *Any other text* | Ask the AI assistant |

### Key Bindings

| Key | Action |
|-----|--------|
| `Ctrl+B` | Toggle file tree panel |
| `Ctrl+E` | Toggle session panel |
| `Ctrl+←` / `Ctrl+→` | Jump word left/right |
| `Ctrl+W` | Delete word backward |
| `↑` / `↓` | Navigate command history |
| `Home` / `End` | Jump to start/end of input |
| `Esc` | Clear current input |
| `Ctrl+C` / `Ctrl+Q` | Quit |
| Mouse click | Open file panel, interact with UI |

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
3. Type `/doctor` to verify environment health
4. Type `/help` to see all commands
5. Type `/analyze` to run a full analysis (security, complexity, churn, etc.)
6. Press `Ctrl+B` to open the file tree panel
7. Ask a natural language question: `What are the main entry points in this project?`
8. Type `/act refactor the largest function into smaller helpers` to try AI-driven edits

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

- Command not found after setup: open a **new terminal** so PATH updates are loaded.
- Wrong Python interpreter: set `NALA_PYTHON` to your `.venv` Python executable.
- Dashboard startup fails: re-run setup (`scripts/setup.sh` or `scripts/setup.ps1`) to install `fastapi` and `uvicorn`.
- No symbols after `scan`: run `index` (index now reparses discovered files even when scan cache is warm).

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
│   │   └── ui/             Rendering (layout, splash, panels, bars)
│   ├── nala-indexer/       Tree-sitter parsing, hashing, SQLite cache
│   ├── nala-lsp/           LSP client (JSON-RPC transport)
│   └── nala-bridge/        PyO3 bindings (Rust → Python)
├── python-orchestrator/    Python package
│   └── nala_orchestrator/
│       ├── config.py       Configuration (loads from .env)
│       ├── llm/            LLM providers (Anthropic, OpenAI, Google, Ollama)
│       ├── graph/          Neo4j code knowledge graph
│       ├── perspectives/   Analysis engines (complexity, security, churn, …)
│       ├── sessions/       Session management and report generation
│       └── agents/         LLM query orchestration
├── dashboard/              Optional FastAPI + D3.js web dashboard
├── scripts/                Setup and benchmark scripts
└── docs/missions/          Complete build plan (24 missions)
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

---

## Mission Plan

The build is structured as 19 missions. Each mission is in `docs/missions/`.

| Phase | Missions | Focus |
|-------|---------|-------|
| Foundation | 01-06 | Setup, indexing, TUI, LSP, PyO3 |
| Analysis | 07-09 | Neo4j graph, perspectives, reports |
| Agent Actions | 10-13 | Sessions, missions, inline edits |
| Polish | 14-16 | Dashboard, review, what's next |
| Docs | 17-19 | Architecture, data flow, extensions |

---

## License

MIT
