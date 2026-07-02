from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from desktop_stock_machine import desktop_entry


class DesktopEntryTests(unittest.TestCase):
    def test_frontend_index_exists(self) -> None:
        index_path = desktop_entry.validate_frontend()

        self.assertEqual(index_path.name, "index.html")
        self.assertTrue(index_path.is_file())

    def test_check_mode_does_not_create_app_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app_data = Path(temp_dir) / "app_data"

            self.assertFalse(app_data.exists())
            self.assertEqual(desktop_entry.main(["--check"]), 0)
            self.assertFalse(app_data.exists())


if __name__ == "__main__":
    unittest.main()
