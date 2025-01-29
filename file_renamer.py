import os
import sys
import time
import logging
import winshell
import re
from pathlib import Path, WindowsPath
from datetime import datetime, timedelta
from win32com.client import Dispatch
from typing import List, Tuple, Dict, Optional
from colorama import init, Fore, Back, Style
from utils import change_dir

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_SHORTCUT = '*.lnk'
DATE_FORMAT_INPUT = '%d.%m.%y'
DATE_FORMAT_OUTPUT = '%Y.%m.%d'
SEARCH_DIR = 'R:\\Departments\\САЦ\\SAC-DB'
# SEARCH_DIR = 'E:\\_Projects\\python\\file-renamer\\temp_dir'

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

class FileAccessChecker:
    """проверка прав доступа к файлам и каталогам"""

    @staticmethod
    def check_read_access(path: Path) -> bool:
        """проверяет права на чтение"""
        try:
            return os.access(path, os.R_OK)
        except Exception:
            return False

    @staticmethod
    def check_write_access(path: Path) -> bool:
        """проверяет права на запись"""
        try:
            return os.access(path, os.W_OK)
        except Exception:
            return False

    @staticmethod
    def check_execute_access(path: Path) -> bool:
        """проверяет права на выполнение"""
        try:
            return os.access(path, os.X_OK)
        except Exception:
            return False

    @staticmethod
    def check_full_access(path: Path) -> bool:
        """проверяет полные права доступа"""
        try:
            return os.access(path, os.R_OK | os.W_OK | os.X_OK)
        except Exception:
            return False

class WindowsPathHandler:
    """обработка путей Windows"""

    MAX_PATH_LENGTH = 260
    EXTENDED_PREFIX = r"\\?\\"

    @staticmethod
    def normalize_path(path: str | Path) -> str:
        """нормализует путь для Windows"""
        # преобразование Path в строку
        path_str = str(path)

        # замена прямых слешей на обратные
        normalized = path_str.replace('/', '\\')

        # удаляем множественные слеши
        normalized = re.sub(r'\\+', r'\\', normalized)

        # удаляем пробелы в конце
        normalized = normalized.rstrip()

        return normalized

    @staticmethod
    def get_extended_path(path: str | Path) -> str:
        """добавляет префикс для длинных путей Windows"""
        normalized_path = WindowsPathHandler.normalize_path(path)

        # если путь уже содержит префикс - возвращаем как есть
        if normalized_path.startswith(WindowsPathHandler.EXTENDED_PREFIX):
            return normalized_path

        # преобразуем в абсолютный путь
        abs_path = os.path.abspath(normalized_path)

        # добавляем префикс для длинных путей
        return f"{WindowsPathHandler.EXTENDED_PREFIX}{abs_path}"

    @staticmethod
    def is_path_too_long(path: str | Path) -> bool:
        """проверяет, превышает ли путь максимальную длину"""
        return len(str(path)) > WindowsPathHandler.MAX_PATH_LENGTH

    @staticmethod
    def validate_path(path: str | Path) -> tuple[bool, Optional[str]]:
        """проверяет валидность пути"""
        try:
            # проверяем на недопустимые символы
            invalid_chars = '<>"|?*'
            path_str = str(path)

            for char in invalid_chars:
                if char in path_str:
                    return False, f"Путь содержит недопустимый символ: {char}"

            # зарезервированные имена Windows
            reserved_names = {
                'CON', 'PRN', 'AUX', 'NUL',
                'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
                'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
            }

            parts = path_str.split('\\')
            for part in parts:
                base_name = part.split('.')[0].upper()
                if base_name in reserved_names:
                    return False, f"Путь содержит зарезервированное имя: {part}"

            return True, None

        except Exception as e:
            return False, str(e)

