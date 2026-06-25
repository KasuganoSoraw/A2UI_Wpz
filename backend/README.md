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

Copy-Item config\models.example.yaml config\models.yaml
# 编辑 config\models.yaml，填入本地模型配置和 API Key

uv run python -m chat_ui_builder
```

模型统一配置在 `config/models.yaml`。该文件包含本机密钥，已被 Git 忽略；
`config/models.example.yaml` 是可提交的配置模板。

配置文件通过 `default_model` 指定默认模型。调用
`POST /api/chat/stream?model=glm-5.1` 可以选择任一已配置模型；省略
`model` 时使用默认模型。请求未配置的模型会返回 HTTP 400。

如需将配置放在其他位置，可设置绝对路径：

```powershell
$env:MODEL_CONFIG_PATH = "D:\configs\a2ui-models.yaml"
```

服务默认监听 `http://localhost:8010`。

## PyCharm 配置

- Working directory：`<仓库目录>\backend`
- Python interpreter：`<仓库目录>\backend\.venv\Scripts\python.exe`
- Run：Module name
- Module name：`chat_ui_builder`
- Environment variables（可选）：`MODEL_CONFIG_PATH=<模型配置绝对路径>`

## 接口

- `GET /health`
- `POST /api/chat/stream`
- `WS /api/chat/ws/stream`
- `WS /ws/debug`

## 测试

```powershell
uv run --with pytest pytest -q
```
