#!/bin/sh
sed \
  -e "s|\${PROMETHEUS_PORT}|${PROMETHEUS_PORT:-9090}|g" \
  -e "s|\${PUSHGATEWAY_PORT}|${PUSHGATEWAY_PORT:-9091}|g" \
  /etc/prometheus/prometheus.yaml.tmpl \
  > /etc/prometheus/prometheus.yaml

exec /bin/prometheus "$@"