#!/usr/bin/env bash
set -euo pipefail
test "$(id -un)" = codex
base="$HOME/.local/share/pedidos360-ep4"
if [ ! -x "$base/session/usr/local/sessionmanagerplugin/bin/session-manager-plugin" ]; then
 mkdir -p "$HOME/.cache/pedidos360-ep4" "$base/session"
 curl --fail --location --proto '=https' --tlsv1.2 https://s3.amazonaws.com/session-manager-downloads/plugin/latest/ubuntu_64bit/session-manager-plugin.deb -o "$HOME/.cache/pedidos360-ep4/session-manager-plugin.deb"
 dpkg-deb -x "$HOME/.cache/pedidos360-ep4/session-manager-plugin.deb" "$base/session"
fi
"$base/session/usr/local/sessionmanagerplugin/bin/session-manager-plugin" --version
mkdir -p "$HOME/.config/pedidos360/ep4"; chmod 700 "$HOME/.config/pedidos360/ep4"
if [ ! -f "$HOME/.config/pedidos360/ep4/deploy-key" ]; then
 ssh-keygen -q -t ed25519 -N '' -C pedidos360-ep4-ssm -f "$HOME/.config/pedidos360/ep4/deploy-key"
fi
