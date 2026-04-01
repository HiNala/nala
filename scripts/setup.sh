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
[[ "${PYTHON_VER}" < "3.11" ]] && fail "Python 3.11+ required (found ${PYTHON_VER})"
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
python3 -m venv .venv
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
echo "Or from any directory (after adding to PATH):"
echo "  nala"
