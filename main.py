import os
import datetime

def main_menu():
    print('Утилита для переименования файлов')

    while True:
        ask = input('\nВыберите действие: Переименовать файлы(П), Выйти(В): ')
        if ask == 'П' or ask == 'п' or ask == 'G' or ask == 'g':
            ask_way_file = input('Введите путь к каталогу файлов: ')
            print('\nСписок каталогов/файлов:\n')
            for dir_file in os.listdir(ask_way_file):
                if os.path.isdir(f'{ask_way_file}/{dir_file}'):
                    print('#', dir_file)
                else:
                    print(' -', dir_file)
            continue
        else:
            print('\nПока!')
            break

if __name__ == "__main__":
    main_menu()
