from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any

from litellm import acompletion

from chat_ui_builder.compiler.frame import FrameCompiler
from chat_ui_builder.compiler.skeleton import SkeletonCompiler
from chat_ui_builder.core.settings import settings
from chat_ui_builder.planning.models import A2UIFrame, AddTextDelta, InitSurfaceDelta
from chat_ui_builder.planning.parser import (
    PlanningDeltaRecord,
    PlanningDeltaStreamParser,
)
from chat_ui_builder.planning.prompting import build_messages

logger = logging.getLogger(__name__)


def _truncate(value: Any) -> str:
    text = _to_log_text(value)
    return text[: settings.max_log_chars]


def _to_log_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)


class ChatUIService:
    def _resolve_model_config(
        self, model_name: str | None
    ) -> tuple[str, str, str, bool | None, bool | None, dict[str, Any] | None]:
        if model_name in {"glm-5", "glm-5.1"}:
            return (
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "sk-xxxxxxx",
                f"openai/{model_name}",
                None,
                None,
                {
                    "chat_template_kwargs": {
                        "enable_thinking": False,
                    }
                },
            )
        if model_name in {"deepseek-v4-flash", "deepseek-v4-pro"}:
            return (
                "https://api.deepseek.com",
                "sk-bbbbbbbbbbb",
                f"deepseek/{model_name}",
                False,
                True,
                None,
            )
        return (
            settings.openai_api_base,
            settings.openai_api_key,
            f"openai/{settings.local_model_name}",
            None,
            None,
            {
                "chat_template_kwargs": {
                    "enable_thinking": False,
                }
            },
        )

    async def stream_frames(
        self,
        user_message: str | None = None,
        source_data: Any | None = None,
        user_query: str | None = None,
        request_id: str = "unknown",
        model_name: str | None = None,
    ) -> AsyncIterator[A2UIFrame]:
        messages = build_messages(
            user_message=user_message, source_data=source_data, user_query=user_query
        )
        api_base, api_key, litellm_model, ssl_verify, aiohttp_trust_env, extra_body = (
            self._resolve_model_config(model_name)
        )
        parser = PlanningDeltaStreamParser()
        skeleton_compiler = SkeletonCompiler()
        rejected_lines: list[str] = []
        logger.info(
            "[%s] Starting LLM stream. endpoint=%s model=%s temperature=%s",
            request_id,
            api_base,
            litellm_model,
            settings.temperature,
        )
        logger.info(
            "[%s] User query=%s",
            request_id,
            _truncate(user_query or user_message or ""),
        )
        logger.info("[%s] Source data=%s", request_id, _truncate(source_data))
        logger.info("[%s] LLM messages=%s", request_id, _truncate(messages))

        completion_kwargs: dict[str, Any] = {
            "model": litellm_model,
            "messages": messages,
            "api_base": api_base,
            "api_key": api_key,
            "stream": True,
            "temperature": settings.temperature,
        }
        if ssl_verify is not None:
            completion_kwargs["ssl_verify"] = ssl_verify
        if aiohttp_trust_env is not None:
            completion_kwargs["aiohttp_trust_env"] = aiohttp_trust_env
        if extra_body is not None:
            completion_kwargs["extra_body"] = extra_body

        response = await acompletion(**completion_kwargs)

        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            content = getattr(delta, "content", None)
            if not content:
                continue
            parsed_records, rejected = parser.feed(content)
            rejected_lines.extend(rejected)
            for frame in self._compile_planning_records(
                parsed_records, skeleton_compiler, request_id
            ):
                yield frame

        parsed_records, trailing_rejected = parser.finish()
        rejected_lines.extend(trailing_rejected)
        for frame in self._compile_planning_records(
            parsed_records, skeleton_compiler, request_id
        ):
            yield frame

        raw_output = parser.raw_output
        logger.info("[%s] Raw LLM output=%s", request_id, raw_output)

        if parser.seen_planning_delta:
            for rejected_line in rejected_lines:
                logger.info(
                    "[%s] Ignoring non-planning line during delta stream=%s",
                    request_id,
                    _truncate(rejected_line),
                )
            return

        logger.warning(
            "[%s] No valid planning deltas parsed from stream; rejected_lines=%s",
            request_id,
            _truncate(rejected_lines),
        )
        for frame in self._error_frames():
            logger.info(
                "[%s] Emitting error frame=%s",
                request_id,
                _truncate(frame.model_dump(exclude_none=True)),
            )
            yield frame

    def _compile_planning_records(
        self,
        records: Iterable[PlanningDeltaRecord],
        skeleton_compiler: SkeletonCompiler,
        request_id: str,
    ) -> list[A2UIFrame]:
        frames: list[A2UIFrame] = []
        for record in records:
            compiled = skeleton_compiler.apply(record.delta)
            frames.extend(compiled)
        return frames

    def _error_frames(self) -> list[A2UIFrame]:
        compiler = FrameCompiler()
        frames = compiler.apply(
            InitSurfaceDelta(
                event="init_surface",
                surface_id="main",
                title="页面规划失败",
                summary="未解析出任何 planning delta，请检查模型输出格式并重试。",
            )
        )
        frames.extend(
            compiler.apply(
                AddTextDelta(
                    event="add_text",
                    id="planning_delta_error_text",
                    parent_id="root",
                    text="当前 demo 仅支持 planning delta 主链路（init_plan / add_region* / finalize_plan）。",
                    usage_hint="body",
                )
            )
        )
        return frames
