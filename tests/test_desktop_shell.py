from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from desktop_shell import DesktopShellConfig, DesktopShellStatus, NullDesktopShell  # noqa: E402


class DesktopShellProtocolTests(unittest.TestCase):
    def test_config_and_status_objects_can_be_created(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            runtime_root = Path(tmp) / "demo_runtime"
            config = DesktopShellConfig(project_root=project_root, runtime_root=runtime_root)
            status = DesktopShellStatus(is_running=False)

        self.assertEqual(config.profile, "demo")
        self.assertTrue(config.demo_mode)
        self.assertEqual(config.window_title, "Local Stock Journal")
        self.assertFalse(status.is_running)
        self.assertEqual(status.base_url, "")

    def test_module_import_does_not_require_desktop_dependencies(self) -> None:
        for module_name in ("pywebview", "webview", "tauri", "electron"):
            sys.modules.pop(module_name, None)

        module = importlib.import_module("desktop_shell")

        self.assertTrue(hasattr(module, "DesktopShell"))
        for module_name in ("pywebview", "webview", "tauri", "electron"):
            self.assertNotIn(module_name, sys.modules)

    def test_null_shell_lifecycle_is_predictable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            shell = NullDesktopShell(
                DesktopShellConfig(project_root=Path(tmp), runtime_root=Path(tmp) / "demo_runtime"),
                base_url="http://127.0.0.1:12345/",
            )

            self.assertFalse(shell.status.is_running)
            self.assertEqual(shell.base_url, "")
            with self.assertRaises(RuntimeError):
                shell.open_main_window()

            returned = shell.start()
            self.assertIs(returned, shell)
            self.assertTrue(shell.status.is_running)
            self.assertEqual(shell.base_url, "http://127.0.0.1:12345")
            self.assertEqual(shell.url, "http://127.0.0.1:12345/demo")

            shell.open_main_window()
            self.assertTrue(shell.status.main_window_opened)

            shell.show_error("demo error")
            self.assertEqual(shell.status.last_error, "demo error")

            shell.stop()
            self.assertFalse(shell.status.is_running)
            self.assertFalse(shell.status.main_window_opened)
            self.assertEqual(shell.base_url, "")

    def test_null_shell_does_not_require_real_data_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            shell = NullDesktopShell(DesktopShellConfig(project_root=project_root))

            shell.start()
            shell.stop()

            self.assertFalse((project_root / "data").exists())


if __name__ == "__main__":
    unittest.main()
