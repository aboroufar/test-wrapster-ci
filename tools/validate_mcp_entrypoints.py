from __future__ import annotations

import argparse
import importlib
from pathlib import Path
from typing import Any

from utils.mcp_entrypoints_utils import (
    MCPEntrypointConfig,
    discover_entrypoint_modules,
    infer_package_name,
    tool_name_for_module,
)


def _has_entrypoint(module: Any) -> bool:
    return hasattr(module, "main") or hasattr(module, "run")


def main() -> int:
    """Validate all discovered MCP entrypoints in the package."""
    parser = argparse.ArgumentParser(description="Validate MCP entrypoints")
    parser.add_argument("--package", default="")
    args = parser.parse_args()

    package = args.package.strip()
    if not package:
        package = infer_package_name(Path(__file__).resolve().parents[1])

    config = MCPEntrypointConfig(package=package)
    modules = discover_entrypoint_modules(config)
    if not modules:
        print("No entrypoint modules discovered.")
        return 1

    print(f"Discovered {len(modules)} modules:")
    failures = 0
    for module_name in modules:
        tool_name = tool_name_for_module(module_name, config)
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:  # noqa: BLE001 - validation script
            print(f"- {module_name} ({tool_name}) -> import error: {exc}")
            failures += 1
            continue
        if not _has_entrypoint(module):
            print(f"- {module_name} ({tool_name}) -> missing main/run")
            failures += 1
            continue
        print(f"- {module_name} ({tool_name}) -> ok")

    if failures:
        print(f"Validation completed with {failures} issue(s).")
        return 1
    print("Validation completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
