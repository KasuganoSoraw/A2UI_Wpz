# Chat UI Builder 后端

后端接收源数据和用户需求，通过 OpenAI-compatible 模型生成增量页面规划事件，
再将其编译为 A2UI NDJSON 数据帧。

## 环境要求

- Windows
- Python 3.12.10
- `uv`
- 可访问的 OpenAI-compatible 模型服务

项目通过 `.python-version` 固定使用 Python 3.12.10。

## 安装和启动

在 PowerShell 中进入 `backend`：

```powershell
uv sync

$env:OPENAI_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:OPENAI_API_KEY = "<你的 API Key>"
$env:LOCAL_MODEL_NAME = "glm-5.1"
$env:LITELLM_MODEL = "openai/glm-5.1"

uv run python -m chat_ui_builder
```

服务默认监听 `http://localhost:8010`。

## PyCharm 配置

- Working directory：`<仓库目录>\backend`
- Python interpreter：`<仓库目录>\backend\.venv\Scripts\python.exe`
- Run：Module name
- Module name：`chat_ui_builder`

## 接口

- `GET /health`
- `POST /api/chat/stream`
- `WS /api/chat/ws/stream`
- `WS /ws/debug`

## 测试

```powershell
uv run --with pytest pytest -q
```
