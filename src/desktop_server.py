from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import Any

from werkzeug.serving import BaseWSGIServer, make_server

from server import create_app, validate_demo_runtime


class DemoDesktopServer:
    """Demo-only embedded server for a future local desktop shell."""

    host = "127.0.0.1"

    def __init__(self, project_root: Path, runtime_root: Path | None = None) -> None:
        self.project_root = Path(project_root)
        self.runtime_root = Path(runtime_root) if runtime_root is not None else None
        self._server: BaseWSGIServer | None = None
        self._thread: Thread | None = None
        self._port: int | None = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("Desktop demo server has not started.")
        return self._port

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def url(self) -> str:
        return f"{self.base_url}/demo"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> "DemoDesktopServer":
        if self.is_running:
            return self
        demo_runtime = validate_demo_runtime(self.project_root, self.runtime_root)
        app = create_app(
            self.project_root,
            refresh_on_start=False,
            runtime_root=demo_runtime,
            demo_mode=True,
        )
        server = make_server(self.host, 0, app)
        port = int(server.socket.getsockname()[1])
        thread = Thread(target=server.serve_forever, name="demo-desktop-server", daemon=True)
        thread.start()
        self.runtime_root = demo_runtime
        self._server = server
        self._thread = thread
        self._port = port
        return self

    def stop(self, timeout: float = 5.0) -> None:
        server = self._server
        thread = self._thread
        if server is None:
            return
        server.shutdown()
        if thread is not None:
            thread.join(timeout=timeout)
        server.server_close()
        if thread is not None and thread.is_alive():
            raise RuntimeError("Desktop demo server thread did not stop cleanly.")
        self._server = None
        self._thread = None
        self._port = None

    def __enter__(self) -> "DemoDesktopServer":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.stop()
