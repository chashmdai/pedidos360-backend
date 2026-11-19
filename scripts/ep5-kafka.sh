#!/usr/bin/env bash
# EP5 Kafka operations (local and on the EC2). Touches only the Pedidos360 Kafka/Kafka UI Compose
# projects; never removes volumes, RabbitMQ or MySQL resources.
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
props="$root/kafka-support/src/main/resources/pedidos-kafka.properties"
[ -f "$props" ] || props="$root/pedidos-kafka.properties"   # release bundle layout
export PEDIDOS_EP5_CONFIG_DIR="${PEDIDOS_EP5_CONFIG_DIR:-$HOME/.config/pedidos360/ep5}"
kafka=(docker compose -f "$root/compose.kafka.yaml")
ui=(docker compose -f "$root/compose.kafka-ui.yaml")
bootstrap=kafka-1:29092
# Kafka CLI tools start a JVM inside the broker container; cap its heap so it cannot
# push the container over mem_limit (the broker itself keeps -Xms512m -Xmx512m).
cli=(docker exec -e KAFKA_HEAP_OPTS=-Xmx128m -e KAFKA_OPTS= -e KAFKA_JMX_OPTS= kafka-1)

prop() { local v; v="$(sed -n "s/^pedidos\.kafka\.$1=//p" "$props")"; [ -n "$v" ] || { echo "Missing pedidos.kafka.$1" >&2; exit 1; }; printf '%s' "$v"; }
topics() {
  local o m s; o="$(prop topics.orders-registered)"; m="$(prop topics.product-metrics)"; s="$(prop topics.dlt-suffix)"
  printf '%s\n' "$o" "$m" "$o$s" "$m$s"
}
groups() { printf '%s\n' "$(prop groups.sales-aggregator)" "$(prop groups.order-monitor)" "$(prop groups.sales-dashboard)"; }
configs_for() {   # report table 7
  local common="min.insync.replicas=$(prop topics.min-insync-replicas),max.message.bytes=$(prop topics.max-message-bytes)"
  case "$1" in
    "$(prop topics.orders-registered)") echo "cleanup.policy=$(prop topics.orders-cleanup-policy),retention.ms=$(prop topics.orders-retention-ms),segment.ms=$(prop topics.orders-segment-ms),$common" ;;
    "$(prop topics.product-metrics)") echo "cleanup.policy=$(prop topics.metrics-cleanup-policy),segment.ms=$(prop topics.metrics-segment-ms),min.cleanable.dirty.ratio=$(prop topics.metrics-min-cleanable-dirty-ratio),delete.retention.ms=$(prop topics.metrics-delete-retention-ms),$common" ;;
    *"$(prop topics.dlt-suffix)") echo "cleanup.policy=$(prop topics.dlt-cleanup-policy),retention.ms=$(prop topics.dlt-retention-ms),segment.ms=$(prop topics.dlt-segment-ms),$common" ;;
  esac
}
ui_secret() {
  install -d -m 0700 "$PEDIDOS_EP5_CONFIG_DIR"
  local file="$PEDIDOS_EP5_CONFIG_DIR/kafka-ui.env"
  if [ ! -f "$file" ]; then
    (umask 077; printf 'SPRING_SECURITY_USER_NAME=pedidos360-admin\nSPRING_SECURITY_USER_PASSWORD=%s\n' "$(openssl rand -hex 24)" > "$file")
    echo "Kafka UI credentials created in $file (mode 0600); not printed."
  fi
}

usage() {
  cat >&2 <<'USAGE'
Usage: bash scripts/ep5-kafka.sh COMMAND
  up | down | ps                     ZooKeeper x3 + brokers x3 (down keeps the volumes)
  ui up | ui down                    Kafka UI on 127.0.0.1:8090
  zk-status                          srvr on each ZooKeeper node (leader/follower)
  topics create                      create missing business and DLT topics (tables 6 and 7)
  topics describe [TOPIC...]         partitions, leader, replicas and ISR
  topics configs [TOPIC...]          effective dynamic topic configuration
  groups describe [GROUP...]         offsets, log-end offset, lag and member per partition
USAGE
  exit 2
}

case "${1:-}" in
  up) "${kafka[@]}" up -d --wait --wait-timeout 300; "${kafka[@]}" ps ;;
  down) "${kafka[@]}" down ;;
  ps) "${kafka[@]}" ps; if docker inspect kafka-ui >/dev/null 2>&1; then "${ui[@]}" ps; fi ;;
  ui)
    case "${2:-}" in
      up) ui_secret; "${ui[@]}" up -d --wait --wait-timeout 180; "${ui[@]}" ps ;;
      down) "${ui[@]}" down ;;
      *) usage ;;
    esac ;;
  zk-status)
    for n in 1 2 3; do
      out="$(docker exec "zookeeper-$n" bash -c 'exec 3<>/dev/tcp/127.0.0.1/2181; echo srvr >&3; cat <&3')"
      printf 'zookeeper-%s: %s | %s\n' "$n" "$(grep '^Mode:' <<<"$out")" "$(grep '^Zookeeper version:' <<<"$out" | cut -d, -f1)"
    done ;;
  topics)
    action="${2:-}"; shift 2 || true
    case "$action" in
      create)
        while read -r t; do
          "${cli[@]}" kafka-topics --bootstrap-server "$bootstrap" --create --if-not-exists --topic "$t" \
            --partitions "$(prop topics.partitions)" --replication-factor "$(prop topics.replicas)" \
            $(tr ',' '\n' <<<"$(configs_for "$t")" | sed 's/^/--config /')
        done < <(topics)
        "$0" topics describe ;;
      describe)
        while read -r t; do "${cli[@]}" kafka-topics --bootstrap-server "$bootstrap" --describe --topic "$t"; done < <(if [ $# -gt 0 ]; then printf '%s\n' "$@"; else topics; fi) ;;
      configs)
        while read -r t; do "${cli[@]}" kafka-configs --bootstrap-server "$bootstrap" --entity-type topics --entity-name "$t" --describe; done < <(if [ $# -gt 0 ]; then printf '%s\n' "$@"; else topics; fi) ;;
      *) usage ;;
    esac ;;
  groups)
    [ "${2:-}" = describe ] || usage; shift 2
    while read -r g; do "${cli[@]}" kafka-consumer-groups --bootstrap-server "$bootstrap" --describe --group "$g" || true; done < <(if [ $# -gt 0 ]; then printf '%s\n' "$@"; else groups; fi) ;;
  *) usage ;;
esac
