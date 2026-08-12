#!/bin/bash
# Cantonese Dubbing Desk - macOS launcher
# Kept ASCII-only for maximum compatibility; serve.py prints the
# Chinese status messages.
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [ ! -f serve.py ]; then
  echo
  echo "  ERROR: serve.py not found next to this launcher."
  echo "  Folder: $(pwd)"
  echo
  read -n 1 -s -r -p "  Press any key to close"
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo
  echo "  ERROR: Python 3 not found."
  echo "  Install with:  brew install python"
  echo "  Or download:   https://www.python.org/downloads/"
  echo
  read -n 1 -s -r -p "  Press any key to close"
  exit 1
fi

"$PY" serve.py "$@"

echo
echo "  Server stopped."
read -n 1 -s -r -p "  Press any key to close"
