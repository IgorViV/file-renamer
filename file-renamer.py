import os
import time
import pathlib
import logging
from datetime import datetime
from typing import List, Tuple
import winshell

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_SHORTCUT = '*.lnk'
TITLE_CLI = """=====================================
| Утилита для переименования файлов |
|           ver. 0.1.1              |
=====================================
Утилита для изменения формата записи
даты в префиксе наименования файлов
и ссылок в ярлыках
"""
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
            print(f'{old_name} переименован --> {new_name}')
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

    def rename_target_shorcut(self, lnk_path: pathlib.Path) -> bool:
        """переименовывает целевой путь ярлыка"""
        try:
            shortcut = winshell.shortcut(str(lnk_path))
            old_target = shortcut.path

            if not old_target == self.mask:
                return False

            dateobj = datetime.strptime(old_target[:8], '%d.%m.%y').date()
            date_string = dateobj.strftime('%Y.%m.%d')
            new_target = f"{date_string}{old_target[8:]}"

            if not os.path.exists(os.path.dirname(new_target)):
                raise FileNotFoundError(f"Путь назначения не существует: {new_target}")

            shortcut.path = new_target
            shortcut.write()
            return True
        except Exception as e:
            self.logger.error(f"Ошибка переименования целевой путь ярлыка {str(lnk_path)}: {e}")
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

# ===========================================================================
def get_list_dirs_files(name_dir: str, mask: str = '*') -> list:
    """
    получает список каталогов/файлов
    с учетом вложенных и отдельно ярлыков
    """
    list_files = []
    list_labels = []
    if not os.path.isdir(name_dir.strip('"')):
        raise Exception('Указанный вами каталог не существует!')
    select_dir = pathlib.Path(name_dir.strip('"'))
    for item in sorted(select_dir.rglob(mask), reverse=True):
        if str(item)[-4:] != '.lnk':
            print(f"{'[папка]' if item.is_dir() else '->'} {item}")
            list_files.append(item)
        else:
            print(f"Ярлык -> {item}")
            list_labels.append(item)
    return [list_files, list_labels]

def set_ending(quantity: int, word: str, first_change_word: str, second_change_word: str) -> str:
    """
    устанавливает необходимое окончание слова,
    например: 11 файлов, 1 файл, 3 файла
    """
    if quantity in (11, 12, 13, 14):
        return word
    elif quantity % 10 == 1:
        return first_change_word
    elif quantity % 10 in (2, 3, 4):
        return second_change_word
    else:
        return word

def rename_prefix(file: pathlib.Path):
    """переименовывает дату в префиксе имени файла"""
    name_file = file.name
    date_in_name = name_file[:8]
    dateobj = datetime.strptime(date_in_name, '%d.%m.%y').date()
    date_string = dateobj.strftime('%Y.%m.%d')
    try:
        os.rename(f'{file}', file.with_name(f'{date_string}{name_file[8:]}'))
    except Exception as e:
        print(e)
        logging.exception(e)
    else:
        print(f'{file} переименован --> {date_string}{name_file[8:]}')

def rename_files(list_files: list):
    """переименовывает файлы"""
    for file in list_files:
        rename_prefix(file)

def rename_label_files(list_label_files: list):
    """переименовывает ярлыки файлов"""
    print(list_label_files)
    for label in list_label_files:
        try:
            # shortcut = winshell.shortcut(str(label))
            # print('Ссылка ярлыка:', shortcut.path)
            print('Temp print')
        except Exception as e:
            print(e)
            logging.exception(e)

def main_menu():
    """главное меню консольного приложения"""
    setup_logging()
    logger = logging.getLogger(__name__)

    print(TITLE_CLI)

    while True:
        ask = input('\nВыберите действие (1-3):\n1. Переименование файлов\n2. Переименование ссылок в ярлыках\n3. Выход\n')
        if ask == '1':
            ask_path_dir = input('Введите путь к каталогу файлов,\nбудет произведен поиск файлов у которых наименование с префиксом датой в формате ДД.ММ.ГГ): ')
            if not ask_path_dir or not os.path.isdir(ask_path_dir.strip('"')):
                print('Указанный вами каталог не существует.')
                continue

            print(f"\nСодержание каталога {ask_path_dir}:")
            filter_file = MASK_FILTER_FILE
            try:
                list_all_files = get_list_dirs_files(ask_path_dir, filter_file)
                list_files = list_all_files[0]
                list_labels_files = list_all_files[1]
            except Exception as e:
                print(e)
                logging.exception(e)
                continue

            len_list_files = len(list_files)
            len_list_labels = len(list_labels_files)

            if len_list_files > 0 and len_list_files > 0:
                print(f"Найдено:\n- {len_list_files} {set_ending(len_list_files, 'каталогов/файлов', 'каталог/файл', 'каталога/файла')}")
                print(f"- {len_list_labels} {set_ending(len_list_labels, 'ярлыков', 'ярлык', 'ярлыка')}")
            if len_list_files > 0:
                print(f"{set_ending(len_list_files, 'Найдено', 'Найден', 'Найдено')} {len_list_files} {set_ending(len_list_files, 'каталогов/файлов', 'каталог/файл', 'каталога/файла')}")
            elif len_list_labels > 0:
                print(f"{set_ending(len_list_labels, 'Найдено', 'Найден', 'Найдено')} {len_list_labels} {set_ending(len_list_labels, 'ярлыков', 'ярлык', 'ярлыка')}")
            else:
                print('Файлов и ярлыков с префиксом датой в формате ДД.ММ.ГГ не найдено!\n')
                continue

            if len_list_files > 0:
                ask_rename = input('\nПереименовать найденные каталоги/файлы (дата префикса будет изменена на дату вида ГГГГ.ММ.ДД)?\nДа (нажми "1"), Нет (нажми "Enter"): ')
                if ask_rename == '1':
                    print('Работаем:')
                    rename_files(list_files)
                    print('Выполнено!\n')
                else:
                    continue

            if len_list_labels > 0:
                ask_rename_label = input('\nПереименовать найденные ярлыки (ссылки и файлы на которые они ссылаются)?\nДа (нажми "1"), Нет (нажми "Enter"): ')
                if ask_rename_label == '1':
                    print('Разбираем ярлыки:')
                    rename_label_files(list_labels_files)
                    print('Выполнено!\n')
                else:
                    continue

            continue

        elif ask == '2':
            print('Переименование ссылок в ярлыках')

        elif ask == '3':
            # logger.info('Программа завершена')
            print('\nПока!')
            print('И больше позитива, ты же в Россетях!')
            time.sleep(0.75)
            break

        else:
            # logger.warning('Неверный выбор')
            print('\nНеверный выбор, придется повторить')
            continue

if __name__ == "__main__":
    main_menu()
