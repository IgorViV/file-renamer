"""Тесты P1-11: каталог, ротация и очистка логов."""

import io
import logging
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest import mock

from tests.support import load_renamer_module

module = load_renamer_module()


class LoggingTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self._reset_logging)
        self.logs = pathlib.Path(self._tmp.name)

    @staticmethod
    def _reset_logging():
        root = logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()


class DefaultDirectoryTests(unittest.TestCase):
    def test_env_override_has_priority(self):
        custom = pathlib.Path("/custom/logs")
        with mock.patch.dict(
            os.environ, {module.LOG_DIR_ENV: str(custom)}, clear=False
        ):
            self.assertEqual(module.default_logs_directory(), custom)

    def test_windows_uses_localappdata(self):
        result = module.default_logs_directory(
            environ={"LOCALAPPDATA": r"C:\Users\user\AppData\Local"},
            os_name="nt",
            home=pathlib.Path("/home/user"),
        )
        self.assertEqual(
            result,
            pathlib.Path(r"C:\Users\user\AppData\Local")
            / "file-renamer"
            / "logs",
        )

    def test_windows_falls_back_to_home(self):
        home = pathlib.Path("/home/user")
        result = module.default_logs_directory(
            environ={}, os_name="nt", home=home
        )
        self.assertEqual(
            result, home / "AppData" / "Local" / "file-renamer" / "logs"
        )

    def test_posix_uses_xdg_state_home(self):
        state = pathlib.Path("/state")
        result = module.default_logs_directory(
            environ={"XDG_STATE_HOME": str(state)},
            os_name="posix",
            home=pathlib.Path("/home/user"),
        )
        self.assertEqual(result, state / "file-renamer" / "logs")

    def test_posix_falls_back_to_home(self):
        home = pathlib.Path("/home/user")
        result = module.default_logs_directory(
            environ={}, os_name="posix", home=home
        )
        self.assertEqual(
            result, home / ".local" / "state" / "file-renamer" / "logs"
        )


class SetupLoggingTests(LoggingTestCase):
    def test_creates_rotating_file_handler(self):
        path = module.setup_logging(
            logs_directory=self.logs, max_bytes=1000, backup_count=2
        )

        self.assertIsNotNone(path)
        self.assertTrue(path.exists())
        self.assertEqual(path.parent, self.logs)

        rotating = [
            handler
            for handler in logging.getLogger().handlers
            if isinstance(handler, module.RotatingFileHandler)
        ]
        self.assertEqual(len(rotating), 1)
        self.assertEqual(rotating[0].encoding, "utf-8")
        self.assertEqual(rotating[0].maxBytes, 1000)
        self.assertEqual(rotating[0].backupCount, 2)

    def test_writes_to_file(self):
        path = module.setup_logging(logs_directory=self.logs)

        logging.getLogger("probe").info("hello-log")
        for handler in logging.getLogger().handlers:
            handler.flush()

        self.assertIn("hello-log", path.read_text(encoding="utf-8"))

    def test_reconfigures_root_handlers(self):
        first = module.setup_logging(logs_directory=self.logs / "one")
        logging.getLogger("probe").info("first-entry")
        for handler in logging.getLogger().handlers:
            handler.flush()

        second = module.setup_logging(logs_directory=self.logs / "two")
        logging.getLogger("probe").info("second-entry")
        for handler in logging.getLogger().handlers:
            handler.flush()

        self.assertIn("first-entry", first.read_text(encoding="utf-8"))
        self.assertNotIn("second-entry", first.read_text(encoding="utf-8"))
        self.assertIn("second-entry", second.read_text(encoding="utf-8"))

    def test_rotation_creates_backup(self):
        module.setup_logging(
            logs_directory=self.logs,
            max_bytes=200,
            backup_count=2,
            keep=5,
        )

        logger = logging.getLogger("rotate")
        for _ in range(20):
            logger.info("x" * 80)
        for handler in logging.getLogger().handlers:
            handler.flush()

        backups = list(self.logs.glob("renamer_*.log.*"))
        self.assertTrue(backups)

    def test_falls_back_to_console_when_directory_unavailable(self):
        stderr = io.StringIO()

        with mock.patch.object(
            module,
            "_prepare_logs_directory",
            side_effect=OSError("denied"),
        ), redirect_stderr(stderr):
            result = module.setup_logging(logs_directory=self.logs)

        self.assertIsNone(result)
        self.assertIn("журнал", stderr.getvalue().lower())


class PruneLogsTests(LoggingTestCase):
    def test_keeps_newest_logs_and_ignores_others(self):
        old = self.logs / "renamer_old.log"
        middle = self.logs / "renamer_middle.log"
        new = self.logs / "renamer_new.log"
        other = self.logs / "other.log"
        for path, mtime in (
            (old, 1000),
            (middle, 2000),
            (new, 3000),
            (other, 500),
        ):
            path.write_text("x", encoding="utf-8")
            os.utime(path, (mtime, mtime))

        module.prune_old_logs(self.logs, keep=2)

        self.assertFalse(old.exists())
        self.assertTrue(middle.exists())
        self.assertTrue(new.exists())
        self.assertTrue(other.exists())

    def test_backup_files_are_also_counted(self):
        first = self.logs / "renamer_first.log"
        backup = self.logs / "renamer_first.log.1"
        newest = self.logs / "renamer_new.log"
        for path, mtime in ((first, 1000), (backup, 2000), (newest, 3000)):
            path.write_text("x", encoding="utf-8")
            os.utime(path, (mtime, mtime))

        module.prune_old_logs(self.logs, keep=2)

        self.assertFalse(first.exists())
        self.assertTrue(backup.exists())
        self.assertTrue(newest.exists())


if __name__ == "__main__":
    unittest.main()
