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

Copy-Item config\models.example.yaml config\models.yaml
# 编辑 config\models.yaml，填入本地模型配置和 API Key

uv run python -m chat_ui_builder
```

`config/models.yaml` 保存本机密钥且已被 Git 忽略；可提交的配置模板为
`config/models.example.yaml`。默认模型为 `glm-5.1`，请求也可以通过
`?model=<已配置模型名>` 选择其他模型。

服务默认监听 `http://localhost:8010`，接口文档位于 `http://localhost:8010/docs`。

后端详细说明见 [backend/README.md](backend/README.md)。

## 前端

前端代码独立维护在 `frontend/`，详细说明见 [frontend/README.md](frontend/README.md)。