class SafePathOperation:
    """безопасное выполнения операций с путями"""

    def __init__(self):
        self.path_handler = WindowsPathHandler()
        self.logger = logging.getLogger(__name__)

    def safe_rename(self, old_path: Path, new_path: Path) -> bool:
        """безопасное переименование с учетом особенностей Windows"""
        try:
            # проверяем длину путей
            if self.path_handler.is_path_too_long(old_path):
                old_path_str = self.path_handler.get_extended_path(old_path)
            else:
                old_path_str = str(old_path)

            if self.path_handler.is_path_too_long(new_path):
                new_path_str = self.path_handler.get_extended_path(new_path)
            else:
                new_path_str = str(new_path)

            # проверяем валидность путей
            is_valid_old, error_old = self.path_handler.validate_path(old_path)
            if not is_valid_old:
                self.logger.error(f"Неверный исходный путь: {error_old}")
                return False

            is_valid_new, error_new = self.path_handler.validate_path(new_path)
            if not is_valid_new:
                self.logger.error(f"Неверный новый путь: {error_new}")
                return False

            # выполняем переименование
            os.rename(old_path_str, new_path_str)
            return True

        except Exception as e:
            self.logger.error(f"Ошибка при переименовании: {str(e)}")
            return False
class FileRenamer:
    def __init__(self, directory: str):
        self.directory = Path(directory.strip('"'))
        self.mask = MASK_FILTER_FILE
        self.mask_shortcut = MASK_FILTER_SHORTCUT
        self.date_f_input = DATE_FORMAT_INPUT
        self.date_f_output = DATE_FORMAT_OUTPUT
        self.logger = logging.getLogger(__name__)
        self.access_checker = FileAccessChecker()
        self.path_operator = SafePathOperation()

    def validate_directory(self) -> bool:
        """проверяет существование каталога и права доступа"""
        if not os.path.exists(self.directory):
            self.logger.error(f"Указанный вами каталог {self.directory} не существует")
            return False

        if not self.access_checker.check_read_access(self.directory):
            self.logger.error(f"Нет прав на чтение каталога {self.directory}")
            return False

        if not self.access_checker.check_write_access(self.directory):
            self.logger.error(f"Нет прав на запись в каталог {self.directory}")
            return False

        if not self.access_checker.check_execute_access(self.directory):
            self.logger.error(f"Нет прав на просмотр содержимого каталога {self.directory}")
            return False

        return True

    def get_files_list(self) -> List[Path]:
        """получает список файлов в каталоге"""
        list_files = []
        try:
            select_dir = self.directory
            for item in sorted(select_dir.rglob(self.mask), reverse=True):
                print(f"{'[папка]' if item.is_dir() else '->'} {item}")
                list_files.append(item)
            self.logger.info(f"Найдено файлов: {len(list_files)}")
            return list_files
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка файлов: {e}")
            return []

    def get_shortcut_list(self) -> List[Path]:
        """получает список ярлыков в каталоге"""
        list_shortcut = []
        try:
            select_dir = self.directory
            for item in sorted(select_dir.rglob(self.mask_shortcut), reverse=True):
                print(f"ярлык -> {item}")
                list_shortcut.append(item)
            self.logger.info(f"Найдено ярлыков: {len(list_shortcut)}")
            return list_shortcut
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка ярлыков: {e}")
            return []

    def rename_prefix(self, file: Path) -> bool:
        """переименовывает дату в префиксе имени файла"""
        old_name = file.name

        # проверка права доступа к файлу
        if not self.access_checker.check_read_access(file):
            self.logger.error(f"Нет прав на чтение файла {file}")
            return False

        if not self.access_checker.check_write_access(file):
            self.logger.error(f"Нет прав на запись файла {file}")
            return False

        try:
            dateobj = datetime.strptime(old_name[:8], self.date_f_input).date()
            date_string = dateobj.strftime(self.date_f_output)
            new_name = f"{date_string}{old_name[8:]}"
            new_path = file.with_name(new_name)

            # проверка права доступа к родительскому каталогу
            if not self.access_checker.check_write_access(file.parent):
                self.logger.error(f"Нет прав на запись в каталог {file.parent}")
                return False

            # проверка существования файла с новым именем
            if new_path.exists():
                self.logger.error(f"Файл с именем {new_name} уже существует")
                return False

            # os.rename(str(file), str(new_path))
            return self.path_operator.safe_rename(file, new_path)

        except Exception as e:
            self.logger.error(f"Ошибка переименования файла {old_name}: {e}")
            return False

    def rename_files(self) -> Tuple[int, int]:
        """переименовывает файлы"""
        success_count = 0
        failed_count = 0
        list_files = self.get_files_list()

        for file in list_files:
            try:
                if self.rename_prefix(file):
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                self.logger.error(f"Ошибка при переименовании {file}: {e}")

        self.logger.info(f"Успешно переименовано: {success_count}, ошибок {failed_count}")
        return success_count, failed_count

    def update_folder_dates(self, path: str) -> str:
        """заменяет старую дату на новую"""

        file_name_parts = path.split('\\')
        new_path = ''

        pattern = re.compile(r'^\d{2}\.\d{2}\.\d{2}')

        for name_part in file_name_parts:
            if pattern.match(name_part):
                dateobj = datetime.strptime(name_part[:8], self.date_f_input).date()
                date_string = dateobj.strftime(self.date_f_output)
                new_name_part = name_part.replace(name_part[:8], date_string)
                new_path = new_path + new_name_part + '\\'
            else:
                new_path = new_path + name_part + '\\'

        return os.path.dirname(new_path)
    def rename_target_shorcut(self, lnk_path: Path) -> bool:
        """переименовывает целевой путь ярлыка"""
        try:
            shortcut = winshell.shortcut(str(lnk_path))
            old_target = shortcut.path
            os.remove(str(lnk_path))
            # lnk_path.unlink(missing_ok=True)

            new_target = self.update_folder_dates(old_target)

            if not os.path.exists(os.path.dirname(new_target)):
                raise FileNotFoundError(f"Путь назначения не существует: {new_target}")

            # cоздаем ярлык для файла
            shell = Dispatch('WScript.Shell')
            shortcut = shell.CreateShortCut(str(lnk_path))
            shortcut.Targetpath = new_target
            shortcut.save()

            return True
        except Exception as e:
            self.logger.error(f"Ошибка переименования целевого пути ярлыка {str(lnk_path)}: {e}")
            return False

    def modify_shorcuts(self) -> Tuple[int, int]:
        """изменяет ярлыки"""
        success_count = 0
        failed_count = 0
        list_shortcuts = self.get_shortcut_list()
        for lnk in list_shortcuts:

            try:
                if self.rename_target_shorcut(lnk):
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                self.logger.error(f"Ошибка при модификации ярлыка {lnk}: {e}")

        self.logger.info(f"Успешно модифицировано ярлыков: {success_count}, ошибок {failed_count}")
        return success_count, failed_count

