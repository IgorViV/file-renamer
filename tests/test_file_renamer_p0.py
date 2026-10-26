"""P0-тесты: безопасность операций переименования и обновления ярлыков.

Тесты написаны до исправлений и на исходном коде должны падать.
Проверяются требования P0-1...P0-7:

* ярлык не удаляется до успешной проверки/записи;
* свойства ярлыка сохраняются (обновление на месте);
* проверяется существование самой цели, а не её родителя;
* переименование не перезаписывает существующий файл;
* есть dry-run и подтверждение;
* счётчики успехов/ошибок честные;
* изменения журналируются («было -> стало»).
"""

import pathlib
import tempfile
import unittest
from unittest import mock

from tests.support import load_renamer_module

module = load_renamer_module()
FileRenamer = module.FileRenamer

FILE_MASK_OK = "26.10.25 file.txt"
FILE_MASK_ALREADY_NEW = "2025.10.26 file.txt"
FILE_MASK_BAD_DATE = "39.19.99 bad-date.txt"


class FakeShortcutBackend:
    """Подмена Windows-бэкенда ярлыков: хранит свойства и пишет только цель."""

    def __init__(self, target, arguments="", working_directory="", icon_location="",
                 description="", hotkey="", window_style=1):
        self.target = target
        self.properties = {
            "arguments": arguments,
            "working_directory": working_directory,
            "icon_location": icon_location,
            "description": description,
            "hotkey": hotkey,
            "window_style": window_style,
        }
        self.updates = []
        self.error = None

    def read_target(self, lnk_path):
        return self.target

    def update_target(self, lnk_path, new_target):
        if self.error is not None:
            raise self.error
        self.updates.append((pathlib.Path(lnk_path), new_target))
        self.target = new_target


class TemporaryProjectTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = pathlib.Path(self._tmp.name)

    def add_file(self, name: str, content: str = "data") -> pathlib.Path:
        path = self.dir / name
        path.write_text(content, encoding="utf-8")
        return path


class RenamePrefixTests(TemporaryProjectTest):
    def test_renames_date_prefix(self):
        source = self.add_file(FILE_MASK_OK)
        renamer = FileRenamer(str(self.dir))

        self.assertTrue(renamer.rename_prefix(source))

        self.assertFalse(source.exists())
        self.assertTrue((self.dir / FILE_MASK_ALREADY_NEW).exists())

    def test_refuses_to_overwrite_existing_file(self):
        source = self.add_file(FILE_MASK_OK, content="source")
        target = self.add_file(FILE_MASK_ALREADY_NEW, content="target")
        renamer = FileRenamer(str(self.dir))

        self.assertFalse(renamer.rename_prefix(source))

        self.assertTrue(source.exists())
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertEqual(target.read_text(encoding="utf-8"), "target")

    def test_invalid_date_returns_false_without_raising(self):
        source = self.add_file(FILE_MASK_BAD_DATE)
        renamer = FileRenamer(str(self.dir))

        self.assertFalse(renamer.rename_prefix(source))
        self.assertTrue(source.exists())


class RenameFilesTests(TemporaryProjectTest):
    def test_dry_run_does_not_touch_files(self):
        source = self.add_file(FILE_MASK_OK)
        renamer = FileRenamer(str(self.dir))

        planned, failed = renamer.rename_files(dry_run=True)

        self.assertEqual((planned, failed), (1, 0))
        self.assertTrue(source.exists())
        self.assertFalse((self.dir / FILE_MASK_ALREADY_NEW).exists())

    def test_declined_confirmation_does_not_touch_files(self):
        source = self.add_file(FILE_MASK_OK)
        renamer = FileRenamer(str(self.dir))

        success, failed = renamer.rename_files(confirm=lambda plan: False)

        self.assertEqual((success, failed), (0, 0))
        self.assertTrue(source.exists())

    def test_accepted_confirmation_renames_files(self):
        self.add_file(FILE_MASK_OK)
        renamer = FileRenamer(str(self.dir))

        success, failed = renamer.rename_files(confirm=lambda plan: True)

        self.assertEqual((success, failed), (1, 0))
        self.assertTrue((self.dir / FILE_MASK_ALREADY_NEW).exists())

    def test_invalid_date_is_counted_as_failure(self):
        source = self.add_file(FILE_MASK_BAD_DATE)
        renamer = FileRenamer(str(self.dir))

        success, failed = renamer.rename_files()

        self.assertEqual((success, failed), (0, 1))
        self.assertTrue(source.exists())

    def test_collision_is_counted_as_failure_and_does_not_overwrite(self):
        source = self.add_file(FILE_MASK_OK, content="source")
        target = self.add_file(FILE_MASK_ALREADY_NEW, content="target")
        renamer = FileRenamer(str(self.dir))

        success, failed = renamer.rename_files()

        self.assertEqual((success, failed), (0, 1))
        self.assertEqual(source.read_text(encoding="utf-8"), "source")
        self.assertEqual(target.read_text(encoding="utf-8"), "target")

    def test_rename_is_logged_as_before_and_after(self):
        self.add_file(FILE_MASK_OK)
        renamer = FileRenamer(str(self.dir))

        with self.assertLogs(renamer.logger, level="INFO") as captured:
            renamer.rename_files()

        joined = "\n".join(captured.output)
        self.assertIn(FILE_MASK_OK, joined)
        self.assertIn(FILE_MASK_ALREADY_NEW, joined)


