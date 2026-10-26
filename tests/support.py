"""Загрузка основного модуля в тестах.

Файл называется ``file-renamer.py`` (дефис в имени), поэтому его нельзя
импортировать обычным ``import``. Кроме того, на не-Windows машинах нет
``winshell``, ``win32com`` и ``colorama`` — для тестов подставляются заглушки,
чтобы проверять логику, не зависящую от Windows.
"""

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "file-renamer.py"
MODULE_NAME = "file_renamer_under_test"


def _stub_colorama() -> None:
    try:
        import colorama  # noqa: F401
    except ImportError:
        colorama = types.ModuleType("colorama")
        empty_style = types.SimpleNamespace(YELLOW="", GREEN="", RESET_ALL="")
        colorama.init = lambda *args, **kwargs: None
        colorama.Fore = empty_style
        colorama.Back = empty_style
        colorama.Style = empty_style
        sys.modules["colorama"] = colorama


def _stub_windows_modules() -> None:
    try:
        import winshell  # noqa: F401
    except ImportError:
        sys.modules["winshell"] = types.ModuleType("winshell")

    try:
        from win32com.client import Dispatch  # noqa: F401
    except ImportError:
        win32com = types.ModuleType("win32com")
        win32com.__path__ = []  # type: ignore[attr-defined]
        client = types.ModuleType("win32com.client")
        client.Dispatch = lambda *args, **kwargs: None
        win32com.client = client
        sys.modules["win32com"] = win32com
        sys.modules["win32com.client"] = client


def load_renamer_module() -> Any:
    """Загружает ``file-renamer.py`` как модуль, не меняя рабочую директорию."""
    if MODULE_NAME in sys.modules:
        return sys.modules[MODULE_NAME]

    _stub_colorama()
    _stub_windows_modules()

    spec = importlib.util.spec_from_file_location(MODULE_NAME, MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль {MODULE_PATH}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module
