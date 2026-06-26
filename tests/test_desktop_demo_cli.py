from __future__ import annotations

import io
import shutil
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cli import build_parser, run_cli  # noqa: E402
from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402


class DesktopDemoCliTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.temp_root = Path(tempfile.mkdtemp())
        self.runtime = self.temp_root / "demo_runtime"
        prepare_demo_runtime(ROOT, self.runtime, reset=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_parser_recognizes_desktop_demo_without_changing_existing_commands(self) -> None:
        parser = build_parser()

        desktop_args = parser.parse_args(["desktop-demo"])
        serve_args = parser.parse_args(["serve"])
        serve_demo_args = parser.parse_args(["serve-demo"])

        self.assertEqual(desktop_args.command, "desktop-demo")
        self.assertEqual(serve_args.command, "serve")
        self.assertEqual(serve_demo_args.command, "serve-demo")
        self.assertEqual(serve_demo_args.port, 8787)

    def test_desktop_demo_validates_runtime_and_calls_shell_launcher(self) -> None:
        with patch("cli.launch_desktop_demo", return_value=None) as launcher:
            result = run_cli(ROOT, ["desktop-demo", "--runtime", str(self.runtime)])

        self.assertEqual(result, 0)
        launcher.assert_called_once_with(ROOT, self.runtime.resolve())

    def test_missing_pywebview_prints_friendly_error(self) -> None:
        error = ModuleNotFoundError("No module named 'webview'")
        error.name = "webview"
        output = io.StringIO()

        with patch("cli.launch_desktop_demo", side_effect=error), redirect_stdout(output):
            result = run_cli(ROOT, ["desktop-demo", "--runtime", str(self.runtime)])

        text = output.getvalue()
        self.assertEqual(result, 2)
        self.assertIn("pip install -r requirements-desktop.txt", text)
        self.assertIn("Normal web commands still work", text)

    def test_missing_demo_runtime_is_rejected_before_shell_launch(self) -> None:
        missing = self.temp_root / "missing_runtime"
        output = io.StringIO()

        with patch("cli.launch_desktop_demo", return_value=None) as launcher, redirect_stdout(output):
            result = run_cli(ROOT, ["desktop-demo", "--runtime", str(missing)])

        self.assertEqual(result, 2)
        self.assertIn("python scripts/prepare_demo_runtime.py --reset", output.getvalue())
        launcher.assert_not_called()

    def test_normal_serve_demo_check_still_uses_existing_flow(self) -> None:
        output = io.StringIO()

        with patch("cli.launch_desktop_demo", return_value=None) as launcher, redirect_stdout(output):
            result = run_cli(ROOT, ["serve-demo", "--runtime", str(self.runtime), "--check"])

        self.assertEqual(result, 0)
        self.assertIn("Demo Dashboard", output.getvalue())
        launcher.assert_not_called()


if __name__ == "__main__":
    unittest.main()
