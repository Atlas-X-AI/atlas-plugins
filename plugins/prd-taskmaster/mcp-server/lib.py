"""
Shared helpers for the MCP server: atomic file writes, locked read-modify-write,
error formatting. All functions return dicts — NEVER call sys.exit (per spec §13.3).
"""
from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically via tmp + os.replace (atomic on POSIX)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(content)
    os.replace(tmp, path)


def locked_update(path: Path, transform: Callable[[str], str]) -> str:
    """Read-modify-write under flock. transform takes current content, returns new content.
    Returns the new content for convenience."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with open(lock_path, "w") as lock_f:
        fcntl.flock(lock_f, fcntl.LOCK_EX)
        try:
            current = path.read_text() if path.exists() else ""
            new = transform(current)
            atomic_write(path, new)
            return new
        finally:
            fcntl.flock(lock_f, fcntl.LOCK_UN)


def emit_json_error(message: str, **extra: Any) -> dict:
    """Format an error response as a dict. DO NOT call sys.exit."""
    return {"ok": False, "error": message, **extra}


def now_iso() -> str:
    """UTC timestamp in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    """Read and parse a JSON file. Returns empty dict if missing."""
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_json(path: Path, data: dict) -> None:
    """Write dict as JSON atomically."""
    atomic_write(path, json.dumps(data, indent=2, default=str))
