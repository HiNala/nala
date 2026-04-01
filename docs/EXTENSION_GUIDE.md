# Nala: Extension Points and Plugin System

This document describes all the ways Nala can be extended without modifying
its core source code. There are six extension points, each with a clear
interface contract.

---

## 1. Custom Analysis Perspectives

Add domain-specific analysis lenses (e.g. "check all API endpoints for
missing authentication", "find all database queries missing indexes").

### How to add a custom perspective

**Step 1** — Create a Python file anywhere in your project:

```python
# .nala/perspectives/auth_check.py
from nala_orchestrator.perspectives.base import BasePerspective, PerspectiveResult, Finding

class AuthCheckPerspective(BasePerspective):
    name = "auth_check"
    description = "Flags API endpoints that may lack authentication checks."

    async def analyze(self, project_root: str, **kwargs) -> PerspectiveResult:
        findings = []
        # ... your analysis logic ...
        findings.append(Finding(
            severity="high",
            title="Unauthenticated endpoint",
            file_path="src/api/users.py",
            start_line=42,
            message="POST /users has no auth decorator",
            recommendation="Add @require_auth decorator",
        ))
        return PerspectiveResult(
            perspective_name=self.name,
            findings=findings,
            summary=f"{len(findings)} auth issues found.",
            stats={"checked": 10, "flagged": len(findings)},
        )
```

**Step 2** — Place the file in one of these discovery locations:
- `<project>/.nala/perspectives/` — project-specific
- `~/.nala/perspectives/` — applies to all projects

**Step 3** — Nala auto-discovers `*Perspective` classes on startup. Run:

```
/analyze auth_check
```

### Finding severity levels

| Level    | When to use                              |
|----------|------------------------------------------|
| critical | Security vulnerability, data loss risk   |
| high     | Likely bug, major tech debt              |
| medium   | Code smell, performance issue            |
| low      | Stylistic, minor improvement             |
| info     | Informational, no action required        |

---

## 2. Custom LLM Providers

Integrate any LLM API — Azure OpenAI, AWS Bedrock, Cohere, a local vLLM
server, or any OpenAI-compatible endpoint.

### How to add a custom provider

```python
# .nala/providers/my_provider.py
from nala_orchestrator.llm.provider import LLMProvider
from typing import Iterator
import httpx

class MyProvider(LLMProvider):
    name = "my_company"

    def complete(self, prompt: str, system: str = "", max_tokens: int = 4096) -> str:
        response = httpx.post(
            "https://my-llm-api.internal/v1/chat",
            json={"system": system, "prompt": prompt, "max_tokens": max_tokens},
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=60,
        )
        return response.json()["text"]

    def stream(self, prompt: str, system: str = "", max_tokens: int = 4096) -> Iterator[str]:
        with httpx.stream("POST", "https://my-llm-api.internal/v1/stream",
                          json={"system": system, "prompt": prompt},
                          headers={"Authorization": f"Bearer {self.api_key}"}) as r:
            for chunk in r.iter_text():
                yield chunk
```

**Register in `.env`:**

```bash
LLM_PROVIDER=my_company
MY_COMPANY_API_KEY=...
```

The provider factory (`nala_orchestrator.llm.provider.get_provider`) discovers
classes named `*Provider` in `~/.nala/providers/` and `.nala/providers/`.

---

## 3. Additional Language Support

Add Tree-sitter parsing for any language not yet in the indexer.

### How to add a language (Rust)

**Step 1** — Add the grammar to `rust-core/nala-indexer/Cargo.toml`:

```toml
[dependencies]
tree-sitter-kotlin = "0.21"
```

**Step 2** — Add a file extension mapping in `nala-indexer/src/scanner.rs`:

```rust
".kt" | ".kts" => Some(Language::Kotlin),
```

**Step 3** — Implement `LanguageExtractor` in `nala-indexer/src/parser.rs`:

```rust
Language::Kotlin => extract_kotlin_symbols(node, source, file_path),
```

The extractor walks the Tree-sitter AST and returns `Vec<Symbol>`. Follow the
existing `extract_python_symbols` or `extract_rust_symbols` as a template.

**Step 4** — Add the LSP server config in `nala-lsp/src/config.rs`:

```rust
"kotlin-language-server" => LspServerConfig {
    command: "kotlin-language-server".to_string(),
    args: vec![],
    language_ids: vec!["kotlin".to_string()],
},
```

### Supported languages (built-in)

| Language   | Indexing | LSP server           |
|------------|----------|----------------------|
| Python     | Full     | pyright              |
| Rust       | Full     | rust-analyzer        |
| TypeScript | Full     | typescript-language-server |
| JavaScript | Full     | typescript-language-server |
| Go         | Full     | gopls                |

---

## 4. Custom TUI Themes

Override Nala's color scheme to match your terminal or preferences.

### How to create a theme

Create `~/.nala/theme.toml`:

```toml
[colors]
background     = "#0d1117"   # main background
foreground     = "#e6edf3"   # default text
accent         = "#58a6ff"   # highlights, active elements
success        = "#3fb950"   # success messages, completed states
warning        = "#d29922"   # warnings, medium severity
error          = "#f85149"   # errors, critical severity
border         = "#30363d"   # panel borders
border_active  = "#58a6ff"   # focused panel border
user_msg       = "#79c0ff"   # user input color
assistant_msg  = "#e6edf3"   # AI response color
system_msg     = "#8b949e"   # system messages
```

Colors can be hex (`#rrggbb`) or named ANSI colors (`red`, `blue`, etc.).

### Built-in themes

- `default` — dark, neutral (active)
- `catppuccin-mocha` — planned
- `gruvbox-dark` — planned
- `solarized-dark` — planned

Set with: `NALA_THEME=gruvbox-dark` in `.env`.

---

## 5. MCP Server Mode (Planned)

Expose Nala's capabilities as an [MCP (Model Context Protocol)](https://modelcontextprotocol.io)
server so Claude Code, Cursor, and other MCP-aware tools can use Nala as a
backend for deep codebase understanding.

### Planned MCP tools

```
nala_index(path)          → index result JSON
nala_search(query, path)  → RAG-retrieved code chunks
nala_graph_query(cypher)  → Neo4j query result
nala_analyze(path, lens)  → perspective findings
nala_session_summary()    → current session context
```

**Launch:** `nala mcp-server --port 3001`

**Status:** Planned for near-term (see ROADMAP.md §2).

---

## 6. Lifecycle Hooks (Planned)

Run custom scripts at key points in Nala's lifecycle.

### Planned hook points

| Hook                  | When it fires                         |
|-----------------------|---------------------------------------|
| `on_scan_complete`    | After every file scan                 |
| `on_index_complete`   | After symbols/metrics are updated     |
| `on_analysis_complete`| After a perspective run finishes      |
| `on_action_applied`   | After an agent action is confirmed    |
| `on_session_save`     | Before session data is written        |
| `on_shutdown`         | Before the process exits              |

### Hook script format

Place executable scripts in `.nala/hooks/`:

```bash
# .nala/hooks/on_index_complete.sh
#!/bin/bash
echo "Indexed $NALA_FILES files with $NALA_SYMBOLS symbols" >> ~/nala-log.txt
```

Environment variables are passed from the event payload. Scripts must complete
within 5 seconds or they are killed.

**Status:** Planned for medium-term (see ROADMAP.md).

---

## Summary Table

| Extension Point       | Ready Now? | Interface                       |
|-----------------------|------------|---------------------------------|
| Custom perspectives   | Yes        | Inherit `BasePerspective`       |
| Custom LLM providers  | Yes        | Inherit `LLMProvider`           |
| Additional languages  | Yes (Rust) | Add grammar + `LanguageExtractor` |
| Custom themes         | Partial    | `~/.nala/theme.toml`            |
| MCP server mode       | Planned    | See ROADMAP.md                  |
| Lifecycle hooks       | Planned    | `.nala/hooks/` scripts          |
