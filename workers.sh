#!/bin/bash
# workers.sh

# Exit immediately if a command fails
set -e

# Calculate workers based on available CPU cores
NUM_CORES=$(nproc)

echo "Starting RQ worker pool with $NUM_CORES workers..."

# Use 'exec' so the worker pool becomes PID 1.
# Replace 'host.docker.internal' with an environment variable for production.
exec rq worker-pool default \
    -n "$NUM_CORES" \
    --job-class rq.job.Job \
    --url "${REDIS_URL:-redis://host.docker.internal:${REDIS_PORT:-6379}}"