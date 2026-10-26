import os
import time
import pathlib
import logging
import unittest
import random
import platform
import re
from datetime import datetime, timedelta
from typing import Callable, List, Optional, Tuple
from colorama import init, Fore, Style

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_SHORTCUT = '*.lnk'


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

def setup_logging():
    """настраивает логирование"""
    logs_directory = 'renamer_logs'
    os.makedirs(logs_directory, exist_ok=True)
    log_filename = f"{logs_directory}/renamer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )

class FileRenamer:
    def __init__(self, directory: str, shortcut_backend=None):
        self.directory = directory.strip('"')
        self.mask = MASK_FILTER_FILE
        self.mask_shortcut = MASK_FILTER_SHORTCUT
        self.logger = logging.getLogger(__name__)
        self._shortcut_backend = shortcut_backend

    def validate_directory(self) -> bool:
        """проверяет существование каталога"""
        if not os.path.exists(self.directory):
            self.logger.error(f"Указанный вами каталог {self.directory} не существует")
            return False
        return True

    def get_files_list(self) -> List[pathlib.Path]:
        """получает список файлов в каталоге"""
        list_files = []
        try:
            select_dir = pathlib.Path(self.directory)
            for item in sorted(select_dir.rglob(self.mask), reverse=True):
                print(f"{'[папка]' if item.is_dir() else '->'} {item}")
                list_files.append(item)
            self.logger.info(f"Найдено файлов: {len(list_files)}")
            return list_files
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка файлов: {e}")
            return []

    def get_shortcut_list(self) -> List[pathlib.Path]:
        """получает список ярлыков в каталоге"""
        list_shortcut = []
        try:
            select_dir = pathlib.Path(self.directory)
            for item in sorted(select_dir.rglob(self.mask_shortcut), reverse=True):
                print(f"ярлык -> {item}")
                list_shortcut.append(item)
            self.logger.info(f"Найдено ярлыков: {len(list_shortcut)}")
            return list_shortcut
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка ярлыков: {e}")
            return []

    def _target_path(self, file: pathlib.Path) -> pathlib.Path:
        """возвращает путь с датой в формате ГГГГ.ММ.ДД"""
        old_name = file.name
        try:
            dateobj = datetime.strptime(old_name[:8], '%d.%m.%y').date()
        except ValueError as e:
            raise ValueError(
                f"в имени '{old_name}' нет корректной даты ДД.ММ.ГГ"
            ) from e
        date_string = dateobj.strftime('%Y.%m.%d')
        return file.with_name(f"{date_string}{old_name[8:]}")

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
        self
    ) -> Tuple[List[Tuple[pathlib.Path, pathlib.Path]], List[Tuple[pathlib.Path, str]]]:
        """строит план переименования и список проблемных объектов"""
        plan = []
        errors = []
        for file in self.get_files_list():
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
        confirm: Optional[
            Callable[[List[Tuple[pathlib.Path, pathlib.Path]]], bool]
        ] = None
    ) -> Tuple[int, int]:
        """переименовывает файлы; dry_run только показывает план"""
        plan, errors = self.build_rename_plan()
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
        """заменяет старую дату на новую"""

        file_name_parts = path.split('\\')
        new_path = ''

        pattern = re.compile(r'^\d{2}\.\d{2}\.\d{2}')

        for name_part in file_name_parts:
            if pattern.match(name_part):
                dateobj = datetime.strptime(name_part[:8], '%d.%m.%y').date()
                date_string = dateobj.strftime('%Y.%m.%d')
                new_name_part = name_part.replace(name_part[:8], date_string)
                new_path = new_path + new_name_part + '\\'
            else:
                new_path = new_path + name_part + '\\'

        return os.path.dirname(new_path)

    def _get_shortcut_backend(self):
        """возвращает бэкенд ярлыков, создавая Windows-бэкенд при необходимости"""
        if self._shortcut_backend is None:
            if os.name != 'nt':
                raise RuntimeError("Обновление ярлыков поддерживается только в Windows")
            self._shortcut_backend = WindowsShortcutBackend()
        return self._shortcut_backend

    def rename_target_shorcut(self, lnk_path: pathlib.Path) -> bool:
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

    def modify_shorcuts(
        self,
        confirm: Optional[Callable[[List[pathlib.Path]], bool]] = None
    ) -> Tuple[int, int]:
        """изменяет ярлыки; confirm позволяет отменить операцию"""
        success_count = 0
        failed_count = 0
        list_shortcuts = self.get_shortcut_list()

        if not list_shortcuts:
            self.logger.info("Ярлыки не найдены")
            return 0, 0

        if confirm is not None and not confirm(list_shortcuts):
            self.logger.info("Обновление ярлыков отменено пользователем")
            return 0, 0

        for lnk in list_shortcuts:

            try:
                if self.rename_target_shorcut(lnk):
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                failed_count += 1
                self.logger.error(f"Ошибка при модификации ярлыка {lnk}: {e}")

        self.logger.info(f"Успешно модифицировано ярлыков: {success_count}, ошибок {failed_count}")
        return success_count, failed_count

