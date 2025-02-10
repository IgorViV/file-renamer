import os
import win32com.client
from pathlib import Path, WindowsPath

long_prefix = '\\\\?\\'

class LongPathHandler(WindowsPath):
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, long_prefix + str(args[0]))


def check_shortcut(shortcut_path):
    """Комплексная проверка ярлыка и его пути"""

    if not shortcut_path.startswith(long_prefix):
        if shortcut_path.startswith('\\\\'):
            shortcut_path = f"{long_prefix}UNC\\{shortcut_path[2:]}"
        else:
            shortcut_path = f"{long_prefix}{shortcut_path}"

    print("FIXED PATH:", shortcut_path)
    try:
        # 1. Проверка существования файла ярлыка
        if not os.path.exists(shortcut_path):
            print(f"Ярлык не существует: {shortcut_path}")
            return

        # 2. Проверка длины пути
        print(f"Длина пути: {len(shortcut_path)} символов")
        if len(shortcut_path) > 260:
            print("Предупреждение: Путь превышает 260 символов")

        # 3. Получение информации о ярлыке
        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(shortcut_path)

        # 4. Проверка целевого пути
        target_path = shortcut.TargetPath
        print(f"Целевой путь: {target_path}")

        if os.path.exists(target_path):
            print("Целевой файл существует")
        else:
            print("Целевой файл не существует")

        # 5. Проверка прав доступа
        try:
            path = Path(shortcut_path)
            path.stat()
            print("Права доступа: есть")
        except PermissionError:
            print("Права доступа: отсутствуют")

        # 6. Дополнительная информация о ярлыке
        print(f"Рабочая директория: {shortcut.WorkingDirectory}")
        print(f"Описание: {shortcut.Description}")

    except Exception as e:
        print(f"Ошибка при проверке ярлыка: {str(e)}")

# Использование
# shortcut_path = r"R:\Departments\САЦ\SAC-DB\Взаимодействие\Генпрокуратура РФ\18.01.24 Обращения прокуратур 2023-2024\ДО\Сибирь (Кемерово)\06.12.23 № 73_1_15_2023_Ид18658-23 (6-28485) Об эл. сн. пос. Кругленькое (Кузбасс)\Проект ответа Сибирь\19-21.10.11.23 Кемеровсая область (С, КЭР).lnk"

# Более детальная проверка доступности сетевого пути
def check_network_path(shortcut_path):
    try:
        parts = shortcut_path.split('\\')
        current = parts[0]
        current += "\\"
        for part in parts[1:]:
            current = os.path.join(current, part)
            if os.path.exists(current):
                print(f"Путь существует: {current}")
            else:
                print(f"Путь не существует: {current}")
                break
    except Exception as e:
        print(f"Ошибка при проверке сетевого пути: {str(e)}")

# Проверка атрибутов файла
def check_file_attributes(path):
    if not path.startswith(long_prefix):
        if path.startswith('\\\\'):
            fixed_path = f"{long_prefix}UNC\\{path[2:]}"
        else:
            fixed_path = f"{long_prefix}{path}"
    try:
        attrs = os.stat(fixed_path)
        print(f"""
              Размер: {attrs.st_size} байт
              Время создания: {os.path.getctime(fixed_path)}
              Время последнего доступа: {os.path.getatime(fixed_path)}
              Время модификации: {os.path.getmtime(fixed_path)}
""")
    except Exception as e:
        print(f"Ошибка при получении атрибутов: {str(e)}")


while True:
    shortcut_path = input("Введите путь к ярлыку: ")
    shortcut_path = shortcut_path.strip('"')
    # Запуск всех проверок
    print("=== Проверка ярлыка ===")
    check_shortcut(shortcut_path)
    print("\n=== Проверка сетевого пути ===")
    check_network_path(shortcut_path)
    print("\n=== Проверка атрибутов файла ===")
    check_file_attributes(shortcut_path)

    choice = input("\nПовторить, введите 1, выйти - Enter: ")
    if choice == "1":
        continue
    else:
        break

# Для использования этого кода вам потребуется установить библиотеку pywin32:
# ```bash
# pip install pywin32
# ```

# Этот код:
# 1. Проверяет существование самого ярлыка
# 2. Проверяет длину пути
# 3. Пытается получить информацию о целевом файле ярлыка
# 4. Проверяет права доступа
# 5. Проверяет доступность каждой части пути
# 6. Проверяет атрибуты файла

# Код выведет подробную информацию о проблеме и поможет определить:
# - Существует ли файл
# - Доступен ли сетевой путь
# - Есть ли проблемы с правами доступа
# - Корректен ли целевой путь ярлыка
# - Нет ли проблем с длиной пути

# Вы можете запустить отдельные функции или весь код целиком, чтобы получить полную картину проблемы.
