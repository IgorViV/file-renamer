import os
import time
import pathlib
import logging
from datetime import datetime
import winshell

logging.basicConfig(level=logging.INFO, filename='renamer_log.log', filemode='w', format='%(asctime)s %(levelname)s %(message)s')
logging.debug('A DEBUG Message')
logging.info('An INFO')
logging.warning('A WARNING')
logging.error('An ERROR')
logging.critical('A message of CRITICAL severity')

MASK_FILTER_FILE = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'
MASK_FILTER_LABEL = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *.lnk'
TITLE_CLI = '''=====================================
| Утилита для переименования файлов |
|           ver. 0.1.1              |
=====================================
* Утилита изменения формата записи
даты в префиксе наименования каталога/файла, ярлыков
'''

def get_list_dirs_files(name_dir: str, mask: str = '*') -> list[list]:
    'получает список каталогов/файлов с учетом вложенных и отдельно ярлыков'
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
    '''устанавливает необходимое окончание слова, например:
    11 файлов, 1 файл, 3 файла
    '''
    if quantity in (11, 12, 13, 14):
        return word
    elif quantity % 10 == 1:
        return first_change_word
    elif quantity % 10 in (2, 3, 4):
        return second_change_word
    else:
        return word

def rename_prefix(file: pathlib.Path):
    'переименовывает дату в префиксе имени файла'
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
    'переименовывает файлы'
    for file in list_files:
        rename_prefix(file)

def rename_label_files(list_label_files: list):
    'переименовывает ярлыки файлов'
    print(list_label_files)
    for label in list_label_files:
        try:
            shortcut = winshell.shortcut(str(label))
            print('Ссылка ярлыка:', shortcut.path)
        except Exception as e:
            print(e)
            logging.exception(e)

def main_menu():
    'главное меню консольного приложения'
    print(TITLE_CLI)
    filter_file = ''

    while True:
        ask = input('\nВыберите действие:\nВыбрать каталог для переименования (нажми "1"), Выйти (нажми "Enter"): ')
        if ask == '1':
            ask_path_dir = input('Введите путь к каталогу файлов: ')
            if not ask_path_dir or not os.path.isdir(ask_path_dir.strip('"')):
                print('Указанный вами каталог не существует.')
                continue

            ask_mask_filter = input(f'В каталоге {ask_path_dir} будет произведен поиск файлов у которых наименование с префиксом датой в формате ДД.ММ.ГГ\nПродолжить (нажми "1"), Выйти (нажми "Enter"): ')

            if ask_mask_filter == '1':
                print('\nСодержание каталога:')
                filter_file = MASK_FILTER_FILE
                try:
                    list_all_files = get_list_dirs_files(ask_path_dir, filter_file)
                    list_files = list_all_files[0]
                    list_labels_files = list_all_files[1]
                except Exception as e:
                    print(e)
                    logging.exception(e)
                    continue
                else:
                    print('\nКаталог проверен:')
                len_list_files = len(list_files)
                len_list_labels = len(list_labels_files)

                if len_list_files > 0:
                    print(f"{set_ending(len_list_files, 'Найдено', 'Найден', 'Найдено')} {len_list_files} {set_ending(len_list_files, 'каталогов/файлов', 'каталог/файл', 'каталога/файла')}")

                if len_list_labels > 0:
                    print(f"{set_ending(len_list_labels, 'Найдено', 'Найден', 'Найдено')} {len_list_labels} {set_ending(len_list_labels, 'ярлыков', 'ярлык', 'ярлыка')}")

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

                else:
                    print('Файлов и ярлыков не найдено!\n')
                continue

            else:
                continue

        else:
            print('\nПока!')
            print('И больше позитива, ты же в Россетях!')
            time.sleep(0.75)
            break

if __name__ == "__main__":
    main_menu()
