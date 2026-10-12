# OpenCode 04｜LLM / Streaming：部分输出、重试与可取消结算

[返回总目录](../README.md) · P0 · 前置：01、Effect.uninterruptibleMask、流式协议

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。本篇覆盖 provider-neutral Runner 边界，不宣称已读完所有模型供应商的 wire adapter。

## 1. 最重要的版本核对结果

同一固定提交中，Session 语义文档描述的重试次数与代码不同。文档写最多 4 次；`runner/retry.ts` 实际使用 `Schedule.recurs(10)`，并另有默认 `MAX_TIMEOUT_RETRIES = 3`。插件 hook 还可以修改重试决定。[S1][S2]

因此，本篇以**已读执行代码**解释默认策略，保留文档差异；不能把旧计划、README 或评论中的数字直接当作当前运行时事实。

## 2. 阅读入口

| 依据 | 已核对位置 | 问题 |
|---|---|---|
| [S1] | `session/runner/retry.ts`，完整已读 | 可重试性、等待、次数、Retry-After 与 hook |
| [S2] | `specs/v2/session.md` | 当前语义概览及文档差异 |
| [S3] | `session/runner/step.ts`，1–290 行 | stream 到 end、outputStarted、工具与终态 |
| [S4] | `session/runner/llm.ts`，1–280 行 | 逻辑 Step 策略与 request preparation |

## 3. 不能只等一个 finish 事件

Step 会把 provider stream 读到末尾，而不只读到 finish，以便后续请求复用响应状态。流里的本地工具调用在完成调用事件发布后即可启动；provider 自己执行的工具不会本地再跑一遍。[S3]

因此模型流和工具 Fiber 可重叠，但它们各自的顺序与最终结算需要协调。即便 provider 流结束，工具也未必全部结束；即便工具结束，最终 Step 事件也可能尚未持久化。

## 4. outputStarted 是重要分界

已读代码区分：输出前可重试的失败、已产生输出后的继续、完整续接恢复、上下文溢出恢复。Attempt 返回 `Retry`、`Continue`、`RecoverFull`、`Compacted` 或 `Completed`，由 Runner 决定下一步。[S3][S4]

输出前的可恢复传输失败可以保留当前 assistant 身份继续尝试；已经产生 durable output 后，不能把它当作从未发生过。代码还会处理未知 finish reason、provider 缺少工具结果、工具参数未完成等异常。[S3]

**分析：** 判断重试安全性需要“已经提交什么”，不是只看 HTTP 状态码。这里是理解 Agent 与普通无状态 HTTP client 差异的好入口。

## 5. 默认重试策略到底做什么？

`retry.ts` 默认指数间隔从 2 秒开始，单次基础间隔上限 10 秒，并加入 jitter、有限次数；provider 请求的 Retry-After 单独有 15 分钟上限。超时失败另有限额。[S1]

但这些不是无条件最大总耗时：每次网络请求本身也可能耗时，Retry-After 可扩大等待，插件 hook 能修改决策。源码中的时间估算注释不是线上 latency guarantee。

发布 `RetryScheduled` 后再按剩余时间等待，避免事件发布消耗的时间被额外叠加到完整 sleep 上。[S1] 学习重点是等待预算与观测事件一致性，而不是背参数。

## 6. 取消与结算

`uninterruptibleMask` 使实际模型/工具工作保持可取消，同时保护末尾状态结算。若直接在最外层 catch 所有错误转成普通字符串，可能吞掉 interruption 或把 defect 当作可恢复工具错误。[S3]

**分析：** 取消是一种控制信号，不只是失败文本；清理与终态发布属于需要明确保证的阶段。不能将受保护的结算区无限扩大，否则取消会失去及时性。

## 7. 待运行实验

**O04-A：四种流中断。** 分别在任何输出前、文字后、完整 tool-call 后和 provider finish 后但流结束前断开。记录 Outcome、assistantMessageID、工具实际执行次数和最终 durable events。

**O04-B：重试预算。** 使用 mock 时间验证默认指数/jitter/Retry-After/超时计数，再安装一个修改 decision 的 hook。记录默认和覆盖后的区别，不拿真实 API 连续报错烧额度。

**O04-C：错误分类。** 发送不完整工具参数和缺失 hosted-tool result，检查明确错误是否形成且未执行不完整调用。

## 8. 验收

产出“失败点 × 已提交状态 × 允许恢复动作”的矩阵，并明确文档与代码差异。能解释为什么 Retry 与 Continue 不同、为何需要读完 stream、为何一个 logical Step 可包含多个 physical attempts。

**迁移到 Agent Infra：** 这些边界直接影响 rollout 的有效样本、重试成本、重复副作用与模型服务稳定性；不能用一个统一 retry 装饰器替代。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/retry.ts
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
