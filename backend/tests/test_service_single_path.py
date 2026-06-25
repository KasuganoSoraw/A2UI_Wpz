from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import chat_ui_builder.planning.service as service_module
from chat_ui_builder.core.model_config import ModelRegistry
from chat_ui_builder.planning.service import ChatUIService


class FakeResponse:
    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        self._iter = iter(self._chunks)
        return self

    async def __anext__(self):
        try:
            content = next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=content))]
        )


async def _collect_frames(
    service: ChatUIService,
    message: str | None,
    source_data: object | None = None,
    user_query: str | None = None,
    model_name: str | None = None,
) -> list[object]:
    frames: list[object] = []
    async for frame in service.stream_frames(
        user_message=message,
        source_data=source_data,
        user_query=user_query,
        request_id="test-request",
        model_name=model_name,
    ):
        frames.append(frame)
    return frames


def _create_model_registry(tmp_path: Path) -> ModelRegistry:
    config_path = tmp_path / "models.yaml"
    config_path.write_text(
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
    temperature: 0.1
    ssl_verify: false
    aiohttp_trust_env: true
""",
        encoding="utf-8",
    )
    return ModelRegistry(config_path)


def test_stream_frames_uses_requested_model_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    completion_kwargs: dict[str, object] = {}

    async def fake_acompletion(**kwargs: object) -> FakeResponse:
        completion_kwargs.update(kwargs)
        return FakeResponse([])

    monkeypatch.setattr(service_module, "acompletion", fake_acompletion)

    service = ChatUIService(model_registry=_create_model_registry(tmp_path))
    asyncio.run(
        _collect_frames(
            service,
            message="test",
            model_name="deepseek-v4-flash",
        )
    )

    assert completion_kwargs["model"] == "deepseek/deepseek-v4-flash"
    assert completion_kwargs["api_base"] == "https://deepseek.example"
    assert completion_kwargs["api_key"] == "secret-deepseek"
    assert completion_kwargs["temperature"] == 0.1
    assert completion_kwargs["ssl_verify"] is False
    assert completion_kwargs["aiohttp_trust_env"] is True


def test_stream_frames_uses_planning_delta_path(monkeypatch, tmp_path: Path) -> None:
    planning_lines = [
        {
            "event": "init_plan",
            "surface_id": "main",
            "title": "审批中心",
            "summary": "待办审批概览",
        },
        {
            "event": "add_region",
            "id": "hero_region",
            "role": "hero",
            "title": "重点提醒",
        },
        {
            "event": "add_region_text",
            "id": "hero_text",
            "region_id": "hero_region",
            "text": "共有 3 条待审批事项",
            "usage_hint": "body",
        },
        {"event": "finalize_plan"},
    ]
    chunks = [
        "\n".join(json.dumps(line, ensure_ascii=False) for line in planning_lines[:2])
        + "\n",
        "\n".join(json.dumps(line, ensure_ascii=False) for line in planning_lines[2:])
        + "\n",
    ]

    async def fake_acompletion(**_: object) -> FakeResponse:
        return FakeResponse(chunks)

    monkeypatch.setattr(service_module, "acompletion", fake_acompletion)

    frames = asyncio.run(
        _collect_frames(
            ChatUIService(model_registry=_create_model_registry(tmp_path)),
            message=None,
            source_data={"summary": "审批结果", "records": ["A", "B"]},
            user_query="构建审批页面",
        )
    )

    assert len(frames) > 3
    assert any(frame.beginRendering for frame in frames)
    component_ids = {
        component.id
        for frame in frames
        if frame.surfaceUpdate
        for component in frame.surfaceUpdate.components
    }
    assert "hero_region" in component_ids
    assert all(
        not (
            frame.dataModelUpdate
            and frame.dataModelUpdate.path == "/content/planning_delta_error_text"
        )
        for frame in frames
    )


def test_stream_frames_emits_error_without_planning_delta(
    monkeypatch, tmp_path: Path
) -> None:
    async def fake_acompletion(**_: object) -> FakeResponse:
        return FakeResponse(["这里不是 planning delta\n"])

    monkeypatch.setattr(service_module, "acompletion", fake_acompletion)

    frames = asyncio.run(
        _collect_frames(
            ChatUIService(model_registry=_create_model_registry(tmp_path)),
            message="返回任意文本",
        )
    )

    assert any(
        frame.dataModelUpdate
        and frame.dataModelUpdate.path == "/content/planning_delta_error_text"
        for frame in frames
    )
