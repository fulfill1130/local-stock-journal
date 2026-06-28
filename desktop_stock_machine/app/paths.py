"""Path helpers for the desktop stock machine skeleton."""

from __future__ import annotations

import os
from pathlib import Path

from desktop_stock_machine.app.settings import DATA_ROOT_ENV_VAR


def desktop_root() -> Path:
    return Path(__file__).resolve().parents[1]


def project_root() -> Path:
    return desktop_root().parent


def default_app_data_root() -> Path:
    override = os.environ.get(DATA_ROOT_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return project_root() / "app_data"


def frontend_root() -> Path:
    return desktop_root() / "frontend"
