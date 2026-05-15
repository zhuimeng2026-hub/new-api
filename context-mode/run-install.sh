#!/bin/bash
set -euo pipefail

SESSION="ctx-mode-install"
LOG="/tmp/context-mode-install-$(date +%Y%m%d-%H%M%S).log"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill existing session if present (stale from previous run)
if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "[warn] tmux session '$SESSION' already exists, killing stale session"
    tmux kill-session -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" "bash '$SCRIPT_DIR/install-context-mode.sh' '$LOG'"

echo "tmux session '$SESSION' started (detached)"
echo "  Attach : tmux attach -t $SESSION"
echo "  Log    : tail -f $LOG"
echo "  Kill   : tmux kill-session -t $SESSION"
