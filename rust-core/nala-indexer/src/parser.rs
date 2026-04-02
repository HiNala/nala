//! Tree-sitter–based parser and symbol extractor.
//!
//! Parses source files into ASTs and extracts symbols (functions, classes,
//! imports, calls). Each language requires its own extraction logic because
//! AST node types differ across grammars.
//!
//! Files are processed in parallel via Rayon. Each file gets its own
//! Tree-sitter parser instance (parsers are not Send).

use crate::hasher::HashedFile;
use crate::symbol_graph::{Symbol, SymbolKind};
use anyhow::Result;
use rayon::prelude::*;
use std::path::Path;

// ── Parsed file ────────────────────────────────────────────────────────────

/// The result of parsing a single source file.
#[derive(Debug)]
pub struct ParsedFile {
    pub relative_path: String,
    pub language: String,
    pub symbols: Vec<Symbol>,
    pub parse_error_count: usize,
    pub line_count: usize,
}

// ── Language detection ─────────────────────────────────────────────────────

/// Map a file extension to a language name.
///
/// Returns None for unrecognised extensions (file will be skipped during parse).
pub fn detect_language(extension: &str) -> Option<&'static str> {
    match extension.to_lowercase().as_str() {
        "rs" => Some("rust"),
        "py" | "pyi" => Some("python"),
        "js" | "mjs" | "cjs" => Some("javascript"),
        "jsx" => Some("javascript"),
        "ts" | "mts" | "cts" => Some("typescript"),
        "tsx" => Some("tsx"),
        "go" => Some("go"),
        _ => None,
    }
}

// ── Parallel entry point ────────────────────────────────────────────────────

/// Parse a slice of files in parallel and return all extracted symbols.
///
/// Files with unrecognised extensions are silently skipped.
/// Parse errors are logged as warnings but do not fail the overall indexing.
pub fn parse_files_parallel(files: &[HashedFile], _root: &Path) -> Result<Vec<Symbol>> {
    let symbols: Vec<Vec<Symbol>> = files
        .par_iter()
        .filter_map(|file| {
            let lang = detect_language(&file.extension)?;
            match parse_file(&file.absolute_path, &file.relative_path, lang) {
                Ok(parsed) => Some(parsed.symbols),
                Err(e) => {
                    tracing::warn!("Parse error in {}: {}", file.relative_path, e);
                    None
                }
            }
        })
        .collect();

    Ok(symbols.into_iter().flatten().collect())
}

// ── Single file parser ─────────────────────────────────────────────────────

/// Parse one file and extract its symbols.
pub fn parse_file(path: &Path, relative_path: &str, language: &str) -> Result<ParsedFile> {
    let source = std::fs::read_to_string(path)?;
    let line_count = source.lines().count();

    let (symbols, error_count) = match language {
        "rust" => extract_rust(&source, relative_path),
        "python" => extract_python(&source, relative_path),
        "javascript" | "typescript" | "tsx" => extract_js_ts(&source, relative_path, language),
        "go" => extract_go(&source, relative_path),
        _ => (vec![], 0),
    };

    Ok(ParsedFile {
        relative_path: relative_path.to_string(),
        language: language.to_string(),
        symbols,
        parse_error_count: error_count,
        line_count,
    })
}

// ── Language extractors ────────────────────────────────────────────────────
// Each extractor uses Tree-sitter to walk the AST and collect symbols.
// Node type names come from the grammar definitions.

fn extract_rust(source: &str, file_path: &str) -> (Vec<Symbol>, usize) {
    let mut parser = tree_sitter::Parser::new();
    if parser.set_language(&tree_sitter_rust::LANGUAGE.into()).is_err() {
        return (vec![], 0);
    }

    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (vec![], 0),
    };

    let mut symbols = Vec::new();
    let _cursor = tree.walk();
    let error_count = count_errors(&tree.root_node());

    walk_node_rust(tree.root_node(), source, file_path, &mut symbols);
    (symbols, error_count)
}

fn walk_node_rust(node: tree_sitter::Node, source: &str, file_path: &str, out: &mut Vec<Symbol>) {
    match node.kind() {
        "function_item" => {
            if let Some(name) = get_child_text(&node, "name", source) {
                let mut sym = Symbol::new(
                    SymbolKind::Function,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "rust",
                );
                // Capture visibility
                if let Some(vis) = node.child_by_field_name("visibility") {
                    sym = sym.with_meta("visibility", vis.utf8_text(source.as_bytes()).unwrap_or(""));
                }
                out.push(sym);
            }
        }
        "struct_item" | "enum_item" | "trait_item" | "impl_item" => {
            if let Some(name) = get_child_text(&node, "name", source) {
                out.push(Symbol::new(
                    SymbolKind::Class,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "rust",
                ));
            }
        }
        "use_declaration" => {
            let text = node.utf8_text(source.as_bytes()).unwrap_or("").to_string();
            out.push(Symbol::new(
                SymbolKind::Import,
                text.trim_start_matches("use ").trim_end_matches(';').trim().to_string(),
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                "rust",
            ));
        }
        _ => {}
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_node_rust(child, source, file_path, out);
    }
}

