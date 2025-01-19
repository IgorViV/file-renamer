import os
import unittest
import random
import platform
from datetime import datetime, timedelta
from win32com.client import Dispatch
from file_renamer import FileRenamer
from pathlib import Path

class FileRenamerTests(unittest.TestCase):
    def setUp(self):
        """создает тестовые каталоги и файлы"""
        self.test_dir = Path('test_directory')
        self.test_files = []

        if not os.path.exists(self.test_dir):
            self.test_dir.mkdir()

        def create_shortcut(target_path, shortcut_path):
            """создает ярлык файла
            Args:
                target_path: путь к целевому файлу
                shortcut_path: путь, где будет создан ярлык
            """
            if platform.system() == "Windows":
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(str(shortcut_path))
                shortcut.Targetpath = str(target_path)
                shortcut.save()

        def create_mock_directories(base_path: Path, current_depth: int = 0,
            max_depth: int = 5):
            """рекурсивно создает структуру mock-каталогов / файлов"""
            if current_depth >= max_depth:
                return
            current_date = datetime.now() + timedelta(days=random.randint(0, 365))
            date_prefix = current_date.strftime("%d.%m.%y")

            # cоздаем каталог для ярлыков на текущем уровне
            shortcuts_dir = base_path / f"{date_prefix} shortcuts"
            shortcuts_dir.mkdir(exist_ok=True)

            # cоздаем от 1 до 3 подкаталогов на каждом уровне
            for index_dir in range(random.randint(1, 3)):
                dir_name = f"{date_prefix} folder-{index_dir}"
                dir_path = base_path / dir_name
                dir_path.mkdir(exist_ok=True)
                self.test_files.append(dir_name)

                for index_file in range(random.randint(1, 3)):
                    file_name = f"{date_prefix} file-{index_file}.txt"
                    file_path = dir_path / file_name
                    self.test_files.append(file_name)

                    with open(file_path, 'w') as f:
                        f.write(f"Этот {index_file} файл создан {datetime.now()}")

                    # cоздаем ярлык для файла
                    shortcut_name = f"{date_prefix} shortcut_to_file_{index_file}.lnk"
                    shortcut_path = shortcuts_dir / shortcut_name
                    create_shortcut(file_path, shortcut_path)

                create_mock_directories(dir_path, current_depth + 1, max_depth)

        create_mock_directories(self.test_dir)

        self.renamer = FileRenamer(str(self.test_dir))

    def tearDown(self):
        """удаляет тестовый каталог"""
        try:
            if self.test_dir.exists():
                for item in self.test_dir.glob('**/*'):
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        item.rmdir()
            self.test_dir.rmdir()
        except Exception as e:
            print(f"Произошла ошибка удаления тестовой директории: {e}")

    def test_validate_directory(self):
        """тест проверки существования каталога"""
        self.assertTrue(self.renamer.validate_directory())

        invalid_renamer = FileRenamer('несуществующая_директория')
        self.assertFalse(invalid_renamer.validate_directory())

    def test_get_files_list(self):
        """тест получения списка файлов"""
        files = self.renamer.get_files_list()
        files_str = [str(f.name) for f in files]

        self.assertEqual(len(files), len(self.test_files))
        for file in self.test_files:
            self.assertIn(file, files_str)

    def test_rename_files(self):
        """тест переименования файлов"""
        success_count, failed_count = self.renamer.rename_files()
        self.assertEqual(success_count, len(self.test_files))
        self.assertEqual(failed_count, 0)

if __name__ == "__main__":
    unittest.main()
