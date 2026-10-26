"""Генератор тестовых каталогов, файлов и ярлыков для проверки утилиты."""

import argparse
import os
import platform
import random
from datetime import datetime, timedelta

try:  # colorama нужна только для цветного вывода
    from colorama import Fore, Style, init
except ImportError:  # pragma: no cover - зависит от окружения
    def init():
        pass

    class _EmptyColors:
        YELLOW = ""
        GREEN = ""
        RESET_ALL = ""

    Fore = _EmptyColors()
    Style = _EmptyColors()

DEFAULT_TEST_DIR = 'temp_dir'
DEFAULT_DEPTH = 5


def clear_screen():
    """очищает экран"""
    os.system('cls' if os.name == 'nt' else 'clear')


def remove_mock_directories(test_dir: str) -> None:
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
        print(f"Произошла ошибка удаления тестового каталога: {e}")


def create_shortcut(target_path, shortcut_path):
    """создает ярлык файла (только в Windows)"""
    if platform.system() != "Windows":
        return

    try:
        from win32com.client import Dispatch
    except ImportError as exc:
        raise RuntimeError("Для создания ярлыков требуется pywin32 (Windows)") from exc

    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = target_path
    shortcut.save()


def create_mock_directories(
    base_path: str,
    current_depth: int = 0,
    max_depth: int = DEFAULT_DEPTH,
    shortcut_factory=None,
) -> None:
    """рекурсивно создает структуру mock-каталогов / файлов"""
    if shortcut_factory is None:
        shortcut_factory = create_shortcut
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

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"Этот {index_file} файл создан {datetime.now()}")

            shortcut_name = f"{date_prefix} shortcut_to_file_{index_file}.lnk"
            shortcut_path = os.path.join(shortcuts_dir, shortcut_name)
            shortcut_factory(os.path.join(os.getcwd(), file_path), shortcut_path)

        create_mock_directories(
            dir_path, current_depth + 1, max_depth, shortcut_factory
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Создает тестовые каталоги, файлы и ярлыки."
    )
    parser.add_argument(
        "--dir", default=DEFAULT_TEST_DIR, help="каталог для тестовых данных"
    )
    parser.add_argument(
        "--depth", type=int, default=DEFAULT_DEPTH, help="глубина вложенности"
    )
    parser.add_argument("--seed", type=int, default=None, help="seed генератора")
    parser.add_argument(
        "--no-shortcuts", action="store_true", help="не создавать ярлыки"
    )
    parser.add_argument(
        "--yes", action="store_true", help="не запрашивать подтверждение"
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.depth < 1:
        parser.error("--depth должен быть больше нуля")

    random.seed(args.seed)
    init()
    clear_screen()
    print(f"\n{Fore.YELLOW}Утилита для создания тестовых каталогов, файлов и ярлыков.")
    print(Style.RESET_ALL)
    print(
        "В текущем каталоге будут созданы фейковые каталоги, файлы и ярлыки "
        "для проверки работы утилиты file-renamer."
    )

    if not args.yes:
        input("\nНажмите Enter для продолжения ...")

    remove_mock_directories(args.dir)
    shortcut_factory = (lambda target, link: None) if args.no_shortcuts else create_shortcut
    create_mock_directories(
        args.dir, max_depth=args.depth, shortcut_factory=shortcut_factory
    )

    created = 0
    for _root, dir_names, file_names in os.walk(args.dir):
        created += len(dir_names) + len(file_names)

    print(f"Создано {created} объектов")
    if not args.yes:
        input("\nДля выхода нажмите Enter ...")
    return created


if __name__ == "__main__":
    main()
