from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from desktop_stock_machine.app import paths
from desktop_stock_machine.app.settings import DATA_ROOT_ENV_VAR


class PathHelperTests(unittest.TestCase):
    def test_paths_resolve_under_project_by_default(self) -> None:
        project_root = paths.project_root()

        self.assertTrue((project_root / "desktop_stock_machine").exists())
        self.assertEqual(paths.desktop_root(), project_root / "desktop_stock_machine")
        self.assertEqual(paths.frontend_root(), paths.desktop_root() / "frontend")
        self.assertEqual(paths.default_app_data_root(), project_root / "app_data")

    def test_env_var_override_works_for_app_data_root(self) -> None:
        previous = os.environ.get(DATA_ROOT_ENV_VAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            override = Path(temp_dir) / "custom_app_data"
            os.environ[DATA_ROOT_ENV_VAR] = str(override)
            try:
                self.assertEqual(paths.default_app_data_root(), override.resolve())
                self.assertFalse(override.exists())
            finally:
                if previous is None:
                    os.environ.pop(DATA_ROOT_ENV_VAR, None)
                else:
                    os.environ[DATA_ROOT_ENV_VAR] = previous

    def test_path_helpers_do_not_create_app_data_root(self) -> None:
        previous = os.environ.get(DATA_ROOT_ENV_VAR)
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "missing_app_data"
            os.environ[DATA_ROOT_ENV_VAR] = str(target)
            try:
                self.assertFalse(target.exists())
                self.assertEqual(paths.default_app_data_root(), target.resolve())
                self.assertFalse(target.exists())
            finally:
                if previous is None:
                    os.environ.pop(DATA_ROOT_ENV_VAR, None)
                else:
                    os.environ[DATA_ROOT_ENV_VAR] = previous


if __name__ == "__main__":
    unittest.main()