class DirRenamer:
    def __init__(self, cur_directory: str):
        self.mask_shortcut = MASK_FILTER_SHORTCUT
        self.cur_dir = Path(cur_directory.strip('"'))
        self.search_dir = Path(SEARCH_DIR)
        self.shell = Dispatch('WScript.Shell')
        self.logger = logging.getLogger(__name__)
        self.access_checker = FileAccessChecker()
        self.path_operator = SafePathOperation()

    def validate_directory(self) -> bool:
        """проверяет существование каталога и права доступа"""

        if not self.cur_dir.exists():
            self.logger.error(f"Указанный вами каталог {self.cur_dir} не существует")
            return False

        if not self.access_checker.check_full_access(self.cur_dir):
            self.logger.error(f"Недостаточно прав для работы с каталогом {self.cur_dir}")
            return False

        return True

    def validate_search_directory(self) -> bool:
        """проверяет существование каталога области поиска"""

        if not self.search_dir.exists():
            self.logger.error(f"Указанный вами каталог области поиска  {self.search_dir} не существует")
            return False
        return True

    def path_is_dir(self) -> bool:
        """проверяет что путь ведет к каталогу"""
        if self.cur_dir.is_dir():
            return True
        return False

    def get_current_path_dir(self) -> Path:
        """получает текущий путь изменяемого каталога"""
        return self.cur_dir

    def get_current_search_dir(self) -> Path:
        """получает текущий каталог области поиска"""
        return self.search_dir

    def modify_search_dir(self, new_dir: str):
        """изменяет каталог области поиска"""
        self.search_dir = Path(new_dir.strip('"'))

    def get_shortcut_target(self, shortcut_path: Path) -> Path | None:
        """получает целевой путь ярлыка"""
        try:
            shortcut = self.shell.CreateShortCut(str(shortcut_path))
            return Path(shortcut.Targetpath)
        except Exception as e:
            self.logger.error(f"Ошибка при получении целевого пути ярлыка: {e}")
            return None

    def find_shortcuts(self, path_before: Path, path_after: Path) -> list[Path]:
        """поиск ярлыков для целевого каталога в указанной директории"""

        shortcuts_found = []

        try:
            search_dir = self.search_dir
            print(f"Выполняется поиск ярлыков в ссылках которых есть путь {str(path_before)} ...")

            for item in sorted(search_dir.rglob(self.mask_shortcut), reverse=True):
                link_shortcut = self.get_shortcut_target(item)
                if link_shortcut and link_shortcut.is_relative_to(path_before):
                    # print(f"              ярлык -> {item}")
                    # print(f"Целевой путь ярлыка -> {self.get_shortcut_target(item)}")
                    shortcuts_found.append(item)

            self.logger.info(f"Найдено ярлыков: {len(shortcuts_found)}")
            return shortcuts_found
        except Exception as e:
            self.logger.error(f"Ошибка при получении списка ярлыков: {e}")
            return []

    def make_new_target(self, old_target: str, target_before: Path, target_after: Path) -> Path | None:
        """подготавливает новую ссылку ярлыка"""
        try:
            old_path = Path(old_target)
            relative = old_path.relative_to(target_before)
            return target_after / relative
        except Exception as e:
            self.logger.error(f"Ошибка при формировании новой ссылки ярлыка: {e}")
            return None
    def rename_target_shorcut(self, lnk_path: Path, target_before: Path, target_after: Path) -> bool:
        """переименовывает целевой путь ярлыка"""
        temp_link = None
        # проверка права доступа к ярлыку
        if not self.access_checker.check_full_access(lnk_path):
            self.logger.error(f"Недостаточно прав для работы с ярлыком {lnk_path}")
            return False

        # проверка права доступа к родительскому каталогу
        if not self.access_checker.check_write_access(lnk_path.parent):
            self.logger.error(f"Нет прав на запись в каталог {lnk_path.parent}")
            return False

        try:
            shortcut = winshell.shortcut(str(lnk_path))
            old_target = shortcut.path

            # временный файл для нового ярлыка
            temp_lnk = lnk_path.with_name(f"temp_{lnk_path.name}")

            new_target = self.make_new_target(old_target, target_before, target_after)
            if not new_target:
                return False

            if not new_target.exists():
                raise FileNotFoundError(f"Путь назначения не существует: {str(new_target)}")

            # новый ярлык во временном файле
            shell = Dispatch('WScript.Shell')
            new_shortcut = shell.CreateShortCut(
                # str(temp_lnk)
                self.path_operator.path_handler.get_extended_path(temp_lnk)
            )
            new_shortcut.Targetpath = str(new_target)
            new_shortcut.save()

            if temp_lnk.exists():
                return self.path_operator.safe_rename(temp_lnk, lnk_path)
            return False

            # удаляем старый ярлык и переименовываем временный
            # os.remove(str(lnk_path))
            # os.rename(str(temp_lnk), str(lnk_path))

        except Exception as e:
            if temp_lnk and temp_lnk.exists():
                try:
                    temp_lnk.unlink()
                except:
                    pass

            self.logger.error(f"Ошибка переименования целевого пути ярлыка {str(lnk_path)}: {e}")
            return False

    def modify_shorcuts(self, list_shortcuts: list[Path], target_before: Path, target_after: Path) -> Tuple[int, int]:
        """изменяет ярлыки"""
        success_count = 0
        failed_count = 0
        for lnk in list_shortcuts:
            try:
                if self.rename_target_shorcut(lnk, target_before, target_after):
                    success_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                self.logger.error(f"Ошибка при модификации ярлыка {lnk}: {e}")

        self.logger.info(f"Успешно модифицировано ярлыков: {success_count}, ошибок {failed_count}")
        return success_count, failed_count


