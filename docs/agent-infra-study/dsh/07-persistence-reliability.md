# DSH 07｜Persistence：Handle 所有权、Flush 与保守修复

[返回总目录](../README.md) · P1 · 前置：日志、写入所有权、物理/逻辑恢复

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。主要依据持久化契约、默认 factory 和 Goal Driver 的调用点；未审计全部 JSONL/压缩后端实现，未做 crash 测试。

## 1. 最关键的区分

Session.append 更新内存事件日志；SessionHandle.append 接纳后端的连续批次；SessionHandle.flush 才给出契约中的持久性屏障。**收到事件、读到自己刚写的值、崩溃后能恢复，是三个不同承诺。**[S1][S2]

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/subsystems/persistence.md`，1–270 行可见部分 | create/open/read/append/flush/close、repair、migration |
| [S2] | `docs/subsystems/session.md`，已读边界事件部分 | 内存日志与 flush 责任分离 |
| [S3] | `agent-loop/src/index.ts`，1–260 行及 README | prepared ownership、StoredSession、恢复职责 |
| [S4] | `goal-round-driver/src/index.ts`，1–300 行 | checkpoint 后复查与失败 disarm |
| [S5] | `agent-loop/src/agent.ts`，260–530 行 | ToolCallRecovery 与 Step/Turn 闭合 |

## 3. 为什么用 Handle 而不是按 ID 随便写？

create/open 返回 SessionHandle，后续 read/append/flush/close 经过该 handle。read-only handle 上写入会失败；活跃 write ownership 阻止第二个 writer；关闭是幂等、异步且不可取消的最终释放。[S1，契约]

同一 backend 实例内，在 append/flush 成功后才开始的读至少能看见该前缀；与写并发的读只承诺有效连续前缀，不承诺最新值。已关闭 handle 的后续操作应拒绝。[S1]

**分析：** 将所有访问绑定到生命周期对象，比散落的 `append(sessionId, ...)` 更容易管理单写者和清理；但单写者本地/文件租约不能自动等同于跨集群一致性协议。

## 4. 不把 append 误写为 durable

append 成功表示接纳、有序及该 backend 内可见，backend 可以缓冲；flush 才承诺已确认追加能在崩溃后存活。close 会完成必要的持久化并释放所有权。[S1]

Session 文档还明确 Loop 不在每一个 Turn 边界直接 await flush。不同 checkpoint policy、显式消费者和 backend teardown 各有责任；本篇没有完整审计 checkpoint-policy，故不以旧描述推断固定刷盘频率。Goal Driver 的已读代码则明确在自己的调度检查点 flush，失败 disarm。[S2][S4]

## 5. 物理恢复与语义修复分层

后端返回物理上有效的连续日志，不因一个 Turn 尚未结束就删除整个 Turn。撕裂尾部与完整逻辑事件是不同概念。resume 持有写权限后，由 Agent 层补充缺失工具结果、Step 结束和 interrupted Turn 结束；只读观察者可以只在内存平衡，不写回原文件。[S1][S3]

默认 Loop 的正常运行失败也通过 ToolCallRecovery 保守补结果，再关闭 Step/Turn。[S5] 未知结果不是“工具肯定没有执行”，修复日志不应自动重演外部副作用。

## 6. 格式迁移不是覆盖旧文件

官方契约描述版本化日志 generation、相邻格式迁移与不可变发布；读打开可以在内存得到当前逻辑格式，写打开在持有所有权时发布新 generation，保留旧来源。遇到未来格式需要拒绝，而不是退回某个更旧但可读的文件假装最新。[S1]

这是文档契约，本轮没有对全部迁移实现与文件系统原子性做证明。

## 7. 待运行实验

**D07-A：append/flush 对照。** 在测试 backend 中让 append 仅缓冲，分别于 flush 前后模拟崩溃；验证可见性与持久性分开，并记录实际持久前缀。

**D07-B：双写者。** 对同一 session 尝试第二个 write open；关闭原 handle 后再打开。进一步测进程异常退出后的租约恢复，但不能直接以同进程结果证明跨进程可靠性。

**D07-C：半个 Turn。** 构造 open turn、tool/call 有无 result 等日志，分别 read-only 查询与 write resume，确认只有有权 writer 追加修复，已完整事实不丢失。

**D07-D：未知版本。** 在日志副本增加未来版本 generation，检查明确 refusal，而不是静默选择旧版。

## 8. 验收

交付一个 Handle 状态机和一张故障矩阵：未 materialize、append accepted、flush durable、ownership lost、closed、format unsupported。每项说明读写行为与恢复者责任。

**迁移到 Agent Infra：** 可靠长任务需要将日志记录、稳定存储、运行权和语义修复分开；这比给每一步写一个 JSONL 就宣称 durable execution 更接近真实系统。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/persistence.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session.md
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/index.ts
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts
[S5]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
