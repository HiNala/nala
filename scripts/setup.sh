#!/usr/bin/env bash
# Nala development environment setup script (Linux/macOS)
set -euo pipefail

BOLD="\033[1m"
CYAN="\033[36m"
GREEN="\033[32m"
RED="\033[31m"
RESET="\033[0m"

info()  { echo -e "${CYAN}→ $*${RESET}"; }
ok()    { echo -e "${GREEN}✓ $*${RESET}"; }
fail()  { echo -e "${RED}✗ $*${RESET}"; exit 1; }

echo -e "\n${BOLD}Nala Setup${RESET}\n"

# ── Prerequisites ──────────────────────────────────────────────────────────

info "Checking prerequisites..."

command -v cargo >/dev/null 2>&1 || fail "Rust not found. Install from https://rustup.rs"
ok "Rust $(rustc --version | awk '{print $2}')"

command -v python3 >/dev/null 2>&1 || fail "Python 3 not found. Install Python 3.11+"
PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
python3 - <<'PY' || fail "Python 3.11+ required (found ${PYTHON_VER})"
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
ok "Python ${PYTHON_VER}"

# ── .env setup ─────────────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
    info "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo -e "${CYAN}  Edit .env and add your API key before running Nala:${RESET}"
    echo "    ANTHROPIC_API_KEY=sk-ant-..."
    echo "  (or OPENAI_API_KEY, GOOGLE_API_KEY)"
    echo ""
fi

# ── Rust build ─────────────────────────────────────────────────────────────

info "Building Rust workspace..."
(cd rust-core && cargo build --release) || fail "Rust build failed"
ok "Rust workspace built"

# ── Python venv ────────────────────────────────────────────────────────────

info "Creating Python virtualenv..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
else
  info "Reusing existing .venv"
fi
source .venv/bin/activate
pip install --upgrade pip --quiet

# ── Maturin + PyO3 bridge ──────────────────────────────────────────────────

info "Building PyO3 bridge (Rust → Python)..."
pip install maturin --quiet
(cd rust-core/nala-bridge && maturin develop --release) || fail "Maturin build failed"
ok "PyO3 bridge built"

# Verify bridge is importable
python3 -c "import nala_core; assert nala_core.version() == '0.1.0'" || fail "nala_core import failed"
ok "nala_core import verified"

# ── Python orchestrator ────────────────────────────────────────────────────

info "Installing Python orchestrator..."
(cd python-orchestrator && pip install -e . --quiet) || fail "Python install failed"
ok "Python orchestrator installed"

# ── Summary ────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}${GREEN}Setup complete!${RESET}"
echo ""
echo "To start Nala:"
echo "  source .venv/bin/activate"
echo "  ./rust-core/target/release/nala"
echo ""

info "Installing global commands (hinala, HiNala, nala)..."
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
REPO_ROOT="$(pwd)"

cat > "$BIN_DIR/hinala" <<EOF
#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$REPO_ROOT"
if [ -x "\$REPO_ROOT/rust-core/target/release/hinala" ]; then
  EXE="\$REPO_ROOT/rust-core/target/release/hinala"
else
  EXE="\$REPO_ROOT/rust-core/target/release/nala"
fi
if [ ! -x "\$EXE" ]; then
  echo "HiNala binary not found. Re-run scripts/setup.sh in the Nala repo."
  exit 1
fi
"\$EXE" --path "\$PWD" "\$@"
EOF
chmod +x "$BIN_DIR/hinala"
ln -sf "$BIN_DIR/hinala" "$BIN_DIR/HiNala"
ln -sf "$BIN_DIR/hinala" "$BIN_DIR/nala"

if ! echo "$PATH" | tr ':' '\n' | grep -Fxq "$BIN_DIR"; then
  SHELL_RC="$HOME/.bashrc"
  [ -n "${ZSH_VERSION:-}" ] && SHELL_RC="$HOME/.zshrc"
  echo "" >> "$SHELL_RC"
  echo "# HiNala command launcher" >> "$SHELL_RC"
  echo "export PATH=\"$BIN_DIR:\$PATH\"" >> "$SHELL_RC"
  ok "Added $BIN_DIR to PATH in $SHELL_RC (open a new terminal)."
else
  ok "PATH already contains $BIN_DIR."
fi

ok "Global command installed. Open a new terminal, then run: HiNala"
