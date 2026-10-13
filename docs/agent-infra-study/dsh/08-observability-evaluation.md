# DSH 08｜Observability / Evaluation：Ledger、Live Stream 与遥测交接

[返回总目录](../README.md) · P2（学习顺序） · 前置：02/04/07；队列、去重和隐私边界

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。已读遥测契约与调度测试；没有向任何遥测端点上传数据，也没有运行 benchmark。

## 1. 观察系统要区分三条路径

Session ledger 保存规范事实；进程本地 assistant-stream 为实时呈现提供增量；telemetry capture 把获准的事实副本交给后端。它们可以来自同一次执行，却有不同持久性、隐私和交付承诺。[S1][S2]

不能把 live frame 丢失当作模型未产生内容，也不能把 telemetry handoff 当作后端已收到，更不能把诊断复制视为修改业务日志。

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/subsystems/session-telemetry.md`，1–210 行 | ledger/ops、handoff cursor、sharing、redaction |
| [S2] | `docs/subsystems/llm-streaming.md`，1–235 行 | compact timed stream、usage、live/durable 分离 |
| [S3] | `agent-loop/tests/tool-calls.spec.ts`，1–225 行 | gated tools 与确定性调度测试 |
| [S4] | `agent-loop/src/tool-calls.ts`，1–320 行 | dispatch、finish、commit 的真实边界 |

## 3. Ledger 与 Ops 不是同一种记录

SessionTelemetryRecord 的 ledger channel 镜像 Session event；ops channel 记录 agent-error、shutdown 等运行信号，故意不伪装成持久日志的 event.seq 身份。遥测 backend 接收的是单独副本，不直接改写 canonical log。[S1]

交接 cursor 只证明 handed-off，不证明 delivered。文档允许丢失或重复：ledger 接收端按 `(session.id, session.format_version, event.seq)` 去重，ops 则是容忍重复的信号，不应该直接当精确计数账本。[S1]

**分析：** 一套“至少记录过一次”的统计不一定能用于账单、训练样本去重或任务完成确认。数据用途必须匹配交付语义。

## 4. 记录完整与隐私保护的边界

Canonical event 可能包含完整工具数据、提示和 compact assistant stream。redact waterfall 作用于导出副本，不改变原始 Session。契约本身不附带通用脱敏规则；没有 listener 时不能假设数据已经清理。[S1]

`includeHistory` 允许包含历史，不等于授权采集；sharing 模式也不是送达回执。官方文档区分 live/on-demand capture 与 full/feedback-only/disabled sharing，学习时不要把这些开关合并成一个 telemetry=true。[S1]

后台 emit 要非阻塞，错误被 containment 捕获而不传进 Loop；shutdown 要等待队列静止，但其失败也不应破坏整个应用 teardown。[S1，契约]

## 5. 时间与 Token 的可解释性

Compact stream 保留 timed chunks，便于区分首次 token、首次可见文本和完整完成时间。usage 没有被 adapter 报告时是缺失值，不应擅自填写 0。[S2]

工具侧又有开始、实际 dispatch 完成、模型顺序 commit 等时间点；后面工具先完成但等待前面结果时，总延迟并非来自它的执行体。[S4]

**分析：** 应分别测模型、调度、工具、顺序等待、持久化和通知，而不是只给一个“Agent TPS”。

## 6. 上游测试的教学价值

[S3] 的 mock adapter 固定产生 tool calls，gatedTool 让测试按 call ID 手动放行。测试可证明所有并发安全工具在任何一个完成前都已开始，也能证明 exclusive barrier 和注册变化后的重新分类。

这比仅用 `sleep` 总耗时更容易解释调度性质。本文只阅读了测试，没有运行，不能把断言存在当作当前环境已通过。

## 7. 待运行实验

**D08-A：三时序对照。** 同时捕获 live frames、Session ledger 和合成 telemetry sink，验证哪些事件会出现在哪一层；不启用真实外发。

**D08-B：重复与丢失。** 用测试 sink 模拟失败和重复 handoff，验证去重键与 ops 统计策略。对敏感字段安装一条 fail-closed redaction，确认只影响导出副本。

**D08-C：调度质量与成本。** 用 gated tools 分离 body duration 与 commit wait；另用固定任务检查最终结果正确性。改变并发上限不保证质量或吞吐单调提高，必须测量。

## 8. 验收与迁移

产出数据分层表，标明每层的真源、采集授权、去重身份、可靠性和可用于什么指标。再给出一条失败任务从 Attempt 到工具结果的证据链，列明缺口。

**迁移到 Agent Infra：** 可用于训练的轨迹、产品分析和诊断事件不应混为一套无限制数据流。学习目标是构建可解释、可审计且有边界的观测系统，而不是无限增加日志。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session-telemetry.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/llm-streaming.md
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/tests/tool-calls.spec.ts
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts
