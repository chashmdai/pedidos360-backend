#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PEDIDOS360_CONFIG_DIR="${PEDIDOS360_CONFIG_DIR:-$HOME/.config/pedidos360/local}"
exec docker compose -f "$root/compose.yaml" "$@"
