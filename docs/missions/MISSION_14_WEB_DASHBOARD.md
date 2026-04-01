# Mission 14: Web Dashboard

## Objective

Build an optional localhost web dashboard that visualises the code knowledge graph as an interactive D3.js force-directed graph, shows complexity heatmaps, and provides a REST API for external integrations. After this mission, `nala dashboard` starts the dashboard at `localhost:3000` — a visual companion to the TUI for exploring complex dependency relationships.

## Why This Matters

Graph relationships are inherently visual. Seeing a tangled web of import cycles, or a single file that everything depends on, is immediately impactful in a way that a text list is not. The dashboard makes Nala's graph analysis accessible to teams, not just terminal-comfortable developers. It also opens the door to CI integration: a CI job can POST to the API after indexing and get a JSON summary of new findings.

The dashboard is **completely optional**. Nala's core functionality (TUI + LLM) works without it.

## Context

The `dashboard/` directory was stubbed in Mission 01. This mission builds it out. The backend is FastAPI (Python) serving both the REST API and the static frontend. The frontend is vanilla HTML + D3.js (no build step, no npm). Data comes from the same SQLite cache and Neo4j graph that the Python orchestration layer uses.

## Implementation Steps

### Step 1: FastAPI backend (dashboard/server.py)

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="Nala Dashboard", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}

@app.get("/graph")
def get_graph(project_root: str = "."):
    """Return the code graph as {nodes: [...], edges: [...]} for D3."""

@app.get("/complexity")
def get_complexity(project_root: str = ".", threshold: int = 5):
    """Return functions above the complexity threshold."""

@app.get("/findings")
def get_findings(project_root: str = ".", session_id: str = "latest"):
    """Return findings from the most recent (or specified) session."""

@app.get("/files")
def get_files(project_root: str = "."):
    """Return file list with language, SLOC, symbol count."""

app.mount("/", StaticFiles(directory="static", html=True), name="static")
```

### Step 2: Graph API response format

The `/graph` endpoint returns a JSON object compatible with D3's force simulation:

```json
{
  "nodes": [
    {"id": "src/auth.py", "type": "file", "sloc": 120, "complexity": 45},
    {"id": "authenticate", "type": "function", "file": "src/auth.py", "complexity": 12}
  ],
  "edges": [
    {"source": "src/auth.py", "target": "authenticate", "type": "contains"},
    {"source": "authenticate", "target": "hash_password", "type": "calls"}
  ],
  "stats": {
    "total_nodes": 342,
    "total_edges": 891,
    "languages": {"python": 45, "rust": 12}
  }
}
```

For large graphs (> 500 nodes), filter to only the top N most-connected nodes to keep the visualisation readable. Add a `?max_nodes=200` query parameter.

### Step 3: Frontend — index.html (dashboard/static/index.html)

Single-page application with:
- Left sidebar: project stats, filter controls (by language, node type, min complexity)
- Main area: D3.js force-directed graph canvas
- Bottom panel: selected node details (file path, symbol count, complexity, related nodes)
- Top right: navigation tabs (Graph | Complexity | Findings | Files)

No build step. Pure HTML/CSS/JS. Use CDN links for D3 v7 and any other dependencies.

### Step 4: D3.js graph (dashboard/static/graph.js)

```javascript
// Force simulation with collision detection
const simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(edges).id(d => d.id).distance(60))
    .force("charge", d3.forceManyBody().strength(-200))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide(20));

// Node colouring by type
const color = d3.scaleOrdinal()
    .domain(["file", "function", "class", "module"])
    .range(["#4a9eff", "#50fa7b", "#f1fa8c", "#ff79c6"]);

// Node sizing by complexity
const radius = d => 5 + Math.sqrt(d.complexity || 1) * 2;
```

Features:
- Zoom/pan (d3.zoom)
- Click node to show details panel
- Hover to highlight connected nodes and edges
- Filter by node type (checkboxes)
- Search box that highlights matching nodes
- "Focus" button that re-centres the simulation on the selected node and its neighbours

### Step 5: Complexity heatmap tab (dashboard/static/complexity.js)

A treemap visualisation (d3.treemap) where:
- Each rectangle is a file
- Rectangle area = SLOC
- Rectangle colour = max cyclomatic complexity (green → yellow → red)
- Click a file to drill down into its functions

### Step 6: Findings tab (dashboard/static/findings.js)

A simple table showing findings from the latest analysis session:
- Columns: Severity, Category, Title, File, Line
- Sortable by any column
- Filterable by severity (checkboxes)
- Click a finding to see its full description
- Export to CSV button

### Step 7: CLI integration

Add a `dashboard` subcommand to `nala-cli/src/main.rs`:

```rust
Commands::Dashboard { port, open } => {
    println!("Starting Nala dashboard on http://localhost:{}", port);
    // Spawn Python dashboard process
    let status = std::process::Command::new("python")
        .args(["-m", "uvicorn", "dashboard.server:app",
               "--host", "127.0.0.1", "--port", &port.to_string()])
        .current_dir(&project_root)
        .status()?;
}
```

If `--open` flag is set, open the browser automatically using the `open` crate.

### Step 8: Security

The dashboard binds to `127.0.0.1` only (never `0.0.0.0`). Add a `--host` flag but document that exposing it on a network interface is the user's responsibility. The API has no authentication — it is a local developer tool.

CORS is restricted to `localhost` origins. No credentials are accepted.

## Acceptance Criteria

- `nala dashboard` starts the server and the browser shows the graph
- Graph visualisation renders with correct node types and colours
- Clicking a node shows its details (file path, complexity, symbol count)
- Complexity heatmap renders correctly with colour-coded files
- Findings table shows all findings from the latest session
- Dashboard binds to 127.0.0.1 only
- All static assets are < 200KB total (no heavy JS bundles)
- No file exceeds 400 lines

## Key Dependencies

- fastapi
- uvicorn
- D3.js v7 (CDN)

## Estimated Complexity

Medium. The FastAPI backend is straightforward. The D3.js force graph is the most complex piece but is well-documented. The main challenge is making the graph readable for large projects (performance tuning for > 500 nodes).
