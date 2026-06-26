from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from flask import Flask


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from desktop_server import DemoDesktopServer  # noqa: E402
from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import DemoRuntimeError  # noqa: E402


class DemoDesktopServerTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)
        self.temp_root = Path(tempfile.mkdtemp())
        self.runtime = self.temp_root / "demo_runtime"
        prepare_demo_runtime(ROOT, self.runtime, reset=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_server_starts_on_loopback_dynamic_port_and_serves_demo(self) -> None:
        server = DemoDesktopServer(ROOT, self.runtime)
        try:
            server.start()

            self.assertTrue(server.is_running)
            self.assertEqual(server.host, "127.0.0.1")
            self.assertGreater(server.port, 0)
            self.assertTrue(server.base_url.startswith("http://127.0.0.1:"))
            self.assertEqual(server.url, f"{server.base_url}/demo")

            response = urlopen(f"{server.base_url}/demo", timeout=5)
            self.assertEqual(response.status, 200)
        finally:
            server.stop()

    def test_demo_write_refresh_request_remains_blocked(self) -> None:
        server = DemoDesktopServer(ROOT, self.runtime)
        try:
            server.start()
            request = Request(f"{server.base_url}/demo/api/refresh", method="POST")

            with self.assertRaises(HTTPError) as ctx:
                urlopen(request, timeout=5)

            self.assertEqual(ctx.exception.code, 403)
        finally:
            server.stop()

    def test_stop_shuts_down_background_thread(self) -> None:
        server = DemoDesktopServer(ROOT, self.runtime)
        server.start()

        server.stop()

        self.assertFalse(server.is_running)
        with self.assertRaises(RuntimeError):
            _ = server.base_url

    def test_missing_demo_sentinel_is_rejected(self) -> None:
        bad_runtime = self.temp_root / "bad_runtime"
        bad_runtime.mkdir()

        with self.assertRaises(DemoRuntimeError):
            DemoDesktopServer(ROOT, bad_runtime).start()

    def test_harness_does_not_require_real_data_root(self) -> None:
        project_root = self.temp_root / "project"
        project_root.mkdir()
        app = Flask("desktop-test")

        @app.get("/demo")
        def demo_index():
            return "demo ok"

        with patch("desktop_server.create_app", return_value=app) as create_app_mock:
            server = DemoDesktopServer(project_root, self.runtime)
            try:
                server.start()
                response = urlopen(f"{server.base_url}/demo", timeout=5)
                self.assertEqual(response.status, 200)
            finally:
                server.stop()

        self.assertFalse((project_root / "data").exists())
        _, kwargs = create_app_mock.call_args
        self.assertEqual(kwargs["runtime_root"], self.runtime.resolve())
        self.assertTrue(kwargs["demo_mode"])
        self.assertFalse(kwargs["refresh_on_start"])


if __name__ == "__main__":
    unittest.main()
