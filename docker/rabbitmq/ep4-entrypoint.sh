#!/bin/sh
set -eu
# Preserve the cookie/data on restart; a mismatched secret is an error, never reset the node.
cookie=/var/lib/rabbitmq/.erlang.cookie
if [ -f "$cookie" ]; then
  cmp -s "$cookie" /run/secrets/rabbit_cookie || { echo 'Cluster cookie mismatch; preserving node data.' >&2; exit 1; }
else
  cp /run/secrets/rabbit_cookie "$cookie"
fi
chown rabbitmq:rabbitmq "$cookie"
chmod 400 "$cookie"
export RABBITMQ_DEFAULT_PASS="$(cat /run/secrets/rabbit_admin_password)"
exec /usr/local/bin/docker-entrypoint.sh "$@"
