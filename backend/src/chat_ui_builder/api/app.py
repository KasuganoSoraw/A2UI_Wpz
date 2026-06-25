from __future__ import annotations

import json
import logging
from uuid import uuid4

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from chat_ui_builder.api.schemas import ChatRequest
from chat_ui_builder.core.logging import configure_logging
from chat_ui_builder.core.settings import settings
from chat_ui_builder.planning.service import ChatUIService
from chat_ui_builder.streaming.runtime import StreamingRuntime

configure_logging(getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger(__name__)


app = FastAPI(title="A2UI Chat UI Builder")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = ChatUIService()
streaming_runtime = StreamingRuntime()


@app.on_event("startup")
async def startup_event() -> None:
    logger.info(
        "Chat UI Builder startup. host=%s port=%s endpoint=%s model=%s log_level=%s",
        settings.host,
        settings.port,
        settings.openai_api_base,
        settings.litellm_model,
        settings.log_level,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/debug")
async def ws_debug(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("WS /ws/debug connected")
    await websocket.send_text("connected")
    try:
        while True:
            message = await websocket.receive_text()
            logger.info("WS /ws/debug message=%s", message[: settings.max_log_chars])
    except WebSocketDisconnect:
        logger.info("WS /ws/debug disconnected")
    except Exception:
        logger.exception("WS /ws/debug error")


@app.websocket("/api/chat/ws/stream")
async def chat_stream_ws(websocket: WebSocket) -> None:
    """streaming ws 薄接口层：收消息 -> 调 runtime 流 -> 逐帧发送。"""

    await websocket.accept()
    # 后端必须有 session_id（runtime 需要按 session 维护状态），
    # 但不强制前端必须传：若 query 未提供，则在“本次连接建立时”生成并固定复用。
    session_id = websocket.query_params.get("session_id") or f"ws_{uuid4().hex}"
    logger.info("WS /api/chat/ws/stream connected session_id=%s", session_id)
    await websocket.send_json({"type": "streaming_connected", "session_id": session_id})

    try:
        while True:
            raw_payload = await websocket.receive_text()
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError:
                logger.warning(
                    "WS /api/chat/ws/stream invalid json session_id=%s", session_id
                )
                await websocket.send_json({"type": "error", "error": "invalid json"})
                continue

            if payload.get("type") != "sendMessage":
                logger.warning(
                    "WS /api/chat/ws/stream unsupported type session_id=%s payload=%s",
                    session_id,
                    payload,
                )
                await websocket.send_json(
                    {"type": "error", "error": "unsupported message type"}
                )
                continue

            if "message" not in payload or "final" not in payload:
                logger.warning(
                    "WS /api/chat/ws/stream missing fields session_id=%s payload=%s",
                    session_id,
                    payload,
                )
                await websocket.send_json(
                    {"type": "error", "error": "missing required fields"}
                )
                continue

            message = payload.get("message")
            is_final = payload.get("final")
            if not isinstance(is_final, bool):
                logger.warning(
                    "WS /api/chat/ws/stream invalid final type session_id=%s value=%s",
                    session_id,
                    is_final,
                )
                await websocket.send_json(
                    {"type": "error", "error": "final must be boolean"}
                )
                continue

            if not isinstance(message, str):
                logger.warning(
                    "WS /api/chat/ws/stream invalid message type session_id=%s",
                    session_id,
                )
                await websocket.send_json(
                    {"type": "error", "error": "missing required fields"}
                )
                continue

            async for item in streaming_runtime.stream_submit_snapshot(
                session_id=session_id,
                raw_text=message,
                is_stream_end=is_final,
            ):
                item_type = item.get("type")
                if item_type == "frame":
                    frame = item.get("frame")
                    serializable_frame = (
                        frame.model_dump(exclude_none=True)
                        if hasattr(frame, "model_dump")
                        else frame
                    )
                    # 单帧消息只表达“有一帧数据”，不承担轮次结束/整流结束语义，因此不携带 final。
                    await websocket.send_json(
                        {
                            "type": "a2ui_frame",
                            "session_id": session_id,
                            "frame": serializable_frame,
                        }
                    )
                    logger.info(
                        "WS /api/chat/ws/stream sent frame session_id=%s", session_id
                    )
                    continue

                if item_type == "final":
                    # runtime 的 final 表达“当前轮次处理完成”，协议上用 round_complete 明确语义。
                    await websocket.send_json(
                        {
                            "type": "streaming_round_complete",
                            "session_id": session_id,
                        }
                    )
                    logger.info(
                        "WS /api/chat/ws/stream sent round_complete session_id=%s",
                        session_id,
                    )
                    # 只有前端本次输入 final=true 时，才补发 complete，表示整条流真正结束。
                    if is_final:
                        await websocket.send_json(
                            {
                                "type": "complete",
                                "session_id": session_id,
                            }
                        )
                        logger.info(
                            "WS /api/chat/ws/stream sent complete session_id=%s",
                            session_id,
                        )
                    continue

                if item_type == "status":
                    await websocket.send_json(
                        {
                            "type": "streaming_status",
                            "session_id": session_id,
                            "processed": False,
                        }
                    )
                    logger.info(
                        "WS /api/chat/ws/stream status session_id=%s reason=%s",
                        session_id,
                        item.get("reason"),
                    )
    except WebSocketDisconnect:
        logger.info("WS /api/chat/ws/stream disconnected session_id=%s", session_id)
    except Exception:
        logger.exception("WS /api/chat/ws/stream error session_id=%s", session_id)
        await websocket.send_json({"type": "error", "error": "internal server error"})


@app.post("/api/chat/stream")
async def chat_stream(
    payload: ChatRequest, model: str | None = Query(default=None)
) -> StreamingResponse:
    request_id = uuid4().hex[:8]
    logger.info(
        "[%s] Incoming chat request user_query=%s source_data=%s",
        request_id,
        (payload.user_query or payload.message or "")[: settings.max_log_chars],
        str(payload.source_data)[: settings.max_log_chars],
    )

    async def frame_stream():
        async for frame in service.stream_frames(
            user_message=payload.message,
            source_data=payload.source_data,
            user_query=payload.user_query,
            request_id=request_id,
            model_name=model,
        ):
            body = frame.model_dump_json(exclude_none=True)
            logger.info(
                "[%s] Streaming frame body=%s",
                request_id,
                body[: settings.max_log_chars],
                extra={"full_message": f"[{request_id}] Streaming frame body={body}"},
            )
            yield body + "\n"

    return StreamingResponse(frame_stream(), media_type="application/x-ndjson")
