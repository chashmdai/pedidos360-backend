#!/usr/bin/env bash
set -euo pipefail
test "$(id -u)" != 0 || { echo "Run as the regular operator user, not root." >&2; exit 1; }
base="$HOME/.local/share/pedidos360-ep4"
if command -v session-manager-plugin >/dev/null 2>&1; then
 session-manager-plugin --version
elif [ ! -x "$base/session/usr/local/sessionmanagerplugin/bin/session-manager-plugin" ]; then
 mkdir -p "$HOME/.cache/pedidos360-ep4" "$base/session"
 curl --fail --location --proto '=https' --tlsv1.2 https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb -o "$HOME/.cache/pedidos360-ep4/session-manager-plugin.deb"
 dpkg-deb -x "$HOME/.cache/pedidos360-ep4/session-manager-plugin.deb" "$base/session"
fi
if ! command -v session-manager-plugin >/dev/null 2>&1; then "$base/session/usr/local/sessionmanagerplugin/bin/session-manager-plugin" --version; fi
mkdir -p "$HOME/.config/pedidos360/ep4"; chmod 700 "$HOME/.config/pedidos360/ep4"
if [ ! -f "$HOME/.config/pedidos360/ep4/deploy-key" ]; then
 ssh-keygen -q -t ed25519 -N '' -C pedidos360-ep4-ssm -f "$HOME/.config/pedidos360/ep4/deploy-key"
fi
