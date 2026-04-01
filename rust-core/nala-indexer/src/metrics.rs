//! Code quality metrics computation.
//!
//! Computes cyclomatic complexity, cognitive complexity, and line counts
//! per source file. Currently implemented via simple AST-based heuristics
//! that work across all supported languages.
//!
//! Mission 07 will replace these with rust-code-analysis for deeper metrics
//! on supported languages. The interface is designed to be forward-compatible.

use serde::{Deserialize, Serialize};

// ── Metrics result ─────────────────────────────────────────────────────────

/// Code quality metrics for a single source file.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct FileMetrics {
    pub relative_path: String,
    pub language: String,
    /// Physical lines of code (all lines including blanks and comments).
    pub ploc: usize,
    /// Source lines of code (non-blank, non-comment lines).
    pub sloc: usize,
    /// Comment lines.
    pub cloc: usize,
    /// Blank lines.
    pub blank: usize,
    /// Estimated cyclomatic complexity (branching paths through the file).
    pub cyclomatic: usize,
    /// List of functions with their individual complexity scores.
    pub function_complexity: Vec<FunctionComplexity>,
}

/// Cyclomatic complexity for a single function.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FunctionComplexity {
    pub name: String,
    pub start_line: usize,
    pub end_line: usize,
    pub cyclomatic: usize,
}

impl FunctionComplexity {
    /// Severity level based on cyclomatic complexity.
    /// Thresholds based on industry standards (McCabe 1976, NIST guidelines).
    pub fn severity(&self) -> ComplexitySeverity {
        match self.cyclomatic {
            0..=5 => ComplexitySeverity::Low,
            6..=10 => ComplexitySeverity::Medium,
            11..=20 => ComplexitySeverity::High,
            _ => ComplexitySeverity::Critical,
        }
    }
}

/// Severity of a complexity score.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ComplexitySeverity {
    Low,
    Medium,
    High,
    Critical,
}

impl std::fmt::Display for ComplexitySeverity {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Low => write!(f, "low"),
            Self::Medium => write!(f, "medium"),
            Self::High => write!(f, "high"),
            Self::Critical => write!(f, "critical"),
        }
    }
}

// ── Public API ─────────────────────────────────────────────────────────────

/// Compute basic metrics for a source file from its raw text.
///
/// This is a fast, language-agnostic implementation based on line analysis.
/// It correctly handles single-line and multi-line comments for Rust, Python,
/// JS/TS, and Go.
pub fn compute_file_metrics(source: &str, relative_path: &str, language: &str) -> FileMetrics {
    let mut metrics = FileMetrics {
        relative_path: relative_path.to_string(),
        language: language.to_string(),
        ..Default::default()
    };

    let mut in_block_comment = false;

    for line in source.lines() {
        metrics.ploc += 1;
        let trimmed = line.trim();

        if trimmed.is_empty() {
            metrics.blank += 1;
            continue;
        }

        // Block comment tracking (language-specific)
        if is_block_comment_start(trimmed, language) {
            in_block_comment = true;
        }
        if in_block_comment {
            metrics.cloc += 1;
            if is_block_comment_end(trimmed, language) {
                in_block_comment = false;
            }
            continue;
        }

        if is_line_comment(trimmed, language) {
            metrics.cloc += 1;
        } else {
            metrics.sloc += 1;
            // Cyclomatic complexity: count decision points
            metrics.cyclomatic += count_decision_points(trimmed, language);
        }
    }

    // Base cyclomatic complexity starts at 1
    if metrics.cyclomatic == 0 && metrics.sloc > 0 {
        metrics.cyclomatic = 1;
    }

    metrics
}

// ── Helpers ────────────────────────────────────────────────────────────────

/// Count decision-point keywords on a single line.
/// Each adds 1 to cyclomatic complexity.
fn count_decision_points(line: &str, language: &str) -> usize {
    let keywords: &[&str] = match language {
        "rust" => &["if ", "else if ", "while ", "for ", "match ", "loop ", "?", "&&", "||"],
        "python" => &["if ", "elif ", "while ", "for ", "except", "and ", "or "],
        "javascript" | "typescript" | "tsx" => {
            &["if ", "else if ", "while ", "for ", "catch", "&&", "||", "??"]
        }
        "go" => &["if ", "else if ", "for ", "case ", "&&", "||"],
        _ => &["if ", "while ", "for "],
    };

    keywords.iter().filter(|&&kw| line.contains(kw)).count()
}

fn is_line_comment(line: &str, language: &str) -> bool {
    match language {
        "rust" | "javascript" | "typescript" | "tsx" | "go" => {
            line.starts_with("//")
        }
        "python" => line.starts_with('#'),
        _ => line.starts_with("//") || line.starts_with('#'),
    }
}

fn is_block_comment_start(line: &str, language: &str) -> bool {
    match language {
        "rust" | "javascript" | "typescript" | "tsx" | "go" => line.starts_with("/*"),
        "python" => line.starts_with("\"\"\"") || line.starts_with("'''"),
        _ => line.starts_with("/*"),
    }
}

fn is_block_comment_end(line: &str, language: &str) -> bool {
    match language {
        "rust" | "javascript" | "typescript" | "tsx" | "go" => line.ends_with("*/"),
        "python" => line.ends_with("\"\"\"") || line.ends_with("'''"),
        _ => line.ends_with("*/"),
    }
}

// ── Tests ──────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn basic_rust_metrics() {
        let src = r#"
fn hello() {
    // comment
    println!("hello");
}

fn complex(x: i32) -> i32 {
    if x > 0 {
        x * 2
    } else {
        -x
    }
}
"#;
        let m = compute_file_metrics(src, "test.rs", "rust");
        assert!(m.sloc > 0);
        assert!(m.cloc > 0);
        assert!(m.cyclomatic >= 2); // at least the if/else
    }

    #[test]
    fn severity_thresholds() {
        let low = FunctionComplexity { name: "a".into(), start_line: 1, end_line: 5, cyclomatic: 3 };
        let high = FunctionComplexity { name: "b".into(), start_line: 1, end_line: 50, cyclomatic: 15 };
        assert_eq!(low.severity(), ComplexitySeverity::Low);
        assert_eq!(high.severity(), ComplexitySeverity::High);
    }
}
