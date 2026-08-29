#!/usr/bin/env bash
# The same kit on bare binaries, no Docker: `./run-local.sh up`, `./run-local.sh down`.
# Binaries go in .bin/ (nats-server, otelcol-contrib, prometheus, promtool, alertmanager, grafana/).
# `./run-local.sh fetch` downloads the versions pinned in docker-compose.yml.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-.venv/bin/python}
mkdir -p data/logs data/pids
NATS=2.14.6; PROM=3.14.0; OTEL=0.159.0; AM=0.34.0; GRAF=13.2.0

fetch() {
  mkdir -p .bin && cd .bin
  curl -sL https://github.com/nats-io/nats-server/releases/download/v$NATS/nats-server-v$NATS-linux-amd64.tar.gz | tar xz --strip-components=1 nats-server-v$NATS-linux-amd64/nats-server
  curl -sL https://github.com/prometheus/prometheus/releases/download/v$PROM/prometheus-$PROM.linux-amd64.tar.gz | tar xz --strip-components=1 prometheus-$PROM.linux-amd64/prometheus prometheus-$PROM.linux-amd64/promtool
  curl -sL https://github.com/open-telemetry/opentelemetry-collector-releases/releases/download/v$OTEL/otelcol-contrib_${OTEL}_linux_amd64.tar.gz | tar xz otelcol-contrib
  curl -sL https://github.com/prometheus/alertmanager/releases/download/v$AM/alertmanager-$AM.linux-amd64.tar.gz | tar xz --strip-components=1 alertmanager-$AM.linux-amd64/alertmanager
  curl -sL https://dl.grafana.com/oss/release/grafana-$GRAF.linux-amd64.tar.gz | tar xz && mv grafana-$GRAF grafana
  ls -la
}

start() { # name, command...
  local name=$1; shift
  nohup "$@" > "data/logs/$name.log" 2>&1 &
  echo $! > "data/pids/$name.pid"
  echo "  $name pid $!"
}

up() {
  sed 's/alertmanager:9093/localhost:9093/; s/otelcol:8889/localhost:8889/' prometheus/prometheus.yml > prometheus/prometheus.local.yml
  sed 's#http://sink:9095#http://localhost:9095#' alertmanager/alertmanager.yml > alertmanager/alertmanager.local.yml
  export QM_NATS_URL=nats://localhost:4222 QM_OTLP_URL=http://localhost:4318
  export QM_PROM_URL=http://localhost:9090 QM_DASH_DIR="$PWD/grafana/dashboards"
  export GF_PATHS_DATA="$PWD/data/grafana" GF_PATHS_LOGS="$PWD/data/logs/grafana" GF_PATHS_PLUGINS="$PWD/data/grafana/plugins"
  export GF_PATHS_PROVISIONING="$PWD/grafana/provisioning" GF_AUTH_ANONYMOUS_ENABLED=true GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
  export GF_SECURITY_ADMIN_PASSWORD=quiet-machine GF_ANALYTICS_REPORTING_ENABLED=false GF_ANALYTICS_CHECK_FOR_UPDATES=false
  start nats .bin/nats-server -js -sd data/nats -p 4222
  start otelcol .bin/otelcol-contrib --config collector/otelcol.yaml
  start prometheus .bin/prometheus --config.file=prometheus/prometheus.local.yml --storage.tsdb.path=data/prom --web.listen-address=:9090
  start alertmanager .bin/alertmanager --config.file=alertmanager/alertmanager.local.yml --storage.path=data/am --web.listen-address=:9093
  QM_LEDGER="$PWD/data/alerts.ledger.jsonl" start sink "$PY" services/sink.py
  start grafana .bin/grafana/bin/grafana server --homepath "$PWD/.bin/grafana"
  sleep 2
  start bridge "$PY" services/bridge.py
  QM_SERVICE=collector-a QM_STATUS_PORT=9101 start collector-a "$PY" services/probe.py
  QM_SERVICE=collector-b QM_STATUS_PORT=9102 start collector-b "$PY" services/probe.py
  echo "up: grafana :3000, prometheus :9090, alertmanager :9093, sink :9095, collectors :9101 :9102"
}

down() {
  for f in data/pids/*.pid; do
    [ -f "$f" ] || continue
    pid=$(cat "$f"); pkill -TERM -P "$pid" 2>/dev/null || true; kill -TERM "$pid" 2>/dev/null || true; rm -f "$f"
  done
  echo "down"
}

case "${1:-}" in
  fetch) fetch ;;
  up) up ;;
  down) down ;;
  *) echo "usage: $0 fetch|up|down"; exit 1 ;;
esac
