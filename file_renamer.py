import os
import time
import pathlib
import logging
import winshell
import re
from datetime import datetime, timedelta
from win32com.client import Dispatch
from typing import List, Tuple
from colorama import init, Fore, Back, Style

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_SHORTCUT = '*.lnk'
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
    def __init__(self, directory: str):
        self.directory = directory.strip('"')
        self.mask = MASK_FILTER_FILE
        self.mask_shortcut = MASK_FILTER_SHORTCUT
        self.logger = logging.getLogger(__name__)

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

    def rename_prefix(self, file: pathlib.Path) -> bool:
        """переименовывает дату в префиксе имени файла"""
        old_name = file.name
        dateobj = datetime.strptime(old_name[:8], '%d.%m.%y').date()
        date_string = dateobj.strftime('%Y.%m.%d')
        new_name = f"{date_string}{old_name[8:]}"
        try:
            os.rename(f'{file}', file.with_name(new_name))
            # print(f'{old_name} переименован --> {new_name}')
            return True
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
                dateobj = datetime.strptime(name_part[:8], '%d.%m.%y').date()
                date_string = dateobj.strftime('%Y.%m.%d')
                new_name_part = name_part.replace(name_part[:8], date_string)
                new_path = new_path + new_name_part + '\\'
            else:
                new_path = new_path + name_part + '\\'

        return os.path.dirname(new_path)
    def rename_target_shorcut(self, lnk_path: pathlib.Path) -> bool:
        """переименовывает целевой путь ярлыка"""
        try:
            shortcut = winshell.shortcut(str(lnk_path))
            old_target = shortcut.path
            os.remove(str(lnk_path))

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
        self.cur_dir = cur_directory.strip('"')
        self.logger = logging.getLogger(__name__)
    def validate_directory(self) -> bool:
        """проверяет существование каталога"""
        if not os.path.exists(self.cur_dir):
            self.logger.error(f"Указанный вами каталог {self.cur_dir} не существует")
            return False
        return True

def main_menu():
    """главное меню консольного приложения"""
    init()
    setup_logging()
    logger = logging.getLogger(__name__)

    while True:
        clear_screen()
        print(f"{Fore.YELLOW}=== Утилита для переименования файлов ===")
        print("1. Переименование файлов (изменение префикса - даты)")
        print("2. Переименование ссылок (изменение префикса - даты) в ярлыках")
        print("3. Переименование каталога")
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
                continue

            if ask_dir_lnk.strip('"') == '.':
                print(f"В текущем каталоге выполняем поиск ярлыков ...")
            else:
                print(f"В каталоге {ask_dir_lnk} выполняем поиск ярлыков ...")

            renamer_lnk.modify_shorcuts()

            input("\nНажмите Enter для продолжения ...")

        elif choice == '3':
            clear_screen()
            print(f"{Fore.GREEN}Переименование каталога")
            print(Style.RESET_ALL)

            ask_current_path_dir = input("Введите текущий путь к изменяемому каталогу: ")

            dir_renamer = DirRenamer(ask_current_path_dir)

            if not dir_renamer.validate_directory():
                continue

            ask_new_path_dir = input("Введите новый путь к каталогу: ")
            # определить разницу между путями: какой элемент отличается или отсутсвует

            input("\nНажмите Enter для продолжения ...")

        elif choice == '4':
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
            print("* может возникнуть ошибка, если файл на который ярлык будет ссылаться еще не переименован.")

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
