"""CLI-утилита для массового переименования дат в именах файлов, папок и ярлыков."""

import contextlib
import logging
import os
import pathlib
import re
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import datetime
from logging.handlers import RotatingFileHandler

from colorama import Fore, Style, init

__version__ = '0.3.0'

LOG_DIR_ENV = 'FILE_RENAMER_LOG_DIR'
LOG_FILE_PREFIX = 'renamer_'
LOG_FILE_SUFFIX = '.log'
LOG_FORMAT = '%(asctime)s %(levelname)s %(message)s'

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_SHORTCUT = '*.lnk'
DATE_PREFIX_PATTERN = re.compile(r'^(?P<date>\d{2}\.\d{2}\.\d{2})')
PATH_SEPARATOR_PATTERN = re.compile(r'([\\/]+)')


class WindowsShortcutBackend:
    """Обновляет ярлык на месте, сохраняя остальные его свойства.

    Используется ``WScript.Shell``: объект ярлыка читается из существующего
    файла, меняется только ``TargetPath``, после чего ярлык сохраняется.
    """

    def _shell(self):
        """лениво импортирует COM-объект (модуль должен импортироваться и без pywin32)"""
        try:
            from win32com.client import Dispatch
        except ImportError as exc:
            raise RuntimeError(
                "Для работы с ярлыками требуется pywin32 (Windows)"
            ) from exc
        return Dispatch('WScript.Shell')

    def read_target(self, lnk_path: pathlib.Path) -> str:
        """возвращает целевой путь ярлыка"""
        shortcut = self._shell().CreateShortCut(str(lnk_path))
        target = shortcut.Targetpath
        if not target:
            raise ValueError(f"У ярлыка не задан целевой путь: {lnk_path}")
        return str(target)

    def update_target(self, lnk_path: pathlib.Path, new_target: str) -> None:
        """меняет целевой путь ярлыка, не затрагивая его свойства"""
        shortcut = self._shell().CreateShortCut(str(lnk_path))
        shortcut.Targetpath = new_target
        shortcut.save()


def clear_screen():
    """очищает экран"""
    os.system('cls' if os.name == 'nt' else 'clear')

def default_logs_directory(
    environ: Mapping[str, str] | None = None,
    os_name: str | None = None,
    home: pathlib.Path | None = None,
) -> pathlib.Path:
    """возвращает каталог логов по умолчанию.

    Windows: ``%LOCALAPPDATA%\\file-renamer\\logs``.
    Остальные ОС: ``$XDG_STATE_HOME/file-renamer/logs`` или
    ``~/.local/state/file-renamer/logs``.
    Переопределяется переменной ``FILE_RENAMER_LOG_DIR``.
    """
    environ = os.environ if environ is None else environ
    os_name = os.name if os_name is None else os_name
    home_path = pathlib.Path.home() if home is None else pathlib.Path(home)

    override = environ.get(LOG_DIR_ENV)
    if override:
        return pathlib.Path(override).expanduser()

    if os_name == 'nt':
        local_appdata = environ.get('LOCALAPPDATA')
        base = (
            pathlib.Path(local_appdata)
            if local_appdata
            else home_path / 'AppData' / 'Local'
        )
        return base / 'file-renamer' / 'logs'

    state_home = environ.get('XDG_STATE_HOME')
    base = (
        pathlib.Path(state_home)
        if state_home
        else home_path / '.local' / 'state'
    )
    return base / 'file-renamer' / 'logs'


def _prepare_logs_directory(directory: pathlib.Path) -> pathlib.Path:
    """создает каталог логов, откатываясь на CWD и временный каталог"""
    candidates = [
        pathlib.Path(directory),
        pathlib.Path.cwd() / 'renamer_logs',
        pathlib.Path(tempfile.gettempdir()) / 'file-renamer-logs',
    ]
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except OSError:
            continue
    raise OSError("не удалось создать ни один каталог для логов")


