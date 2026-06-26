from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class DesktopShellConfig:
    """Framework-neutral configuration for a future desktop shell."""

    project_root: Path
    runtime_root: Path | None = None
    profile: str = "demo"
    demo_mode: bool = True
    window_title: str = "Local Stock Journal"


@dataclass(frozen=True)
class DesktopShellStatus:
    """Snapshot of shell lifecycle state."""

    is_running: bool
    base_url: str = ""
    url: str = ""
    last_error: str = ""
    main_window_opened: bool = False


class DesktopShell(Protocol):
    """Minimal shell contract shared by future desktop implementations."""

    @property
    def base_url(self) -> str:
        """Return the local app base URL after the shell starts."""

    @property
    def url(self) -> str:
        """Return the main app URL after the shell starts."""

    @property
    def status(self) -> DesktopShellStatus:
        """Return a read-only lifecycle status snapshot."""

    def start(self) -> "DesktopShell":
        """Start shell-owned resources such as the embedded server."""

    def stop(self) -> None:
        """Stop shell-owned resources and release background work."""

    def open_main_window(self) -> None:
        """Open or focus the main desktop window."""

    def show_error(self, message: str) -> None:
        """Show a user-readable shell error message."""


class NullDesktopShell:
    """Dependency-free shell placeholder for tests and future adapters."""

    def __init__(self, config: DesktopShellConfig, base_url: str = "http://127.0.0.1:0") -> None:
        self.config = config
        self._base_url = base_url.rstrip("/")
        self._is_running = False
        self._main_window_opened = False
        self._last_error = ""

    @property
    def base_url(self) -> str:
        return self._base_url if self._is_running else ""

    @property
    def url(self) -> str:
        return f"{self.base_url}/{self.config.profile}" if self.base_url else ""

    @property
    def status(self) -> DesktopShellStatus:
        return DesktopShellStatus(
            is_running=self._is_running,
            base_url=self.base_url,
            url=self.url,
            last_error=self._last_error,
            main_window_opened=self._main_window_opened,
        )

    def start(self) -> "NullDesktopShell":
        self._is_running = True
        self._last_error = ""
        return self

    def stop(self) -> None:
        self._is_running = False
        self._main_window_opened = False

    def open_main_window(self) -> None:
        if not self._is_running:
            raise RuntimeError("Desktop shell must be started before opening the main window.")
        self._main_window_opened = True

    def show_error(self, message: str) -> None:
        self._last_error = str(message)
