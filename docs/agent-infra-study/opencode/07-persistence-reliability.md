# OpenCode 07｜Reliability：durable inbox、write-ahead claim 与恢复边界

[返回总目录](../README.md) · P1 · 前置：事务、幂等键、进程崩溃；已读 01

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。已核对执行协调代码与 Session 契约；所有 crash/replay 实验待运行。

## 1. 本篇的核心设计

接纳工作先持久化；启动执行记录 durable claim；终态释放 claim；没有终态而残留的 claim 可用于恢复。这里关注的是数据库能留下什么事实，而不是寄希望于进程关闭钩子一定执行。[S1][S2]

## 2. 阅读入口

| 依据 | 已核对位置 | 证据 |
|---|---|---|
| [S1] | `session/execution.ts`，1–280 行 | claimOnCommit/releaseOnCommit、terminal、interrupt |
| [S2] | `specs/v2/session.md` | inbox 幂等、恢复、durable log 与 replay |
| [S3] | `session/runner/llm.ts`，1–280 行 | stale tool/compaction settlement、输入边界 |
| [S4] | `session/runner/step.ts`，1–290 行 | 终态事件与未知工具结果 |

## 3. 接纳不是启动，启动不是完成

Session 文档规定输入先以 inbox 事件记录，再产生 advisory wake。重复提交相同 ID 的幂等性有 Session/type 等条件，不是所有相同文本都会被去重；第一次接纳的载荷优先，跨 Session 或类型冲突不能静默当作成功。[S2，文档契约]

在执行代码中，`Execution.Started` 发布时同时使用 `store.claim` 的 commit 回调；成功/失败等终态发布时释放 claim。主动停止会取消相关 job 并释放；shutdown interruption 则保留 claim，让下次启动能识别未结束的意图。[S1]

**分析：** 这是 durable intent 的模式。但 claim 不是业务工具副作用的提交记录，也不是多节点环境中的 lease + fencing token。

## 4. 中断有多个完成点

`interrupt()` 可以在请求被接受后返回，清理仍由执行 Fiber 异步完成；`awaitSettlement` 只等待被中断的那次执行，`awaitIdle` 则观察本进程何时不再拥有该 Session 的活动工作。[S1]

如果清理期间又接纳了新输入，一个笼统的“等待完成”函数就会产生歧义。学习时务必分别标注 interrupted execution 与 successor execution。

## 5. 恢复时不能重演未知副作用

Runner 在进入执行前调用 stale compaction/tool settlement；Attempt 在遇到不完整参数或缺失工具结果时给出明确失败。[S3][S4] 文档说明残留 running/streaming 工具需要被结算为失败/中断，而不是盲目把旧副作用重放。[S2]

这不意味着外部操作一定未发生。正确的故障描述是：运行记录不知道完整结果，必须保留 ambiguity；是否可重试，应由工具的幂等契约、外部查询或人工确认决定。

## 6. 两种事件流的边界

durable Session log 可按 aggregate sequence 重放；实时 HTTP 全局事件流则是 volatile。文档中的 subscribe-before-replay/watermark 是恢复订阅顺序的协议，不能用“重新连上 SSE”替代持久日志恢复。[S2] 慢客户端处理参见 [08](08-observability-evaluation.md)。

## 7. 待运行实验

**O07-A：接纳后、wake 前退出。** 保存输入并在 wake 前终止进程，重启后检查待处理输入是否仍存在。用测试 seam 固定窗口，避免概率性重现。

**O07-B：四种结束。** 分别正常成功、明确 user interrupt、正常服务 shutdown、无清理的 SIGKILL；比较 claim 是否保留以及下一次启动行为。只在隔离测试进程运行。

**O07-C：重复 ID。** 同 Session/type 同 ID 换 payload 重试、跨 Session 重用 ID、相同文本不同 ID，分别验证契约；不得把内容相同理解为自动去重。

**O07-D：工具结果未知。** 工具在外部计数副本产生一次效果后断开，检查恢复是否保存未知结果以及后续重试有没有重复效果。

## 8. 验收与下一层问题

产出“已接纳、已提升、已启动、工具已发生、终态已记录”五阶段时间线，并写明每个 ACK 的承诺。能够回答为什么 shutdown hook 不是恢复基础、为什么本地 claim 不是集群锁、为什么一个终态只覆盖一个 busy period。

进一步做分布式平台时，需要增加 worker ownership、租约过期、fencing、重复提交和外部副作用幂等。本文不把这些未在已读路径证明的能力归给 OpenCode。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
