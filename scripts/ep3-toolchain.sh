#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -un)" != codex ]; then echo 'Run inside WSL as codex.' >&2; exit 1; fi
destination="$HOME/.local/share/pedidos360-ep3"
mkdir -p "$destination"
if [ ! -x "$destination/node/bin/node" ]; then
  curl --fail --location --proto '=https' --proto-redir '=https' \
    https://nodejs.org/dist/v24.20.0/node-v24.20.0-linux-x64.tar.xz \
    -o "$destination/node-v24.20.0-linux-x64.tar.xz"
  echo "2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2  $destination/node-v24.20.0-linux-x64.tar.xz" | sha256sum -c -
  mkdir -p "$destination/node"
  tar -xJf "$destination/node-v24.20.0-linux-x64.tar.xz" -C "$destination/node" --strip-components=1
fi
"$destination/node/bin/node" --version
echo 'Java 25, Docker and the project Maven Wrapper are required; no global packages were replaced.'
