#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
# Test phase only: do not repackage the already deployed, checksum-verified JARs.
bash mvnw -B -Dpedidos.build.root="$HOME/.cache/pedidos360-ep4/build" -pl order-insights-service -am test > docs/evidence/ep4/insights-http-final.txt 2>&1
