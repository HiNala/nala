# Nala

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

# Configure your LLM API key
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY (or OPENAI_API_KEY, GOOGLE_API_KEY)

# Build the Rust workspace
cd rust-core
cargo build --release
cd ..

# Set up Python environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# Build the PyO3 bridge (Rust → Python)
cd rust-core/nala-bridge
maturin develop
cd ../..

# Install the Python orchestrator
cd python-orchestrator
pip install -e .
cd ..
```

### Run

```bash
# From project root, with venv active:
./rust-core/target/release/nala

# Or with cargo:
cd rust-core && cargo run -- --path /your/project
```

### Commands inside Nala

| Command | Description |
|---------|-------------|
| `/help` | Show all available commands |
| `/scan` | Scan project files (fast, hash-only) |
| `/index` | Full index: parse + symbol extraction |
| `/analyze` | Run analysis perspectives |
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
