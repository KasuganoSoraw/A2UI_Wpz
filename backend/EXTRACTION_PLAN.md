# Chat UI Builder 仓库抽离说明

## 目标

将上游 A2UI 大仓精简为前后端分离的 Chat UI Builder 项目，同时保留可复现的后端依赖安装和运行方式。

## 保留内容

- `backend/src/chat_ui_builder/` 后端源码
- `backend/tests/` 后端测试
- `backend/uv.lock` 后端依赖锁文件
- `frontend/` 前端独立维护目录
- 根目录 `README.md`
- 根目录 `.gitignore`
- 根目录 `LICENSE`
- Git 元数据

## 已删除内容

- Renderer 和前端代码
- 示例与 Agent SDK
- A2UI 规范源码
- 原仓库工具
- 上游文档与站点配置
- 上游 GitHub 和 Gemini 配置
- 运行时生成的日志

## 验证要求

1. 在 `backend/` 目录使用 `uv sync` 安装锁定依赖。
2. 运行后端测试，并单独记录已有失败。
3. 在不持久化 API Key 的情况下启动 FastAPI 服务。
4. 验证 `GET /health`。
5. 确认后端不再引用本仓库之外的上游代码。
