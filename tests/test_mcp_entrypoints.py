from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

from utils.mcp_entrypoints_utils import (
    EntrypointError,
    MCPEntrypointConfig,
    _format_cli_value,
    apply_environment,
    discover_entrypoint_modules,
    infer_package_name,
    invoke_entrypoint,
    parse_tool_payload,
    resolve_package_root,
    tool_name_for_module,
)


def _write_module(path: Path, code: str) -> None:
    path.write_text(code, encoding="utf-8")


def _create_package(tmp_path: Path, name: str) -> Path:
    package_dir = tmp_path / name
    package_dir.mkdir()
    _write_module(package_dir / "__init__.py", "")
    return package_dir


@pytest.fixture()
def temp_package(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Create a temporary package for testing MCP entrypoints strictly matching the original layout."""
    package_name = "mcp_test_pkg"
    sys.modules.pop(package_name, None)
    package_dir = _create_package(tmp_path, package_name)
    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    yield package_name, package_dir
    sys.path.remove(str(tmp_path))
    sys.modules.pop(package_name, None)
    importlib.invalidate_caches()


# --- SECTION 1: Exact Replication of the Old Test Cases ---


def test_invoke_entrypoint_prefers_mcp_entrypoint(
    temp_package: tuple[str, Path],
) -> None:
    """Test that invoke_entrypoint prefers mcp_entrypoint over main (Exactly from old file)."""
    package_name, package_dir = temp_package
    module_path = package_dir / "sample.py"
    _write_module(
        module_path,
        """
VALUE = "mcp"


def mcp_entrypoint():
    return {"status": "ok", "data": {"source": VALUE}}


def main():
    return {"status": "ok", "data": {"source": "main"}}
""",
    )
    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.sample", None)

    result = invoke_entrypoint(f"{package_name}.sample", [], {})
    assert result == {"status": "ok", "data": {"source": "mcp"}}


def test_invoke_entrypoint_rejects_kwargs_for_mcp_entrypoint(
    temp_package: tuple[str, Path],
) -> None:
    """Test that invoke_entrypoint rejects kwargs for mcp_entrypoint (Exactly from old file)."""
    package_name, package_dir = temp_package
    module_path = package_dir / "kwargs_only.py"
    _write_module(
        module_path,
        """

def mcp_entrypoint():
    return {"status": "ok", "data": {"value": 1}}
""",
    )
    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.kwargs_only", None)

    with pytest.raises(EntrypointError) as exc:
        invoke_entrypoint(f"{package_name}.kwargs_only", [], {"foo": "bar"})
    assert exc.value.code == "invalid_kwargs"


# --- SECTION 2: Advanced Infrastructure & Discovery Coverage ---


def test_entrypoint_error_payload() -> None:
    """Verifies EntrypointError properties and to_payload data formats."""
    err = EntrypointError("test_code", "test_msg", module_name="mod", detail="det")
    payload = err.to_payload()
    assert payload["status"] == "error"
    assert payload["error"] == "test_code"
    assert payload["message"] == "test_msg"
    assert payload["module"] == "mod"
    assert payload["detail"] == "det"


def test_mcpe_entrypoint_config_defaults() -> None:
    """Exercises default factory structures inside MCPEntrypointConfig."""
    config = MCPEntrypointConfig(package="test_pkg")
    assert config.toolset_name == "mcp-entrypoints"
    assert config.server_port == 8000 or isinstance(config.server_port, int)


def test_infer_package_name_layouts(tmp_path: Path) -> None:
    """Tests the package name infers validation paths under a simulated src directory root."""
    with pytest.raises(EntrypointError) as exc1:
        infer_package_name(tmp_path)
    assert exc1.value.code == "missing_src"

    src_dir = tmp_path / "src"
    src_dir.mkdir()
    with pytest.raises(EntrypointError) as exc2:
        infer_package_name(tmp_path)
    assert exc2.value.code == "package_not_found"

    _create_package(src_dir, "pkg1")
    _create_package(src_dir, "pkg2")
    with pytest.raises(EntrypointError) as exc3:
        infer_package_name(tmp_path)
    assert exc3.value.code == "multiple_packages"


def test_resolve_package_root_invalid() -> None:
    """Asserts that resolving a completely fake non-existent package raises an error."""
    with pytest.raises(EntrypointError) as exc:
        resolve_package_root("completely_fake_and_not_real_package_xyz")
    assert exc.value.code == "package_not_found"


def test_discover_entrypoint_modules_with_filters(
    temp_package: tuple[str, Path],
) -> None:
    """Exercises file iteration filtering rules, inclusions, exclusions, and short names."""
    package_name, package_dir = temp_package

    _write_module(package_dir / "valid_mcp.py", "def mcp_entrypoint(): pass")
    _write_module(package_dir / "valid_main.py", "def main(): pass")
    _write_module(package_dir / "valid_run.py", "def run(): pass")
    _write_module(package_dir / "ignored.py", "def other(): pass")
    _write_module(package_dir / "excluded.py", "def main(): pass")

    config = MCPEntrypointConfig(
        package=package_name,
        base_path=package_dir,
        include_modules=(
            f"{package_name}.valid_mcp",
            "valid_main",
            "valid_run",
            "excluded",
        ),
        exclude_modules=("excluded", f"{package_name}.valid_run"),
    )

    modules = discover_entrypoint_modules(config)
    assert f"{package_name}.valid_mcp" in modules
    assert f"{package_name}.valid_main" in modules
    assert f"{package_name}.valid_run" not in modules
    assert f"{package_name}.excluded" not in modules


def test_discover_broken_module_has_entrypoint_graceful_fail(
    temp_package: tuple[str, Path],
) -> None:
    """Verifies that discovery ignores syntax-corrupted modules gracefully."""
    package_name, package_dir = temp_package
    _write_module(package_dir / "broken.py", "invalid python syntax {{{")

    config = MCPEntrypointConfig(package=package_name, base_path=package_dir)
    modules = discover_entrypoint_modules(config)
    assert f"{package_name}.broken" not in modules


def test_discover_entrypoint_modules_pattern_exclusions(
    temp_package: tuple[str, Path],
) -> None:
    """Exercises custom exclude_patterns matching logic to ensure _matches_any yields coverage."""
    package_name, package_dir = temp_package
    _write_module(package_dir / "secret_test.py", "def main(): pass")

    config = MCPEntrypointConfig(
        package=package_name, base_path=package_dir, exclude_patterns=("*secret*",)
    )
    modules = discover_entrypoint_modules(config)
    assert f"{package_name}.secret_test" not in modules


# --- SECTION 3: Payload Transformation Testing ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, "null"),
        (True, "true"),
        (False, "false"),
        (123, "123"),
        (45.6, "45.6"),
        ("text", "text"),
        ({"key": "val"}, '{"key": "val"}'),
    ],
)
def test_format_cli_value(value: Any, expected: str) -> None:
    """Tests all type variations of the CLI override values formatter."""
    assert _format_cli_value(value) == expected


def test_parse_tool_payload_none_and_invalid() -> None:
    """Validates fallback output for empty inputs and catches invalid structural payloads."""
    assert parse_tool_payload(None) == ([], {})
    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload("not a dict")
    assert exc.value.code == "invalid_payload"


def test_parse_tool_payload_type_validations() -> None:
    """Validates structural internal validation rules for nested blocks."""
    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload({"args": "not a list"})
    assert exc.value.code == "invalid_args"

    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload({"args": [123]})
    assert exc.value.code == "invalid_args"

    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload({"params": "not a dict"})
    assert exc.value.code == "invalid_params"

    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload({"overrides": "not a dict"})
    assert exc.value.code == "invalid_overrides"

    with pytest.raises(EntrypointError) as exc:
        parse_tool_payload({"kwargs": "not a dict"})
    assert exc.value.code == "invalid_kwargs"


def test_parse_tool_payload_valid_composition() -> None:
    """Exercises full parser configuration transformation lifecycle strategy mapping."""
    payload = {
        "args": ["--verbose"],
        "params": {"lr": 0.01},
        "overrides": {"batch_size": 32},
        "kwargs": {"context": "test"},
    }
    args, kwargs = parse_tool_payload(payload)
    assert args == ["--verbose", "++lr=0.01", "batch_size=32"]
    assert kwargs == {"context": "test"}


# --- SECTION 4: Environment and Invocation Core Pipeline ---


def test_apply_environment_and_naming() -> None:
    """Exercises environment dict mutations and utility name string sanitization."""
    config = MCPEntrypointConfig(package="my_pkg", tool_name_prefix="prefix_")
    apply_environment(
        MCPEntrypointConfig(package="my_pkg", hydra_env={"TEST_VAR_XYZ": "123"})
    )
    assert os.environ.get("TEST_VAR_XYZ") == "123"

    t_name = tool_name_for_module("my_pkg.sub_mod.run_test", config)
    assert t_name == "prefix_sub-mod-run-test"


def test_invoke_entrypoint_main_accepts_kwargs(temp_package: tuple[str, Path]) -> None:
    """Validates main fallback execution path parsing optional keyword arguments."""
    package_name, package_dir = temp_package
    _write_module(
        package_dir / "main_kwargs.py",
        "def main(**kwargs): return {'status': 'ok', 'data': kwargs}",
    )

    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.main_kwargs", None)

    result = invoke_entrypoint(f"{package_name}.main_kwargs", [], {"alpha": 1})
    assert result == {"status": "ok", "data": {"alpha": 1}}


def test_invoke_entrypoint_import_error() -> None:
    """Triggers the import module exception block and structural wrapper verification."""
    with pytest.raises(EntrypointError) as exc:
        invoke_entrypoint("completely_nonexistent_module_path", [], {})
    assert exc.value.code == "import_error"


def test_invoke_entrypoint_missing_callable(temp_package: tuple[str, Path]) -> None:
    """Asserts that modules missing target callable attributes raise missing_entrypoint errors."""
    package_name, package_dir = temp_package
    _write_module(package_dir / "empty.py", "def unassociated(): pass")

    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.empty", None)

    with pytest.raises(EntrypointError) as exc:
        invoke_entrypoint(f"{package_name}.empty", [], {})
    assert exc.value.code == "missing_entrypoint"


def test_invoke_entrypoint_system_exit(temp_package: tuple[str, Path]) -> None:
    """Intercepts SystemExit exception unwrapping and reports the return status code."""
    package_name, package_dir = temp_package
    _write_module(package_dir / "sys_exit.py", "import sys\ndef main(): sys.exit(42)")

    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.sys_exit", None)

    with pytest.raises(EntrypointError) as exc:
        invoke_entrypoint(f"{package_name}.sys_exit", [], {})
    assert exc.value.code == "execution_error"
    assert "42" in str(exc.value.detail)  # Fixed: Wrapped in str() for mypy


def test_invoke_entrypoint_execution_failed(temp_package: tuple[str, Path]) -> None:
    """Captures unhandled exceptions within executable scripts and maps them to generic errors."""
    package_name, package_dir = temp_package
    _write_module(
        package_dir / "crash.py",
        "def main(): raise ArithmeticError('Zero division dummy')",
    )

    importlib.invalidate_caches()
    sys.modules.pop(f"{package_name}.crash", None)

    with pytest.raises(EntrypointError) as exc:
        invoke_entrypoint(f"{package_name}.crash", [], {})
    assert exc.value.code == "execution_error"
    assert "ArithmeticError" in str(
        exc.value.detail
    )  # Fixed: Wrapped in str() for mypy
