from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError


DEFAULT_MODEL_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "config" / "models.yaml"
)


class ModelConfigError(RuntimeError):
    """模型配置文件无法读取或内容无效。"""


class ModelNotFoundError(ModelConfigError):
    """请求的模型未在配置文件中注册。"""


class ModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    litellm_model: str = Field(min_length=1)
    api_base: str = Field(min_length=1)
    api_key: SecretStr
    temperature: float = 0.2
    ssl_verify: bool | None = None
    aiohttp_trust_env: bool | None = None
    extra_body: dict[str, Any] | None = None


class ModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    default_model: str = Field(min_length=1)
    models: dict[str, ModelConfig] = Field(min_length=1)


class ModelRegistry:
    def __init__(self, config_path: str | Path | None = None) -> None:
        configured_path = config_path or os.getenv("MODEL_CONFIG_PATH")
        self._config_path = Path(configured_path or DEFAULT_MODEL_CONFIG_PATH)
        self._catalog: ModelCatalog | None = None

    @property
    def config_path(self) -> Path:
        return self._config_path

    @property
    def default_model_name(self) -> str:
        return self._load_catalog().default_model

    def resolve(self, model_name: str | None = None) -> ModelConfig:
        catalog = self._load_catalog()
        selected_name = model_name or catalog.default_model
        try:
            return catalog.models[selected_name]
        except KeyError as exc:
            available_models = ", ".join(sorted(catalog.models))
            raise ModelNotFoundError(
                f"模型 {selected_name!r} 未配置；可用模型：{available_models}"
            ) from exc

    def _load_catalog(self) -> ModelCatalog:
        if self._catalog is not None:
            return self._catalog

        try:
            with self._config_path.open(encoding="utf-8") as config_file:
                raw_config = yaml.safe_load(config_file)
        except FileNotFoundError as exc:
            raise ModelConfigError(f"模型配置文件不存在：{self._config_path}") from exc
        except OSError as exc:
            raise ModelConfigError(
                f"无法读取模型配置文件 {self._config_path}：{exc}"
            ) from exc
        except yaml.YAMLError as exc:
            raise ModelConfigError(
                f"模型配置文件 YAML 格式无效 {self._config_path}：{exc}"
            ) from exc

        try:
            catalog = ModelCatalog.model_validate(raw_config)
        except ValidationError as exc:
            raise ModelConfigError(
                f"模型配置文件内容无效 {self._config_path}：{exc}"
            ) from exc

        if catalog.default_model not in catalog.models:
            raise ModelConfigError(
                f"默认模型 {catalog.default_model!r} 未在 models 中配置"
            )

        self._catalog = catalog
        return catalog


def build_completion_kwargs(
    model_config: ModelConfig,
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    completion_kwargs: dict[str, Any] = {
        "model": model_config.litellm_model,
        "messages": messages,
        "api_base": model_config.api_base,
        "api_key": model_config.api_key.get_secret_value(),
        "stream": True,
        "temperature": model_config.temperature,
    }
    if model_config.ssl_verify is not None:
        completion_kwargs["ssl_verify"] = model_config.ssl_verify
    if model_config.aiohttp_trust_env is not None:
        completion_kwargs["aiohttp_trust_env"] = model_config.aiohttp_trust_env
    if model_config.extra_body is not None:
        completion_kwargs["extra_body"] = model_config.extra_body
    return completion_kwargs


model_registry = ModelRegistry()
