#!/usr/bin/env bash
# install.sh — drop fixed files into the tessiture repo.
# Usage: cd /path/to/tessiture && bash /path/to/tessiture-fixes/install.sh
#
# This replaces 5 files. Run `git diff` afterward to review changes.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${1:-.}"

if [[ ! -f "$REPO_ROOT/api/analysis_core.py" ]]; then
    echo "ERROR: run from tessiture repo root, or pass it as \$1" >&2
    exit 1
fi

files=(
    "analysis/pitch/estimator.py"
    "analysis/pitch/midi_converter.py"
    "analysis/dsp/vocal_separation.py"
    "api/analysis_core.py"
    "api/streaming.py"
)

for f in "${files[@]}"; do
    cp -v "$SCRIPT_DIR/$f" "$REPO_ROOT/$f"
done

echo ""
echo "Done. Review with:  cd $REPO_ROOT && git diff"