class FakeWScriptShortcut:
    """Подмена COM-объекта WScript.Shell.CreateShortCut."""

    def __init__(self, target):
        self.Targetpath = target
        self.Arguments = "--keep-me"
        self.WorkingDirectory = r"C:\26.10.25 folder"
        self.IconLocation = "shell32.dll,3"
        self.Description = "описание"
        self.Hotkey = "Ctrl+Alt+F"
        self.WindowStyle = 3
        self.saved = False

    def save(self):
        self.saved = True


class FakeWScriptShell:
    def __init__(self, shortcut):
        self.shortcut = shortcut
        self.progid = None
        self.created = []

    def CreateShortCut(self, path):
        self.created.append(str(path))
        return self.shortcut


class WindowsShortcutBackendTests(TemporaryProjectTest):
    OLD_TARGET = r"C:\26.10.25 folder\26.10.25 file.txt"
    NEW_TARGET = r"C:\2025.10.26 folder\2025.10.26 file.txt"

    def setUp(self):
        super().setUp()
        self.lnk = self.add_file("26.10.25 link.lnk", content="fake-lnk")

    def test_read_target_uses_wscript_shell(self):
        import win32com.client

        shortcut = FakeWScriptShortcut(self.OLD_TARGET)
        shell = FakeWScriptShell(shortcut)
        backend = module.WindowsShortcutBackend()

        with mock.patch.object(win32com.client, "Dispatch", return_value=shell) as dispatch:
            self.assertEqual(backend.read_target(self.lnk), self.OLD_TARGET)

        dispatch.assert_called_once_with("WScript.Shell")
        self.assertEqual(shell.created, [str(self.lnk)])

    def test_update_target_keeps_other_properties_and_saves(self):
        import win32com.client

        shortcut = FakeWScriptShortcut(self.OLD_TARGET)
        shell = FakeWScriptShell(shortcut)
        backend = module.WindowsShortcutBackend()

        with mock.patch.object(win32com.client, "Dispatch", return_value=shell):
            backend.update_target(self.lnk, self.NEW_TARGET)

        self.assertTrue(shortcut.saved)
        self.assertEqual(shortcut.Targetpath, self.NEW_TARGET)
        self.assertEqual(shortcut.Arguments, "--keep-me")
        self.assertEqual(shortcut.WorkingDirectory, r"C:\26.10.25 folder")
        self.assertEqual(shortcut.IconLocation, "shell32.dll,3")
        self.assertEqual(shortcut.Description, "описание")
        self.assertEqual(shortcut.Hotkey, "Ctrl+Alt+F")
        self.assertEqual(shortcut.WindowStyle, 3)


