from pathlib import Path

old_path = Path("/home/dir-1/dir-2-new")
new_path = Path("/home/dir-1/dir-2/dir-3")

# Что надо реализовать
# определить что поменялось в пути к каталогу
# варианты различий:
    # /home/user/dir
    # /home/user/dir-new
    # =======================
    # /home/user/dir
    # /home/user-new/dir
    # =======================
    # /home/user/dir
    # /home-new/user/dir
    # ==== исключительный случай когда меняются два каталога, пока не будет реализации ====
    # /home/dir-1/dir-2/dir-3
    # /home/dir-1/dir-2-new/dir-3-new
    # ==== удаление каталога ====
    # /home/user/dir-1/dir-2
    # /home/user/dir-2

# Сравнить части пути
if old_path.parts != new_path.parts and len(old_path.parts) == len(new_path.parts):
    # Найти различия
    for old, new in reversed(list(zip(old_path.parts, new_path.parts))):
        if old != new:
            print(f"Изменилось: {old} -> {new}")
elif old_path.parts == new_path.parts:
    print('Пути одинаковы')
elif len(old_path.parts) > len(new_path.parts):
    print('Из пути удален один из каталогов')
else:
    print('В путь добавлен каталог')

def find_diff_dir(old_dir: Path, new_dir: Path) -> None:
    """определяет разницу между двумя путями к каталогу"""
    pass
