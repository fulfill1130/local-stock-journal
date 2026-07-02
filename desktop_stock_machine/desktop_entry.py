"""Desktop window entry point for the packaged stock machine UI."""

from __future__ import annotations

import sys
from pathlib import Path


APP_TITLE = "桌面股票機"


def bundled_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return Path(__file__).resolve().parent


def frontend_root() -> Path:
    return bundled_root() / "frontend"


def frontend_index() -> Path:
    return frontend_root() / "index.html"


def validate_frontend() -> Path:
    index_path = frontend_index()
    if not index_path.is_file():
        raise FileNotFoundError(f"Desktop UI entry file was not found: {index_path}")
    return index_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    index_path = validate_frontend()

    if "--check" in args:
        print(index_path)
        return 0

    import webview

    webview.create_window(
        APP_TITLE,
        index_path.as_uri(),
        width=1440,
        height=960,
        min_size=(1120, 720),
    )
    webview.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
