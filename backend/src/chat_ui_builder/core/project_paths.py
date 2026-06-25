from __future__ import annotations

from pathlib import Path


def find_project_root(start_path: Path) -> Path:
    """从指定路径向上查找包含 pyproject.toml 的项目根目录。"""
    current_path = start_path.resolve()
    if current_path.is_file():
        current_path = current_path.parent

    for directory in (current_path, *current_path.parents):
        if (directory / "pyproject.toml").is_file():
            return directory

    raise RuntimeError(f"无法从 {start_path} 定位项目根目录：未找到 pyproject.toml")


PROJECT_ROOT = find_project_root(Path(__file__))
