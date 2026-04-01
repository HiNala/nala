//! Symbol types extracted from parsed source files.
//!
//! A Symbol is any named, meaningful unit of code: functions, classes,
//! modules, imports, or call sites. These become nodes in the Neo4j code
//! knowledge graph (Mission 07).

use serde::{Deserialize, Serialize};

// ── Symbol kind ────────────────────────────────────────────────────────────

/// The kind of code symbol.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum SymbolKind {
    /// A function or method definition.
    Function,
    /// A class, struct, enum, or interface definition.
    Class,
    /// A module or namespace declaration.
    Module,
    /// An import or use statement.
    Import,
    /// A call to a function (edge in the call graph).
    Call,
}

impl std::fmt::Display for SymbolKind {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Function => write!(f, "function"),
            Self::Class => write!(f, "class"),
            Self::Module => write!(f, "module"),
            Self::Import => write!(f, "import"),
            Self::Call => write!(f, "call"),
        }
    }
}

// ── Symbol ─────────────────────────────────────────────────────────────────

/// A named, meaningful unit of code extracted from a source file.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Symbol {
    /// The kind of symbol.
    pub kind: SymbolKind,
    /// The symbol's name.
    pub name: String,
    /// Path to the file containing this symbol (relative to project root).
    pub file_path: String,
    /// 1-based line where the symbol starts.
    pub start_line: usize,
    /// 1-based line where the symbol ends.
    pub end_line: usize,
    /// Programming language of the file.
    pub language: String,
    /// Additional language-specific metadata (e.g. visibility, param count).
    pub metadata: std::collections::HashMap<String, String>,
}

impl Symbol {
    pub fn new(
        kind: SymbolKind,
        name: impl Into<String>,
        file_path: impl Into<String>,
        start_line: usize,
        end_line: usize,
        language: impl Into<String>,
    ) -> Self {
        Self {
            kind,
            name: name.into(),
            file_path: file_path.into(),
            start_line,
            end_line,
            language: language.into(),
            metadata: std::collections::HashMap::new(),
        }
    }

    pub fn with_meta(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.metadata.insert(key.into(), value.into());
        self
    }
}
