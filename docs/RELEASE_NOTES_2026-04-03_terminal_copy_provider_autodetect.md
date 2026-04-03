# Release Notes — 2026-04-03

## UX: Terminal copy/paste friendliness

- Disabled mouse capture by default in the TUI boot path so terminal text selection works naturally.
- Bracketed paste remains enabled, so pasting into HiNala still works.
- Added help note: set `NALA_MOUSE_CAPTURE=1` if you want legacy mouse-capture behavior.

## Provider/key detection improvements

- Updated config provider resolution to better honor project settings while still auto-switching for default first-run configs.
- Prevented provider/model mismatch bleed by keeping model selection tied to the matching configured provider.
- Improved behavior for common setup:
  - If project settings are still default (`anthropic` + `claude-sonnet-4-6`) and only another provider key is present, HiNala can switch to that available provider.
  - If project settings explicitly choose a provider/model, those choices are preserved.

## Validation

- Rust: `cargo check` passed.
- Python: `pytest` passed (`32 passed`).

