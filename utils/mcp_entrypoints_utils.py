from __future__ import annotations

from dataclasses import dataclass, field
import fnmatch
import importlib
import importlib.util
import json
import logging
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Iterator


@dataclass(frozen=True)
class MCPEntrypointConfig:
    """Configuration for MCP entrypoints discovery and server."""

    package: str
    toolset_name: str = "mcp-entrypoints"
    tool_name_prefix: str = ""
    include_modules: tuple[str, ...] = ()
    exclude_modules: tuple[str, ...] = ()
    exclude_patterns: tuple[str, ...] = ("**/__init__.py",)
    hydra_env: dict[str, str] = field(default_factory=dict)
    base_path: Path | None = None
    require_entrypoint: bool = True
    server_host: str | None = None
    server_port: int = int(os.environ.get("CONTAINER_PORT", "8000"))


class EntrypointError(Exception):
    """Custom exception for MCP entrypoint related errors."""

    def __init__(
        self,
        code: str,
        message: str,
        module_name: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.module_name = module_name
        self.detail = detail

    def to_payload(self) -> dict[str, Any]:
        """Convert the error to a JSON-serializable payload."""
        payload: dict[str, Any] = {
            "status": "error",
            "error": self.code,
            "message": self.message,
        }
        if self.module_name:
            payload["module"] = self.module_name
        if self.detail:
            payload["detail"] = self.detail
        return payload


def infer_package_name(project_root: Path) -> str:
    """Infer the package name from the project structure."""
    src_root = project_root / "src"
    if not src_root.is_dir():
        raise EntrypointError("missing_src", f"Missing src directory: {src_root}")

    candidates = [
        path.name for path in src_root.iterdir() if (path / "__init__.py").is_file()
    ]
    if not candidates:
        raise EntrypointError(
            "package_not_found", "No package with __init__.py found under src"
        )
    if len(candidates) > 1:
        raise EntrypointError(
            "multiple_packages",
            "Multiple packages found under src; pass --package explicitly",
        )
    return candidates[0]


def resolve_package_root(package: str) -> Path:
    """Resolve the physical path of a given package."""
    spec = importlib.util.find_spec(package)
    if not spec or not spec.submodule_search_locations:
        raise EntrypointError("package_not_found", f"Package not found: {package}")
    return Path(spec.submodule_search_locations[0]).resolve()


def _matches_any(path: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def _normalize_module_name(module_name: str, package: str) -> str:
    if module_name.startswith(f"{package}."):
        return module_name[len(package) + 1 :]
    return module_name


def _module_in_list(
    module_name: str,
    package: str,
    allowed: Iterable[str],
) -> bool:
    short_name = _normalize_module_name(module_name, package)
    for item in allowed:
        if item == module_name or item == short_name:
            return True
    return False


def discover_entrypoint_modules(config: MCPEntrypointConfig) -> list[str]:
    """Discover all modules within a package that have valid entrypoints."""
    base_path = config.base_path or resolve_package_root(config.package)
    modules: list[str] = []
    for file_path in base_path.rglob("*.py"):
        rel_path = file_path.relative_to(base_path)
        rel_posix = rel_path.as_posix()
        if _matches_any(rel_posix, config.exclude_patterns):
            continue
        module_id = ".".join(rel_path.with_suffix("").parts)
        module_name = f"{config.package}.{module_id}"
        if config.include_modules and not _module_in_list(
            module_name, config.package, config.include_modules
        ):
            continue
        if config.exclude_modules and _module_in_list(
            module_name, config.package, config.exclude_modules
        ):
            continue
        if config.require_entrypoint and not _module_has_entrypoint(module_name):
            continue
        modules.append(module_name)
    return sorted(modules)


def _module_has_entrypoint(module_name: str) -> bool:
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return False
    return (
        hasattr(module, "mcp_entrypoint")
        or hasattr(module, "main")
        or hasattr(module, "run")
    )


def tool_name_for_module(module_name: str, config: MCPEntrypointConfig) -> str:
    """Generate a sanitized tool name for a given module."""
    short_name = _normalize_module_name(module_name, config.package)
    sanitized = short_name.replace("_", "-").replace(".", "-")
    prefix = config.tool_name_prefix.strip()
    return f"{prefix}{sanitized}" if prefix else sanitized


def apply_environment(config: MCPEntrypointConfig) -> None:
    """Apply environment variables from configuration to the current process."""
    for key, value in config.hydra_env.items():
        os.environ[key] = value


def _format_cli_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value)


def _append_overrides(
    args: list[str],
    overrides: dict[str, Any],
    prefix: str,
) -> None:
    for key, value in overrides.items():
        args.append(f"{prefix}{key}={_format_cli_value(value)}")


def parse_tool_payload(payload: Any) -> tuple[list[str], dict[str, Any]]:
    """Parse the tool payload into CLI arguments and keyword arguments."""
    if payload is None:
        return [], {}
    if not isinstance(payload, dict):
        raise EntrypointError("invalid_payload", "Tool input must be a JSON object")

    args: list[str] = []
    raw_args = payload.get("args", [])
    if raw_args:
        if not isinstance(raw_args, list) or not all(
            isinstance(item, str) for item in raw_args
        ):
            raise EntrypointError("invalid_args", "args must be a list of strings")
        args.extend(raw_args)

    params = payload.get("params")
    if params is not None:
        if not isinstance(params, dict):
            raise EntrypointError("invalid_params", "params must be an object")
        _append_overrides(args, params, "++")

    overrides = payload.get("overrides")
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise EntrypointError("invalid_overrides", "overrides must be an object")
        _append_overrides(args, overrides, "")

    kwargs = payload.get("kwargs", {})
    if not isinstance(kwargs, dict):
        raise EntrypointError("invalid_kwargs", "kwargs must be an object")

    return args, kwargs


@contextmanager
def _patched_argv(module_name: str, args: list[str]) -> Iterator[None]:
    original = sys.argv
    # Mimic the module as the script name
    sys.argv = [f"{module_name}.py"] + args
    try:
        yield
    finally:
        sys.argv = original


def invoke_entrypoint(
    module_name: str,
    args: list[str],
    kwargs: dict[str, Any],
) -> Any:
    """Invoke the entrypoint function of a module with given arguments."""
    logger = logging.getLogger(__name__)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - pass through structured error
        raise EntrypointError(
            "import_error",
            "Failed to import entrypoint module",
            module_name=module_name,
            detail=repr(exc),
        ) from exc

    func = (
        getattr(module, "mcp_entrypoint", None)
        or getattr(module, "main", None)
        or getattr(module, "run", None)
    )
    if func is None:
        raise EntrypointError(
            "missing_entrypoint",
            "Module does not define mcp_entrypoint, main, or run",
            module_name=module_name,
        )

    try:
        with _patched_argv(module_name, args):
            logger.debug("Hydra argv: %s", sys.argv)
            if func.__name__ == "mcp_entrypoint" and kwargs:
                raise EntrypointError(
                    "invalid_kwargs",
                    "mcp_entrypoint does not accept kwargs; use args/params/overrides",
                    module_name=module_name,
                )
            if kwargs:
                return func(**kwargs)
            return func()
    except EntrypointError:
        raise
    except SystemExit as exc:
        raise EntrypointError(
            "execution_error",
            "Entrypoint exited",
            module_name=module_name,
            detail=str(exc.code),
        ) from exc
    except Exception as exc:  # noqa: BLE001 - pass through structured error
        raise EntrypointError(
            "execution_error",
            "Entrypoint execution failed",
            module_name=module_name,
            detail=repr(exc),
        ) from exc
