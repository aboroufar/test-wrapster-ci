#!/usr/bin/env bash
set -Eeuo pipefail

MODE="${1:-serve}"
shift || true

log() { echo "[mkdocs] $*"; }

DEFAULT_PORT="${MKDOCS_PORT:-7000}"
ADDR="0.0.0.0:${DEFAULT_PORT}"

case "$MODE" in
  serve)
    log "Starting MkDocs dev server on ${ADDR}"
    exec mkdocs serve --dev-addr "$ADDR" "$@"
    ;;

  build)
    log "Building static site"
    exec mkdocs build --clean "$@"
    ;;

  pdf)
    log "Building site with PDF export"
    export ENABLE_PDF_EXPORT=1
    exec mkdocs build --clean "$@"
    ;;

  *)
    log "Running custom command: $MODE $*"
    exec "$MODE" "$@"
    ;;
esac