def prune_old_logs(directory: pathlib.Path, keep: int = 10) -> None:
    """удаляет старые логи, оставляя ``keep`` самых новых файлов"""
    if keep < 1:
        return

    logs = []
    for path in pathlib.Path(directory).glob(
        f'{LOG_FILE_PREFIX}*{LOG_FILE_SUFFIX}*'
    ):
        try:
            if path.is_file():
                logs.append((path.stat().st_mtime, path))
        except OSError:
            continue

    logs.sort(key=lambda item: item[0], reverse=True)
    for _mtime, path in logs[keep:]:
        try:
            path.unlink()
        except OSError:
            continue


def setup_logging(
    logs_directory=None,
    max_bytes: int = 1_000_000,
    backup_count: int = 3,
    keep: int = 10,
) -> pathlib.Path | None:
    """настраивает логирование с ротацией, возвращает путь к файлу лога"""
    try:
        directory = _prepare_logs_directory(
            pathlib.Path(logs_directory)
            if logs_directory is not None
            else default_logs_directory()
        )
        prune_old_logs(directory, keep=keep)
        log_filename = directory / (
            f"{LOG_FILE_PREFIX}{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
            f"{LOG_FILE_SUFFIX}"
        )
        file_handler = RotatingFileHandler(
            log_filename,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
    except OSError as e:
        logging.basicConfig(
            level=logging.INFO,
            format=LOG_FORMAT,
            handlers=[logging.StreamHandler()],
            force=True,
        )
        logging.getLogger(__name__).warning(
            "Не удалось открыть файл журнала: %s", e
        )
        return None

    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        handlers=[file_handler, logging.StreamHandler()],
        force=True,
    )
    return log_filename

