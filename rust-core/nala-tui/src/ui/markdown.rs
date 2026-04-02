//! Lightweight markdown-to-ratatui renderer.
//!
//! Handles the subset of markdown that LLMs commonly produce:
//!   - **bold**, *italic*, `inline code`
//!   - ```code blocks``` (with optional language tag)
//!   - ## headings (levels 1-3)
//!   - - bullet lists

use ratatui::{
    style::{Color, Modifier, Style},
    text::{Line, Span},
};

use super::theme;

pub fn render_markdown(text: &str, indent: &str) -> Vec<Line<'static>> {
    let mut lines: Vec<Line<'static>> = Vec::new();
    let mut in_code_block = false;
    let mut code_lang = String::new();
    let mut code_lines: Vec<String> = Vec::new();

    for raw_line in text.lines() {
        if raw_line.trim_start().starts_with("```") {
            if in_code_block {
                // End code block — flush accumulated lines
                let lang_label = if code_lang.is_empty() {
                    String::new()
                } else {
                    format!(" [{}]", code_lang)
                };
                lines.push(Line::from(Span::styled(
                    format!("{indent}  ╭─{lang_label}─"),
                    Style::default().fg(theme::DARK_GRAY),
                )));
                for cl in &code_lines {
                    lines.push(Line::from(Span::styled(
                        format!("{indent}  │ {cl}"),
                        Style::default().fg(theme::GREEN),
                    )));
                }
                lines.push(Line::from(Span::styled(
                    format!("{indent}  ╰───"),
                    Style::default().fg(theme::DARK_GRAY),
                )));
                code_lines.clear();
                code_lang.clear();
                in_code_block = false;
            } else {
                // Start code block
                in_code_block = true;
                let after_ticks = raw_line.trim_start().trim_start_matches('`');
                code_lang = after_ticks.trim().to_string();
            }
            continue;
        }

        if in_code_block {
            code_lines.push(raw_line.to_string());
            continue;
        }

        let trimmed = raw_line.trim_start();

        // Headings
        if trimmed.starts_with("### ") {
            let heading = trimmed.trim_start_matches('#').trim();
            lines.push(Line::from(Span::styled(
                format!("{indent}  {heading}"),
                Style::default()
                    .fg(theme::YELLOW)
                    .add_modifier(Modifier::BOLD),
            )));
            continue;
        }
        if trimmed.starts_with("## ") {
            let heading = trimmed.trim_start_matches('#').trim();
            lines.push(Line::from(Span::styled(
                format!("{indent}  {heading}"),
                Style::default()
                    .fg(theme::CYAN)
                    .add_modifier(Modifier::BOLD),
            )));
            continue;
        }
        if trimmed.starts_with("# ") {
            let heading = trimmed.trim_start_matches('#').trim();
            lines.push(Line::from(Span::styled(
                format!("{indent}  {heading}"),
                Style::default()
                    .fg(theme::CYAN)
                    .add_modifier(Modifier::BOLD | Modifier::UNDERLINED),
            )));
            continue;
        }

        // Horizontal rule
        if trimmed == "---" || trimmed == "***" || trimmed == "___" {
            lines.push(Line::from(Span::styled(
                format!("{indent}  ────────────────────────"),
                Style::default().fg(theme::DARK_GRAY),
            )));
            continue;
        }

        // Bullet points and numbered lists
        let (bullet_prefix, content) = if trimmed.starts_with("- ") {
            (Some("  • ".to_string()), &trimmed[2..])
        } else if trimmed.starts_with("* ") {
            (Some("  • ".to_string()), &trimmed[2..])
        } else if let Some(num_content) = strip_numbered_prefix(trimmed) {
            (Some(num_content.0), num_content.1)
        } else {
            (None, raw_line)
        };

        let mut spans: Vec<Span<'static>> = Vec::new();
        if let Some(bp) = bullet_prefix {
            spans.push(Span::styled(
                format!("{indent}{bp}"),
                Style::default().fg(theme::CYAN),
            ));
            render_inline_spans(content, &mut spans);
        } else {
            spans.push(Span::raw(format!("{indent}  ")));
            render_inline_spans(content.trim_start(), &mut spans);
        }

        lines.push(Line::from(spans));
    }

    // If the text ended while still in a code block, flush it
    if in_code_block && !code_lines.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("{indent}  ╭───"),
            Style::default().fg(theme::DARK_GRAY),
        )));
        for cl in &code_lines {
            lines.push(Line::from(Span::styled(
                format!("{indent}  │ {cl}"),
                Style::default().fg(theme::GREEN),
            )));
        }
        lines.push(Line::from(Span::styled(
            format!("{indent}  ╰───"),
            Style::default().fg(theme::DARK_GRAY),
        )));
    }

    lines
}

/// Match `1. text`, `2. text`, etc. and return (prefix, remaining content).
fn strip_numbered_prefix(line: &str) -> Option<(String, &str)> {
    let bytes = line.as_bytes();
    let mut i = 0;
    while i < bytes.len() && bytes[i].is_ascii_digit() {
        i += 1;
    }
    if i == 0 || i > 3 {
        return None;
    }
    if bytes.get(i) == Some(&b'.') && bytes.get(i + 1) == Some(&b' ') {
        let num = &line[..i];
        let rest = &line[i + 2..];
        Some((format!("  {num}. "), rest))
    } else {
        None
    }
}

fn render_inline_spans(text: &str, out: &mut Vec<Span<'static>>) {
    let base_style = Style::default().fg(theme::WHITE);
    let bold_style = Style::default()
        .fg(theme::WHITE)
        .add_modifier(Modifier::BOLD);
    let code_style = Style::default().fg(Color::Yellow);

    let mut remaining = text;

    while !remaining.is_empty() {
        // Look for the next special marker
        if let Some(pos) = remaining.find(|c| c == '`' || c == '*') {
            if pos > 0 {
                out.push(Span::styled(remaining[..pos].to_string(), base_style));
            }
            remaining = &remaining[pos..];

            // Inline code: `...`
            if remaining.starts_with('`') {
                if let Some(end) = remaining[1..].find('`') {
                    let code_text = &remaining[1..1 + end];
                    out.push(Span::styled(code_text.to_string(), code_style));
                    remaining = &remaining[2 + end..];
                    continue;
                }
            }

            // Bold: **...**
            if remaining.starts_with("**") {
                if let Some(end) = remaining[2..].find("**") {
                    let bold_text = &remaining[2..2 + end];
                    out.push(Span::styled(bold_text.to_string(), bold_style));
                    remaining = &remaining[4 + end..];
                    continue;
                }
            }

            // Single * (just emit it as text)
            out.push(Span::styled(remaining[..1].to_string(), base_style));
            remaining = &remaining[1..];
        } else {
            out.push(Span::styled(remaining.to_string(), base_style));
            break;
        }
    }
}
