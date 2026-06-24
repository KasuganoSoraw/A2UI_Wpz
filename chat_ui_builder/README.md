# Chat UI Builder Demo

这个 demo 会把自然语言需求转换成增量 A2UI 数据帧。
它通过 LiteLLM 调用本地 OpenAI-compatible 模型，要求模型流式输出 **planning delta**（一行一个 JSON 事件），
后端解析后直接编译成 A2UI v0.8 数据帧并流式返回前端。

当前定位：A2UI 是**上游 Agent 结果展示层**，负责组织和呈现输入数据，不负责补充新的业务结论或解决方案。

## 为什么需要这个 demo

和固定领域模板示例不同，这个 demo 不把模型锁死在单一业务域里。
模型会流式输出页面规划事件，后端负责把事件增量编译成可渲染帧。

## 本地模型配置

在 PowerShell 中配置 OpenAI-compatible 端点：

```powershell
$env:OPENAI_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
$env:OPENAI_API_KEY = "<你的 API Key>"
$env:LOCAL_MODEL_NAME = "glm-5.1"
$env:LITELLM_MODEL = "openai/glm-5.1"
```

可选日志参数：

```powershell
$env:LOG_LEVEL = "INFO"
$env:MAX_LOG_CHARS = "1200"
```

后端会记录：
- LLM 调用端点、模型名、温度
- 发送给 LLM 的消息
- LLM 的流式 chunk / planning delta
- planning delta 与编译后的 A2UI 骨架帧摘要
- 编译后的 A2UI 数据帧

## 启动后端

```powershell
cd chat_ui_builder
uv sync --project .
uv run python -m chat_ui_builder
```

默认启动在 `http://localhost:8010`。

## API

### `POST /api/chat/stream`

请求体：

```json
{
  "source_data": {
    "summary": "模型推理耗时上升",
    "metrics": {"latency_p95_ms": 920, "error_rate": "2.1%"},
    "logs": ["10:32 timeout request_id=abc123", "10:34 upstream reset"]
  },
  "user_query": "帮我看一下线上推理服务发生了什么"
}
```

兼容旧格式（`message`）仍可使用，但推荐以 `source_data` 作为主输入。

返回：
- `application/x-ndjson`
- 每一行都是一个合法的 A2UI envelope（`beginRendering`、`surfaceUpdate`、`dataModelUpdate` 或 `deleteSurface`）

## 中间层说明

当前版本主路径：

- `init_plan / add_region* / finalize_plan` 等 planning delta 事件（逐行 JSON）

后端链路：

- `PlanningDeltaStreamParser`：解析 LLM 流中的 planning delta 行
- `SkeletonCompiler`：将 planning delta 编译成低层布局增量
- `FrameCompiler`：输出 `beginRendering` / `surfaceUpdate` / `dataModelUpdate`
- 前端按帧渐进式渲染

当前 demo 不再包含 IntentPlan fallback 或 legacy line-by-line fallback。
并且默认启用纯展示约束：不生成按钮、表单、可点击操作或交互动作。
