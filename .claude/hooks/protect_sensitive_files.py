"""
Claude Code PreToolUse hook for Edit|Write tools.
Blocks direct modifications to .env files, uv.lock, and locked initial migrations.
Exit code 2 blocks the tool call and surfaces the stderr message to Claude.
"""

import json
import pathlib
import sys


LOCKED_MIGRATIONS = {
    "01d2c1dca0d8_initial_production_schema.py",
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input") or {}
    file_path_str = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path_str:
        return 0

    path = pathlib.Path(file_path_str)
    name = path.name
    parts = [p.lower() for p in path.parts]

    # 1. Block .env modifications (allow .env.example)
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        sys.stderr.write(
            f"Blocked by repository hook: Direct modification of '{name}' is prohibited. "
            "Update '.env.example' for template changes instead.\n"
        )
        return 2

    # 2. Block manual edits to uv.lock
    if name == "uv.lock":
        sys.stderr.write(
            "Blocked by repository hook: Do not edit 'uv.lock' manually. "
            "Use 'uv lock' or 'uv add <pkg>' instead.\n"
        )
        return 2

    # 3. Block edits to committed initial Alembic schema migrations
    if "migrations" in parts and "versions" in parts and name in LOCKED_MIGRATIONS:
        sys.stderr.write(
            f"Blocked by repository hook: Migration '{name}' is locked. "
            "Create a new migration with 'uv run alembic revision --autogenerate -m \"...\"'.\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
