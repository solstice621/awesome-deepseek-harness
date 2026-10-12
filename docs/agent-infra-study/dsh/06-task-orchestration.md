# DSH 06｜Goal / Subagent：完成目标与调度授权分离

[返回总目录](../README.md) · P1 · 前置：01/05/07；身份、版本与竞态

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。Goal Driver 已读实现，Subagent 部分主要依据当前接口契约；未运行后台任务。

## 1. 两个不同的编排问题

`/goal` 是同一个 Session 跨多个 Round 推进目标；subagent 是将工作交给本地子会话或外部执行。二者不能混成“无限多 Agent 自动循环”。[S1][S3]

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `packages/goal/README.md` | goal、tool-goal、command-goal、goal-round-driver 分工 |
| [S2] | `goal-round-driver/src/index.ts`，1–300 行 | exact lifecycle、revision、checkpoint、串行触发 |
| [S3] | `docs/subsystems/subagent.md`，1–175 行 | activation、capabilities、delivery、dispose |
| [S4] | `agent-loop/src/agent.ts`，1–230 行 | followup/steer/inject 与取消 |

## 3. Goal 数据不负责自行调度

每个 Session 一个当前 goal，保存完成状态；模型通过工具修改，人通过 `/goal` 直接控制，自动续跑由独立 driver 提供。[S1]

源码进一步区分 goal 的业务 phase 与自动执行的 activation。只有 active 且 armed、未超过 rounds 上限、当前 Agent lifecycle 仍有效并满足输入/状态条件时，driver 才预留下一轮。[S2]

**分析：** “任务尚未完成”并不等于“系统现在有权继续消耗模型和执行工具”。把它们分开，才能暂停、取消、限额和处理异常。

## 4. 自动续跑中的竞态处理

DriverState 以 **Agent 对象**为 key，而不仅是 Session ID；每次读取当前 goal 都检查 registry 中还是同一个活对象。RoundIdentity 包含 goalId、revision、round，attempt 另存 messageId、queued/claimed/admitted、cancelled/stale 等状态。[S2]

这避免一个旧目标或旧生命周期的异步回调影响新任务。状态改变需要 checkpoint 时先 flush，await 之后再次检查就绪条件；失败会 disarm，而不是继续无限预留新轮次。[S2]

多次触发通过 requested/run 合并成单一 agent-local driver。queued 的自动消息与普通用户输入存在竞争，不能让自动 round 永远排在用户之前。代码也区分宿主发起暂停与模型在自己 Turn 内暂停：前者可取消正在进行的目标执行，后者可以正常收尾。[S2]

## 5. Subagent activation 的能力契约

当前 API 通过 `startActivation` 区分 backend capabilities。agentOptions、outputSchema、depthLimit、toolFilter、persona 并非所有 provider 都支持，不支持的请求选项要拒绝，而不是静默忽略。[S3]

本地 continuable child 与 external execution 的准备方式不同。`delivery:parent` 负责通知父模型；`delivery:caller` 把结果交回工作流调用者，避免额外注入一条父消息。dispose 指向**这一次 activation**，而不是后来恢复出来的同 ID 新执行。[S3]

toolFilter 的契约同时控制 prompt 可见性和执行许可，不能只隐藏工具说明；但工具过滤本身仍不等于进程隔离。[S3]

## 6. 学习中应避免的结论

Round counter 不是分布式队列；Agent 对象身份不是跨机器 fencing token；goal.active 不是预算无限授权；结果通知成功也不是业务任务已经正确完成。本篇没有把这些本地机制外推为集群编排能力。

## 7. 待运行实验

**D06-A：暂停与立即恢复竞争。** 自动 round 已排队或正在执行时，暂停后立即恢复；记录 revision 变化，确认旧回调不会把新 goal 再暂停。

**D06-B：checkpoint 失败。** 让测试 persistence flush 拒绝，观察 driver 是否 disarm、是否停止产生下一轮，而不是只有 warning 但持续烧模型。

**D06-C：普通输入抢先。** round 预留前后加入用户消息，检查自动工作不会吞掉或长期阻塞普通输入。

**D06-D：旧 activation disposer。** 子任务结束后恢复同 ID 新 activation，再调用旧 disposer；验证新任务不被错误取消。此实验针对接口契约，当前尚未跑过。

## 8. 验收

分别画 Goal 数据状态机与 Driver 调度状态机，再画 child activation 生命周期。自测：为什么同时需要 goal revision 与 Agent 对象身份？为什么 flush 之后还要复查？为什么 parent/caller delivery 不应混用？

**迁移到 Agent Infra：** 长期任务需要可撤回授权、版本化目标、有限预算、用户输入优先和确切资源所有权；“while goal 未完成”不足以实现可靠自动执行。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/README.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/subagent.md
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
