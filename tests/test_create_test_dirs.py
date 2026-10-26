"""Тесты генератора тестовых данных create-test-dirs.py."""

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "create-test-dirs.py"
MODULE_NAME = "create_test_dirs_under_test"


def load_generator_module():
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]

    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль {MODULE_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


module = load_generator_module()


class GeneratorTests(unittest.TestCase):
    def test_import_does_not_create_test_directory(self):
        self.assertFalse((PROJECT_ROOT / module.DEFAULT_TEST_DIR).exists())

    def test_creates_dated_entries_without_shortcuts(self):
        with tempfile.TemporaryDirectory() as tmp:
            module.random.seed(7)
            module.create_mock_directories(
                tmp, max_depth=2, shortcut_factory=lambda target, link: None
            )

            entries = list(pathlib.Path(tmp).rglob("*"))

            self.assertTrue(entries)
            for entry in entries:
                self.assertRegex(entry.name, r"^\d{2}\.\d{2}\.\d{2} ")
            self.assertTrue(any(entry.is_file() for entry in entries))
            self.assertTrue(any(entry.is_dir() for entry in entries))
            self.assertFalse(any(entry.suffix == ".lnk" for entry in entries))

    def test_remove_mock_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            module.random.seed(1)
            module.create_mock_directories(
                tmp, max_depth=1, shortcut_factory=lambda target, link: None
            )
            module.remove_mock_directories(tmp)
            self.assertFalse(pathlib.Path(tmp).exists())

    def test_main_creates_entries_and_returns_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(module, "clear_screen"):
                created = module.main(
                    [
                        "--dir", tmp,
                        "--depth", "1",
                        "--seed", "42",
                        "--no-shortcuts",
                        "--yes",
                    ]
                )
            self.assertGreater(created, 0)
            self.assertTrue(any(pathlib.Path(tmp).iterdir()))

    def test_main_seed_is_reproducible(self):
        relative_names = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(module, "clear_screen"):
                    module.main(
                        [
                            "--dir", tmp,
                            "--depth", "2",
                            "--seed", "5",
                            "--no-shortcuts",
                            "--yes",
                        ]
                    )
                relative_names.append(
                    sorted(
                        str(item.relative_to(tmp))
                        for item in pathlib.Path(tmp).rglob("*")
                    )
                )

        self.assertEqual(relative_names[0], relative_names[1])


if __name__ == "__main__":
    unittest.main()
