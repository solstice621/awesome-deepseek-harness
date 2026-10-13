# DSH 03｜Tool / Sandbox：滚动并发池、顺序提交与可报告的隔离能力

[返回总目录](../README.md) · P0 · 前置：有界并发、屏障、AbortSignal、最小权限

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。已读调度实现、相关测试和 Sandbox 契约；未执行 OS 隔离测试。

## 1. 三层责任

Loop 决定工具调用的调度和结果记录；Tool pipeline 决定策略、hooks、guard 和规范结果；Sandbox provider 执行其声明的文件副作用约束。它们不是一个大函数，也不能互相替代。[S1][S2][S3]

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `agent-loop/src/tool-calls.ts`，1–320 行 | rolling pool、exclusive barrier、ordered commit、abort drain |
| [S2] | `docs/tool-execution-pipeline.md` | waterfall、monotonic guard、finalizeContent、tools/result |
| [S3] | `docs/subsystems/sandbox.md`，1–240 行 | per-call policy、full/partial、fail-closed |
| [S4] | `agent-loop/tests/tool-calls.spec.ts`，1–225 行 | gated tools、barrier、运行中替换 |

## 3. 最值得逐行读的调度器

`executeToolCalls()` 按模型给出的调用顺序规划任务；parallel-safe 调用进入有界滚动池，exclusive 调用形成屏障。每个待启动调用会重新读取 executionMode，已经登记为 parallel 不保证整个批次期间永远 parallel。[S1]

`runGroup()` 将状态拆成 started、inFlight、slots、committed。工具 body 可以并发完成，但 `commitReady()` 只沿连续的模型顺序推进，执行后置处理、写 result、接纳 additionalContexts。[S1]

**分析：** 这把吞吐与确定的结果顺序分开。代价是较早的慢调用可能阻塞后面已完成结果的提交，即 head-of-line blocking；本篇没有量化这个代价。

## 4. 动态变化与取消

在 exclusive barrier 后，或结果观察者修改注册表后，未启动工具可以被重新分类。[S1] 上游测试用替换工具的方式实际断言了这个语义。[S4] 这与 OpenCode 的 request-scoped captured tool 形成明确研究对照，但两者的权限/注册生命周期不能仅靠这一个差异完整评价。

取消停止补充新任务，等待已启动 dispatch 收敛，并为没有启动的调用记录 `TOOL_ABORTED_BEFORE_DISPATCH` 结果。调度器自身失败则停止补充、等待 started dispatch，再让拥有 Step 的层补保守恢复结果。[S1]

## 5. Pipeline：可变 hook 与不可放宽 guard

官方管线依次经过 pre-execute waterfall、单调 guard、execute/post-execute、content 规范化/最终约束，最终 `tools/result` 观察冻结的权威结果。[S2]

Guard 的 deny/abstain 与一般 hook 的转换能力不同；审批不存在或无法回答时应拒绝。最终结果观察点不能把中途候选结果当作事实。PTC 子调用也有自己的管线与邻接规则，不能假设“藏进 code mode 就绕过工具政策”。[S2，文档契约]

## 6. Sandbox 的准确边界

`SandboxMode` 只定义文件副作用：read-only、workspace-write、danger-full-access；网络与进程可见性不在这个词汇的承诺中。后端返回 full/partial 以报告实际执行完整度；消费者不能把 partial 当成完整安全边界。[S3]

策略按每次调用携带 mode、workspaceRoot、sessionId，而不是改一个全局 provider 模式。后端不可用时，受限策略必须 fail closed，不能静默原 argv 裸跑。还要区分 sandbox runner 启动失败与沙箱正常工作时阻止了命令访问；退出码本身不足以归因。[S3]

## 7. 待运行实验

**D03-A：受控乱序完成。** 使用 [S4] 的 gated tool，让 c2/c3 先完成、c1 最后完成，比较启动顺序、完成顺序、result 提交顺序与 additionalContext 顺序。

**D03-B：动态屏障。** 在一次结果提交时将后续工具改为 exclusive，验证不会继续按旧分类补满池。测试已有相近案例，先读再扩展。

**D03-C：取消 drain。** 池中有两项运行、一项待启动时取消，核对 started 的真实结果与未启动的合成错误，不把未知副作用写成“从未执行”。

**D03-D：隔离报告。** 在隔离虚拟机/测试目录中模拟 provider unavailable 和 partial，检查消费者是否明确处理；不把网络访问成功当作 SandboxMode 缺陷，因为该契约不包含网络。

## 8. 验收

画一个五调用实例：parallel、parallel、exclusive、parallel、parallel，标出资源上限、屏障、dispatch 与 commit 四条时间线。另写隔离威胁模型：承诺什么、不承诺什么、partial 怎么处理。

**迁移到 Agent Infra：** 可并发性分类、顺序提交、动态配置与执行能力协商，都是扩展到大规模 rollout 前必须理解的运行时基础。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/tool-execution-pipeline.md
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/sandbox.md
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/tests/tool-calls.spec.ts
