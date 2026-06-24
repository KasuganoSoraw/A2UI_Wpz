from __future__ import annotations

from pathlib import Path


def test_repository_root_is_python_project_root() -> None:
  repository_root = Path(__file__).resolve().parents[1]

  assert (repository_root / 'pyproject.toml').is_file()
  assert (repository_root / 'uv.lock').is_file()
  assert (repository_root / 'src' / 'chat_ui_builder' / '__main__.py').is_file()
  assert not (repository_root / 'chat_ui_builder' / 'pyproject.toml').exists()
