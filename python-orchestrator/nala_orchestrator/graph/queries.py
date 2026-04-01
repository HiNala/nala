"""
Common Cypher query library.

Centralises all graph queries so they are easy to review, optimise,
and update when the schema changes. Each function returns a Cypher
string and an optional params dict.
"""

from __future__ import annotations

from typing import Any


def find_high_complexity_functions(threshold: int = 10) -> tuple[str, dict[str, Any]]:
    """Find functions with cyclomatic complexity above the threshold."""
    return (
        """
        MATCH (fn:Function)
        WHERE fn.cyclomatic >= $threshold
        RETURN fn.name AS name,
               fn.file_path AS file_path,
               fn.start_line AS line,
               fn.cyclomatic AS complexity
        ORDER BY fn.cyclomatic DESC
        """,
        {"threshold": threshold},
    )


def find_most_imported_modules() -> tuple[str, dict]:
    """Find modules that are imported by many files (high fan-in)."""
    return (
        """
        MATCH (f:File)-[:IMPORTS]->(m)
        RETURN m.path AS module,
               count(f) AS import_count
        ORDER BY import_count DESC
        LIMIT 20
        """,
        {},
    )


def find_circular_dependencies() -> tuple[str, dict]:
    """Detect files that import each other (circular dependency)."""
    return (
        """
        MATCH (a:File)-[:IMPORTS]->(b:File)-[:IMPORTS]->(a)
        RETURN a.path AS file_a, b.path AS file_b
        """,
        {},
    )


def find_isolated_functions() -> tuple[str, dict]:
    """Find functions that are defined but never called (dead code)."""
    return (
        """
        MATCH (fn:Function)
        WHERE NOT (fn)<-[:CALLS]-()
          AND fn.visibility <> 'public'
        RETURN fn.name AS name,
               fn.file_path AS file_path,
               fn.start_line AS start_line
        ORDER BY fn.file_path, fn.start_line
        """,
        {},
    )


def find_high_coupling(fan_out: int = 15, fan_in: int = 10) -> tuple[str, dict]:
    """Find files with unusually high import coupling."""
    return (
        """
        MATCH (f:File)-[:IMPORTS]->(m)
        WITH f, count(m) AS out_count
        WHERE out_count >= $fan_out
        RETURN f.path AS file, out_count AS fan_out_count, 'high_fan_out' AS kind
        UNION
        MATCH (f:File)-[:IMPORTS]->(m)
        WITH m, count(f) AS in_count
        WHERE in_count >= $fan_in
        RETURN m.path AS file, in_count AS fan_out_count, 'high_fan_in' AS kind
        ORDER BY fan_out_count DESC
        LIMIT 20
        """,
        {"fan_out": fan_out, "fan_in": fan_in},
    )


def find_dead_functions() -> tuple[str, dict]:
    """Find functions that are defined but never called."""
    return (
        """
        MATCH (fn:Function)
        WHERE NOT (fn)<-[:CALLS]-()
          AND fn.visibility <> 'public'
        RETURN fn.name AS name,
               fn.file_path AS file_path,
               fn.start_line AS line
        ORDER BY fn.file_path, fn.start_line
        """,
        {},
    )


def get_call_graph(function_name: str) -> tuple[str, dict[str, Any]]:
    """Get the call graph rooted at a function (2 levels deep)."""
    return (
        """
        MATCH path = (fn:Function {name: $name})-[:CALLS*1..2]->(callee:Function)
        RETURN path
        """,
        {"name": function_name},
    )


def upsert_file(path: str, language: str, size_bytes: int) -> tuple[str, dict[str, Any]]:
    """Create or update a File node."""
    return (
        """
        MERGE (f:File {path: $path})
        SET f.language = $language,
            f.size_bytes = $size_bytes,
            f.updated_at = timestamp()
        """,
        {"path": path, "language": language, "size_bytes": size_bytes},
    )


# ── Mission 07 named query API ────────────────────────────────────────────────

def get_file_dependencies(file_path: str) -> tuple[str, dict[str, Any]]:
    """What modules/files does this file depend on?"""
    return (
        """
        MATCH (f:File {path: $path})-[:IMPORTS]->(m)
        RETURN m.name AS module, m.path AS path, labels(m)[0] AS kind
        ORDER BY module
        """,
        {"path": file_path},
    )


def get_dependents(module_name: str) -> tuple[str, dict[str, Any]]:
    """What files import this module?"""
    return (
        """
        MATCH (f:File)-[:IMPORTS]->(m {name: $name})
        RETURN f.path AS file_path
        ORDER BY file_path
        """,
        {"name": module_name},
    )


def get_function_callers(function_name: str) -> tuple[str, dict[str, Any]]:
    """What functions call this function?"""
    return (
        """
        MATCH (caller:Function)-[:CALLS]->(fn:Function {name: $name})
        RETURN caller.name AS caller_name,
               caller.file_path AS caller_file,
               caller.start_line AS caller_line
        ORDER BY caller_file, caller_line
        """,
        {"name": function_name},
    )


def get_function_callees(function_name: str) -> tuple[str, dict[str, Any]]:
    """What functions does this function call?"""
    return (
        """
        MATCH (fn:Function {name: $name})-[:CALLS]->(callee:Function)
        RETURN callee.name AS callee_name,
               callee.file_path AS callee_file,
               callee.start_line AS callee_line
        ORDER BY callee_file, callee_line
        """,
        {"name": function_name},
    )


def get_most_connected_modules(limit: int = 10) -> tuple[str, dict[str, Any]]:
    """Which modules have the most connections (fan-in + fan-out)?"""
    return (
        """
        MATCH (m:Module)
        OPTIONAL MATCH (m)<-[:IMPORTS]-(importer)
        WITH m, count(importer) AS fan_in
        OPTIONAL MATCH (m)-[:DEPENDS_ON]->(dep)
        WITH m, fan_in, count(dep) AS fan_out
        RETURN m.name AS module,
               fan_in,
               fan_out,
               fan_in + fan_out AS total_connections
        ORDER BY total_connections DESC
        LIMIT $limit
        """,
        {"limit": limit},
    )


def get_complexity_hotspots(threshold: int = 10) -> tuple[str, dict[str, Any]]:
    """Functions above a complexity threshold (alias for find_high_complexity_functions)."""
    return find_high_complexity_functions(threshold)


def upsert_function(
    func_id: str, name: str, file_path: str,
    start_line: int, end_line: int, cyclomatic: int = 0,
) -> tuple[str, dict[str, Any]]:
    """Create or update a Function node and link it to its file."""
    return (
        """
        MERGE (fn:Function {id: $id})
        SET fn.name = $name,
            fn.file_path = $file_path,
            fn.start_line = $start_line,
            fn.end_line = $end_line,
            fn.cyclomatic = $cyclomatic
        WITH fn
        MATCH (f:File {path: $file_path})
        MERGE (f)-[:CONTAINS]->(fn)
        """,
        {
            "id": func_id, "name": name, "file_path": file_path,
            "start_line": start_line, "end_line": end_line,
            "cyclomatic": cyclomatic,
        },
    )
