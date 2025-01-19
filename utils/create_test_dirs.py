# создание тестовых каталогов, файлов и ярлыков
import os
import random
import platform
from win32com.client import Dispatch
from datetime import datetime, timedelta
from colorama import init, Fore, Back, Style

TEST_DIR = 'temp_dir'
test_files = []
init()

def clear_screen():
    """очищает экран"""
    os.system('cls' if os.name == 'nt' else 'clear')
def remove_mock_directories(test_dir: str):
    """удаляет тестовый каталог"""
    if not os.path.exists(test_dir):
        return

    try:
        for root, dirs, files in os.walk(test_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(test_dir)
    except PermissionError:
        print("Нет прав доступа на удаление тестового каталога")
    except Exception as e:
        print(f"Произошла ошибка удаления тестовой каталога: {e}")

def create_shortcut(target_path, shortcut_path):
    """создает ярлык файла
    Args:
        target_path: путь к целевому файлу
        shortcut_path: путь, где будет создан ярлык
    """
    if platform.system() == "Windows":
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
            file_path = os.path.join(dir_path, file_name)

            with open(file_path, 'w') as f:
                f.write(f"Этот {index_file} файл создан {datetime.now()}")

            # cоздаем ярлык для файла
            shortcut_name = f"{date_prefix} shortcut_to_file_{index_file}.lnk"
            shortcut_path = os.path.join(shortcuts_dir, shortcut_name)
            create_shortcut(os.path.join(os.getcwd(), file_path), shortcut_path)

        create_mock_directories(dir_path, current_depth + 1, max_depth)

clear_screen()
print(f"\n{Fore.YELLOW}Утилита для создания тестовых каталогов, файлов и ярлыков.")
print(Style.RESET_ALL)
print("В текущем каталоге будет созданы фейковые каталоги, файлы и ярлыки для проверки работы утилиты file-renamer.")
input("\nНажмите Enter для продолжения ...")

remove_mock_directories(TEST_DIR)

create_mock_directories(TEST_DIR)

for dir_path, dir_names, file_names in os.walk(TEST_DIR):
    for cur_dir in dir_names:
        test_files.append(cur_dir)
    for file in file_names:
        test_files.append(file)

print(f"Создано {len(test_files)} файлов")
input("\nДля выхода нажмите Enter ...")