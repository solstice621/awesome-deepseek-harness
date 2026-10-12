# DSH 01｜Agent Loop：可替换驱动、输入边界与完整结算

[返回总目录](../README.md) · P0 · 前置：TypeScript、AbortSignal、异步状态机

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。已读默认驱动关键路径与官方架构，未运行模型或测试。

## 1. 最重要的抽象

DSH 将公开 Agent 契约与默认 `agent-loop` 实现分离。消费者通过公开服务控制 Agent，默认驱动 `ReactLoopAgent` 负责 inbox、Turn/Step、模型请求和工具结算。[S1][S2]

这里值得学的不是“一切皆插件”口号，而是：**换掉默认循环时，哪些接口和持久化事实仍必须保持稳定？**

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/architecture.md`，1–280 行可见部分 | 服务/事件域、Turn 主路径 |
| [S2] | `agent-loop/src/agent.ts`，1–230、260–530 行 | Phase、inbox、turn、step、重试与异常结算 |
| [S3] | `agent-loop/src/index.ts`，1–260 行 | factory ownership、startup/dispose |
| [S4] | `agent-loop/README.md` | 默认驱动契约与实现索引 |

## 3. 三种输入行为不是别名

源码中 `followup` 指向 next-turn 并唤醒；`steer` 指向 next-step 并唤醒；`inject` 指向 next-step 但不主动唤醒。取消后的新 waking input 会被导向下一 Turn，避免加入已经 abort 的活动。[S2]

因此“注入上下文”不一定立刻消耗模型请求，“追加一个任务”也不一定抢占当前 Step。学习时要把存放位置与 wakeup 布尔行为分开画。

内部 Phase 包含 idle、maintenance、running；对外 status 会把 maintenance 也映射为 idle。**分析：** 不能只看 UI 的 idle 判断没有维护活动，真正的资源静止还需结合活动 Promise 与相关生命周期契约。[S2]

## 4. 一次 Turn 的实际路径

```text
写入 turn/start → claim inbox → assemble prompt/tools
  → agent/pre-step 决定 reject / enter
  → 若首个 enter 为空：关闭 Turn，不调用模型
  → 写入 step/start
  → prepareRequest，得到绑定的 preparedCall
  → 提交 system/user/request 事实，构造请求
  → 模型流 → assistant/message 或 assistant/attempt
  → 调用工具并记录结果
  → step/end
  → 仍欠后续请求或有 next-step 输入则继续
  → agent/turn-stopping → turn/end
```

该流程是源码阅读摘要，不是声称所有插件都会按同一种策略介入。[S1][S2]

## 5. 错误路径比 happy path 更值得读

`turn()` 在每个 Step 安装 ToolCallRecovery 观察器，Step 失败时补写未结算工具结果，再在 finally 关闭 Step；若恢复本身也失败，会保留原错误与恢复错误的 AggregateError。Turn 最终也要记录结束原因。[S2]

`max-tokens` 是粘性的：一旦某 Step 达到该上限，后续正常完成不能把 Turn 原因降级为普通 completed。取消则记录明确 cause，而不是把所有停止都变成 UNKNOWN。[S2]

模型 in-band failure 可以进入 `agent/request-error` waterfall，由策略决定 retry；重试留在同一 Step，已接受的用户消息只在 firstAttempt 提交，不重复 pre-step 接纳。扩展自身抛错与可重试 provider failure 不能混为一类。[S2]

## 6. 生命周期所有权

FactoryOwnership 追踪 startup 和 live agent teardown；卸载先停止接受新生命周期、触发取消，再等待已启动工作。`raceAbortCall` 还处理取消后异步创建结果迟到的问题：若资源后来才产生，必须释放 abandoned value，不能只抛出 AbortError 就忘掉它。[S3]

**分析：** 这是异步资源获取与取消竞争的典型问题，适用于容器创建、远程工作区和连接初始化，不只适用于 Agent。

## 7. 待运行实验

**D01-A：输入三分法。** 使用 mock adapter，分别调用 followup、steer、inject；记录何时唤醒、进入哪一个 Step、是否产生模型请求。

**D01-B：空接纳。** 在 pre-step 将首批输入变为空，检查存在成对 Turn 边界而没有 Step 和模型请求；不要把零 Step Turn 当作日志损坏。

**D01-C：流中取消。** 让模型先产生文本再阻塞，然后取消；核对 interrupted assistant/message 或无可见输出的 assistant/attempt，以及 Step/Turn 关闭事件。

**D01-D：启动迟到。** 用受控 Promise 模拟资源创建，先取消再 resolve；检查资源是否释放、旧 lifecycle 是否误影响同 ID 的新对象。

## 8. 验收

画出内部 Phase 与公开 status 的映射、输入路由表，以及一个 Step 重试两次的事件序列。能解释为什么 Turn 可包含零个 Step、为何 inject 不唤醒、为何取消后的迟到资源仍需释放。

**迁移到 Agent Infra：** 默认 Loop 提供可替换执行器的案例；真正稳定的是接纳、状态、事件和所有权契约，而不是类名或插件目录。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/architecture.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/index.ts
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/README.md
