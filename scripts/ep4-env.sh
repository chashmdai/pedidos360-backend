#!/usr/bin/env bash
# Process-local settings; never copy or rewrite the operator's AWS credentials.
export AWS_CLI="${AWS_CLI:-$HOME/.local/share/pedidos360-ep4/bin/aws}"
export AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE:-/mnt/c/Users/Benja/.aws/credentials}"
export AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1 AWS_PAGER=""
export PATH="$HOME/.local/share/pedidos360-ep3/node/bin:$PATH"
