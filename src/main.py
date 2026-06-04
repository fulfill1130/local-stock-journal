from __future__ import annotations

import sys
from pathlib import Path

from cli import run_cli


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    return run_cli(project_root)


if __name__ == "__main__":
    raise SystemExit(main())
