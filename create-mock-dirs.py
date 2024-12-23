# создание фейковых директорий и файлов
import os
import random
import platform
from win32com.client import Dispatch
from datetime import datetime, timedelta

test_dir = 'temp_dir'
test_files = []

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

create_mock_directories(test_dir)

for dir_path, dir_names, file_names in os.walk(test_dir):
    for cur_dir in dir_names:
        test_files.append(cur_dir)
    for file in file_names:
        # full_path = os.path.join(dir_path, file)
        test_files.append(file)


print(f"Создано {len(test_files)} файлов")