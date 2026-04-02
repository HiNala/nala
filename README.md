# HiNala (Nala)

> Terminal-first AI-powered coding environment. Fast, deep, keyboard-driven.

Nala combines the speed of NeoVim, the intelligence of Cursor, the code-review depth of CodeRabbit, and the clean SSH-style boot of OpenCode — without Electron, without a browser, without the bloat.

**Status:** Active development. See [docs/missions/](docs/missions/) for the full build plan.

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
| `/session` | List past sessions |
| `/quit` | Exit |
| *Any other text* | Ask the AI assistant |

### Key Bindings

| Key | Action |
|-----|--------|
| `Ctrl+B` | Toggle file tree panel |
| `Ctrl+E` | Toggle session panel |
| `↑` / `↓` | Navigate command history |
| `Ctrl+C` / `Ctrl+Q` | Quit |

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
├── rust-core/           Rust workspace (TUI, indexer, LSP, PyO3 bridge)
│   ├── nala-cli/        Binary entry point — type `nala` to start
│   ├── nala-tui/        Ratatui terminal user interface
│   ├── nala-indexer/    Tree-sitter parsing, content hashing, SQLite cache
│   ├── nala-lsp/        LSP client (go-to-def, find-refs, hover)
│   └── nala-bridge/     PyO3 bindings (Rust → Python)
├── python-orchestrator/ Python package (AI, Neo4j graph, perspectives)
│   └── nala_orchestrator/
│       ├── config.py    Configuration (loads from .env)
│       ├── llm/         LLM providers (Anthropic, OpenAI, Google, Ollama)
│       ├── graph/       Neo4j code knowledge graph
│       ├── perspectives/ Analysis engines (complexity, deps, dead code...)
│       ├── sessions/    Session management and report generation
│       └── agents/      LLM query orchestration
├── dashboard/           Optional FastAPI + D3.js web dashboard
└── docs/missions/       Complete build plan (19 missions)
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
