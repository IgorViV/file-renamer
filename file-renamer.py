import os
import time
import pathlib
import logging
from datetime import datetime

TITLE_CLI = '''=====================================
| Утилита для переименования файлов |
|           ver. 0.1.0              |
=====================================
* Утилита изменения формата записи
даты в префиксе наименования файла
'''
current_dir = os.getcwd()

def get_all_list_dir(name_dir: str, mask: str = '*') -> list:
    'получает список каталогов/файлов с учетом вложенных'
    list_files = []
    if not os.path.isdir(name_dir.strip('"')):
        raise Exception('Указанный вами каталог не существует!')
    select_dir = pathlib.Path(name_dir.strip('"'))
    for item in sorted(select_dir.rglob(mask), reverse=True):
        print(f"{'[папка]' if item.is_dir() else '->'} {item}")
        list_files.append(item)
    return list_files

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

def rename_prefix(list_files: list):
    'переименовывает дату в префиксе имени файла'
    for item in list_files:
        name_file = item.name
        date_in_name = name_file[:8]
        dateobj = datetime.strptime(date_in_name, '%d.%m.%y').date()
        date_string = dateobj.strftime('%Y.%m.%d')
        try:
            os.rename(f'{item}', item.with_name(f'{date_string}{name_file[8:]}'))
        except Exception as e:
            print('Исключение:', e)
        else:
            print(f'{item} переименован --> {date_string}{name_file[8:]}')

def main_menu():
    'главное меню консольного приложения'
    print(TITLE_CLI)
    mask_filter = ''

    while True:
        ask = input('Выберите действие:\nВыбрать каталог для переименования (нажми "1"), Выйти (нажми "Enter"): ')
        if ask == '1':
            while True:
                ask_path_dir = input('Введите путь к каталогу файлов: ')
                if not ask_path_dir:
                    print('Хм, вы не ввели данные, повторим:')
                if ask_path_dir:
                    break

            ask_mask_filter = input(f'В каталоге {ask_path_dir} будет произведен поиск файлов у которых наименование с префиксом датой в формате ДД.ММ.ГГ\nПродолжить (нажми "1"), Выйти (нажми "Enter"): ')

            if ask_mask_filter == '1':
                mask_filter = '[0-3][0-9].[0-1][0-9].[0-9][0-9] *'

                try:
                    list_files = get_all_list_dir(ask_path_dir, mask_filter)
                except Exception as e:
                    print(e)
                    continue
                else:
                    print('Каталог проверен:')

                len_list_files = len(list_files)

                if len_list_files > 0:
                    print(f"{set_ending(len_list_files, 'Найдено', 'Найден', 'Найдено')} {len_list_files} {set_ending(len_list_files, 'файлов', 'файл', 'файла')}")
                    ask_rename = input('Переименовать найденные каталоги/файлы?\nДа (нажми "1"), Нет (нажми "Enter"): ')
                    if ask_rename == '1':
                        ask_mask_renamed = input('Дата в префиксе наименований файлов будет изменена на дату вида ГГГГ.ММ.ДД\nУверены что это нужно? Да (нажми "1"), Выйти (нажми "Enter"): ')
                        if ask_mask_renamed == '1':
                            print('Работаем:')
                            rename_prefix(list_files)
                            print('Выполнено!\n')
                        else:
                            continue
                    else:
                        continue
                else:
                    print('Файлы не найдены!\n')
                continue
            else:
                continue
        else:
            print('\nПока!')
            time.sleep(0.5)
            break

if __name__ == "__main__":
    main_menu()
