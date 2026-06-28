"""Development entry point for the desktop stock machine skeleton."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    project_root = Path(__file__).resolve().parents[1]
    project_root_text = str(project_root)
    if project_root_text not in sys.path:
        sys.path.insert(0, project_root_text)


def run() -> int:
    _ensure_project_root_on_path()

    from desktop_stock_machine.app.main import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
