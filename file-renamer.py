import os
import datetime

def main_menu():
    print('Утилита для переименования файлов')

    while True:
        ask = input('\nВыберите действие: Посмотреть каталог(1), Выйти(2): ')
        if ask == '1':
            ask_way_file = input('Введите путь к каталогу файлов: ')
            print('\nСписок каталогов/файлов:\n')
            for dir_file in os.listdir(ask_way_file):  # переписать через рекурсию
                if os.path.isdir(f'{ask_way_file}/{dir_file}'):
                    print('#', dir_file)
                else:
                    print(' -', dir_file)
            ask_rename = input('Переименовать? Да(1), Нет(2): ')
            if ask_rename == '1':
                print('Работаем! ====>')
                for dir_file in os.listdir(ask_way_file):
                    # print(dir_file)
                    # проверить наличие даты в наименование файла
                    # отфарматировать дату по шаблону
                    # переименовать файл
                    if os.path.exists(f'{ask_way_file}/{dir_file}') and '.tmp' in f'{ask_way_file}/{dir_file}':
                        print(dir_file)
                        # os.rename(f'{ask_way_file}/{dir_file}', f'{ask_way_file}/new{dir_file}')
            continue
        else:
            print('\nПока!')
            break

if __name__ == "__main__":
    main_menu()