class FileRenamerTests(unittest.TestCase):
    def setUp(self):
        """создает тестовые каталоги и файлы"""
        self.test_dir = 'test_directory'
        self.test_files = []

        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)

        def create_shortcut(target_path, shortcut_path):
            """создает ярлык файла
            Args:
                target_path: путь к целевому файлу
                shortcut_path: путь, где будет создан ярлык
            """
            if platform.system() == "Windows":
                from win32com.client import Dispatch

                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = target_path
                shortcut.save()

        def create_mock_directories(base_path: str, current_depth: int = 0, max_depth: int = 5):
            """рекурсивно создает структуру mock-каталогов / файлов"""
            if current_depth >= max_depth:
                return
            current_date = datetime.now() + timedelta(days=random.randint(0, 365))
            date_prefix = current_date.strftime("%d.%m.%y")

            # cоздаем каталог для ярлыков на текущем уровне
            shortcuts_dir = os.path.join(base_path, f"{date_prefix} shortcuts")
            os.makedirs(shortcuts_dir, exist_ok=True)

            # cоздаем от 1 до 3 подкаталогов на каждом уровне
            for index_dir in range(random.randint(1, 3)):
                dir_name = f"{date_prefix} folder-{index_dir}"
                dir_path = os.path.join(base_path, dir_name)
                os.makedirs(dir_path, exist_ok=True)

                for index_file in range(random.randint(1, 3)):
                    file_name = f"{date_prefix} file-{index_file}.txt"
                    file_path = os.path.join(dir_path,file_name)

                    with open(file_path, 'w') as f:
                        f.write(f"Этот {index_file} файл создан {datetime.now()}")

                    # cоздаем ярлык для файла
                    shortcut_name = f"{date_prefix} shortcut_to_file_{index_file}.lnk"
                    shortcut_path = os.path.join(shortcuts_dir, shortcut_name)
                    create_shortcut(file_path, shortcut_path)

                create_mock_directories(dir_path, current_depth + 1, max_depth)

        create_mock_directories(self.test_dir)

        for dir_path, dir_names, file_names in os.walk(self.test_dir):
            for cur_dir in dir_names:
                self.test_files.append(cur_dir)
            for file in file_names:
                self.test_files.append(file)

        self.renamer = FileRenamer(self.test_dir)

    def tearDown(self):
        """удаляет тестовый каталог"""
        try:
            for root, dirs, files in os.walk(self.test_dir, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            os.rmdir(self.test_dir)
        except FileNotFoundError:
            print("Каталог не существует")
        except PermissionError:
            print("Нет прав доступа")
        except Exception as e:
            print(f"Произошла ошибка удаления тестовой директории: {e}")

    def test_validate_directory(self):
        """тест проверки существования каталога"""
        self.assertTrue(self.renamer.validate_directory())

        invalid_renamer = FileRenamer('несуществующая_директория')
        self.assertFalse(invalid_renamer.validate_directory())

    def test_get_files_list(self):
        """тест получения списка файлов"""
        files = self.renamer.get_files_list()
        print(files)
        self.assertEqual(len(files), len(self.test_files))
        # for file in self.test_files:  TODO понять, что с WindowsPath
        #     self.assertIn(file, files)

    def test_rename_files(self):
        """тест переименования файлов"""
        success_count, failed_count = self.renamer.rename_files()
        self.assertEqual(success_count, len(self.test_files))
        self.assertEqual(failed_count, 0)

def ask_confirmation(prompt: str) -> bool:
    """запрашивает подтверждение операции (y/N)"""
    return input(prompt).strip().lower() in ('y', 'yes', 'д', 'да')


def main_menu():
    """главное меню консольного приложения"""
    init()
    setup_logging()
    logger = logging.getLogger(__name__)

    while True:
        clear_screen()
        print(f"{Fore.YELLOW}=== Утилита для переименования файлов ===")
        print("1. Переименование файлов")
        print("2. Переименование ссылок в ярлыках")
        print("3. Справка")
        print("4. Выход")
        print(Style.RESET_ALL)

        choice = input("\nВыберите действие (1-4): ")
        print(Style.RESET_ALL)

        if choice == '1':
            clear_screen()
            print(f"{Fore.GREEN}Переименование файлов")
            print(Style.RESET_ALL)
            ask_path_dir = input("Введите путь к каталогу: ")

            renamer = FileRenamer(ask_path_dir)

            if not renamer.validate_directory():
                continue

            if ask_path_dir.strip('"') == '.':
                print(f"В текущем каталоге выполняем поиск файлов с префиксом датой в формате ДД.ММ.ГГ) ...")
            else:
                print(f"В каталоге {ask_path_dir} выполняем поиск файлов с префиксом датой в формате ДД.ММ.ГГ) ...")

            dry_run = ask_confirmation("Только показать план без изменений (dry-run)? [y/N]: ")

            renamer.rename_files(
                dry_run=dry_run,
                confirm=lambda plan: ask_confirmation(
                    f"\nПереименовать {len(plan)} объект(ов)? [y/N]: "
                )
            )

            input("\nНажмите Enter для продолжения ...")

        elif choice == '2':
            clear_screen()
            print(f"{Fore.GREEN}Переименование ссылок в ярлыках")
            print(Style.RESET_ALL)
            ask_dir_lnk = input('Введите путь к каталогу: ')

            renamer_lnk = FileRenamer(ask_dir_lnk)

            if not renamer_lnk.validate_directory():
                continue

            if ask_dir_lnk.strip('"') == '.':
                print(f"В текущем каталоге выполняем поиск ярлыков ...")
            else:
                print(f"В каталоге {ask_dir_lnk} выполняем поиск ярлыков ...")

            renamer_lnk.modify_shorcuts(
                confirm=lambda shortcuts: ask_confirmation(
                    f"\nОбновить {len(shortcuts)} ярлык(ов)? [y/N]: "
                )
            )

            input("\nНажмите Enter для продолжения ...")

        elif choice == '3':
            clear_screen()
            print(f"{Fore.GREEN}О программе")
            print(Style.RESET_ALL)
            print(f"{Fore.YELLOW}=====================================")
            print("| Утилита для переименования файлов |")
            print("|           ver. 0.1.2              |")
            print("=====================================")
            print(Style.RESET_ALL)
            print("Это утилита для изменения формата записи даты в")
            print("префиксе наименования файлов и ссылок в ярлыках:")
            print("- формат записи даты ДД.ММ.ГГ в имени каталога")
            print("(файла, ссылки) будет изменен на ГГГГ.ММ.ДД.")
            print("\nПорядок использования:")
            print("- сначала переименовываем файлы;")
            print("- затем переименовываем ссылки в ярлыках.")
            print("- перед изменениями показывается план")
            print("  и запрашивается подтверждение.")
            print("* может возникнуть ошибка, если файл на который ярлык будет ссылаться еще не переименован.")

            input("\nНажмите Enter для продолжения ...")

        elif choice == '4':
            clear_screen()
            print(f"{Fore.YELLOW}Пока!")
            print(Style.RESET_ALL)
            time.sleep(0.75)
            break

        else:
            print("неверный выбор!")
            input("\nНажмите Enter для продолжения ...")

if __name__ == "__main__":
    main_menu()
