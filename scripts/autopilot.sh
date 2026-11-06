#!/bin/bash
# Run the autopilot on your own computer: N work cycles, each in a new Claude Code session.
# Needs: the Claude Code CLI (logged in with your Max account) and the GitHub CLI (`gh auth login`).
#
#   scripts/autopilot.sh        # 1 cycle
#   scripts/autopilot.sh 5      # 5 cycles, one ticket each
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out
cycles="${1:-1}"
for i in $(seq 1 "$cycles"); do
  echo "=== cycle $i of $cycles ==="
  git checkout main && git pull --ff-only
  claude -p "/autopilot 1" --permission-mode acceptEdits | tee "out/autopilot-$(date +%Y%m%d-%H%M%S).log" \
    || { echo "cycle $i failed"; exit 1; }
done
