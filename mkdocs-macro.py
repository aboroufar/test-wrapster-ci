import os
from dotenv import load_dotenv
from typing import Any


def define_env(env: Any) -> None:
    """Define MkDocs macros and load environment variables for documentation builds."""
    load_dotenv()

    def mkdocs_macro(name: str, default: str | None = None) -> str | None:
        return os.getenv(name, default)

    # Register the macro with the expected API
    if hasattr(env, "macro") and callable(env.macro):
        env.macro(mkdocs_macro)
