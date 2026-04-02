#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "HiNala benchmark (scan/index)"

if [ ! -x "./rust-core/target/release/hinala" ] && [ ! -x "./rust-core/target/release/nala" ]; then
  echo "Release binary missing. Run ./scripts/setup.sh first."
  exit 1
fi

BIN="./rust-core/target/release/hinala"
[ -x "$BIN" ] || BIN="./rust-core/target/release/nala"

echo "Command: $BIN --path \"$ROOT_DIR\" scan"
time "$BIN" --path "$ROOT_DIR" scan

echo "Command: $BIN --path \"$ROOT_DIR\" index"
time "$BIN" --path "$ROOT_DIR" index
