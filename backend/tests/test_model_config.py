from __future__ import annotations

from pathlib import Path

import pytest

from chat_ui_builder.core.model_config import (
    ModelConfigError,
    ModelNotFoundError,
    ModelRegistry,
)


def _write_config(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_registry_resolves_default_and_named_models(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "models.yaml",
        """
default_model: glm-5.1
models:
  glm-5.1:
    litellm_model: openai/glm-5.1
    api_base: https://dashscope.example/v1
    api_key: secret-glm
    temperature: 0.2
    extra_body:
      chat_template_kwargs:
        enable_thinking: false
  deepseek-v4-flash:
    litellm_model: deepseek/deepseek-v4-flash
    api_base: https://deepseek.example
    api_key: secret-deepseek
    ssl_verify: false
    aiohttp_trust_env: true
""",
    )

    registry = ModelRegistry(config_path)

    default_model = registry.resolve()
    named_model = registry.resolve("deepseek-v4-flash")

    assert registry.default_model_name == "glm-5.1"
    assert default_model.litellm_model == "openai/glm-5.1"
    assert default_model.api_key.get_secret_value() == "secret-glm"
    assert default_model.extra_body == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
    assert named_model.litellm_model == "deepseek/deepseek-v4-flash"
    assert named_model.ssl_verify is False
    assert named_model.aiohttp_trust_env is True


def test_registry_rejects_unknown_model(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "models.yaml",
        """
default_model: glm-5.1
models:
  glm-5.1:
    litellm_model: openai/glm-5.1
    api_base: https://dashscope.example/v1
    api_key: secret-glm
""",
    )

    registry = ModelRegistry(config_path)

    with pytest.raises(ModelNotFoundError, match="unknown-model"):
        registry.resolve("unknown-model")


def test_registry_rejects_missing_api_key(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "models.yaml",
        """
default_model: glm-5.1
models:
  glm-5.1:
    litellm_model: openai/glm-5.1
    api_base: https://dashscope.example/v1
""",
    )

    registry = ModelRegistry(config_path)

    with pytest.raises(ModelConfigError, match="api_key"):
        registry.resolve()


def test_registry_does_not_expose_api_key_in_repr(tmp_path: Path) -> None:
    config_path = _write_config(
        tmp_path / "models.yaml",
        """
default_model: glm-5.1
models:
  glm-5.1:
    litellm_model: openai/glm-5.1
    api_base: https://dashscope.example/v1
    api_key: secret-that-must-not-leak
""",
    )

    model = ModelRegistry(config_path).resolve()

    assert "secret-that-must-not-leak" not in repr(model)
