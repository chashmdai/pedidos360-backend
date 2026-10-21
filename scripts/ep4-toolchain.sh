#!/usr/bin/env bash
set -euo pipefail
test "$(id -un)" = codex
root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/ep4-env.sh"
if [ ! -x "$AWS_CLI" ]; then
  cache="$HOME/.cache/pedidos360-ep4/aws-installer"
  mkdir -p "$cache" "$HOME/.local/share/pedidos360-ep4/bin"
  curl --fail --location --proto '=https' --tlsv1.2 https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip -o "$cache/awscliv2.zip"
  unzip -q -n "$cache/awscliv2.zip" -d "$cache"
  "$cache/aws/install" --install-dir "$HOME/.local/share/pedidos360-ep4/aws-cli" --bin-dir "$HOME/.local/share/pedidos360-ep4/bin"
fi
"$AWS_CLI" --version
"$AWS_CLI" sts get-caller-identity --region us-east-1 --output json --no-cli-pager
python3 "$root/scripts/ep4-inspect.py"
