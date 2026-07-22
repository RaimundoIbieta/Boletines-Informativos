#!/bin/zsh
set -euo pipefail

ROOT="/Users/raimundoibietaazocar/Boletines Informativos"
cd "$ROOT"

export PYTHONPATH="$ROOT/src"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

LOG_DIR="$ROOT/output"
mkdir -p "$LOG_DIR"

{
  echo "===== $(date '+%Y-%m-%d %H:%M:%S %Z') ====="
  "$ROOT/.venv/bin/python" -m boletin run -v
  echo "OK"
} >>"$LOG_DIR/boletin-lunes.log" 2>&1
