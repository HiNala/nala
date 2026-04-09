"""Mission 30: Project Intelligence — detect project type, frameworks, and structure.

Determines whether the current directory is a code project, a multi-project
workspace (like a Desktop folder), or a non-project directory — and returns
structured metadata used to drive smart launch behavior.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path


# ── Project markers ────────────────────────────────────────────────────────

_TYPE_MARKERS: dict[str, list[str]] = {
    "rust":   ["Cargo.toml"],
    "python": ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "Pipfile"],
    "node":   ["package.json"],
    "go":     ["go.mod"],
    "java":   ["pom.xml", "build.gradle", "build.gradle.kts"],
    "dotnet": ["*.csproj", "*.sln"],
    "ruby":   ["Gemfile"],
    "php":    ["composer.json"],
}

_FRAMEWORK_SIGNALS: dict[str, list[str]] = {
    "react":    ["react", "react-dom"],
    "next":     ["next"],
    "vue":      ["vue"],
    "svelte":   ["svelte"],
    "fastapi":  ["fastapi"],
    "django":   ["django"],
    "flask":    ["flask"],
    "actix":    ["actix-web"],
    "axum":     ["axum"],
    "tokio":    ["tokio"],
    "expo":     ["expo"],
    "react-native": ["react-native"],
}

_PKG_MANAGERS: dict[str, str] = {
    "yarn.lock":       "yarn",
    "pnpm-lock.yaml":  "pnpm",
    "package-lock.json": "npm",
    "bun.lockb":       "bun",
    "Pipfile.lock":    "pipenv",
    "poetry.lock":     "poetry",
    "uv.lock":         "uv",
    "Cargo.lock":      "cargo",
    "go.sum":          "go modules",
}


@dataclass
class ProjectInfo:
    is_project: bool
    project_type: str            # "rust" | "node" | "python" | "go" | "multi" | "unknown"
    project_root: Path
    project_name: str
    languages: list[str] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    package_manager: str = ""
    has_git: bool = False
    git_branch: str = ""
    estimated_size: str = "unknown"   # "small" | "medium" | "large"
    sub_projects: list[Path] = field(default_factory=list)


class ProjectDetector:
    """Analyse a directory and return structured project metadata."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def detect(self) -> ProjectInfo:
        languages = self._detect_languages(self.root)
        sub_projects = self._find_sub_projects()

        # Multi-project root (Desktop, workspace) — no top-level markers but
        # multiple children look like independent projects.
        if not languages and len(sub_projects) >= 2:
            return ProjectInfo(
                is_project=False,
                project_type="multi",
                project_root=self.root,
                project_name=self.root.name,
                languages=[],
                sub_projects=sub_projects,
            )

        if not languages and not sub_projects:
            return ProjectInfo(
                is_project=False,
                project_type="unknown",
                project_root=self.root,
                project_name=self.root.name,
            )

        name = self._detect_name(languages)
        frameworks = self._detect_frameworks(languages)
        pkg_mgr = self._detect_package_manager()
        has_git = (self.root / ".git").exists()
        git_branch = self._git_branch() if has_git else ""
        size = self._estimate_size()

        return ProjectInfo(
            is_project=True,
            project_type=languages[0] if languages else "unknown",
            project_root=self.root,
            project_name=name,
            languages=languages,
            frameworks=frameworks,
            package_manager=pkg_mgr,
            has_git=has_git,
            git_branch=git_branch,
            estimated_size=size,
            sub_projects=sub_projects,
        )

    # ── Private helpers ────────────────────────────────────────────────────

    def _detect_languages(self, path: Path) -> list[str]:
        found: list[str] = []
        try:
            children = {e.name for e in path.iterdir()}
        except OSError:
            return found
        for lang, markers in _TYPE_MARKERS.items():
            for m in markers:
                if "*" in m:
                    if any(path.glob(m)):
                        found.append(lang)
                        break
                elif m in children:
                    found.append(lang)
                    break
        return found

    def _find_sub_projects(self) -> list[Path]:
        subs: list[Path] = []
        try:
            for entry in self.root.iterdir():
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                if self._detect_languages(entry):
                    subs.append(entry)
        except OSError:
            pass
        return subs

    def _detect_name(self, languages: list[str]) -> str:
        # Rust
        cargo = self.root / "Cargo.toml"
        if cargo.exists():
            try:
                for line in cargo.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("name"):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except OSError:
                pass
        # Node
        pkg = self.root / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "name" in data:
                    return str(data["name"])
            except Exception:
                pass
        # Python
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            try:
                for line in pyproject.read_text(encoding="utf-8").splitlines():
                    if line.strip().startswith("name"):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
            except OSError:
                pass
        return self.root.name

    def _detect_frameworks(self, languages: list[str]) -> list[str]:
        found: list[str] = []
        # Node: parse package.json
        if "node" in languages:
            pkg = self.root / "package.json"
            if pkg.exists():
                try:
                    data = json.loads(pkg.read_text(encoding="utf-8"))
                    all_deps = set(
                        list(data.get("dependencies", {}).keys())
                        + list(data.get("devDependencies", {}).keys())
                    )
                    for fw, signals in _FRAMEWORK_SIGNALS.items():
                        if any(s in all_deps for s in signals):
                            found.append(fw)
                except Exception:
                    pass
        # Rust: parse Cargo.toml
        if "rust" in languages:
            cargo = self.root / "Cargo.toml"
            if cargo.exists():
                try:
                    content = cargo.read_text(encoding="utf-8")
                    for fw, signals in _FRAMEWORK_SIGNALS.items():
                        if any(s in content for s in signals):
                            found.append(fw)
                except OSError:
                    pass
        return found

    def _detect_package_manager(self) -> str:
        for lock_file, name in _PKG_MANAGERS.items():
            if (self.root / lock_file).exists():
                return name
        return ""

    def _git_branch(self) -> str:
        head = self.root / ".git" / "HEAD"
        try:
            content = head.read_text(encoding="utf-8").strip()
            if content.startswith("ref: refs/heads/"):
                return content[len("ref: refs/heads/"):]
            return content[:8]
        except OSError:
            return ""

    def _estimate_size(self) -> str:
        try:
            count = sum(1 for _ in self.root.rglob("*") if _.is_file()
                        and not any(p.startswith(".") for p in _.parts[-3:]))
        except OSError:
            return "unknown"
        if count < 100:
            return "small"
        if count < 1000:
            return "medium"
        return "large"


