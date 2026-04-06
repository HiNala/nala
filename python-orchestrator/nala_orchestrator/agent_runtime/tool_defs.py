"""Tool definitions for LLM function calling.

Each tool maps to a Toolbox method. The schemas follow OpenAI's
function-calling format and are also compatible with Anthropic tool use.
"""

from __future__ import annotations

AGENT_TOOLS: list[dict] = [
    # ── Read / navigate ──────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Read the full contents of a file. Returns text with line numbers "
                "prepended (format: '   1  code here') so you can reference exact "
                "lines when making edits. Accepts relative or absolute paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative (from project root) or absolute path",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to return (1-based, optional — default: 1)",
                        "default": 1,
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to return inclusive (optional — default: read all)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_info",
            "description": "Return metadata about a file: total lines, size in bytes, last-modified timestamp.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a path (one level). Skips noise dirs automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Relative or absolute directory path (empty for project root)",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tree",
            "description": "Recursive directory tree listing. Use to understand project layout before editing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "Relative or absolute directory (empty for root)",
                        "default": "",
                    },
                    "max_depth": {
                        "type": "integer",
                        "description": "Max recursion depth (default 4)",
                        "default": 4,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_in_files",
            "description": (
                "Search files for a regex pattern (like grep -rn). Returns matching "
                "lines with file path and line number. Essential for locating functions, "
                "classes, variable usages, TODOs, etc. across the whole codebase."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Python regex pattern to search for",
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory to search (relative or absolute; default: project root)",
                        "default": "",
                    },
                    "file_glob": {
                        "type": "string",
                        "description": "File glob filter like '*.py', '*.rs', '*.ts' (default: all text files)",
                        "default": "",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max matching lines to return (default 60)",
                        "default": 60,
                    },
                    "ignore_case": {
                        "type": "boolean",
                        "description": "Case-insensitive search (default false)",
                        "default": False,
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": (
                "Semantic/keyword search of the indexed codebase. Returns the most "
                "relevant code chunks. Use for concept-level searches ('authentication logic', "
                "'error handling pattern'). For exact text use find_in_files instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (function name, class name, concept)",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cwd",
            "description": "Get the project root path (current working directory for all relative paths).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },

    # ── Write / edit ─────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file, creating it (and any parent dirs) if needed. "
                "Overwrites the file completely. Use for new files or full rewrites. "
                "For targeted changes prefer edit_file or replace_lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full file content to write",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Replace an exact verbatim block of text in a file. "
                "old_text MUST match character-for-character including whitespace/indentation. "
                "If not found, returns an error with surrounding context to help you fix the match. "
                "Use read_file first to get the exact text."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find and replace (verbatim, including indentation)",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "Replace all occurrences instead of just the first (default false)",
                        "default": False,
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "insert_lines",
            "description": (
                "Insert one or more lines of text into a file at a specific position. "
                "The new text is inserted BEFORE the given line number. "
                "Use line_number=1 to prepend to the file. "
                "Use a very large line_number (e.g. 999999) to append to the end."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    },
                    "line_number": {
                        "type": "integer",
                        "description": "1-based line number to insert BEFORE. Use 999999 to append.",
                    },
                    "text": {
                        "type": "string",
                        "description": "Text to insert (include trailing newline if needed)",
                    },
                },
                "required": ["path", "line_number", "text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "replace_lines",
            "description": (
                "Replace a specific range of lines in a file with new text. "
                "Useful when the exact old content is hard to match but you know the line range. "
                "Use read_file with start_line/end_line to inspect the target range first."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Relative path from project root",
                    },
                    "start_line": {
                        "type": "integer",
                        "description": "First line to replace (1-based, inclusive)",
                    },
                    "end_line": {
                        "type": "integer",
                        "description": "Last line to replace (1-based, inclusive)",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Replacement text (replaces the entire line range)",
                    },
                },
                "required": ["path", "start_line", "end_line", "new_text"],
            },
        },
    },

    # ── Shell / system ───────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": (
                "Run a shell command in the project. Use for: building, testing, linting, "
                "checking if a file exists, reading output of CLI tools. "
                "Returns exit_code and combined stdout+stderr."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Shell command to execute",
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory (relative or absolute; default: project root)",
                        "default": "",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default 60, max 300)",
                        "default": 60,
                    },
                },
                "required": ["command"],
            },
        },
    },

    # ── Git ──────────────────────────────────────────────────────────────────
    {
        "type": "function",
        "function": {
            "name": "git_status",
            "description": "Get current git status: branch, modified files, staged changes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_diff",
            "description": (
                "Get the current git diff (unified diff format). Shows exactly what has "
                "changed since the last commit. Use to review your own edits."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Limit diff to a specific file (optional)",
                        "default": "",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": "Show recent git commit history (author, date, message, hash).",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_commits": {
                        "type": "integer",
                        "description": "Number of commits to show (default 10)",
                        "default": 10,
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "git_commit",
            "description": (
                "Stage and commit changes to git. Stages all modified files by default. "
                "Use after a set of edits to checkpoint your work."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Commit message",
                    },
                    "add_all": {
                        "type": "boolean",
                        "description": "Stage all changes before committing (default true)",
                        "default": True,
                    },
                },
                "required": ["message"],
            },
        },
    },
]
