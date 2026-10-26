"""P1-тесты: корректность поиска, дат, путей и ввода.

Проверяются требования P1-1...P1-7, P1-9:

* файлы и каталоги разделены, обход идёт от самых глубоких;
* проверяется, что путь является каталогом;
* дата проверяется строго, включая календарь;
* update_folder_dates не зависит от ОС и поддерживает UNC/прямые слэши;
* подтверждение и ввод переживают EOF/Ctrl+C;
* результат переименования проверяется;
* повторный запуск ничего не меняет.
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from tests.support import load_renamer_module

module = load_renamer_module()
FileRenamer = module.FileRenamer

FILE_OLD = "26.10.25 file.txt"
FILE_NEW = "2025.10.26 file.txt"


class TemporaryProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)

    def add_file(self, name: str, content: str = "data") -> pathlib.Path:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def add_dir(self, name: str) -> pathlib.Path:
        path = self.dir / name
        path.mkdir(parents=True, exist_ok=True)
        return path


class ValidateDirectoryTests(TemporaryProjectTest):
    def test_accepts_existing_directory(self):
        self.assertTrue(FileRenamer(str(self.dir)).validate_directory())

    def test_rejects_file(self):
        file = self.add_file("file.txt")
        self.assertFalse(FileRenamer(str(file)).validate_directory())

    def test_rejects_empty_string(self):
        self.assertFalse(FileRenamer("").validate_directory())

    def test_rejects_missing_directory(self):
        self.assertFalse(FileRenamer(str(self.dir / "missing")).validate_directory())

    def test_normalizes_quotes_and_spaces(self):
        renamer = FileRenamer(f'  "{self.dir}"  ')
        self.assertEqual(renamer.directory, str(self.dir))
        self.assertTrue(renamer.validate_directory())


class SearchTests(TemporaryProjectTest):
    def setUp(self):
        super().setUp()
        self.parent = self.add_dir("26.10.25 folder")
        self.child = self.add_dir("26.10.25 folder/27.10.25 child")
        self.deep_file = self.add_file("26.10.25 folder/27.10.25 child/28.10.25 deep.txt")
        self.top_file = self.add_file("29.10.25 top.txt")
        self.new_format = self.add_file("2025.10.26 done.txt")
        self.no_date = self.add_file("readme.txt")
        self.shortcuts_dir = self.add_dir("30.10.25 shortcuts")
        self.shortcut = self.add_file("30.10.25 shortcuts/link.lnk")
        self.renamer = FileRenamer(str(self.dir))

    def test_files_list_contains_only_files(self):
        files = self.renamer.get_files_list()

        self.assertEqual(set(files), {self.deep_file, self.top_file})
        self.assertTrue(all(item.is_file() for item in files))

    def test_directories_list_contains_only_directories(self):
        directories = self.renamer.get_directories_list()

        self.assertEqual(
            set(directories), {self.parent, self.child, self.shortcuts_dir}
        )

    def test_candidates_are_ordered_by_depth(self):
        candidates = self.renamer.get_rename_candidates()

        self.assertEqual(
            set(candidates),
            {self.parent, self.child, self.deep_file, self.top_file, self.shortcuts_dir},
        )
        depths = [len(item.parts) for item in candidates]
        self.assertEqual(depths, sorted(depths, reverse=True))
        self.assertGreater(
            candidates.index(self.child), candidates.index(self.deep_file)
        )
        self.assertGreater(
            candidates.index(self.parent), candidates.index(self.child)
        )

    def test_candidates_can_exclude_directories(self):
        candidates = self.renamer.get_rename_candidates(include_directories=False)

        self.assertEqual(set(candidates), {self.deep_file, self.top_file})

    def test_candidates_order_is_deterministic(self):
        first = self.renamer.get_rename_candidates()
        second = self.renamer.get_rename_candidates()

        self.assertEqual(first, second)


class DateValidationTests(TemporaryProjectTest):
    def test_leap_day_is_valid(self):
        source = self.add_file("29.02.24 event.txt")
        renamer = FileRenamer(str(self.dir))

        self.assertTrue(renamer.rename_prefix(source))
        self.assertTrue((self.dir / "2024.02.29 event.txt").exists())

    def test_non_leap_day_is_reported(self):
        source = self.add_file("29.02.25 event.txt")
        renamer = FileRenamer(str(self.dir))

        with self.assertLogs(renamer.logger, level="ERROR") as captured:
            self.assertFalse(renamer.rename_prefix(source))

        self.assertIn("некорректная дата", "\n".join(captured.output))
        self.assertTrue(source.exists())

    def test_invalid_month_is_reported(self):
        source = self.add_file("31.04.25 event.txt")
        renamer = FileRenamer(str(self.dir))

        self.assertFalse(renamer.rename_prefix(source))
        self.assertTrue(source.exists())

    def test_out_of_range_date_is_reported(self):
        source = self.add_file("39.19.99 event.txt")
        renamer = FileRenamer(str(self.dir))

        self.assertFalse(renamer.rename_prefix(source))
        self.assertTrue(source.exists())

    def test_date_without_space_is_ignored(self):
        self.add_file("26.10.25file.txt")
        renamer = FileRenamer(str(self.dir))

        self.assertEqual(renamer.get_files_list(), [])

    def test_two_digit_year_window(self):
        source = self.add_file("01.01.69 event.txt")
        renamer = FileRenamer(str(self.dir))

        self.assertTrue(renamer.rename_prefix(source))
        self.assertTrue((self.dir / "1969.01.01 event.txt").exists())


class UpdateFolderDatesTests(TemporaryProjectTest):
    def setUp(self):
        super().setUp()
        self.renamer = FileRenamer(str(self.dir))

    def test_windows_file_path(self):
        self.assertEqual(
            self.renamer.update_folder_dates(
                r"C:\26.10.25 folder\26.10.25 file.txt"
            ),
            r"C:\2025.10.26 folder\2025.10.26 file.txt",
        )

    def test_unc_path(self):
        self.assertEqual(
            self.renamer.update_folder_dates(
                r"\\server\share\26.10.25 folder\file.txt"
            ),
            r"\\server\share\2025.10.26 folder\file.txt",
        )

    def test_forward_slashes(self):
        self.assertEqual(
            self.renamer.update_folder_dates("C:/26.10.25 folder/file.txt"),
            "C:/2025.10.26 folder/file.txt",
        )

    def test_trailing_separator_is_preserved(self):
        self.assertEqual(
            self.renamer.update_folder_dates("C:\\26.10.25 folder\\"),
            "C:\\2025.10.26 folder\\",
        )

    def test_path_without_date_is_unchanged(self):
        path = r"C:\folder\file.txt"
        self.assertEqual(self.renamer.update_folder_dates(path), path)

    def test_only_date_prefix_is_replaced(self):
        self.assertEqual(
            self.renamer.update_folder_dates(
                r"C:\26.10.25 folder\26.10.25 26.10.25.txt"
            ),
            r"C:\2025.10.26 folder\2025.10.26 26.10.25.txt",
        )

    def test_invalid_date_raises(self):
        with self.assertRaises(ValueError):
            self.renamer.update_folder_dates(r"C:\31.04.25 folder\file.txt")


class FakeBackend:
    def __init__(self, target):
        self.target = target
        self.updates = []

    def read_target(self, lnk_path):
        return self.target

    def update_target(self, lnk_path, new_target):
        self.updates.append(new_target)
        self.target = new_target


class ShortcutTargetIntegrationTests(TemporaryProjectTest):
    def test_shortcut_target_is_converted_with_windows_path(self):
        lnk = self.add_file("26.10.25 link.lnk", content="fake")
        backend = FakeBackend(r"C:\26.10.25 folder\26.10.25 file.txt")
        renamer = FileRenamer(str(self.dir), shortcut_backend=backend)

        with mock.patch.object(module.os.path, "exists", return_value=True):
            self.assertTrue(renamer.rename_target_shorcut(lnk))

        self.assertEqual(
            backend.target,
            r"C:\2025.10.26 folder\2025.10.26 file.txt",
        )


class RenameResultTests(TemporaryProjectTest):
    def test_rename_without_effect_is_failure(self):
        source = self.add_file(FILE_OLD)
        renamer = FileRenamer(str(self.dir))

        with mock.patch.object(module.os, "rename") as rename:
            with self.assertLogs(renamer.logger, level="ERROR") as captured:
                self.assertFalse(renamer.rename_prefix(source))

        rename.assert_called_once()
        self.assertTrue(source.exists())
        self.assertFalse((self.dir / FILE_NEW).exists())
        self.assertIn("подтвердить", "\n".join(captured.output))


class RenameScopeTests(TemporaryProjectTest):
    def setUp(self):
        super().setUp()
        self.folder = self.add_dir("26.10.25 folder")
        self.file = self.add_file("26.10.25 folder/27.10.25 inner.txt")
        self.renamer = FileRenamer(str(self.dir))

    def test_files_only_scope(self):
        success, failed = self.renamer.rename_files(include_directories=False)

        self.assertEqual((success, failed), (1, 0))
        self.assertTrue(self.folder.exists())
        self.assertTrue((self.folder / "2025.10.27 inner.txt").exists())

    def test_directories_are_renamed_after_children(self):
        success, failed = self.renamer.rename_files()

        self.assertEqual((success, failed), (2, 0))
        new_folder = self.dir / "2025.10.26 folder"
        self.assertTrue(new_folder.exists())
        self.assertTrue((new_folder / "2025.10.27 inner.txt").exists())


class IdempotencyTests(TemporaryProjectTest):
    def test_second_run_changes_nothing(self):
        self.add_file(FILE_OLD)
        renamer = FileRenamer(str(self.dir))

        self.assertEqual(renamer.rename_files(), (1, 0))
        self.assertEqual(renamer.rename_files(), (0, 0))
        self.assertTrue((self.dir / FILE_NEW).exists())


class InputTests(unittest.TestCase):
    def test_confirmation_accepts_yes(self):
        with mock.patch("builtins.input", return_value=" Y "):
            self.assertTrue(module.ask_confirmation("?"))
        with mock.patch("builtins.input", return_value="да"):
            self.assertTrue(module.ask_confirmation("?"))

    def test_confirmation_rejects_empty_and_no(self):
        for answer in ("", "n", "нет"):
            with mock.patch("builtins.input", return_value=answer):
                self.assertFalse(module.ask_confirmation("?"))

    def test_confirmation_survives_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertFalse(module.ask_confirmation("?"))

    def test_confirmation_survives_keyboard_interrupt(self):
        with mock.patch("builtins.input", side_effect=KeyboardInterrupt):
            self.assertFalse(module.ask_confirmation("?"))

    def test_prompt_input_strips_value(self):
        with mock.patch("builtins.input", return_value="  C:\\dir  "):
            self.assertEqual(module.prompt_input("?"), r"C:\dir")

    def test_prompt_input_returns_none_on_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(module.prompt_input("?"))


class MainMenuTests(TemporaryProjectTest):
    def _run_menu(self, inputs):
        calls = iter(inputs)
        with mock.patch.object(module, "setup_logging"), \
                mock.patch.object(module, "clear_screen"), \
                mock.patch.object(module.time, "sleep"), \
                mock.patch("builtins.input", side_effect=lambda prompt: next(calls)):
            module.main_menu()

    def test_menu_renames_files_after_confirmation(self):
        self.add_file(FILE_OLD)
        self._run_menu(["1", str(self.dir), "n", "y", "", "4"])

        self.assertTrue((self.dir / FILE_NEW).exists())

    def test_menu_declined_confirmation_changes_nothing(self):
        source = self.add_file(FILE_OLD)
        self._run_menu(["1", str(self.dir), "n", "n", "", "4"])

        self.assertTrue(source.exists())
        self.assertFalse((self.dir / FILE_NEW).exists())

    def test_menu_exits_on_eof(self):
        with mock.patch.object(module, "setup_logging"), \
                mock.patch.object(module, "clear_screen"), \
                mock.patch("builtins.input", side_effect=EOFError):
            module.main_menu()


if __name__ == "__main__":
    unittest.main()
