#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f "$ROOT_DIR/venv/bin/activate" ]; then
  echo "[ERROR] Virtual environment not found."
  echo "Create it with: python3 -m venv venv"
  exit 1
fi

source "$ROOT_DIR/venv/bin/activate"
python -m backend.utils.generate_test_data "$@"
