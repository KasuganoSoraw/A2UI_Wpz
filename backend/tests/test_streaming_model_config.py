from __future__ import annotations

import asyncio
from pathlib import Path

import chat_ui_builder.streaming.service as service_module
from chat_ui_builder.core.model_config import ModelRegistry
from chat_ui_builder.streaming.service import StreamingPromptService


class EmptyResponse:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


def test_streaming_service_uses_default_model_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "models.yaml"
    config_path.write_text(
        """
default_model: glm-5.1
models:
  glm-5.1:
    litellm_model: openai/glm-5.1
    api_base: https://dashscope.example/v1
    api_key: secret-glm
    temperature: 0.3
    extra_body:
      chat_template_kwargs:
        enable_thinking: false
""",
        encoding="utf-8",
    )
    completion_kwargs: dict[str, object] = {}

    async def fake_acompletion(**kwargs: object) -> EmptyResponse:
        completion_kwargs.update(kwargs)
        return EmptyResponse()

    monkeypatch.setattr(service_module, "acompletion", fake_acompletion)
    service = StreamingPromptService(model_registry=ModelRegistry(config_path))

    async def collect_chunks() -> list[str]:
        return [
            chunk
            async for chunk in service._stream_event_chunks(
                [{"role": "user", "content": "test"}]
            )
        ]

    assert asyncio.run(collect_chunks()) == []
    assert completion_kwargs["model"] == "openai/glm-5.1"
    assert completion_kwargs["api_base"] == "https://dashscope.example/v1"
    assert completion_kwargs["api_key"] == "secret-glm"
    assert completion_kwargs["temperature"] == 0.3
    assert completion_kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }
