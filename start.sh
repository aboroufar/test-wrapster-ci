#!/bin/bash
set -e

echo "CONFPATH is: ${CONFPATH}"

# Start MCP server
python -m tools.expose_mcp_server \
    --host 0.0.0.0 \
    --port "${CONTAINER_PORT:-8000}" &

MCP_PID=$!

echo "FastMCP PID: $MCP_PID"

# Clean shutdown
cleanup() {
  echo "Shutting down MCP..."
  kill $MCP_PID 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "Starting workers..."

exec ./workers.sh