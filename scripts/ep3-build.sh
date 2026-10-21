#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$HOME/.local/share/pedidos360-ep3/node/bin:$PATH"
if [ "$(id -un)" != codex ]; then echo 'Run inside WSL as codex.' >&2; exit 1; fi
build="${PEDIDOS_EP3_BUILD_ROOT:-$HOME/.cache/pedidos360-ep3/build}"
frontend="$HOME/.cache/pedidos360-ep3/frontend"
mkdir -p "$root/docs/evidence/ep3" "$frontend"
case "${1:-all}" in backend|frontend|all) ;; *) echo 'Usage: bash scripts/ep3-build.sh backend|frontend|all' >&2; exit 2 ;; esac
case "${1:-all}" in
  backend|all)
    cd "$root"
    bash mvnw -B -Dpedidos.build.root="$build" clean verify > docs/evidence/ep3/backend-verify.txt 2>&1
    ;;&
  frontend|all)
    # Copy sources only; do not move the workspace or replace another user's dependencies.
    rsync -a --no-owner --no-group --no-perms --exclude .git --exclude node_modules --exclude dist --exclude docs/evidence "$root/../pedidos360-frontend/" "$frontend/"
    cd "$frontend"
    npm ci > "$root/docs/evidence/ep3/frontend-install.txt" 2>&1
    npm test > "$root/docs/evidence/ep3/frontend-tests.txt" 2>&1
    cd "$root"
    export VITE_AUTH_MODE=entra
    eval "$(python3 -c 'from scripts.entra_config import environment; import shlex; print("\n".join("export "+k+"="+shlex.quote(v) for k,v in environment().items() if k.startswith("VITE_")))')"
    cd "$frontend"
    npm run build > "$root/docs/evidence/ep3/frontend-build.txt" 2>&1
    ;;
esac
