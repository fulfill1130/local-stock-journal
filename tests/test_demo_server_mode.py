from __future__ import annotations

import gc
import io
import shutil
import sys
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path

from werkzeug.exceptions import NotFound


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cli import run_cli  # noqa: E402
from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import DEMO_PROFILE, PROFILES, DemoRuntimeError, create_app, profile_info, validate_demo_runtime  # noqa: E402


class DemoServerModeTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)

    def test_demo_runtime_validation_rejects_missing_directory(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            missing = Path(tmp) / "demo_runtime"
            with self.assertRaises(DemoRuntimeError) as ctx:
                validate_demo_runtime(ROOT, missing)
            self.assertIn("python scripts/create_demo_data.py", str(ctx.exception))
            self.assertIn("python scripts/prepare_demo_runtime.py --reset", str(ctx.exception))

    def test_demo_runtime_validation_rejects_directory_without_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "demo_runtime"
            target.mkdir()
            with self.assertRaises(DemoRuntimeError):
                validate_demo_runtime(ROOT, target)

    def test_demo_runtime_validation_rejects_targets_inside_private_data(self) -> None:
        with self.assertRaises(DemoRuntimeError):
            validate_demo_runtime(ROOT, ROOT / "data" / "demo_runtime")

    def test_demo_profile_is_only_in_demo_registry(self) -> None:
        self.assertNotIn("demo", PROFILES)
        self.assertIn("demo", DEMO_PROFILE)
        app = create_app(ROOT, runtime_root=self._prepared_runtime(), demo_mode=True)
        self.addCleanup(self._cleanup_runtime, Path(app.config["RUNTIME_ROOT"]))
        with app.test_request_context():
            self.assertEqual(profile_info("demo", profiles=DEMO_PROFILE)["slug"], "demo")
            with self.assertRaises(NotFound):
                profile_info("demo")

    def test_demo_app_loads_demo_profile_and_local_history(self) -> None:
        runtime = self._prepared_runtime()
        self.addCleanup(self._cleanup_runtime, runtime)
        app = create_app(ROOT, runtime_root=runtime, demo_mode=True)
        client = app.test_client()

        state_response = client.get("/demo/api/state")
        self.assertEqual(state_response.status_code, 200)
        state = state_response.get_json()
        self.assertTrue(state["demo_mode"])
        self.assertEqual(state["profile"]["slug"], "demo")
        self.assertEqual(len(state["holdings"]), 1)
        self.assertEqual(state["holdings"][0]["ticker"], "DEMOA")
        self.assertTrue(str(app.config["RUNTIME_ROOT"]).endswith("demo_runtime"))

        history_response = client.get("/api/database/DEMOA/history?start=2026-01-01&end=2026-04-30")
        self.assertEqual(history_response.status_code, 200)
        history = history_response.get_json()
        self.assertGreaterEqual(history["summary"]["row_count"], 60)

    def test_demo_app_blocks_write_refresh_and_import_actions(self) -> None:
        runtime = self._prepared_runtime()
        self.addCleanup(self._cleanup_runtime, runtime)
        app = create_app(ROOT, runtime_root=runtime, demo_mode=True)
        client = app.test_client()

        for method, path in (
            ("post", "/demo/api/refresh"),
            ("post", "/api/database/DEMOA/history/refresh"),
            ("post", "/api/database/DEMOA/history/check"),
            ("post", "/api/database/dividends/refresh-all"),
            ("post", "/demo/api/uploads"),
            ("post", "/demo/api/import/extract"),
            ("patch", "/demo/api/transactions/tx_demo"),
            ("delete", "/demo/api/transactions/tx_demo"),
        ):
            with self.subTest(path=path):
                response = getattr(client, method)(path)
                self.assertEqual(response.status_code, 403)

    def test_serve_demo_check_command_rejects_bad_runtime_and_accepts_prepared_runtime(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bad_runtime = Path(tmp) / "demo_runtime"
            bad_runtime.mkdir()
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(run_cli(ROOT, ["serve-demo", "--runtime", str(bad_runtime), "--check"]), 2)
            self.assertIn(".demo_runtime", output.getvalue())

            runtime = Path(tmp) / "prepared" / "demo_runtime"
            prepare_demo_runtime(ROOT, runtime, reset=False)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(run_cli(ROOT, ["serve-demo", "--runtime", str(runtime), "--check"]), 0)
            self.assertIn("Demo Dashboard", output.getvalue())
            gc.collect()

    def _prepared_runtime(self) -> Path:
        root = Path(tempfile.mkdtemp())
        runtime = root / "demo_runtime"
        prepare_demo_runtime(ROOT, runtime, reset=False)
        return runtime

    def _cleanup_runtime(self, runtime: Path) -> None:
        gc.collect()
        shutil.rmtree(runtime.parent, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
