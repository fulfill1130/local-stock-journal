"""Runtime status helpers for the desktop stock machine skeleton."""

from __future__ import annotations

from desktop_stock_machine.app import paths
from desktop_stock_machine.app.settings import APP_NAME, MODE


def get_desktop_status() -> dict[str, object]:
    app_data_root = paths.default_app_data_root()

    return {
        "app_name": APP_NAME,
        "mode": MODE,
        "project_root": str(paths.project_root()),
        "desktop_root": str(paths.desktop_root()),
        "frontend_root": str(paths.frontend_root()),
        "app_data_root": str(app_data_root),
        "app_data_exists": app_data_root.exists(),
        "legacy_web_runtime_imported": False,
    }
