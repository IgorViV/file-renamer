import os
import pathlib

TITLE_CLI = '''=====================================
| Утилита для переименования файлов |
|           ver. 0.1.0              |
=====================================
'''
current_dir = os.getcwd()

def get_list_dir(name_dir: str):
    'получает список каталогов/файлов'
    select_dir = pathlib.Path(name_dir)
    for item in select_dir.iterdir():
        print(f"{'#' if item.is_dir() else '->'} {item}")

def get_all_list_dir(name_dir: str, mask: str = '*') -> int:
    'получает список каталогов/файлов с учетом вложенных'
    select_dir = pathlib.Path(name_dir.strip('"'))
    index = 0
    for item in select_dir.rglob(mask):
        print(f"{'#' if item.is_dir() else '->'} {item}")
        index += 1
    return index

def main_menu():
    print(TITLE_CLI)
    mask_filter = ''

    while True:
        ask = input('Выберите действие:\nВыбрать каталог(нажми "1"), Выйти(нажми "2"): ')
        if ask == '1':
            ask_path_dir = input('Введите путь к каталогу файлов: ')
            ask_mask_filter = input('Выберите маску фильтра поиска:\nДД.ММ.ГГГГ(нажми "1"), ДД-ММ-ГГГГ(нажми "2") или введите вручную (нажми "3"): ')
            if not ask_mask_filter:
                mask_filter = '*'
            if ask_mask_filter == '1':
                mask_filter = '[0-3][0-9].[0-1][0-2].[1-2][0-9][0-9][0-9]*'
            if ask_mask_filter == '2':
                mask_filter = '[0-3][0-9]-[0-1][0-2]-[1-2][0-9][0-9][0-9]*'
            if ask_mask_filter == '3':
                handler_mask = input('Введите маску даты вручную: ')
                mask_filter = handler_mask
            if get_all_list_dir(ask_path_dir, mask_filter) > 0:
                ask_rename = input('Переименовать найденные каталоги/файлы?\n Да(нажми "1"), Нет(нажми "2"): ')
                if ask_rename == '1':
                    mask_renamed = input('Выберите маску даты для переименования:\nГГГГ.ММ.ДД(нажми "1"), ГГ.ММ.ДД(нажми "2"): ')
                    if not mask_renamed:
                        continue
                    if mask_renamed == '1':
                        mask_renamed = '[0-3][0-9].[0-1][0-2].[1-2][0-9][0-9][0-9]*'
                    if mask_renamed == '2':
                        mask_renamed = '[0-3][0-9].[0-1][0-2].[0-9][0-9]*'
                    print('Работаем! ====>')
                    # for dir_file in os.listdir(ask_path_dir):
                        # print(dir_file)
                        # os.rename(f'{ask_way_file}/{dir_file}', f'{ask_way_file}/{dir_file}')
            else:
                print('Файлы не найдены!\n')
            continue

        else:
            print('\nПока!')
            break

if __name__ == "__main__":
    main_menu()
