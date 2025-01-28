from pathlib import Path

old_path = Path("/home/dir-1/dir-2/dir-3/dir-4")
new_path = Path("/home/dir-1/dir-2/dir-3/dir-4")

def find_diff_path(old_path: Path, new_path: Path) -> dict[str, Path | str] | None:
    """определяет разницу между двумя путями к каталогу"""
    diff_path: dict[str, Path] = {}
    # max_index: int = 0
    info_msg: str = ''

    # Сравнить части пути
    if old_path.parts != new_path.parts and len(old_path.parts) == len(new_path.parts):
        # Найти различия
        index = 0
        index_diff_part = 0
        for old, new in list(zip(old_path.parts, new_path.parts)):
            if old != new:
                index_diff_part = index
                info_msg = f"Изменилось: {old} -> {new}"
            index += 1

        diff_path['path_before'] = Path(*old_path.parts[:index_diff_part + 1])
        diff_path['path_after'] = Path(*new_path.parts[:index_diff_part + 1])

    elif old_path.parts == new_path.parts:
        info_msg = 'Пути одинаковы'
        diff_path['path_before'] = old_path
        diff_path['path_after'] = new_path

    elif len(old_path.parts) > len(new_path.parts):

        # Получаем список частей пути
        old_parts = list(old_path.parts)
        new_parts = list(new_path.parts)

        # Находим разницу
        removed = set(old_parts) - set(new_parts)
        info_msg = f"Из пути удален каталог: {removed}"
        # print(list(removed))
        max_index = len(old_parts)

        if len(list(removed)) > 1:
            print('В пути удалено более одиного каталога, это пока не поддерживается')
            return None

        for item in list(removed):
            if item in old_parts:
                if old_parts.index(item) < max_index:
                    max_index = old_parts.index(item)

        diff_path['path_before'] = Path(*old_path.parts[:max_index + 1])
        diff_path['path_after'] = Path(*old_path.parts[:max_index])

    elif len(old_path.parts) < len(new_path.parts) and old_path.parts == new_path.parts[:(len(old_path.parts) - len(new_path.parts))]:
        info_msg = 'В путь добавлен каталог'
        diff_path['path_before'] = old_path
        diff_path['path_after'] = new_path

    else:
        print('В пути сделано более одного изменения, это пока не поддерживается')
        return None

    diff_path['info_msg'] = info_msg

    return diff_path

if __name__ == '__main__':
    print(find_diff_path(old_path, new_path))
