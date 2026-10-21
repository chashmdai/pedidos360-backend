#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ep4-env.sh"
test "$(id -un)" = codex
mkdir -p "$root/docs/evidence/ep4"
case "${1:-all}" in backend|all)
 cd "$root"
 bash mvnw -B -Dpedidos.build.root="$HOME/.cache/pedidos360-ep4/build" clean verify > docs/evidence/ep4/backend-verify.txt 2>&1
 ;;&
 frontend|all)
 frontend="$HOME/.cache/pedidos360-ep4/frontend"
 mkdir -p "$frontend"
 rsync -a --delete --no-owner --no-group --no-perms --exclude .git --exclude node_modules --exclude dist "$root/../pedidos360-frontend/" "$frontend/"
 cd "$root"
 eval "$(python3 -c 'from scripts.entra_config import environment; import shlex; print("\n".join("export "+k+"="+shlex.quote(v) for k,v in environment(cloud=True).items() if k.startswith("VITE_")))')"
 export VITE_APP_BASE_PATH=/app/
 cd "$frontend"
 npm ci > "$root/docs/evidence/ep4/frontend-install.txt" 2>&1
 npm test > "$root/docs/evidence/ep4/frontend-tests.txt" 2>&1
 npm run build > "$root/docs/evidence/ep4/frontend-build.txt" 2>&1
 ;;
esac
