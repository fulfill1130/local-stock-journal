"""CLI entry for the desktop stock machine skeleton."""

from __future__ import annotations

from pathlib import Path

from desktop_stock_machine.app.status import get_desktop_status


def _format_status_value(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def main() -> int:
    status = get_desktop_status()

    print("Desktop Stock Machine startup")
    print(f"app name: {status['app_name']}")
    print(f"mode: {status['mode']}")
    print(f"current working directory: {Path.cwd()}")
    print(f"resolved project root: {status['project_root']}")
    print(f"resolved desktop folder: {status['desktop_root']}")
    print(f"resolved default app data root path: {status['app_data_root']}")
    print(f"app data root exists: {_format_status_value(status['app_data_exists'])}")
    print("server: not started")
    print("window: not opened")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
