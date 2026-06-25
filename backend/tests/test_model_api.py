from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import chat_ui_builder.api.app as app_module
from chat_ui_builder.api.schemas import ChatRequest
from chat_ui_builder.core.model_config import ModelNotFoundError


class RejectingService:
    def resolve_model_config(self, model_name: str | None = None) -> None:
        raise ModelNotFoundError(f"模型 {model_name!r} 未配置")


def test_chat_stream_rejects_unknown_model_before_streaming(monkeypatch) -> None:
    monkeypatch.setattr(app_module, "service", RejectingService())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            app_module.chat_stream(
                ChatRequest(message="test"),
                model="unknown-model",
            )
        )

    assert exc_info.value.status_code == 400
    assert "unknown-model" in str(exc_info.value.detail)
