# OpenCode 02｜Context / Session：可见历史、指令状态与压缩 Epoch

[返回总目录](../README.md) · P0 · 前置：[Loop](01-agent-loop.md)

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。本篇以 Session 语义文档与 Runner 调用点交叉分析；没有完整审计全部 projector 和 provider serializer。

## 1. 研究主线

核心问题不是“怎样把消息塞进 context window”，而是**给定持久化事实、当前指令和模型路由，下一次模型请求是怎样产生的**。

OpenCode 文档将 durable inbox 与模型历史分开，描述了按内容哈希保存的指令状态、压缩后的活动上下文，以及 provider continuation state 的失效边界。[S1] Runner 源码则展示这些服务被调用的顺序。[S2]

## 2. 阅读入口

| 依据 | 已核对位置 | 阅读任务 |
|---|---|---|
| [S1] | `specs/v2/session.md` | inbox、历史、指令、compaction、fork 的语义 |
| [S2] | `session/runner/llm.ts`，1–280 行 | InstructionState.prepare、context.select/load、baseTranscript |
| [S3] | `session/runner/step.ts`，1–290 行 | overflow 与 durable output 的关系 |
| [S4] | `specs/v2/tools.md` | 模型可见 content 与机器 output 的差异 |

## 3. 四种状态不要混淆

| 状态 | 作用 | 常见误读 |
|---|---|---|
| 已接纳 inbox | 表示系统接受了工作 | 已经发送给模型 |
| durable Session history | 记录已经发生的会话事实 | 当前请求必须包含全部事实 |
| 当前活动 context | 为下一次请求选取的历史、指令、工具 | 就是完整数据库内容 |
| provider continuation state | 协议层复用上一响应 | 等同于可永久恢复的业务状态 |

这些划分来自 [S1] 的语义；具体字段和投影实现需要沿调用点进一步阅读。

## 4. 实际准备顺序

`prepareContext()` 先 `context.select()`，再 `InstructionState.prepare()`。注释明确：初始指令基线被阻塞时，已接纳输入要继续留在 pending 状态。之后 Runner 才 promote 输入并 load context。[S2]

`runStep()` 可以先自动压缩，成功后重新准备请求；`SessionModelRequest.baseTranscript()` 组合当前 agent/model/tools/initial/messages。重试会刷新上下文，但不提升新的 inbox 输入。[S2]

**分析：** 指令准备与输入消费的顺序，是一种避免“任务已被拿走但执行前提未满足”的设计。它不仅影响用户体验，也影响故障后的可恢复性。

## 5. 压缩不是删除所有历史

文档将 durable transcript 与活动摘要/近期消息分开；压缩会改变活动上下文，并要求相应 provider 续接状态重新建立。它也描述了按内容哈希保存指令、通过 delta 表达变化及压缩 epoch。[S1，文档契约]

Attempt 对 provider overflow 的恢复限定在尚未产生 durable output 的条件下；Runner 拥有压缩策略，而 Attempt 只在合适的失败边界请求恢复。[S2][S3]

**分析：** 若已经执行工具，再把整个请求当作“没有发生过”重试，可能造成重复动作。所以压缩恢复不能只依据错误字符串 `context length exceeded`，还必须看状态推进到哪里。

工具输出也有两种表示：`output` 可供 Code Mode 使用，持久化给模型的 canonical `content` 才是请求重建依据；不能随手从 UI metadata 或内部机器值重建模型历史。[S4]

## 6. Fork 与指令：不要凭直觉补规则

Session 文档对 fork 的指令基线有专门语义，不能假定分叉后一定使用“分叉那一刻所有旧文件内容”。应分别记录继承的消息、当前有效指令、内容 blob 以及 provider 状态。[S1] 本篇尚未动态验证 fork 与文件变更的组合，不能将文档描述扩展成所有插件的行为保证。

## 7. 待运行实验

**O02-A：接纳成功、指令准备失败。** mock 一个不可用的初始指令来源，先提交输入，再调用执行；检查 inbox 是否保留、恢复来源后是否只 promote 一次。

**O02-B：压缩的三视图。** 保存压缩前 durable log、压缩后活动历史和实际 provider 请求；标注哪些原始信息仅保留在存储，哪些进入摘要，哪些需要重新注入。

**O02-C：overflow 的副作用边界。** 在输出前与工具执行后分别注入 overflow；比较是恢复、继续还是失败。只使用无真实副作用的测试工具。

## 8. 学习重点与验收

交付一个“下一请求来源表”，覆盖初始指令、用户输入、摘要、工具 content、provider 状态。必须标注每一项从哪一类事实派生，以及何时失效。

能回答：为什么指令 prepare 在 promote 前？为什么机器 output 不等于持久化 content？为什么压缩必须处理续接状态？为什么历史保存完整也不能保证摘要保真？

**迁移到 Agent Infra：** context preparation 应被视为可审计、有版本、可失败的执行阶段；在训练/评测中，记录最终请求快照比只保存用户 Prompt 更有价值。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/tools.md
