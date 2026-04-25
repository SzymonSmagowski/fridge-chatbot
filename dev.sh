#!/usr/bin/env bash
# Start fridge-chatbot backend + frontend with color-coded interleaved logs.
# Ctrl+C — or either service exiting — tears down both cleanly.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
# Poetry lands in /usr/local/bin on a fresh image, ~/.local/bin on a stale one.
export PATH="$HOME/.local/bin:/usr/local/bin:$PATH"

CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
RESET='\033[0m'

# Kill every descendant of $1 except $$ itself.
kill_tree() {
    local parent=$1 sig=${2:-TERM} child
    for child in $(pgrep -P "$parent" 2>/dev/null); do
        kill_tree "$child" "$sig"
    done
    [ "$parent" != "$$" ] && kill -"$sig" "$parent" 2>/dev/null || true
}

cleanup() {
    trap - INT TERM  # re-entry guard
    printf "\n%b▸ Shutting down…%b\n" "$YELLOW" "$RESET"
    kill_tree $$ TERM
    sleep 1
    kill_tree $$ KILL
    exit 0
}
trap cleanup INT TERM

prefix() {
    local color=$1 tag=$2
    while IFS= read -r line; do
        printf "%b[%s]%b %s\n" "$color" "$tag" "$RESET" "$line"
    done
}

# Preflight
[ -d "$BACKEND_DIR" ]  || { printf "%b✗ %s not found%b\n"  "$RED" "$BACKEND_DIR"  "$RESET"; exit 1; }
[ -d "$FRONTEND_DIR" ] || { printf "%b✗ %s not found%b\n"  "$RED" "$FRONTEND_DIR" "$RESET"; exit 1; }
command -v poetry >/dev/null || { printf "%b✗ poetry not on PATH — rebuild the devcontainer%b\n" "$RED" "$RESET"; exit 1; }
command -v pnpm   >/dev/null || { printf "%b✗ pnpm not on PATH — run 'corepack enable && corepack prepare pnpm@latest --activate'%b\n" "$RED" "$RESET"; exit 1; }

printf "%b● backend%b  → http://localhost:8001\n"  "$CYAN"    "$RESET"
printf "%b● frontend%b → http://localhost:3000\n"  "$MAGENTA" "$RESET"
echo ""

# `exec` inside the subshell so the real process (poetry / pnpm) replaces the
# subshell — makes the process tree shorter and lets kill_tree reach uvicorn
# and next-server cleanly.
( cd "$BACKEND_DIR"  && exec ./run.sh     ) 2>&1 | prefix "$CYAN"    "backend"  &
( cd "$FRONTEND_DIR" && exec pnpm dev     ) 2>&1 | prefix "$MAGENTA" "frontend" &

# If either service exits, tear down the other.
wait -n
cleanup
