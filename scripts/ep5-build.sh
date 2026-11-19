#!/usr/bin/env bash
# EP5 build on native Linux: backend clean verify (Testcontainers) and the cloud SPA build for /app/.
# Keep the local Kafka Compose stopped while verifying (memory). Outputs go to docs/evidence/ep5/build/.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
test "$(id -u)" != 0 || { echo "Run as the regular operator user, not root." >&2; exit 1; }
out="$root/docs/evidence/ep5/build"; mkdir -p "$out"
case "${1:-all}" in backend|all)
  (cd "$root" && ./mvnw -B clean verify) > "$out/backend-verify.txt" 2>&1
  grep -q 'BUILD SUCCESS' "$out/backend-verify.txt"
  ;;&
 frontend|all)
  frontend="$HOME/.cache/pedidos360-ep5/frontend"
  mkdir -p "$frontend"
  rsync -a --delete --exclude .git --exclude node_modules --exclude dist "$root/../pedidos360-frontend/" "$frontend/"
  # Public Entra identifiers + the HTTP API of config/aws-public.json (validated against config/aws-target.json).
  eval "$(cd "$root" && python3 -c 'from scripts.entra_config import environment; import shlex; print("\n".join("export "+k+"="+shlex.quote(v) for k,v in environment(cloud=True).items() if k.startswith("VITE_")))')"
  export VITE_APP_BASE_PATH=/app/
  cd "$frontend"
  npm ci > "$out/frontend-install.txt" 2>&1
  npm test > "$out/frontend-tests.txt" 2>&1
  npm run build > "$out/frontend-build.txt" 2>&1
  ;;
esac
