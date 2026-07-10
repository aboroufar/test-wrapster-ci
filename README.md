## Project Environment Management

This project uses a unified management script: `setup.bash` for orchestrating Docker Compose environments, profiles, and documentation workflows.

### Main Commands

All commands can be run via **`uv run poe <task>`** (recommended) or directly via `setup.bash`.

| Poe Task                   | Equivalent                    | Description                                                                                  |
|----------------------------|-------------------------------|----------------------------------------------------------------------------------------------|
| `uv run poe up [profiles...]`    | `setup.bash up [profiles...]` | Launches the main stack and multiple additional profile services.                            |
| `uv run poe remove <profiles...>`| `setup.bash remove <profiles...>` | Stops and removes containers/volumes for the specified profiles (excludes default services). |
| `uv run poe down`                | `setup.bash down`             | Destroys all containers, networks, and volumes for all profiles.                             |
| `uv run poe status`              | `setup.bash status`           | Shows the status of all services, their state, architecture, and profiles.                   |
| `uv run poe docs [mode]`         | `setup.bash docs [mode]`      | Manages MkDocs documentation (see below for modes).                                          |

### Usage Examples

#### Start Core Services (default profile)
```bash
uv run poe up
# or
./setup.bash up
```

#### Start with Additional Profiles
```bash
uv run poe up <profile1 profile2>
# or
./setup.bash up <profile1 profile2>
```

#### Check Status of All Services
```bash
uv run poe status
# or
./setup.bash status
```

#### Remove Only Profile Services (not default)
```bash
uv run poe remove <profile-name>
# or
./setup.bash remove <profile-name>
```

#### Stop and Remove Everything
```bash
uv run poe down
# or
./setup.bash down
```

### Documentation Management (MkDocs)

| Poe Task                    | Direct                        | Description                                              |
|-----------------------------|-------------------------------|----------------------------------------------------------|
| `uv run poe docs serve`     | `./setup.bash docs serve`     | Start MkDocs dev server (http://localhost:7005 by default) |
| `uv run poe docs build`     | `./setup.bash docs build`     | Build static HTML/PDF docs (output in `./site/`)         |
| `uv run poe docs stop`      | `./setup.bash docs stop`      | Stop MkDocs service                                      |
| `uv run poe docs logs`      | `./setup.bash docs logs`      | View MkDocs logs                                         |

### Default Profile Services

The following services are included in the `default and monitoring` profile:

- **wrapster_project** (main application)
- **redis** (cache/database)
- **redis-insight** (Redis Insight dashboard)
- **rq-dashboard** (RQ dashboard, if `MONITORING=enable`)
- **prometheus** (Prometheus, if `MONITORING=enable`)
- **pushgateway** (Pushgateway, if `MONITORING=enable`)
- **grafana** (Grafana, if `MONITORING=enable`)

> Some services are conditionally included in `monitoring` profile, to enable:

#### Start monitoring services
```bash
uv run poe up monitoring
# or
./setup.bash up monitoring
```

### Example: Adding a Service with a Custom Profile

To add a new service with a custom profile (e.g., `analytics`), add a block like this to your `docker-compose.yaml.jinja`:

```yaml
  analytics_service:
    image: analytics-image:latest
    container_name: ${CONTAINER_NAME}_analytics
    ports:
      - "9000:9000"
    profiles:
      - analytics
```

To start or remove this service with the rest of the stack:
```bash
uv run poe up analytics
# or
./setup.bash up analytics

uv run poe remove analytics
# or
./setup.bash remove analytics
```

### Running Pipelines and Tests

Run a pipeline inside the main container:
```bash
docker exec -it sfsdf python src/sf/whetherstack_retrieve_pipeline_test.py
```

Run all tests:
```bash
docker exec -it sfsdf python -m pytest --cov
```

Run MCP StreamableHttp tests:

```bash
docker exec -it sfsdf \
  pytest --cov=src/sf tests/test_mcp_streamable_http.py
```

Run all MCP tests:

```bash
docker exec -it sfsdf \
  pytest --cov=src/sf tests/test_mcp_streamable_http.py tests/test_mcp_entrypoints.py
```

### MCP Entrypoint Server

Expose entrypoints as tools via the MCP server:
```bash
docker exec -it sfsdf \
  python -m tools.expose_mcp_server \
  --host 0.0.0.0 \
  --port <<your-port-number>>
```

Use MCP Inspector with: (http://localhost:8005/mcp/ by default)

Optional filters and naming (from the container):

```bash
docker exec -it sfsdf \
  python -m tools.expose_mcp_server --port <<your-port-number>>
```

Validate discovery and entrypoint availability (from the container):

```bash
docker exec -it sfsdf \
  python -m tools.validate_mcp_entrypoints
```

Use --package to override auto-detection when the workspace has multiple Python packages.

### Quick Reference: Ports
- Redis Insight: http://localhost:5540/
- Grafana: http://localhost:3000/
- Redis queue dashboard: http://localhost:9181/
- Pushgateway: http://localhost:9091/
- Prometheus: http://localhost:9090/


## Support

- sdf -> s@g.com
# test-wrapster-ci
