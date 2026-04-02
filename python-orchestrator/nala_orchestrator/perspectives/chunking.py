"""Pre-analysis chunking strategies (Mission 08).

Groups project files into logical sections so users can pick which areas
to analyse, keeping the experience focused and interactive.

Three strategies are provided:

  * **directory** — group by top-level directory
  * **module**    — group by detected import clusters (via dependency counts)
  * **complexity** — group by average function complexity tier
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = {
    "node_modules", "target", ".git", "__pycache__", ".venv",
    "venv", "dist", "build", ".nala", ".mypy_cache", ".ruff_cache",
}
_SOURCE_EXTS = {
    ".py", ".rs", ".js", ".ts", ".jsx", ".tsx", ".go", ".java",
    ".rb", ".cpp", ".c", ".cs",
}


@dataclass
class AnalysisSection:
    """A group of files presented to the user as a single analysis unit."""

    name: str
    description: str
    file_paths: list[str] = field(default_factory=list)
    file_count: int = 0
    total_sloc: int = 0
    avg_complexity: float = 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "file_count": self.file_count,
            "total_sloc": self.total_sloc,
            "avg_complexity": round(self.avg_complexity, 1),
        }


def chunk_by_directory(
    project_root: str,
    file_metrics: list[dict] | None = None,
) -> list[AnalysisSection]:
    """Group source files by their top-level directory under `project_root`."""
    root = Path(project_root)
    groups: dict[str, list[Path]] = defaultdict(list)

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SOURCE_EXTS:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root)
        top = rel.parts[0] if len(rel.parts) > 1 else "<root>"
        groups[top].append(path)

    metrics_map = _build_metrics_map(file_metrics)

    sections: list[AnalysisSection] = []
    for name, files in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        sloc, complexity = _aggregate_metrics(files, root, metrics_map)
        sections.append(AnalysisSection(
            name=name,
            description=f"{len(files)} files in {name}/",
            file_paths=[str(f.relative_to(root)) for f in files],
            file_count=len(files),
            total_sloc=sloc,
            avg_complexity=complexity,
        ))
    return sections


def chunk_by_complexity(
    project_root: str,
    file_metrics: list[dict] | None = None,
) -> list[AnalysisSection]:
    """Group files into Low / Medium / High complexity tiers."""
    root = Path(project_root)
    tiers: dict[str, list[Path]] = {"Low": [], "Medium": [], "High": []}
    metrics_map = _build_metrics_map(file_metrics)

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SOURCE_EXTS:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel_str = str(path.relative_to(root)).replace("\\", "/")
        m = metrics_map.get(rel_str, {})
        avg_cx = m.get("avg_complexity", 1.0)
        if avg_cx > 15:
            tiers["High"].append(path)
        elif avg_cx > 5:
            tiers["Medium"].append(path)
        else:
            tiers["Low"].append(path)

    sections: list[AnalysisSection] = []
    for tier_name in ("High", "Medium", "Low"):
        files = tiers[tier_name]
        if not files:
            continue
        sloc, complexity = _aggregate_metrics(files, root, metrics_map)
        emoji = {"High": " (hotspots)", "Medium": "", "Low": ""}[tier_name]
        sections.append(AnalysisSection(
            name=f"{tier_name} complexity{emoji}",
            description=f"{len(files)} files with {tier_name.lower()} complexity",
            file_paths=[str(f.relative_to(root)) for f in files],
            file_count=len(files),
            total_sloc=sloc,
            avg_complexity=complexity,
        ))
    return sections


def chunk_by_module(
    project_root: str,
    file_metrics: list[dict] | None = None,
    import_edges: list[tuple[str, str]] | None = None,
) -> list[AnalysisSection]:
    """Group files by detected module/import clusters.

    Uses a simple union-find over import edges when available,
    falling back to directory grouping.
    """
    if not import_edges:
        return chunk_by_directory(project_root, file_metrics)

    root = Path(project_root)
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for src, dst in import_edges:
        union(src, dst)

    clusters: dict[str, list[str]] = defaultdict(list)
    all_files: set[str] = set()
    for src, dst in import_edges:
        all_files.add(src)
        all_files.add(dst)

    for f in all_files:
        clusters[find(f)].append(f)

    # Add unclustered source files as singletons
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _SOURCE_EXTS:
            continue
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = str(path.relative_to(root))
        if rel not in all_files:
            clusters[rel].append(rel)

    metrics_map = _build_metrics_map(file_metrics)
    sections: list[AnalysisSection] = []
    for _i, (_rep, members) in enumerate(
        sorted(clusters.items(), key=lambda kv: -len(kv[1])), start=1
    ):
        paths = [root / m for m in members]
        sloc, complexity = _aggregate_metrics(paths, root, metrics_map)
        label = _cluster_label(members)
        sections.append(AnalysisSection(
            name=label,
            description=f"{len(members)} related files",
            file_paths=members,
            file_count=len(members),
            total_sloc=sloc,
            avg_complexity=complexity,
        ))
    return sections


# ── Helpers ──────────────────────────────────────────────────────────────────


def _build_metrics_map(file_metrics: list[dict] | None) -> dict[str, dict]:
    if not file_metrics:
        return {}
    return {m["file_path"].replace("\\", "/"): m for m in file_metrics if "file_path" in m}


def _sloc(path: Path) -> int:
    try:
        return sum(
            1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
            if line.strip()
        )
    except OSError:
        return 0


def _aggregate_metrics(
    files: list[Path],
    root: Path,
    metrics_map: dict[str, dict],
) -> tuple[int, float]:
    """Return (total_sloc, avg_complexity) for a file group."""
    total_sloc = 0
    complexity_sum = 0.0
    complexity_count = 0
    for f in files:
        rel = str(f.relative_to(root)).replace("\\", "/")
        m = metrics_map.get(rel)
        if m:
            total_sloc += m.get("sloc", 0)
            if "avg_complexity" in m:
                complexity_sum += m["avg_complexity"]
                complexity_count += 1
        else:
            total_sloc += _sloc(f)
    avg = complexity_sum / complexity_count if complexity_count else 0.0
    return total_sloc, avg


def _cluster_label(members: list[str]) -> str:
    """Derive a readable label from the common path prefix of cluster members."""
    if len(members) == 1:
        return members[0]
    parts = [Path(m).parts for m in members]
    common: list[str] = []
    for i, seg in enumerate(parts[0]):
        if all(len(p) > i and p[i] == seg for p in parts):
            common.append(seg)
        else:
            break
    if common:
        return "/".join(common) + "/*"
    return members[0].rsplit("/", 1)[0] if "/" in members[0] else members[0]