class ShortcutTests(TemporaryProjectTest):
    OLD_TARGET = r"C:\26.10.25 folder\26.10.25 file.txt"
    NEW_TARGET = r"C:\2025.10.26 folder\2025.10.26 file.txt"
    PARENT = r"C:\2025.10.26 folder"

    def setUp(self):
        super().setUp()
        self.lnk = self.add_file("26.10.25 link.lnk", content="fake-lnk")
        self.backend = FakeShortcutBackend(
            target=self.OLD_TARGET,
            arguments="--flag",
            working_directory=r"C:\26.10.25 folder",
            icon_location="shell32.dll,3",
            description="описание",
            hotkey="Ctrl+Alt+F",
            window_style=3,
        )
        self.renamer = FileRenamer(str(self.dir), shortcut_backend=self.backend)

    def _patch_target(self, new_target):
        return mock.patch.object(
            FileRenamer, "update_folder_dates", return_value=new_target
        )

    def test_updates_target_in_place_without_deleting_shortcut(self):
        with self._patch_target(self.NEW_TARGET), \
                mock.patch.object(module.os.path, "exists", return_value=True), \
                mock.patch.object(module.os, "remove") as remove:
            self.assertTrue(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertTrue(self.lnk.exists())
        self.assertEqual(self.backend.updates, [(self.lnk, self.NEW_TARGET)])
        self.assertEqual(self.backend.properties["arguments"], "--flag")
        self.assertEqual(self.backend.properties["working_directory"], r"C:\26.10.25 folder")
        self.assertEqual(self.backend.properties["icon_location"], "shell32.dll,3")
        self.assertEqual(self.backend.properties["description"], "описание")
        self.assertEqual(self.backend.properties["hotkey"], "Ctrl+Alt+F")
        self.assertEqual(self.backend.properties["window_style"], 3)

    def test_missing_target_leaves_shortcut_untouched(self):
        with self._patch_target(self.NEW_TARGET), \
                mock.patch.object(module.os.path, "exists", return_value=False), \
                mock.patch.object(module.os, "remove") as remove:
            self.assertFalse(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertTrue(self.lnk.exists())
        self.assertEqual(self.backend.updates, [])
        self.assertEqual(self.backend.target, self.OLD_TARGET)

    def test_checks_target_itself_and_not_its_parent(self):
        # Родительский каталог существует, самой цели нет: обновлять нельзя.
        def exists(path):
            return str(path) == self.PARENT

        with self._patch_target(self.NEW_TARGET), \
                mock.patch.object(module.os.path, "exists", side_effect=exists), \
                mock.patch.object(module.os, "remove") as remove:
            self.assertFalse(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertEqual(self.backend.updates, [])
        self.assertTrue(self.lnk.exists())

    def test_invalid_target_date_leaves_shortcut_untouched(self):
        with mock.patch.object(
                FileRenamer, "update_folder_dates", side_effect=ValueError("bad date")
        ), mock.patch.object(module.os, "remove") as remove:
            self.assertFalse(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertTrue(self.lnk.exists())
        self.assertEqual(self.backend.updates, [])

    def test_backend_error_leaves_shortcut_untouched(self):
        self.backend.error = RuntimeError("COM error")
        with self._patch_target(self.NEW_TARGET), \
                mock.patch.object(module.os.path, "exists", return_value=True), \
                mock.patch.object(module.os, "remove") as remove:
            self.assertFalse(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertTrue(self.lnk.exists())
        self.assertEqual(self.backend.updates, [])
        self.assertEqual(self.backend.target, self.OLD_TARGET)

    def test_unchanged_target_is_not_rewritten(self):
        with self._patch_target(self.OLD_TARGET), \
                mock.patch.object(module.os.path, "exists", return_value=True), \
                mock.patch.object(module.os, "remove") as remove:
            self.assertTrue(self.renamer.rename_shortcut_target(self.lnk))

        remove.assert_not_called()
        self.assertEqual(self.backend.updates, [])

    def test_modify_shortcuts_counts_success_and_failure(self):
        second = self.add_file("27.10.25 link.lnk", content="fake-lnk-2")
        self.backend.target = self.OLD_TARGET

        def read_target(lnk_path):
            if pathlib.Path(lnk_path) == second:
                raise ValueError("битый ярлык")
            return self.OLD_TARGET

        self.backend.read_target = read_target
        self.renamer.get_shortcut_list = lambda: [self.lnk, second]

        with self._patch_target(self.NEW_TARGET), \
                mock.patch.object(module.os.path, "exists", return_value=True):
            success, failed = self.renamer.modify_shortcuts()

        self.assertEqual((success, failed), (1, 1))
        self.assertEqual(len(self.backend.updates), 1)

    def test_legacy_method_names_are_aliases(self):
        self.assertIs(
            FileRenamer.rename_target_shorcut,
            FileRenamer.rename_shortcut_target,
        )
        self.assertIs(FileRenamer.modify_shorcuts, FileRenamer.modify_shortcuts)


if __name__ == "__main__":
    unittest.main()