class FileRenamer:
    def __init__(self, directory: str, shortcut_backend=None):
        self.directory = str(directory).strip().strip('"').strip()
        self.mask = MASK_FILTER_FILE
        self.mask_shortcut = MASK_FILTER_SHORTCUT
        self.logger = logging.getLogger(__name__)
        self._shortcut_backend = shortcut_backend

    def validate_directory(self) -> bool:
        """проверяет, что путь задан и является существующим каталогом"""
        if not self.directory:
            self.logger.error("Каталог не указан")
            return False
        if not os.path.exists(self.directory):
            self.logger.error(f"Указанный вами каталог {self.directory} не существует")
            return False
        if not os.path.isdir(self.directory):
            self.logger.error(f"Указанный путь не является каталогом: {self.directory}")
            return False
        return True

    def _collect_matching(self) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
        """собирает файлы и каталоги, подходящие под маску"""
        files = []
        directories = []
        try:
            select_dir = pathlib.Path(self.directory)
            for item in select_dir.rglob(self.mask):
                if item.is_dir():
                    directories.append(item)
                elif item.is_file():
                    files.append(item)
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка объектов: {e}")
            return [], []
        return files, directories

    @staticmethod
    def _rename_order(item: pathlib.Path):
        """сначала более глубокие объекты, затем по пути"""
        return (-len(item.parts), str(item))

    def get_files_list(self) -> list[pathlib.Path]:
        """получает список файлов (без каталогов) в каталоге"""
        files, _ = self._collect_matching()
        files.sort(key=self._rename_order)
        self.logger.info(f"Найдено файлов: {len(files)}")
        return files

    def get_directories_list(self) -> list[pathlib.Path]:
        """получает список каталогов в каталоге"""
        _, directories = self._collect_matching()
        directories.sort(key=self._rename_order)
        self.logger.info(f"Найдено каталогов: {len(directories)}")
        return directories

    def get_rename_candidates(
        self, include_directories: bool = True
    ) -> list[pathlib.Path]:
        """возвращает файлы и, при необходимости, каталоги в порядке переименования"""
        files, directories = self._collect_matching()
        candidates = (files + directories) if include_directories else files
        candidates.sort(key=self._rename_order)
        self.logger.info(
            f"Найдено объектов для переименования: {len(candidates)} "
            f"(файлов {len(files)}, каталогов "
            f"{len(directories) if include_directories else 0})"
        )
        return candidates

    def get_shortcut_list(self) -> list[pathlib.Path]:
        """получает список ярлыков в каталоге"""
        list_shortcut = []
        try:
            select_dir = pathlib.Path(self.directory)
            for item in select_dir.rglob(self.mask_shortcut):
                if item.is_file():
                    list_shortcut.append(item)
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка ярлыков: {e}")
            return []
        list_shortcut.sort(key=self._rename_order)
        self.logger.info(f"Найдено ярлыков: {len(list_shortcut)}")
        return list_shortcut

    def _format_date(self, raw_date: str) -> str:
        """переводит ДД.ММ.ГГ в ГГГГ.ММ.ДД, проверяя календарь.

        Двузначный год: 69-99 -> 1969-1999, 00-68 -> 2000-2068.
        """
        return datetime.strptime(raw_date, '%d.%m.%y').strftime('%Y.%m.%d')

    def _target_path(self, file: pathlib.Path) -> pathlib.Path:
        """возвращает путь с датой в формате ГГГГ.ММ.ДД"""
        old_name = file.name
        match = DATE_PREFIX_PATTERN.match(old_name)
        if not match:
            raise ValueError(f"в имени '{old_name}' нет даты ДД.ММ.ГГ")
        raw_date = match.group('date')
        try:
            new_date = self._format_date(raw_date)
        except ValueError as e:
            raise ValueError(
                f"некорректная дата '{raw_date}' в имени '{old_name}'"
            ) from e
        return file.with_name(f"{new_date}{old_name[len(raw_date):]}")

    def _apply_rename(self, source: pathlib.Path, target: pathlib.Path) -> bool:
        """переименовывает объект, не перезаписывая существующую цель"""
        if source == target:
            self.logger.info(f"{source} уже имеет корректное имя")
            return True
        if target.exists():
            self.logger.error(f"Не переименован {source}: цель уже существует {target}")
            return False
        try:
            os.rename(source, target)
        except Exception as e:
            self.logger.error(f"Ошибка переименования файла {source}: {e}")
            return False
        if not target.exists() or source.exists():
            self.logger.error(
                f"Не удалось подтвердить переименование {source} -> {target}"
            )
            return False
        self.logger.info(f"{source} -> {target}")
        return True

    def rename_prefix(self, file: pathlib.Path) -> bool:
        """переименовывает дату в префиксе имени файла"""
        try:
            new_path = self._target_path(file)
        except ValueError as e:
            self.logger.error(f"Не переименован {file}: {e}")
            return False
        return self._apply_rename(file, new_path)

    def build_rename_plan(
        self, include_directories: bool = True
    ) -> tuple[list[tuple[pathlib.Path, pathlib.Path]], list[tuple[pathlib.Path, str]]]:
        """строит план переименования и список проблемных объектов"""
        plan = []
        errors = []
        for file in self.get_rename_candidates(
            include_directories=include_directories
        ):
            try:
                new_path = self._target_path(file)
            except ValueError as e:
                errors.append((file, str(e)))
                self.logger.error(f"Пропущен {file}: {e}")
                continue
            if new_path == file:
                continue
            if new_path.exists():
                reason = f"цель уже существует: {new_path}"
                errors.append((file, reason))
                self.logger.error(f"Пропущен {file}: {reason}")
                continue
            plan.append((file, new_path))
        return plan, errors

    def rename_files(
        self,
        dry_run: bool = False,
        confirm: Callable[[list[tuple[pathlib.Path, pathlib.Path]]], bool] | None = None,
        include_directories: bool = True
    ) -> tuple[int, int]:
        """переименовывает файлы и каталоги; dry_run только показывает план"""
        plan, errors = self.build_rename_plan(
            include_directories=include_directories
        )
        failed_count = len(errors)

        if plan:
            print("\nПланируемые изменения:")
            for source, target in plan:
                print(f"{source} -> {target}")

        if dry_run:
            self.logger.info(
                f"Предпросмотр (dry-run): будет переименовано {len(plan)}, "
                f"проблем {failed_count}"
            )
            return len(plan), failed_count

        if not plan:
            self.logger.info("Нет файлов для переименования")
            return 0, failed_count

        if confirm is not None and not confirm(plan):
            self.logger.info("Переименование отменено пользователем")
            return 0, failed_count

        success_count = 0
        for source, target in plan:
            if self._apply_rename(source, target):
                success_count += 1
            else:
                failed_count += 1

        self.logger.info(f"Успешно переименовано: {success_count}, ошибок {failed_count}")
        return success_count, failed_count

    def update_folder_dates(self, path: str) -> str:
        """заменяет дату ДД.ММ.ГГ на ГГГГ.ММ.ДД во всех компонентах пути.

        Разделители (``\\`` и ``/``) сохраняются, поэтому функция одинаково
        работает с локальными, сетевыми (UNC) и смешанными путями Windows.
        """
        converted = []
        for part in PATH_SEPARATOR_PATTERN.split(path):
            match = DATE_PREFIX_PATTERN.match(part)
            if not match:
                converted.append(part)
                continue
            raw_date = match.group('date')
            converted.append(
                f"{self._format_date(raw_date)}{part[len(raw_date):]}"
            )
        return ''.join(converted)

    def _get_shortcut_backend(self):
        """возвращает бэкенд ярлыков, создавая Windows-бэкенд при необходимости"""
        if self._shortcut_backend is None:
            if os.name != 'nt':
                raise RuntimeError("Обновление ярлыков поддерживается только в Windows")
            self._shortcut_backend = WindowsShortcutBackend()
        return self._shortcut_backend

    def rename_shortcut_target(self, lnk_path: pathlib.Path) -> bool:
        """переименовывает целевой путь ярлыка, не удаляя сам ярлык"""
        try:
            backend = self._get_shortcut_backend()
            old_target = backend.read_target(lnk_path)
            new_target = self.update_folder_dates(old_target)

            if new_target == old_target:
                self.logger.info(
                    f"Ярлык {lnk_path} уже указывает на {new_target}, "
                    "изменение не требуется"
                )
                return True

            if not os.path.exists(new_target):
                self.logger.error(f"Путь назначения не существует: {new_target}")
                return False

            backend.update_target(lnk_path, new_target)
            self.logger.info(f"{lnk_path}: {old_target} -> {new_target}")
            return True
        except Exception as e:
            self.logger.error(f"Ошибка переименования целевого пути ярлыка {lnk_path}: {e}")
            return False

    def modify_shortcuts(
        self,
        confirm: Callable[[list[pathlib.Path]], bool] | None = None
    ) -> tuple[int, int]:
        """изменяет ярлыки; confirm позволяет отменить операцию"""
        success_count = 0
        failed_count = 0
        list_shortcuts = self.get_shortcut_list()

        if not list_shortcuts:
            self.logger.info("Ярлыки не найдены")
            return 0, 0

        print("\nНайденные ярлыки:")
        for lnk in list_shortcuts:
            print(f"ярлык -> {lnk}")

        if confirm is not None and not confirm(list_shortcuts):
            self.logger.info("Обновление ярлыков отменено пользователем")
            return 0, 0

        for lnk in list_shortcuts:

            try:
                if self.rename_shortcut_target(lnk):
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1
                self.logger.error(f"Ошибка при модификации ярлыка {lnk}: {e}")

        self.logger.info(f"Успешно модифицировано ярлыков: {success_count}, ошибок {failed_count}")
        return success_count, failed_count

    # устаревшие имена оставлены для обратной совместимости
    rename_target_shorcut = rename_shortcut_target
    modify_shorcuts = modify_shortcuts


