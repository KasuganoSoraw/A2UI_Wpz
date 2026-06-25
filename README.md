# A2UI

本仓库按前后端分离方式组织 Chat UI Builder：

```text
A2UI/
├── backend/   Python 后端
└── frontend/  前端项目
```

## 后端

后端负责调用 OpenAI-compatible 模型，将源数据和用户需求转换为 A2UI NDJSON 数据帧。

在 PowerShell 中运行：

```powershell
cd backend
uv sync

$env:OPENAI_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:OPENAI_API_KEY = "<你的 API Key>"
$env:LOCAL_MODEL_NAME = "glm-5.1"
$env:LITELLM_MODEL = "openai/glm-5.1"

uv run python -m chat_ui_builder
```

服务默认监听 `http://localhost:8010`，接口文档位于 `http://localhost:8010/docs`。

后端详细说明见 [backend/README.md](backend/README.md)。

## 前端

前端代码独立维护在 `frontend/`，详细说明见 [frontend/README.md](frontend/README.md)。
