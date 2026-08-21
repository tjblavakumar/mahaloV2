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

echo "============================================================"
echo " MAHALO - Reset Demo Data (Linux)"
echo "============================================================"
echo ""
echo "This will drop and recreate all demo data."
read -rp $'Press Enter to continue or Ctrl+C to cancel...\n' _

echo "[INFO] Resetting database..."
python -m backend.utils.reset_data

echo ""
echo "============================================================"
echo " Demo data reset complete!"
echo "============================================================"