def prompt_input(prompt: str) -> str | None:
    """читает строку, переживая EOF и Ctrl+C"""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print("\nВвод прерван.")
        return None


def pause() -> None:
    """ждет Enter, не падая при EOF/Ctrl+C"""
    with contextlib.suppress(EOFError, KeyboardInterrupt):
        input("\nНажмите Enter для продолжения ...")


def ask_confirmation(prompt: str) -> bool:
    """запрашивает подтверждение операции (y/N)"""
    answer = prompt_input(prompt)
    return answer is not None and answer.lower() in ('y', 'yes', 'д', 'да')


def main_menu():
    """главное меню консольного приложения"""
    init()
    setup_logging()

    while True:
        clear_screen()
        print(f"{Fore.YELLOW}=== Утилита для переименования файлов ===")
        print("1. Переименование файлов и папок")
        print("2. Переименование ссылок в ярлыках")
        print("3. Справка")
        print("4. Выход")
        print(Style.RESET_ALL)

        choice = prompt_input("\nВыберите действие (1-4): ")
        print(Style.RESET_ALL)

        if choice is None:
            print(f"{Fore.YELLOW}Пока!")
            print(Style.RESET_ALL)
            break

        if choice == '1':
            clear_screen()
            print(f"{Fore.GREEN}Переименование файлов и папок")
            print(Style.RESET_ALL)
            ask_path_dir = prompt_input("Введите путь к каталогу: ")

            if not ask_path_dir:
                print("Путь не указан.")
                pause()
                continue

            renamer = FileRenamer(ask_path_dir)

            if not renamer.validate_directory():
                pause()
                continue

            if renamer.directory == '.':
                print("В текущем каталоге выполняем поиск файлов и папок "
                      "с префиксом-датой в формате ДД.ММ.ГГ ...")
            else:
                print(f"В каталоге {renamer.directory} выполняем поиск "
                      "файлов и папок с префиксом-датой в формате ДД.ММ.ГГ ...")

            dry_run = ask_confirmation(
                "Только показать план без изменений (dry-run)? [y/N]: "
            )

            renamer.rename_files(
                dry_run=dry_run,
                confirm=lambda plan: ask_confirmation(
                    f"\nПереименовать {len(plan)} объект(ов)? [y/N]: "
                )
            )

            pause()

        elif choice == '2':
            clear_screen()
            print(f"{Fore.GREEN}Переименование ссылок в ярлыках")
            print(Style.RESET_ALL)
            ask_dir_lnk = prompt_input('Введите путь к каталогу: ')

            if not ask_dir_lnk:
                print("Путь не указан.")
                pause()
                continue

            renamer_lnk = FileRenamer(ask_dir_lnk)

            if not renamer_lnk.validate_directory():
                pause()
                continue

            if renamer_lnk.directory == '.':
                print("В текущем каталоге выполняем поиск ярлыков ...")
            else:
                print(f"В каталоге {renamer_lnk.directory} выполняем поиск ярлыков ...")

            renamer_lnk.modify_shortcuts(
                confirm=lambda shortcuts: ask_confirmation(
                    f"\nОбновить {len(shortcuts)} ярлык(ов)? [y/N]: "
                )
            )

            pause()

        elif choice == '3':
            clear_screen()
            print(f"{Fore.GREEN}О программе")
            print(Style.RESET_ALL)
            print(f"{Fore.YELLOW}=====================================")
            print("| Утилита для переименования файлов |")
            print(f"|           ver. {__version__:<19}|")
            print("=====================================")
            print(Style.RESET_ALL)
            print("Это утилита для изменения формата записи даты в")
            print("префиксе наименования файлов, папок и ссылок в ярлыках:")
            print("- формат записи даты ДД.ММ.ГГ в имени каталога")
            print("(файла, ссылки) будет изменен на ГГГГ.ММ.ДД.")
            print("- двузначный год: 69-99 -> 1969-1999, 00-68 -> 2000-2068.")
            print("- файлы и папки переименовываются от самых глубоких;")
            print("  перед изменениями показывается план")
            print("  и запрашивается подтверждение.")
            print("\nПорядок использования:")
            print("- сначала переименовываем файлы и папки;")
            print("- затем переименовываем ссылки в ярлыках.")
            print("* может возникнуть ошибка, если файл на который ярлык будет ссылаться еще не переименован.")

            pause()

        elif choice == '4':
            clear_screen()
            print(f"{Fore.YELLOW}Пока!")
            print(Style.RESET_ALL)
            time.sleep(0.75)
            break

        else:
            print("неверный выбор!")
            pause()

if __name__ == "__main__":
    main_menu()
