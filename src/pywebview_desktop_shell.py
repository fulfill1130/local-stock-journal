from __future__ import annotations

from importlib import import_module
from typing import Any

from desktop_server import DemoDesktopServer
from desktop_shell import DesktopShellConfig, DesktopShellStatus


class PyWebviewDesktopShell:
    """Demo-only pywebview shell adapter for the embedded desktop server."""

    def __init__(
        self,
        config: DesktopShellConfig,
        *,
        server: Any | None = None,
        webview_module: Any | None = None,
    ) -> None:
        if not config.demo_mode or config.profile != "demo":
            raise ValueError("PyWebviewDesktopShell is demo-only for now.")
        self.config = config
        self._server = server or DemoDesktopServer(config.project_root, config.runtime_root)
        self._webview_module = webview_module
        self._window: Any | None = None
        self._is_running = False
        self._main_window_opened = False
        self._last_error = ""

    @property
    def base_url(self) -> str:
        if not self._is_running:
            return ""
        try:
            return str(self._server.base_url)
        except RuntimeError:
            return ""

    @property
    def url(self) -> str:
        if not self._is_running:
            return ""
        try:
            return str(self._server.url)
        except RuntimeError:
            return ""

    @property
    def status(self) -> DesktopShellStatus:
        return DesktopShellStatus(
            is_running=self._is_running,
            base_url=self.base_url,
            url=self.url,
            last_error=self._last_error,
            main_window_opened=self._main_window_opened,
        )

    def start(self) -> "PyWebviewDesktopShell":
        if self._is_running:
            return self
        self._server.start()
        self._is_running = True
        self._last_error = ""
        return self

    def stop(self) -> None:
        try:
            self._server.stop()
        finally:
            self._is_running = False
            self._main_window_opened = False

    def open_main_window(self) -> None:
        self.start()
        webview = self._webview()
        window = webview.create_window(self.config.window_title, self.url)
        self._window = window
        self._attach_close_handler(window)
        self._main_window_opened = True
        try:
            webview.start()
        except Exception as exc:
            self.show_error(str(exc))
            raise
        finally:
            self.stop()

    def show_error(self, message: str) -> None:
        self._last_error = str(message)

    def _webview(self) -> Any:
        if self._webview_module is None:
            self._webview_module = import_module("webview")
        return self._webview_module

    def _attach_close_handler(self, window: Any) -> None:
        events = getattr(window, "events", None)
        if events is None:
            return
        for event_name in ("closed", "closing"):
            event = getattr(events, event_name, None)
            if event is None:
                continue
            if hasattr(event, "__iadd__"):
                event += self._handle_window_closed
                return
            if hasattr(event, "connect"):
                event.connect(self._handle_window_closed)
                return
            if hasattr(event, "append"):
                event.append(self._handle_window_closed)
                return

    def _handle_window_closed(self, *args: Any) -> None:
        self.stop()
