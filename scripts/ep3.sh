#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PEDIDOS_EP3_CONFIG_DIR="${PEDIDOS_EP3_CONFIG_DIR:-$HOME/.config/pedidos360/ep3}"
export PATH="$HOME/.local/share/pedidos360-ep3/node/bin:$PATH"
cd "$root"
action="${1:-status}"
case "$action" in
  setup) exec python3 scripts/ep3-runtime.py setup ;;
  broker)
    shift
    for argument in "$@"; do
      case "$argument" in -v|--volumes) echo 'Volume deletion is not an EP3 demo action.' >&2; exit 2 ;; esac
    done
    exec docker compose -f compose.rabbitmq.yaml "$@"
    ;;
  configure-broker) exec python3 scripts/ep3-runtime.py configure-broker ;;
  start|stop|status) exec python3 scripts/ep3-runtime.py "$action" "${2:-local}" ;;
  *) echo 'Usage: bash scripts/ep3.sh setup|broker [compose args]|configure-broker|start [local|entra]|stop|status' >&2; exit 2 ;;
esac
