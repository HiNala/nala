# Mission 09: Analysis Perspectives Engine

## Objective

Build the perspectives engine — a set of pluggable analysis lenses that examine the codebase from different angles and produce structured findings. Each perspective answers one type of question: complexity, dependencies, dead code, security hotspots, test coverage gaps, or duplication. After this mission, `/analyze` runs all perspectives and returns a prioritised report.

## Why This Matters

Raw symbol data doesn't tell you what to pay attention to. Perspectives do. A complexity perspective tells you which functions are cognitively hard to maintain. A dead code perspective tells you what to delete. A security perspective flags dangerous patterns. Together they give a senior engineer's code review in seconds — which is the core value proposition of Nala.

This is directly inspired by CodeRabbit's multi-perspective review system and SonarQube's rule-based analysis, but built to run locally without a cloud service.

## Context

Perspectives live in the Python orchestration layer. They read from two sources:
1. **SQLite cache** (via `nala_core.index_project()`) — always available, provides symbol metadata and metrics
2. **Neo4j** — available optionally, provides relationship traversal

Each perspective is self-contained and declares which source it needs. Perspectives that only need SQLite work without Neo4j.

## Implementation Steps

### Step 1: BasePerspective (perspectives/base.py)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class Finding:
    severity: str          # "critical", "high", "medium", "low", "info"
    category: str          # perspective name
    title: str
    description: str
    file_path: Optional[str] = None
    line: Optional[int] = None
    symbol: Optional[str] = None
    metric_value: Optional[float] = None

@dataclass
class PerspectiveResult:
    perspective_name: str
    findings: list[Finding]
    summary: str
    requires_neo4j: bool

class BasePerspective(ABC):
    requires_neo4j: bool = False

    @abstractmethod
    def analyze(self, symbols: list[dict], graph=None) -> PerspectiveResult:
        ...
```

### Step 2: Complexity Perspective (perspectives/complexity.py)

Finds functions with high cyclomatic complexity. Thresholds (configurable via config):
- CC > 20: critical
- CC > 15: high
- CC > 10: medium
- CC > 5: low

Also flags:
- Functions longer than 100 lines
- Classes with more than 20 methods
- Files with more than 500 SLOC

Does NOT require Neo4j — reads from symbol metadata.

### Step 3: Dead Code Perspective (perspectives/dead_code.py)

Requires Neo4j for full accuracy; degrades to heuristics without it.

**With Neo4j:** Use the `DEAD_FUNCTIONS` Cypher query (non-public functions with no incoming CALLS edges).

**Without Neo4j (heuristic):** Flag private functions (prefixed `_` in Python, lowercase with no `pub` in Rust) that appear nowhere in the grep of all source files except their own definition.

Findings: each dead function/class with file and line.

### Step 4: Dependency Perspective (perspectives/dependencies.py)

Requires Neo4j.

Runs three analyses:
1. **Circular dependencies** — files that form import cycles
2. **High coupling** — files with the most incoming dependencies (most-imported)
3. **Fragile files** — files that import many others (high fan-out = brittle to changes)

Each analysis returns the top 10 findings.

### Step 5: Security Perspective (perspectives/security.py)

Pattern-based, no Neo4j needed. Scans source content for dangerous patterns:

**Python patterns:**
- `eval(`, `exec(`, `pickle.loads(` — code injection risk
- `subprocess.shell=True` — shell injection
- `hashlib.md5(`, `hashlib.sha1(` — weak hash
- Hardcoded secrets regex: `(password|secret|api_key)\s*=\s*["'][^"']{8,}`

**Rust patterns:**
- `unsafe {` blocks — mark as info (not necessarily bad, but worth reviewing)
- `std::mem::transmute` — high severity

**JavaScript patterns:**
- `innerHTML =`, `document.write(` — XSS risk
- `eval(` — code injection

For each finding, include the file, line, matched pattern, and a brief explanation.

### Step 6: Duplication Perspective (perspectives/duplication.py)

Lightweight similarity detection using function-level hashing:
1. For each function, compute a "structure hash" — the token sequence with variable names normalised to `VAR` and string literals to `STR`
2. Group functions by structure hash
3. Groups with 3+ members are reported as duplication clusters

This is simpler than full clone detection (e.g., NiCad) but sufficient to find copy-paste code.

### Step 7: Test Coverage Perspective (perspectives/test_coverage.py)

Without running tests, use structural heuristics:
- Count test files (files named `test_*.py`, `*_test.rs`, `*.test.ts`)
- For each non-test source file, check if a corresponding test file exists
- Flag source files with no corresponding test file

Report: coverage ratio (tested files / total files) and list of untested files.

### Step 8: PerspectivesEngine (perspectives/engine.py)

```python
class PerspectivesEngine:
    def __init__(self, config: Config, graph=None):
        self.perspectives = [
            ComplexityPerspective(),
            DeadCodePerspective(),
            DependencyPerspective(),
            SecurityPerspective(),
            DuplicationPerspective(),
            TestCoveragePerspective(),
        ]
        self.graph = graph

    def run_all(self, symbols: list[dict]) -> list[PerspectiveResult]:
        results = []
        for p in self.perspectives:
            if p.requires_neo4j and (not self.graph or not self.graph.is_available()):
                continue
            results.append(p.analyze(symbols, self.graph))
        return results

    def run_one(self, name: str, symbols: list[dict]) -> Optional[PerspectiveResult]:
        for p in self.perspectives:
            if p.__class__.__name__.lower().startswith(name.lower()):
                return p.analyze(symbols, self.graph)
        return None
```

### Step 9: IPC integration

Add a `run_perspectives` request type to the Python IPC server (`cli.py`):

```python
elif req_type == "run_perspectives":
    perspective_name = req.get("perspective", "all")
    symbols = agent.get_cached_symbols()  # from last index run
    engine = PerspectivesEngine(config, agent.graph)
    if perspective_name == "all":
        results = engine.run_all(symbols)
    else:
        results = [engine.run_one(perspective_name, symbols)]
    write_response({"id": req_id, "type": "perspectives", "results": [r.__dict__ for r in results]})
```

Add a `run_perspectives` method to `PythonBridge` in Rust, and wire `/analyze` in `app.rs` to call it and stream the formatted findings into the message log.

## Acceptance Criteria

- All 6 perspectives run on the test fixture project
- Complexity perspective correctly identifies functions with CC > 10
- Security perspective finds `eval(` and `innerHTML =` patterns
- Dead code perspective finds at least one false-positive-free dead function
- PerspectivesEngine gracefully skips Neo4j perspectives when the graph is unavailable
- `/analyze` in the TUI streams findings into the message log
- No file exceeds 400 lines

## Estimated Complexity

High. Six perspectives, each with its own logic. The security pattern matching and dead code heuristics require careful calibration to avoid excessive false positives.
