#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config="${PEDIDOS360_CONFIG_DIR:-$HOME/.config/pedidos360/local}"
action="${1:-status}"
if [ "$action" = start ] && [ "${2:-entra}" != cloud ]; then
  if [ ! -f "$config/application.env" ]; then echo 'Run bash scripts/setup-local.sh first.' >&2; exit 1; fi
  source "$config/application.env"
fi
exec python3 "$root/scripts/dev-processes.py" "$action" "${2:-entra}"
