from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from typing import Any, AsyncIterator

import importlib
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount
import uvicorn

from contextlib import asynccontextmanager

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

from utils.mcp_entrypoints_utils import (
    MCPEntrypointConfig,
    apply_environment,
    discover_entrypoint_modules,
    invoke_entrypoint,
    parse_tool_payload,
    tool_name_for_module,
    infer_package_name,
    EntrypointError,
)

# -------------------------
# CONFPATH (DYNAMIC SAFE)
# -------------------------


def init_confpath() -> None:
    """Dynamic config resolution.

    - supports relative paths
    - supports override via env
    """
    confpath = os.getenv("CONFPATH")
    if not confpath:
        return

    path = Path(confpath).expanduser()

    if not path.is_absolute():
        path = Path.cwd() / path

    path = path.resolve()

    # DO NOT break container startup if missing (important for copier templates)
    if path.exists():
        os.environ["CONFPATH"] = str(path)


# -------------------------
# CLI
# -------------------------


def load_args() -> MCPEntrypointConfig:
    """Load and parse command line arguments for the MCP server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", default="")
    parser.add_argument("--toolset-name", default="mcp-entrypoints")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args()

    package = args.package.strip()
    if not package:
        package = infer_package_name(Path.cwd())

    return MCPEntrypointConfig(
        package=package,
        toolset_name=args.toolset_name,
        server_host=args.host,
        server_port=args.port,
    )


# -------------------------
# TOOL WRAPPER
# -------------------------


def _invoke_sync(module_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Synchronous entrypoint execution — always called via asyncio.to_thread."""
    try:
        args, kwargs = parse_tool_payload(payload)
        result = invoke_entrypoint(module_name, args, kwargs)

        if isinstance(result, dict) and "status" in result:
            return result

        return {"status": "ok", "data": result}

    except EntrypointError as e:
        return e.to_payload()

    except SystemExit as e:
        return {
            "status": "error",
            "error": "system_exit",
            "message": (
                f"Entrypoint called sys.exit({e.code}). "
                "Use initialize_config_dir + compose in mcp_entrypoint() "
                "instead of calling the @hydra.main-decorated main()."
            ),
            "module": module_name,
        }

    except Exception as e:
        return {
            "status": "error",
            "error": "unexpected_error",
            "message": str(e),
            "module": module_name,
        }


def register_tool(mcp: FastMCP, module_name: str, tool_name: str) -> None:
    """Register a tool with FastMCP.

    Dynamically pulls the description from the module's mcp_entrypoint docstring.
    """
    # 1. Extract the specific tool description from the module
    try:
        module = importlib.import_module(module_name)
        entrypoint_func = getattr(module, "mcp_entrypoint", None)
        # Priority: mcp_entrypoint docstring -> module docstring -> default
        tool_description = (
            (entrypoint_func.__doc__ if entrypoint_func else None)
            or module.__doc__
            or f"Run {tool_name}"
        )
    except Exception:
        tool_description = f"Execute tool from {module_name}"

    @mcp.tool(name=tool_name, description=tool_description)  # type: ignore[misc]
    async def _tool(payload: dict[str, Any] | None = None) -> Any:
        """Async wrapper that offloads the blocking entrypoint to a thread pool."""
        return await asyncio.to_thread(_invoke_sync, module_name, payload or {})


# -------------------------
# SERVER BUILD
# -------------------------


def build_server(config: MCPEntrypointConfig) -> FastMCP:
    """Build and configure the FastMCP server instance."""
    apply_environment(config)
    init_confpath()
    mcp = FastMCP(config.toolset_name)

    for module_name in discover_entrypoint_modules(config):
        tool_name = tool_name_for_module(module_name, config)
        register_tool(mcp, module_name, tool_name)

    return mcp


# -------------------------
# STREAMABLE HTTP SERVER
# -------------------------


def run_http(server: FastMCP, host: str, port: int, stateless: bool = True) -> None:
    """Run the MCP server over HTTP using Starlette and Uvicorn."""
    session_manager = StreamableHTTPSessionManager(
        server._mcp_server,
        stateless=stateless,
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        async with session_manager.run():
            yield

    app = Starlette(
        routes=[
            Mount("/mcp/", app=session_manager.handle_request),
        ],
        lifespan=lifespan,
    )

    uvicorn.run(app, host=host, port=port, log_level="info")


# -------------------------
# MAIN
# -------------------------


def main() -> None:
    """Main entrypoint for the MCP server CLI."""
    config = load_args()
    server = build_server(config)

    run_http(
        server,
        host=config.server_host if config.server_host is not None else "0.0.0.0",
        port=config.server_port if config.server_port is not None else 8000,
        stateless=True,
    )


if __name__ == "__main__":
    main()
