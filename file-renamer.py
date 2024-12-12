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
                    print('Успешно!')

                if len(list_files) > 0:
                    print(f"Найдено {len(list_files)} файла(ов)")
                    ask_rename = input('Переименовать найденные каталоги/файлы?\nДа (нажми "1"), Нет (нажми "Enter"): ')
                    if ask_rename == '1':
                        ask_mask_renamed = input('Дата в префиксе наименований найденных файлов будет изменена на дату вида ГГГГ.ММ.ДД\nУверены что это нужно? Да (нажми "1"), Выйти (нажми "Enter"): ')
                        if ask_mask_renamed == '1':
                            print('Работаем ====>')
                            for item in list_files:
                                name_file = item.name
                                date_in_name = name_file[:8]
                                dateobj = datetime.strptime(date_in_name, '%d.%m.%y').date()
                                date_string = dateobj.strftime('%Y.%m.%d')
                                print(f'{date_string}{name_file[8:]}')
                                os.rename(f'{item}', item.with_name(f'{date_string}{name_file[8:]}'))
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
