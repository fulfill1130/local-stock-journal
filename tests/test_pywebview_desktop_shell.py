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

from desktop_shell import DesktopShellConfig  # noqa: E402
from pywebview_desktop_shell import PyWebviewDesktopShell  # noqa: E402


class FakeEvent:
    def __init__(self) -> None:
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def trigger(self) -> None:
        for handler in list(self.handlers):
            handler()


class FakeEvents:
    def __init__(self) -> None:
        self.closed = FakeEvent()


class FakeWindow:
    def __init__(self, title: str, url: str) -> None:
        self.title = title
        self.url = url
        self.events = FakeEvents()


class FakeWebview:
    def __init__(self, *, raise_on_start: bool = False, close_on_start: bool = False) -> None:
        self.raise_on_start = raise_on_start
        self.close_on_start = close_on_start
        self.windows: list[FakeWindow] = []
        self.start_calls = 0

    def create_window(self, title: str, url: str) -> FakeWindow:
        window = FakeWindow(title, url)
        self.windows.append(window)
        return window

    def start(self) -> None:
        self.start_calls += 1
        if self.close_on_start and self.windows:
            self.windows[-1].events.closed.trigger()
        if self.raise_on_start:
            raise RuntimeError("webview failed")


class FakeDemoServer:
    host = "127.0.0.1"

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0
        self.is_running = False

    @property
    def base_url(self) -> str:
        if not self.is_running:
            raise RuntimeError("server is stopped")
        return "http://127.0.0.1:45678"

    @property
    def url(self) -> str:
        return f"{self.base_url}/demo"

    def start(self) -> "FakeDemoServer":
        if not self.is_running:
            self.start_calls += 1
            self.is_running = True
        return self

    def stop(self) -> None:
        if self.is_running:
            self.stop_calls += 1
            self.is_running = False


class PyWebviewDesktopShellTests(unittest.TestCase):
    def test_shell_can_be_constructed_without_importing_webview_when_injected(self) -> None:
        sys.modules.pop("webview", None)
        module = importlib.import_module("pywebview_desktop_shell")

        with tempfile.TemporaryDirectory() as tmp:
            shell = module.PyWebviewDesktopShell(
                DesktopShellConfig(project_root=Path(tmp)),
                server=FakeDemoServer(),
                webview_module=FakeWebview(),
            )

        self.assertIsInstance(shell, module.PyWebviewDesktopShell)
        self.assertNotIn("webview", sys.modules)

    def test_start_starts_demo_server_and_exposes_loopback_url(self) -> None:
        server = FakeDemoServer()
        shell = PyWebviewDesktopShell(_config(), server=server, webview_module=FakeWebview())

        shell.start()

        self.assertEqual(server.start_calls, 1)
        self.assertTrue(shell.status.is_running)
        self.assertEqual(shell.base_url, "http://127.0.0.1:45678")
        self.assertEqual(shell.url, "http://127.0.0.1:45678/demo")

    def test_open_main_window_passes_demo_url_and_starts_webview_loop(self) -> None:
        webview = FakeWebview()
        server = FakeDemoServer()
        shell = PyWebviewDesktopShell(_config(), server=server, webview_module=webview)

        shell.open_main_window()

        self.assertEqual(server.start_calls, 1)
        self.assertEqual(webview.start_calls, 1)
        self.assertEqual(len(webview.windows), 1)
        self.assertEqual(webview.windows[0].title, "Local Stock Journal")
        self.assertEqual(webview.windows[0].url, "http://127.0.0.1:45678/demo")
        self.assertEqual(server.stop_calls, 1)

    def test_closed_handler_stops_server_when_triggered(self) -> None:
        webview = FakeWebview(close_on_start=True)
        server = FakeDemoServer()
        shell = PyWebviewDesktopShell(_config(), server=server, webview_module=webview)

        shell.open_main_window()

        self.assertFalse(server.is_running)
        self.assertEqual(server.stop_calls, 1)

    def test_finally_cleanup_stops_server_if_webview_start_raises(self) -> None:
        webview = FakeWebview(raise_on_start=True)
        server = FakeDemoServer()
        shell = PyWebviewDesktopShell(_config(), server=server, webview_module=webview)

        with self.assertRaises(RuntimeError):
            shell.open_main_window()

        self.assertFalse(server.is_running)
        self.assertEqual(server.stop_calls, 1)
        self.assertEqual(shell.status.last_error, "webview failed")

    def test_stop_is_idempotent(self) -> None:
        server = FakeDemoServer()
        shell = PyWebviewDesktopShell(_config(), server=server, webview_module=FakeWebview())

        shell.start()
        shell.stop()
        shell.stop()

        self.assertFalse(shell.status.is_running)
        self.assertEqual(server.stop_calls, 1)

    def test_shell_does_not_require_real_data_root_with_injected_server(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            shell = PyWebviewDesktopShell(
                DesktopShellConfig(project_root=project_root),
                server=FakeDemoServer(),
                webview_module=FakeWebview(),
            )

            shell.start()
            shell.stop()

            self.assertFalse((project_root / "data").exists())

    def test_shell_rejects_non_demo_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                PyWebviewDesktopShell(
                    DesktopShellConfig(project_root=Path(tmp), demo_mode=False),
                    server=FakeDemoServer(),
                    webview_module=FakeWebview(),
                )


def _config() -> DesktopShellConfig:
    return DesktopShellConfig(project_root=ROOT)


if __name__ == "__main__":
    unittest.main()