fn extract_python(source: &str, file_path: &str) -> (Vec<Symbol>, usize) {
    let mut parser = tree_sitter::Parser::new();
    if parser.set_language(&tree_sitter_python::LANGUAGE.into()).is_err() {
        return (vec![], 0);
    }
    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (vec![], 0),
    };

    let mut symbols = Vec::new();
    let error_count = count_errors(&tree.root_node());
    walk_node_python(tree.root_node(), source, file_path, &mut symbols);
    (symbols, error_count)
}

fn walk_node_python(node: tree_sitter::Node, source: &str, file_path: &str, out: &mut Vec<Symbol>) {
    match node.kind() {
        "function_definition" => {
            if let Some(name) = get_child_text(&node, "name", source) {
                out.push(Symbol::new(
                    SymbolKind::Function,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "python",
                ));
            }
        }
        "class_definition" => {
            if let Some(name) = get_child_text(&node, "name", source) {
                out.push(Symbol::new(
                    SymbolKind::Class,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "python",
                ));
            }
        }
        "import_statement" | "import_from_statement" => {
            let text = node.utf8_text(source.as_bytes()).unwrap_or("").to_string();
            out.push(Symbol::new(
                SymbolKind::Import,
                text.trim().to_string(),
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                "python",
            ));
        }
        _ => {}
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_node_python(child, source, file_path, out);
    }
}

fn extract_js_ts(source: &str, file_path: &str, language: &str) -> (Vec<Symbol>, usize) {
    let mut parser = tree_sitter::Parser::new();
    let set_ok = match language {
        "typescript" => parser.set_language(&tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into()),
        "tsx" => parser.set_language(&tree_sitter_typescript::LANGUAGE_TSX.into()),
        _ => parser.set_language(&tree_sitter_javascript::LANGUAGE.into()),
    };
    if set_ok.is_err() {
        return (vec![], 0);
    }
    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (vec![], 0),
    };

    let mut symbols = Vec::new();
    let error_count = count_errors(&tree.root_node());
    walk_node_js(tree.root_node(), source, file_path, language, &mut symbols);
    (symbols, error_count)
}

fn walk_node_js(node: tree_sitter::Node, source: &str, file_path: &str, lang: &str, out: &mut Vec<Symbol>) {
    match node.kind() {
        "function_declaration" | "function_expression" | "arrow_function"
        | "method_definition" => {
            let name = get_child_text(&node, "name", source).unwrap_or_else(|| "<anonymous>".to_string());
            out.push(Symbol::new(
                SymbolKind::Function,
                name,
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                lang,
            ));
        }
        "class_declaration" | "class_expression" => {
            let name = get_child_text(&node, "name", source).unwrap_or_else(|| "<anonymous>".to_string());
            out.push(Symbol::new(
                SymbolKind::Class,
                name,
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                lang,
            ));
        }
        "import_statement" => {
            let text = node.utf8_text(source.as_bytes()).unwrap_or("").to_string();
            out.push(Symbol::new(
                SymbolKind::Import,
                text.trim().to_string(),
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                lang,
            ));
        }
        _ => {}
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_node_js(child, source, file_path, lang, out);
    }
}

fn extract_go(source: &str, file_path: &str) -> (Vec<Symbol>, usize) {
    let mut parser = tree_sitter::Parser::new();
    if parser.set_language(&tree_sitter_go::LANGUAGE.into()).is_err() {
        return (vec![], 0);
    }
    let tree = match parser.parse(source, None) {
        Some(t) => t,
        None => return (vec![], 0),
    };

    let mut symbols = Vec::new();
    let error_count = count_errors(&tree.root_node());
    walk_node_go(tree.root_node(), source, file_path, &mut symbols);
    (symbols, error_count)
}

fn walk_node_go(node: tree_sitter::Node, source: &str, file_path: &str, out: &mut Vec<Symbol>) {
    match node.kind() {
        "function_declaration" | "method_declaration" => {
            if let Some(name) = get_child_text(&node, "name", source) {
                out.push(Symbol::new(
                    SymbolKind::Function,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "go",
                ));
            }
        }
        "type_declaration" => {
            if let Some(name) = node.child(1).and_then(|n| {
                n.utf8_text(source.as_bytes()).ok().map(|s| s.to_string())
            }) {
                out.push(Symbol::new(
                    SymbolKind::Class,
                    name,
                    file_path,
                    node.start_position().row + 1,
                    node.end_position().row + 1,
                    "go",
                ));
            }
        }
        "import_declaration" => {
            let text = node.utf8_text(source.as_bytes()).unwrap_or("").to_string();
            out.push(Symbol::new(
                SymbolKind::Import,
                text.trim().to_string(),
                file_path,
                node.start_position().row + 1,
                node.end_position().row + 1,
                "go",
            ));
        }
        _ => {}
    }

    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        walk_node_go(child, source, file_path, out);
    }
}

// ── Helpers ────────────────────────────────────────────────────────────────

/// Get the text of a named child node (e.g. the "name" field of a function).
fn get_child_text(node: &tree_sitter::Node, field: &str, source: &str) -> Option<String> {
    node.child_by_field_name(field)
        .and_then(|n| n.utf8_text(source.as_bytes()).ok())
        .map(|s| s.to_string())
}

/// Count ERROR nodes in the syntax tree (indicates parse failures).
fn count_errors(node: &tree_sitter::Node) -> usize {
    let mut count = if node.is_error() { 1 } else { 0 };
    let mut cursor = node.walk();
    for child in node.children(&mut cursor) {
        count += count_errors(&child);
    }
    count
}
