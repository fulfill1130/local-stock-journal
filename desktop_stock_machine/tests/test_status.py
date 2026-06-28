from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from desktop_stock_machine.app.settings import APP_NAME, DATA_ROOT_ENV_VAR, MODE
from desktop_stock_machine.app.status import get_desktop_status


class DesktopStatusTests(unittest.TestCase):
    def test_status_returns_required_keys(self) -> None:
        status = get_desktop_status()

        self.assertEqual(
            set(status),
            {
                "app_name",
                "mode",
                "project_root",
                "desktop_root",
                "frontend_root",
                "app_data_root",
                "app_data_exists",
                "legacy_web_runtime_imported",
            },
        )
        self.assertEqual(status["app_name"], APP_NAME)
        self.assertEqual(status["mode"], MODE)
        self.assertIs(status["legacy_web_runtime_imported"], False)

    def test_status_does_not_create_app_data_root(self) -> None:
        previous = os.environ.get(DATA_ROOT_ENV_VAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "status_app_data"
            os.environ[DATA_ROOT_ENV_VAR] = str(target)
            try:
                self.assertFalse(target.exists())
                status = get_desktop_status()
                self.assertEqual(status["app_data_root"], str(target.resolve()))
                self.assertIs(status["app_data_exists"], False)
                self.assertFalse(target.exists())
            finally:
                if previous is None:
                    os.environ.pop(DATA_ROOT_ENV_VAR, None)
                else:
                    os.environ[DATA_ROOT_ENV_VAR] = previous


if __name__ == "__main__":
    unittest.main()
