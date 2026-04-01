"""
Nala Python IPC server.

This module runs as a subprocess spawned by the Rust TUI. It listens for
JSON-lines requests on stdin and writes JSON-lines responses to stdout.

Protocol (JSON-lines over stdin/stdout):
  Request:  {"id": "1", "type": "query", "text": "...", "project_root": "..."}
  Response: {"id": "1", "type": "chunk",  "text": "..."}   (streamed, 0..N)
            {"id": "1", "type": "done"}                     (end of stream)
            {"id": "1", "type": "error",  "text": "..."}   (on failure)

  Request:  {"id": "2", "type": "index_context", "total_files": 10, "total_symbols": 50}
  Response: {"id": "2", "type": "ok"}

  Request:  {"id": "3", "type": "ping"}
  Response: {"id": "3", "type": "pong", "version": "0.1.0"}

Usage (from Rust):
    let child = Command::new("python")
        .args(["-m", "nala_orchestrator.cli"])
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()?;
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from .config import Config
from .agents.orchestrator import AgentOrchestrator

# Flush immediately — Rust reads line-by-line
sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]


def write_response(data: dict) -> None:
    """Write a JSON-lines response to stdout."""
    print(json.dumps(data), flush=True)


async def handle_request(req: dict, agent: AgentOrchestrator) -> None:
    """Dispatch one request and write response(s) to stdout."""
    req_id = req.get("id", "0")
    req_type = req.get("type", "")

    if req_type == "ping":
        write_response({"id": req_id, "type": "pong", "version": "0.1.0"})

    elif req_type == "index_context":
        agent.update_index_context(
            total_files=req.get("total_files", 0),
            total_symbols=req.get("total_symbols", 0),
        )
        write_response({"id": req_id, "type": "ok"})

    elif req_type == "query":
        text = req.get("text", "").strip()
        if not text:
            write_response({"id": req_id, "type": "error", "text": "Empty query"})
            return

        try:
            async for chunk in agent.stream_query(text):
                write_response({"id": req_id, "type": "chunk", "text": chunk})
            write_response({"id": req_id, "type": "done"})
        except Exception as e:
            write_response({"id": req_id, "type": "error", "text": str(e)})

    else:
        write_response({"id": req_id, "type": "error", "text": f"Unknown type: {req_type}"})


async def run_ipc_loop(project_root: Optional[str] = None) -> None:
    """
    Main IPC loop: read JSON-lines from stdin, write responses to stdout.

    Runs until stdin closes (Rust process exits or sends EOF).
    """
    root = Path(project_root) if project_root else Path.cwd()
    config = Config.load(project_root=root)
    agent = AgentOrchestrator(config)

    # Signal ready
    write_response({"type": "ready", "has_llm": config.has_llm(), "provider": config.llm_provider})

    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break  # EOF — Rust side closed stdin
            line = line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            req = json.loads(line)
            # Handle each request concurrently so streaming doesn't block pings
            asyncio.create_task(handle_request(req, agent))
        except json.JSONDecodeError as e:
            write_response({"type": "error", "text": f"JSON parse error: {e}"})
        except Exception as e:
            write_response({"type": "error", "text": f"IPC error: {e}"})
            break


def main() -> None:
    """Entry point: parse optional --root arg and run the IPC loop."""
    import argparse
    parser = argparse.ArgumentParser(description="Nala Python IPC server")
    parser.add_argument("--root", default=None, help="Project root directory")
    args = parser.parse_args()

    asyncio.run(run_ipc_loop(args.root))


if __name__ == "__main__":
    main()
