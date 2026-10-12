# OpenCode 01｜Agent Loop：接纳、协调、Step 与 Attempt

[返回总目录](../README.md) · P0 · 前置：TypeScript、Effect 基本类型、Fiber/Scope

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`，取自 `dev`。本篇描述该固定提交的 Core 路径，不代表某个已安装发行版。静态分析，未运行。

## 1. 先修正学习入口

原计划中的 `packages/opencode/src/session/processor.ts` 在本次提交下返回 404。不要继续按旧版 `SessionProcessor` 的 continue/compact/stop 三分支讲当前实现。

当前已核对的执行链是：**SessionExecution → SessionRunner.drain → runStep → SessionStep.attempt**。`runner/index.ts` 只是接口；具体 LLM Runner 位于 `runner/llm.ts`。[S1][S2][S3][S4]

## 2. 源码地图

| 依据 | 已核对位置 | 所有权 |
|---|---|---|
| [S1] | `session/execution.ts`，1–280 行 | 本进程的运行协调、唤醒、中断、终态 |
| [S2] | `session/runner/index.ts` | drain 契约与 Complete/Moved/Reloaded |
| [S3] | `session/runner/llm.ts`，1–280 行 | 输入提升、上下文准备、逻辑 Step、压缩策略 |
| [S4] | `session/runner/step.ts`，1–290 行 | 一次模型尝试、工具 Fiber、事件结算 |
| [S5] | `specs/v2/session.md` | durable inbox 与完整 Session 语义概览 |

## 3. 为什么要拆四层？

**接纳层**先把输入放进 durable inbox，然后再发出 wake；没有被提升的输入不属于模型可见消息。`resume:false` 可以只记录而不启动。[S5，文档契约]

**协调层**按 Session ID 维护本进程的活动执行。同一会话的 resume 可以加入已有执行，重复 wake 可以合并；不同会话允许并发。中断接受与清理结束是不同完成点。[S1]

**Runner 层**先等待插件激活，处理残留压缩和工具状态，然后寻找可提升输入；手动 compaction/move 作为控制项占据边界。准备初始指令失败时不能先消费输入。具体循环由 `advanceToStep()` 与 `runStep()` 组成。[S3]

**Attempt 层**拥有模型流、当前工具 Fiber、快照与终态事件，而不是整个会话的调度策略。[S4]

```text
durable admission → advisory wake
  → SessionExecution / coordinator
  → selected Location 的 runner.drain
  → 边界处理、输入 promote、上下文 load
  → runStep（一个逻辑 Step，可以多次尝试）
  → attempt（模型流 + 工具 + durable settlement）
  → Completed / Retry / Continue / RecoverFull / Compacted
```

## 4. 一个 Step 不等于一个网络请求

`runStep` 将一次逻辑工作与物理尝试分开。第一次使用边界准备好的上下文，重试可以刷新上下文但不再次提升新输入。自动压缩、续接恢复和部分输出后的继续也有独立结果。[S3][S4]

最后允许的 Step 会保留工具声明、设置 `toolChoice:none`，在限制执行的同时尽量保留 provider 缓存前缀。Attempt 侧也拒绝执行被关闭的工具；只靠给模型一句“不要再用工具”不是约束。[S3][S4]

**分析：** 这套拆分的价值在于每层都有可测试的责任边界。代价是理解成本提高；必须追踪 Effect 的 Scope、取消与 terminal publication，不能只看返回类型。

## 5. 关键不变量

输入记录与输入进入模型历史分离；同一 Session 的本地执行归属有明确协调者；工具本地执行要晚于 `Tool.Called` 发布；取消工作以后仍需完成终态结算；Location 改变时 Runner 返回 Moved/Reloaded，而不是把旧环境继续假装有效。[S1][S3][S4]

注意：这些是本地服务与数据库协议，不能直接称为分布式 lease/fencing。

## 6. 待运行实验

**O01-A：合并唤醒。** 先持久化三条输入，再对同一 Session 重复 wake。记录实际 drain 数和消息 promote 次数，区分唤醒合并与输入合并。

**O01-B：steer/queue/control。** 模型正在执行时分别加入 steer、下一轮 queue、compaction 控制项。记录每条何时成为模型可见，验证控制项不会被当成普通聊天文本。

**O01-C：一个 Step 多个 Attempt。** mock provider 先在输出前失败，再成功；第二组在输出后失败。观察 assistantMessageID、逻辑 step 和 physical attempt 的关系，不能简单计数 HTTP 请求当作 Step。

## 7. 验收

产出一张四层责任表和一张输入队列状态图。能解释：为什么 Runner 接口不是 Loop 实现；为什么重试不能再次 promote；为什么 interrupt 返回不等于 awaitIdle；为什么编排器与单步执行器不应拥有同一份隐式状态。

**迁移到 Agent Infra：** 这是学习 durable admission、worker 协调、环境作用域和逻辑/物理执行分离的优先样本。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/index.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[S5]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