# ── LSP detector ───────────────────────────────────────────────────────────

_LSP_SEARCH_PATHS: dict[str, list[str]] = {
    "rust": [
        "rust-analyzer",
        "~/.cargo/bin/rust-analyzer",
    ],
    "python": [
        "pyright",
        "pylsp",
        "~/.local/bin/pyright",
        "~/.local/bin/pylsp",
    ],
    "node": [
        "typescript-language-server",
        "./node_modules/.bin/typescript-language-server",
        "~/.npm-global/bin/typescript-language-server",
    ],
    "go": [
        "gopls",
        "~/go/bin/gopls",
    ],
}

_LSP_INSTALL_HINTS: dict[str, str] = {
    "rust":   "rustup component add rust-analyzer",
    "python": "pip install pyright  OR  pip install python-lsp-server",
    "node":   "npm install -g typescript-language-server typescript",
    "go":     "go install golang.org/x/tools/gopls@latest",
}


def find_lsp_binary(language: str) -> tuple[str, str] | None:
    """Return (binary_path, language) or None if not found.

    Searches PATH plus common install locations.
    """
    candidates = _LSP_SEARCH_PATHS.get(language, [])
    for candidate in candidates:
        expanded = str(Path(candidate).expanduser()) if "~" in candidate else candidate
        if shutil.which(expanded) or (Path(expanded).is_absolute() and Path(expanded).exists()):
            return (expanded, language)
    return None


def lsp_availability(info: ProjectInfo) -> dict[str, str | None]:
    """Return {language: binary_path_or_None} for the project's languages."""
    result: dict[str, str | None] = {}
    for lang in info.languages:
        found = find_lsp_binary(lang)
        result[lang] = found[0] if found else None
    return result


def lsp_install_hint(language: str) -> str:
    return _LSP_INSTALL_HINTS.get(language, f"Install a language server for {language}")
