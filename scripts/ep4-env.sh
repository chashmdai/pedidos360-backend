#!/usr/bin/env bash
# Process-local settings; never copy or rewrite the operator's AWS credentials.
# Defaults target native Linux (system aws CLI and ~/.aws/credentials); both remain overridable.
export AWS_CLI="${AWS_CLI:-$(command -v aws || echo "$HOME/.local/share/pedidos360-ep4/bin/aws")}"
export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-$HOME/.aws/credentials}"
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
# Legacy WSL toolchain location, only if it exists.
if [ -d "$HOME/.local/share/pedidos360-ep3/node/bin" ]; then export PATH="$HOME/.local/share/pedidos360-ep3/node/bin:$PATH"; fi