def main_menu():
    """главное меню консольного приложения"""
    init()
    setup_logging()
    logger = logging.getLogger(__name__)
    shortcuts_list = []

    def seconds_to_time(seconds: float) -> str:
        """изменяет формат времени"""
        if int(seconds) <= 0:
            return f"{seconds} секунд"

        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    while True:
        clear_screen()
        print(f"{Fore.YELLOW}=== Утилита для переименования файлов ===")
        print("1. Переименование файлов (изменение префикса - даты)")
        print("2. Переименование ссылок (изменение префикса - даты) в ярлыках")
        print("3. Переименование ссылок в ярлыках при изменении каталога")
        print("4. Справка")
        print("5. Выход")
        print(Style.RESET_ALL)

        choice = input("\nВыберите действие (1-5): ")
        print(Style.RESET_ALL)

        if choice == '1':
            clear_screen()
            print(f"{Fore.GREEN}Переименование файлов (изменение префикса - даты)")
            print(Style.RESET_ALL)
            ask_path_dir = input("Введите путь к каталогу: ")

            renamer = FileRenamer(ask_path_dir)

            if not renamer.validate_directory():
                input("\nНажмите Enter для продолжения ...")
                continue

            if ask_path_dir.strip('"') == '.':
                print(f"В текущем каталоге выполняем поиск файлов с префиксом датой в формате ДД.ММ.ГГ) ...")
            else:
                print(f"В каталоге {ask_path_dir} выполняем поиск файлов с префиксом датой в формате ДД.ММ.ГГ) ...")

            renamer.rename_files()

            input("\nНажмите Enter для продолжения ...")

        elif choice == '2':
            clear_screen()
            print(f"{Fore.GREEN}Переименование ссылок (изменение префикса - даты) в ярлыках")
            print(Style.RESET_ALL)
            ask_dir_lnk = input('Введите путь к каталогу: ')

            renamer_lnk = FileRenamer(ask_dir_lnk)

            if not renamer_lnk.validate_directory():
                input("\nНажмите Enter для продолжения ...")
                continue

            if ask_dir_lnk.strip('"') == '.':
                print(f"В текущем каталоге выполняем поиск ярлыков ...")
            else:
                print(f"В каталоге {ask_dir_lnk} выполняем поиск ярлыков ...")

            renamer_lnk.modify_shorcuts()

            input("\nНажмите Enter для продолжения ...")

        elif choice == '3':
            clear_screen()
            print(f"{Fore.GREEN}Переименование ссылок в ярлыках при изменении каталога")
            print(Style.RESET_ALL)

            ask_current_path_dir = input("Введите текущий путь к изменяемому каталогу: ")

            dir_renamer = DirRenamer(ask_current_path_dir)

            if not dir_renamer.validate_directory():
                input("\nНажмите Enter для продолжения ...")
                continue

            while True:
                clear_screen()
                print(f"{Fore.GREEN}Переименование ссылок в ярлыках при изменении каталога")
                print(Style.RESET_ALL)

                print(f"Поиск ярлыков будет производится в {dir_renamer.get_current_search_dir()}")
                ask_modify_search_dir = input("Хотите изменить каталог области поиска - введите 1, продолжить без изменения - Enter: ")
                if ask_modify_search_dir == '1':
                    new_search_dir = input("Введите новый каталог области поиска: ")
                    dir_renamer.modify_search_dir(new_search_dir)
                else:
                    break

            if not dir_renamer.validate_search_directory():
                input("\nНажмите Enter для продолжения ...")
                continue

            while True:
                clear_screen()
                print(f"{Fore.GREEN}Переименование ссылок в ярлыках при изменении каталога")
                print(Style.RESET_ALL)

                print(f"Выполните требуемые изменения каталога {dir_renamer.get_current_path_dir()}, и ...\n")
                ask_new_path_dir = input("Введите новый путь к каталогу: ")
                new_path_dir = Path(ask_new_path_dir.strip('"'))
                if not new_path_dir.exists() and new_path_dir != dir_renamer.get_current_path_dir():
                    logger.error(f"Указанный вами новый каталог {new_path_dir} не существует, вы не сделали изменения")
                    input("\nНажмите Enter для продолжения ...")
                    continue
                else:
                    break

            if new_path_dir == dir_renamer.get_current_path_dir():
                logger.info(f"Указанный вами новый каталог {new_path_dir} без изменений")
                input("\nНажмите Enter для продолжения ...")
                continue

            print(f"Новый каталог {str(new_path_dir)}")

            # определить разницу между путями: какой элемент отличается или отсутствует
            diff_path = change_dir.find_diff_path(dir_renamer.get_current_path_dir(), new_path_dir)

            if not diff_path:
                print('Ошибка при сравнении путей каталогов!')
                input("\nНажмите Enter для продолжения ...")
                continue

            start_time = time.perf_counter()

            shortcuts_list = dir_renamer.find_shortcuts(diff_path['path_before'], diff_path['path_after'])

            search_time = time.perf_counter() - start_time
            print(f"Время поиска составило: {seconds_to_time(search_time)}")

            if not shortcuts_list:
                print("Ошибка при поиске ярлыков")
                input("\nНажмите Enter для продолжения ...")
                continue

            ask_renamed = input('Хотите переименовать ярлыки - введите 1, продолжить без изменения - Enter: ')
            if ask_renamed == '1':
                dir_renamer.modify_shorcuts(shortcuts_list, diff_path['path_before'], diff_path['path_after'])

            input("\nНажмите Enter для продолжения ...")

        elif choice == '4':
            clear_screen()
            print(f"{Fore.GREEN}О программе")
            print(Style.RESET_ALL)
            print(f"{Fore.YELLOW}=====================================")
            print("| Утилита для переименования файлов |")
            print("|           ver. 0.1.3              |")
            print("=====================================")
            print(Style.RESET_ALL)
            print(f"{Fore.GREEN}Это утилита позволяет:")
            print("\n1. Изменить формат записи даты в префиксе наименования файлов и ссылок в ярлыках:")
            print("- формат записи даты ДД.ММ.ГГ в имени каталога (файла, ссылки) будет изменен на ГГГГ.ММ.ДД.")
            print("2. Переименовать ссылки в ярлыках, ссылающихся на каталог при изменении его наименования (пути к нему).")
            print(Style.RESET_ALL)
            print("\nПорядок использования:")
            print("1. Изменение формата записи даты:")
            print("- сначала переименовываем файлы;")
            print("- затем переименовываем ссылки в ярлыках.")
            print("  * может возникнуть ошибка, если файл на который ярлык будет ссылаться еще не переименован.")
            print("\n2. Переименование ссылок в ярлыках при изменении каталога:")
            print("- сначала задаем текущий путь к изменяемому каталогу;")
            print("- вносим необходимые изменения пути к изменяемому каталогу;")
            print("- задаем новый (с изменениями) путь к каталогу;")
            print("- ждем, когда найдутся все существующие ярлыки завязанные на этот путь;")
            print("- переименовываем ссылки в найденных ярлыках.")
            input("\nНажмите Enter для продолжения ...")

        elif choice == '5':
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
