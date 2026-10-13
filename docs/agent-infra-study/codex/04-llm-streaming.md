# Codex 04｜LLM Integration / Streaming：连接复用、请求连续性与重试

[返回总目录](../README.md) · P0 · 前置：HTTP/WebSocket、流式事件、请求作用域

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。本文核对客户端状态与调用方，没有抓取真实服务端流量。

## 1. 先问“哪一种会话”

模型集成至少存在产品 Session、Turn 内的客户端会话、底层连接和服务端续接状态。它们的生命周期不同。只会把 messages 传给 API，无法解释长任务为什么会因重连、认证切换、上下文变更而失效。

## 2. 阅读入口

| 依据 | 已核对位置 | 所属边界 |
|---|---|---|
| [S1] | `core/src/client.rs`，150–410 行 | ModelClientState、ModelClientSession、WebsocketSession、续接判断 |
| [S2] | `core/src/session/turn.rs`，1–260、360–665 行 | Turn 内复用与多次采样 |
| [S3] | `core/src/tools/parallel.rs`，1–275 行 | 工具开始、结果就绪与模型流回收 |

## 3. 三层状态及生命周期

**Session 级状态。** `ModelClientState` 持有 provider/认证等共享信息，以及 WebSocket 失败后使用 HTTP 的状态。该 fallback 可以在 Session 范围保留，不必每个工具回合重新撞一次失败的连接。[S1]

**Turn 级状态。** `ModelClientSession` 用于一个 Turn 内多次采样。`turn_state` 使用 `OnceLock` 记住第一次确定的粘性路由信息，跨本 Turn 的重试和追加请求复用；它不是下一 Turn 的无限期身份。认证归属变化需要清理相关状态。[S1][S2]

**连接/续接状态。** WebsocketSession 记录连接 key、认证代际、上一请求和上一响应等。发增量请求不是单纯比较 messages 长度；还要确认上一请求/响应存在、配置兼容、输入确实扩展原前缀。代码提供 NoPreviousRequest、NoPreviousResponse、输入缩短或不匹配等原因分类。[S1]

## 4. 为什么这些判断重要

### 请求前缀是语义约束，不只是缓存优化

假设上一请求包含某个工具定义和权限说明，随后发生上下文替换或工具变化。即便连接仍活着，也不一定能合法地只发送消息增量。**分析：** 连接可复用、缓存可复用和语义可续接是三个不同命题，后者必须依据完整请求状态判断。

### 认证代际属于连接所有权

若凭证或 provider 归属变化，还继续使用旧的路由/响应状态，就可能把不相容的请求串到一起。[S1] 学习时画出认证刷新、连接缓存、上一响应之间的依赖，不要把 auth 看成调用前填入 header 的常量。

### 重试必须感知已发生的行为

网络读取失败不意味着此前没有形成工具调用或工具副作用。应把“模型传输尝试失败”与“工具执行失败”分开记录。客户端层的重试能力不能作为重复执行 Shell 命令的授权。[S2][S3]

## 5. 重点研究的问题

先列出哪些字段是 Session 共享、哪些只在 Turn 内存在，解释它们为什么不是全局单例。再沿增量请求判断逐项找出使续接失效的情况。最后区分 streamed delta、完整工具调用、工具结果和最终 Turn 完成事件；不能仅以收到 finish 文本判断整个工作已结束。

客户端诊断采用受控原因标签，不需要把整段 Prompt 或响应 ID 塞入指标标签。[S1] **分析：** 这是低基数指标与敏感请求证据分层存放的实例；原始信息应走受控诊断通道。

## 6. 待运行实验

**C04-A：传输矩阵。** 用受控 provider/mock 服务分别制造连接建立失败、流开始前断开、已输出部分文本后断开、工具调用完成后断开。记录是否换传输、是否续接、是否重发整个请求。实验前固定配置，不能混用不同版本客户端。

**C04-B：前缀失效。** 先完成一次可续接请求，再分别改变输入前缀、模型配置、工具集合和认证归属，观察 fallback reason。只有实际捕获到请求后，才填写“发送了完整/增量输入”的结论。

**C04-C：成本归因。** 对同一 Turn 记录物理请求数、重试等待、首个事件时间、首个可见文本时间、工具时间和最终延迟。不要把它们都称为 TTFT，尤其不能忽略工具导致的等待。

## 7. 验收

交付一个“状态—作用域—失效条件”表，外加一段流中断的时序记录。能回答：为何 OnceLock 放在 Turn 客户端？为什么消息变长仍不一定可增量发送？为什么网络重试不等于工具重试？

**迁移到 Agent Infra：** 这里与推理网关、会话路由、连接池、重试预算和成本控制直接相连，但不涉及 CUDA kernel 或 GPU 调度的实现。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs
