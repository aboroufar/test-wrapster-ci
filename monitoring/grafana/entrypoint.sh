#!/bin/sh
sed \
  -e "s|\${PROMETHEUS_PORT}|${PROMETHEUS_PORT:-9090}|g" \
  -e "s|\${REDIS_PORT}|${REDIS_PORT:-6379}|g" \
  /etc/grafana/provisioning/datasources/datasources.yaml.tmpl \
  > /etc/grafana/provisioning/datasources/datasources.yaml

exec /run.sh "$@"