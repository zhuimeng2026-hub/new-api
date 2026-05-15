#!/bin/bash
set -euo pipefail

LOG_FILE="${1:-/tmp/context-mode-install-$(date +%Y%m%d-%H%M%S).log}"

# Dual output: terminal + log file
exec > >(tee -a "$LOG_FILE") 2>&1

ts() { date '+%Y-%m-%d %H:%M:%S'; }
step() { echo; echo "============================================================"; echo "[$(ts)] Step $1: $2"; echo "============================================================"; }
skip() { echo "[$(ts)] SKIP — $1"; }
ok()   { echo "[$(ts)] OK — $1"; }
die()  { echo "[$(ts)] FATAL — $1"; exit 1; }

SETTINGS="$HOME/.claude/settings.json"
NPM_MIRROR="https://mirrors.tencentyun.com/npm"

# ── Step 1: Prerequisites ────────────────────────────────────────────
step "1/7" "Checking prerequisites"

for cmd in node npm jq; do
    if command -v "$cmd" &>/dev/null; then
        ok "$cmd found: $($cmd --version 2>&1 | head -1)"
    else
        die "$cmd not found"
    fi
done

# ── Step 2: Configure npm mirror ─────────────────────────────────────
step "2/7" "Configuring npm mirror"

CUR_REGISTRY=$(npm config get registry)
if [ "$CUR_REGISTRY" = "$NPM_MIRROR" ]; then
    skip "npm registry already set to $NPM_MIRROR"
elif curl -sI --connect-timeout 5 "$NPM_MIRROR" &>/dev/null; then
    npm config set registry "$NPM_MIRROR"
    ok "npm registry set to $NPM_MIRROR"
else
    skip "mirror unreachable, using default registry ($CUR_REGISTRY)"
fi

# ── Step 3: Install context-mode ─────────────────────────────────────
step "3/7" "Installing context-mode"

DEFAULT_REGISTRY="https://registry.npmjs.org"

if npm list -g context-mode --depth=0 &>/dev/null; then
    VER=$(npm list -g context-mode --depth=0 2>/dev/null | grep context-mode | head -1)
    skip "context-mode already installed: $VER"
else
    if ! npm install -g context-mode; then
        echo "[$(ts)] WARN — mirror $CUR_REGISTRY failed, falling back to $DEFAULT_REGISTRY"
        npm config set registry "$DEFAULT_REGISTRY"
        npm install -g context-mode
        ok "context-mode installed (via default registry)"
    else
        ok "context-mode installed"
    fi
fi

# ── Step 4: Locate start.mjs ─────────────────────────────────────────
step "4/7" "Locating start.mjs"

NPM_ROOT=$(npm root -g)
START_MJS="$NPM_ROOT/context-mode/start.mjs"
ok "npm global root: $NPM_ROOT"
ok "expected start.mjs: $START_MJS"

# ── Step 5: Verify start.mjs exists ──────────────────────────────────
step "5/7" "Verifying start.mjs"

if [ -f "$START_MJS" ]; then
    ok "start.mjs found"
else
    die "start.mjs not found at $START_MJS"
fi

# ── Step 6: Register in settings.json ─────────────────────────────────
step "6/7" "Registering context-mode in settings.json"

if [ ! -f "$SETTINGS" ]; then
    die "$SETTINGS not found — cannot register context-mode"
fi

# Idempotent: ensure all three settings.json entries are correct.
# 1) enabledPlugins["context-mode@context-mode"] = true
# 2) extraKnownMarketplaces["context-mode"] = {source: {source: "github", repo: "mksglu/context-mode"}}
# 3) mcpServers["context-mode"] = {command: "node", args: [start.mjs]}
jq --arg start "$START_MJS" '
  (if .enabledPlugins                                     then . else . + {"enabledPlugins": {}}                                     end) |
  (if .enabledPlugins["context-mode@context-mode"] == true then . else .enabledPlugins["context-mode@context-mode"] = true          end) |
  (if .extraKnownMarketplaces                                     then . else . + {"extraKnownMarketplaces": {}}                                     end) |
  (if .extraKnownMarketplaces["context-mode"]                     then . else .extraKnownMarketplaces["context-mode"] = {"source": {"source": "github", "repo": "mksglu/context-mode"}} end) |
  (if .mcpServers                                     then . else . + {"mcpServers": {}}                                     end) |
  (if .mcpServers["context-mode"]                     then . else .mcpServers["context-mode"] = {"command": "node", "args": [$start]} end)
' "$SETTINGS" > "${SETTINGS}.tmp"

if cmp -s "$SETTINGS" "${SETTINGS}.tmp"; then
    rm "${SETTINGS}.tmp"
    skip "context-mode already fully registered in settings.json"
else
    mv "${SETTINGS}.tmp" "$SETTINGS"
    ok "context-mode registered in settings.json (enabledPlugins + extraKnownMarketplaces + mcpServers)"
fi

# ── Step 7: Summary ──────────────────────────────────────────────────
step "7/7" "Installation complete"

echo "  Log file   : $LOG_FILE"
echo "  start.mjs  : $START_MJS"
echo "  MCP entry  : mcpServers.context-mode"
echo
echo "  Verify with: ctx stats   (restart Claude Code first)"

echo
echo "[$(ts)] Done."
