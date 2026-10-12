# OpenCode 08｜Observability / Evaluation：事件扇出、背压与故障隔离

[返回总目录](../README.md) · P2（学习顺序） · 前置：有界队列、SSE、durable/volatile 区别

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。已读架构决策和实际测试；没有执行 benchmark、类型检查或测试。

## 1. 为什么把 SSE 事件服务作为重点

成熟 Agent 通常有多个客户端同时观察执行。若每个客户端都独立编码全部事件，CPU 重复消耗；若共享队列又被最慢客户端阻塞，则一个 UI 可以拖住所有任务。OpenCode 的 EventFeed 文档与测试提供了清晰的取舍实例。[S1][S2]

这不是纯前端话题，而是基础设施中的 fan-out、背压、内存预算和故障域问题。

## 2. 依据与阅读次序

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `specs/v2/event-stream-architecture.md` | 单次编码、连接级队列、溢出和编码错误策略 |
| [S2] | `packages/server/test/event-feed.test.ts`，1–240 行 | 确定性行为测试 |
| [S3] | `session/runner/step.ts`，1–290 行 | usage、Step 结果与快照 |
| [S4] | `specs/v2/session.md` | durable Session log 与 replay |

## 3. 一次编码，独立失败

设计使用一个 Server 级全局监听器：过滤公开事件、schema/JSON/SSE 编码一次，然后将同一个不可变字符串交给各连接自己的队列。默认容量是 4,096 个 frame。[S1]

一个队列满时，移除并失败该订阅者，其他订阅者继续；此前已接纳的 backlog 可以先排空，触发溢出的 frame 没有被那个连接接纳。核心发布不等待慢连接。[S1]

**分析：** 优化的是重复编码；fan-out 的队列 offer 和 socket 写仍随客户端数量增长。共享字符串引用也不表示所有内存只保留一份引用槽。

## 4. 为什么不直接共享一个 PubSub？

文档比较了 bounded、dropping、sliding、unbounded 的语义：可能阻塞全局发布、为所有人丢事件、静默让落后者跳过，或失去结构性内存上限。逐连接失败可以构建在共享 ring 上，但需要额外协议和清理协调。[S1]

选择独立有界队列，是用一定引用存储换更简单的故障隔离。它不是放之四海皆准的最优方案；若测量发现引用内存或逐队列 offer 成为瓶颈，再重新评估。

**4,096 是事件数阈值，不是字节/RSS 总上限。** 大 frame、HTTP buffer、内核 buffer 和客户端缓冲都在这个计数之外。[S1]

## 5. 编码失败与慢客户端不同

慢客户端只影响自身。若某个公开事件无法编码，设计选择断开当前订阅者，避免让它们保持一个有静默缺口的流；跳过坏事件后，服务仍能接受后续新连接。[S1]

HTTP live feed 是 volatile，不承担持久化重放职责。客户端重新连接要结合 Session 状态/日志恢复，不能认为 TCP 或 SSE 保证离线期间的业务事件不丢。[S4]

## 6. 上游测试实际验证什么？

[S2] 已读用例包含：多个订阅者只编码一次；容量为 1 时只让慢订阅者失败、快订阅者仍收齐三条；内部事件不消耗公开队列容量；编码异常使当前连接失败，但后续连接仍可收到有效事件。

这些测试使用 Deferred/Fiber 控制推进，是行为验证，不是完整网络栈负载测试。文档中的微基准也只隔离编码边界；本文不把它转换成端到端吞吐提升百分比。

## 7. 待运行实验与指标

**O08-A：重跑确定性测试。** 从 [S2] 开始理解容量为 1 的用例，记录实际测试命令、环境和通过/失败/跳过状态。再增加一个订阅者提前取消的测试。

**O08-B：字节压力。** 固定事件数，改变单条 frame 大小和订阅者数量，分别量队列高水位、heap/RSS、编码 CPU、overflow 和重连次数。不要只提高容量掩盖问题。

**O08-C：任务评估。** 将 Step.Ended 的 tokens/cost、失败原因与最终任务正确性关联。工具权限拒绝、provider 错误、客户端掉线应分别统计；UI 掉线不自动等于任务失败。[S3]

## 8. 验收

产出一个事件交付契约：谁编码、谁排队、满了丢谁、怎样报告 gap、怎样恢复业务状态。再给出一份同模型/同任务/同环境的测量方案，明确不能从微基准推出什么。

**迁移到 Agent Infra：** 当大量 rollout 同时产生流式事件时，独立故障域、有界滞后和诊断数据与业务状态分层，比“给所有事件加一个 websocket”重要得多。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/event-stream-architecture.md
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/test/event-feed.test.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
