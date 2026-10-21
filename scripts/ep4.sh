#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ep4-env.sh"
export PATH="$HOME/.local/share/pedidos360-ep4/session/usr/local/sessionmanagerplugin/bin:$PATH"
case "${1:-}" in
 inspect) exec python3 "$root/scripts/ep4-inspect.py" ;;
 ssm) shift; exec python3 "$root/scripts/ep4-ssm.py" "$@" ;;
 transfer) shift; exec python3 "$root/scripts/ep4-transfer.py" "$@" ;;
 *) echo 'Usage: ep4.sh inspect|ssm SCRIPT --output FILE|transfer setup|tunnel|upload BUNDLE' >&2; exit 2 ;;
esac
