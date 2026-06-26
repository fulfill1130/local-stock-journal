from __future__ import annotations

import json
import gc
import shutil
import socket
import sys
import tempfile
import unittest
import warnings
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPTS = ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from cli import preflight_port_available  # noqa: E402
from prepare_demo_runtime import prepare_demo_runtime  # noqa: E402
from server import create_app  # noqa: E402


class RuntimeSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        warnings.filterwarnings("ignore", category=ResourceWarning)

    def test_runtime_info_reports_normal_runtime_without_private_state(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            project_root = Path(tmp)
            profile_dir = project_root / "data" / "profiles" / "son"
            profile_dir.mkdir(parents=True)
            (profile_dir / "state.json").write_text(
                json.dumps(
                    {
                        "profile": "son",
                        "transactions": [
                            {
                                "id": "tx_private",
                                "action": "BUY",
                                "ticker": "PRIVATE123",
                                "date": "2026-06-01",
                                "shares": 1,
                                "price": 1,
                                "note": "PRIVATE_TRANSACTION_NOTE",
                            }
                        ],
                        "holdings": [{"ticker": "PRIVATE123", "shares": 1}],
                        "lots": [],
                        "dividend_movements": [],
                        "watchlist": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            app = create_app(project_root)
            response = app.test_client().get("/api/runtime-info")

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertFalse(payload["demo_mode"])
            self.assertEqual(payload["app_mode"], "normal")
            self.assertEqual(Path(payload["project_root"]), project_root.resolve())
            self.assertEqual(Path(payload["data_root"]), (project_root / "data").resolve())
            self.assertEqual(sorted(payload["available_profiles"]), ["mom", "son"])

            serialized = json.dumps(payload, ensure_ascii=False)
            self.assertNotIn("PRIVATE123", serialized)
            self.assertNotIn("PRIVATE_TRANSACTION_NOTE", serialized)
            self.assertNotIn("transactions", serialized)
            self.assertNotIn("holdings", serialized)
            gc.collect()

    def test_runtime_info_reports_demo_runtime(self) -> None:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            runtime = Path(tmp) / "demo_runtime"
            prepare_demo_runtime(ROOT, runtime, reset=False)
            try:
                app = create_app(ROOT, runtime_root=runtime, demo_mode=True)
                response = app.test_client().get("/api/runtime-info")
            finally:
                gc.collect()
                shutil.rmtree(runtime.parent, ignore_errors=True)

            self.assertEqual(response.status_code, 200)
            payload = response.get_json()
            self.assertTrue(payload["demo_mode"])
            self.assertEqual(payload["app_mode"], "demo")
            self.assertEqual(Path(payload["runtime_root"]), runtime.resolve())
            self.assertEqual(payload["available_profiles"], ["demo"])

    def test_preflight_port_available_detects_occupied_port(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            sock.listen(1)
            port = sock.getsockname()[1]

            available, message = preflight_port_available("127.0.0.1", port)

        self.assertFalse(available)
        self.assertIn(str(port), message)


if __name__ == "__main__":
    unittest.main()
