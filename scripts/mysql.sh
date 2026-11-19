#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
export PEDIDOS360_CONFIG_DIR="${PEDIDOS360_CONFIG_DIR:-$HOME/.config/pedidos360/local}"
# Reuse the host port chosen by setup-local.sh (default 13306).
if [ -z "${PEDIDOS360_MYSQL_PORT:-}" ] && [ -f "$PEDIDOS360_CONFIG_DIR/application.env" ]; then
  PEDIDOS360_MYSQL_PORT="$(sed -n "s/^export PEDIDOS360_MYSQL_PORT=//p" "$PEDIDOS360_CONFIG_DIR/application.env" | tr -d "'")"
fi
export PEDIDOS360_MYSQL_PORT="${PEDIDOS360_MYSQL_PORT:-13306}"
exec docker compose -f "$root/compose.yaml" "$@"
