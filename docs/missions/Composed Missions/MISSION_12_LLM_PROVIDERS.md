# Mission 12: LLM Provider Integration

## Objective

Complete the LLM provider integration so users can interact with Nala using Anthropic, OpenAI, Google Gemini, or local Ollama models. After this mission, adding an API key to `.env` and restarting gives a fully functional AI coding assistant.

## Status

**Core implementation in place.** See:
- `python-orchestrator/nala_orchestrator/llm/provider.py` — base class + factory
- `python-orchestrator/nala_orchestrator/llm/anthropic_provider.py` — Claude
- `python-orchestrator/nala_orchestrator/llm/openai_provider.py` — GPT
- `python-orchestrator/nala_orchestrator/llm/google_provider.py` — Gemini
- `python-orchestrator/nala_orchestrator/llm/ollama_provider.py` — local
- `python-orchestrator/nala_orchestrator/agents/orchestrator.py` — query pipeline
- `python-orchestrator/nala_orchestrator/config.py` — .env config loading

## How to Test Right Now

```bash
# Set up .env
cp .env.example .env
# Edit .env: LLM_PROVIDER=anthropic, ANTHROPIC_API_KEY=sk-ant-...

# Quick test from Python
source .venv/bin/activate
python3 -c "
import asyncio
from nala_orchestrator.config import Config
from nala_orchestrator.agents.orchestrator import AgentOrchestrator

async def test():
    config = Config.load()
    agent = AgentOrchestrator(config)
    print('Provider:', config.llm_provider)
    print('Model:', config.active_model())
    print('Has LLM:', config.has_llm())
    if config.has_llm():
        response = await agent.query('Hello, what can you do?')
        print('Response:', response[:200])

asyncio.run(test())
"
```

## Remaining Work

### Wire streaming to the Rust TUI

The TUI's `dispatch_command()` in `app.rs` currently shows a placeholder for non-slash queries. Connect it to the Python agent:

1. Call `nala_core.stream_query(text, project_root)` (add this to the PyO3 bridge)
2. The bridge spawns a Python async task
3. Chunks are sent back via the `bg_tx` channel as `BackgroundEvent::AssistantChunk`
4. The TUI renders them in real-time in the main content area

### Add streaming to the PyO3 bridge

In `nala-bridge/src/lib.rs`:
```rust
#[pyfunction]
fn start_query(project_path: &str, query: &str, callback: PyObject) -> PyResult<()> {
    // Call Python orchestrator, invoke callback for each chunk
}
```

### Add token counting and context management

Before sending a query, count the context size and warn if it exceeds the provider's limit. Truncate history intelligently.

## Acceptance Criteria

- [ ] ANTHROPIC_API_KEY in .env → Claude responds to queries
- [ ] OPENAI_API_KEY in .env → GPT responds to queries
- [ ] GOOGLE_API_KEY in .env → Gemini responds to queries
- [ ] Ollama running locally → local model responds
- [ ] No API key → clear, actionable error message in TUI
- [ ] Responses stream token-by-token in the TUI (not all at once)
- [ ] Context history is maintained across multiple queries in a session
