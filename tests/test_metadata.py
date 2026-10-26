"""Проверки метаданных и точки входа."""

import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from tests.support import load_renamer_module

module = load_renamer_module()


class MetadataTests(unittest.TestCase):
    def test_version_has_semver_format(self):
        self.assertRegex(module.__version__, r"^\d+\.\d+\.\d+$")

    def test_help_shows_version(self):
        calls = iter(["3", "", "4"])
        output = io.StringIO()

        with mock.patch.object(module, "setup_logging"), \
                mock.patch.object(module, "clear_screen"), \
                mock.patch.object(module.time, "sleep"), \
                mock.patch("builtins.input", side_effect=lambda prompt: next(calls)), \
                redirect_stdout(output):
            module.main_menu()

        self.assertIn(f"ver. {module.__version__}", output.getvalue())


if __name__ == "__main__":
    unittest.main()
