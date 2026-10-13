# DSH 02｜Context / Session：事件日志、Surface 与纯投影

[返回总目录](../README.md) · P0 · 前置：事件溯源、不可变值、已读 01

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。以 Session/Compaction 契约和默认 Loop 调用点分析；未执行恢复实验。

## 1. 核心区别：日志顺序不等于模型上下文顺序

Session 是 append-only typed event log；模型 messages 是从它派生的视图，而不是另存的一套任意可变历史。[S1] 但这不意味着所有事件都成为 LLM 消息，也不意味着活动视图一直按事件 seq 数值递增。

必须区分：**log-only 事实、产生消息的 Surface 节点、对既有消息的纯投影、实际 request envelope**。

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/subsystems/session.md`，1–290 行可见部分 | SessionEventMap、surfaceOp、request/header/context |
| [S2] | `docs/subsystems/compaction.md`，1–190 行 | summary、替换范围、tool pairing、可选 capability |
| [S3] | `agent-loop/src/agent.ts`，260–530 行 | prepared route 后的 system/user 提交 |
| [S4] | `docs/architecture.md`，已读 Turn/Session 部分 | 模型可见内容须可由日志解释 |

## 3. 并非每个事件都进入模型历史

`assistant/message` 是成功或部分中断后的模型可见回答；`assistant/attempt` 保存未形成可见消息的尝试流。`request/header` 保存配置与工具声明，不产生一条普通聊天消息；`request/context` 保存路由容量等元数据，也不是 Prompt 文本。[S1]

system prompt 位于 `system/message`。当前规范禁止把它重新放进 header 的旧 `system` 字段；空 prompt 是明确清空，而不是回退到更早一版非空指令。[S1][S3]

**分析：** “模型看到的必须可重建”并不要求把所有调度、错误和诊断元数据塞给模型。正确做法是保留可重建所需事实，在命名清楚的边界派生视图。

## 4. 路由能力参与指令更新

Loop 在 `prepareRequest` 后拿到 preparedCall，根据绑定路由的能力决定 system prompt 是历史中追加更新还是规范化到初始节点。取消如果发生在请求准备期间，不应提前提交这一轮 system/user 内容。[S3]

这是一个重要顺序：先确定真实执行路由及能力，再决定怎样构造它会接收的请求。旧 `request/context` 记录是历史诊断信息，不能替代本次 preparedCall 的事实。

## 5. 压缩如何保持 append-only

Compaction 是可选 capability，不是写死在核心 Loop 的私有动作。`compaction/start`、`summary`、`end` 都是 log-only；真正改变模型可见范围的是单独的 user/message replacement。锁括号包围摘要生成与替换，结束标记最后落下。[S2]

一个容易出错的细节：`shadowedRange.start/end` 是 **Surface 位置范围的边界节点 seq**，不是数值区间。一次新摘要拥有较大的 log seq，却可能替换到较早的 Surface 位置，因此 start 可能大于 end；完整 `shadowedSeqs` 才是被替换节点集合。[S2]

压缩边界要保留 tool-call/result 配对，不一定保留整个 Turn。手动压缩期间无关注入仍可能发生，契约要求重新校验选中范围，而不是把 start/end 之间所有新事件都删除。[S2]

## 6. 需要学习的不变量

活动 Surface 不任意改写历史事实；log-only attempt 不冒充模型已见消息；清空 system 不复活旧指令；替换范围按位置而非 seq 数值理解；tool call/result 保持可解释；detached replay 要使用对应投影定义。[S1][S2][S4]

这些是官方设计契约及已读调用点支持的分析，不代表本轮验证了所有扩展投影的纯度。

## 7. 待运行实验

**D02-A：三视图。** 为一个 mock 对话列出原始事件、Surface 节点、deriveMessages 结果；添加 log-only attempt，确认它不成为模型回答。

**D02-B：连续两次替换。** 在已有摘要后再次局部压缩，构造 Surface 顺序与 seq 数值顺序不同的例子，检查范围选取不会按数值过滤误删。

**D02-C：system 清空与路由变化。** 先设置 prompt，再清空，再恢复；比较支持和不支持 in-history 更新的 mock route，确认不会残留旧有效指令。

## 8. 验收

交付一个带 log seq 与 surface position 两列的例子，以及每次模型请求的重建表。能解释：为什么 summary 事件本身不必是消息；为什么 log append-only 仍能改变活动上下文；为什么 startSeq > endSeq 不必是错误。

**迁移到 Agent Infra：** 事件溯源的价值在于保留事实并构造可审计视图；代价是投影版本、迁移和上下文重建协议必须严格管理。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/compaction.md
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/architecture.md
