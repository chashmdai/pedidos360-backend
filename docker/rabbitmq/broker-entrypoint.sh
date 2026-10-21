#!/bin/sh
set -eu
# The image entrypoint drops privileges; no secret appears in Compose environment/output.
export RABBITMQ_DEFAULT_PASS="$(cat /run/secrets/rabbit_admin_password)"
exec /usr/local/bin/docker-entrypoint.sh "$@"
