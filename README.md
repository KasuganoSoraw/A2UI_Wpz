# Chat UI Builder 后端

本仓库仅包含 Chat UI Builder 的 Python 后端。

服务接收源数据和用户需求，通过 OpenAI-compatible 模型生成增量页面规划事件，
再将其编译为 A2UI NDJSON 数据帧。

## 环境要求

- Windows
- Python 3.11 或更高版本
- `uv`
- 可访问的 OpenAI-compatible 模型服务

## 使用阿里云百炼运行

在 PowerShell 中执行：

```powershell
uv sync

$env:OPENAI_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:OPENAI_API_KEY = "<你的 API Key>"
$env:LOCAL_MODEL_NAME = "glm-5.1"
$env:LITELLM_MODEL = "openai/glm-5.1"

uv run python -m chat_ui_builder
```

服务默认监听 `http://localhost:8010`。

## 接口

- `GET /health`
- `POST /api/chat/stream`
- `WS /api/chat/ws/stream`
- `WS /ws/debug`

HTTP 流式接口返回 `application/x-ndjson`。

## 测试

```powershell
uv run --with pytest pytest -q
```
