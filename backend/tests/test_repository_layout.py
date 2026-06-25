from __future__ import annotations

from pathlib import Path


def test_repository_separates_backend_and_frontend_projects() -> None:
  repository_root = Path(__file__).resolve().parents[2]
  backend_root = repository_root / 'backend'

  assert (backend_root / 'pyproject.toml').is_file()
  assert (backend_root / 'uv.lock').is_file()
  assert (backend_root / 'src' / 'chat_ui_builder' / '__main__.py').is_file()
  assert (repository_root / 'frontend' / 'README.md').is_file()
  assert not (repository_root / 'pyproject.toml').exists()
