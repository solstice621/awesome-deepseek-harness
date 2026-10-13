# 第 15 章　持久化与恢复：重启后究竟知道什么

[教材目录](../README.md)

**先修知识：** 第 13、14 章，文件与数据库的基本事务概念。**学习目标：** 区分接纳、可见、持久化与执行；根据崩溃点推导恢复策略；理解日志、投影、快照、所有权与格式迁移各自承担的职责。

## 15.1 先定义恢复承诺，再选择存储

CSV 修复任务已经运行一分钟，桌面进程突然退出。任务要把漏乘 quantity 的 15.50 改成 `Decimal("3.50")×2 + Decimal("12.00")×3 = 43.00`。用户说“恢复任务”，可能指恢复聊天记录、恢复待执行输入、重建运行状态、继续模型推理，或者把一个已经启动的测试进程接回来。这些要求的难度和证据不同。一份完整聊天记录并不自动包含任务的运行权、工具的外部结果或可复用的进程句柄。

**接纳（admission）**表示系统接受了输入。**持久接纳（durable admission）**进一步承诺：确认之后，即使当前进程丢失，恢复者仍能找到这份工作。**wake**只是提醒运行器有事可做，不应该成为唯一工作凭证。先写数据库再发 wake，即使提醒丢失，也能由恢复扫描重新发现输入；反过来先启动模型再持久化，崩溃后可能出现“花了成本，却找不到用户为何发起请求”的孤儿执行。

下面的时间线是本章教学模型，不是任一项目的统一实现：

```text
记录输入 → 持久接纳 → 唤醒 → 取得运行权 → 记录调用意图
                                  ↓
                        执行副作用 → 记录结果 → 持久终态 → 释放运行权
```

每条箭头都是要审计的故障窗口。记录调用意图后崩溃，可以知道“计划执行”，却不能仅凭缺少结果断定“没有执行”。这正是上一章结果不确定性的来源。

## 15.2 日志、投影和快照并不是三份同样的数据

日志保存已经发生的事实，例如输入入队、工具被调用、结果结算。投影通过 reducer 把日志转成便于查询的当前状态，例如待处理 inbox、最近回答、累计费用。快照则保存某个日志位置的投影状态，加速重放。

一个可验证快照至少要标明日志身份、包含到哪个序号、投影/schema 版本。恢复先验证这些条件，再从快照之后重放。若把 seq=100 的状态配上“已消费到 120”的游标，101–120 会永久遗漏；若版本升级后继续用旧 reducer 的快照，字段存在也未必语义正确。

不是所有“snapshot”都表示同一件事：工作目录快照用于比较文件，恢复候选快照用于选择该重新加载的会话，状态投影快照用于加速重放。命名相同不意味着它们都能恢复执行。把三者分别画出来，是读大型 Agent 仓库的一项基本功。

日志顺序还不等于持久性。程序可在内存中追加事件，后台把事件提交给 writer，操作系统再把数据写入设备。必须明确哪个返回值提供哪一级保证。`flush` 在不同 API 中也可能有不同含义，要读契约与实现，不能只看函数名。

## 15.3 OpenCode：数据库中的工作与运行意图

`SessionInbox.reconcile` 以消息 ID 找到尚未消费的 inbox 项或已经提升的消息，同 Session、同类型时复用首次接纳的事实；不兼容生命周期则报冲突。`admit` 发布 `InboxEnqueued` 而不是直接开始模型计算。客户端重发同一个逻辑输入因此有对齐入口，但这不能代替工具副作用的幂等键。[inbox.ts:154–201][O15-a]

要证明“事件与投影一起提交”，还必须继续读 Bus。其 durable 事件路径在同一个 `db.transaction` 中检查 aggregate sequence，执行 projectors 和可选 `commit` 回调，更新序列并写 EventTable；事务完成后才路由和唤醒订阅。已经存在的 replay 序号要匹配 ID、类型、时间和数据，否则拒绝分叉；新序号必须连续。[bus.ts:315–378][O15-b] [bus.ts:395–443][O15-c]

`SessionExecution` 把 execution started 与 `store.claim` 放在同一次发布的提交回调中，终态则释放 claim。用户主动停止会释放；shutdown interruption 特意保留，以便下次启动继续。这里的 claim 是“这轮有未完成执行意图”，不是外部文件已经写完的证明。[execution.ts:76–145][O15-d]

恢复服务还要防止无限崩溃循环：`prepareResume` 在运行前持久增加恢复次数，默认最大 10 次；超出则发布失败终态并原子释放 claim。该计数是按未完成轮次累计，终态重置。恢复扫描建立在旧 owner 已死的部署前提上，因此不能把此实现直接移植到两个可同时工作的节点上，再声称已有分布式 fencing。[restart.ts:23–61][O15-e] [restart.ts:75–98][O15-f]

## 15.4 Codex：持久线程与有条件的继续资格

Codex `Session::interrupted_turn` 只捕获符合条件的活动 turn：普通任务、未取消、存在 `RecordedTurnInput`、恰好一个本地环境，且环境配置来自 thread。`RecordedTurnInput` 的含义仅是输入及 turn-start 注入已进入 rollout writer；文件开头明确要求调用者在保存恢复快照前 flush。这个标记是阶段证据，不是磁盘确认。[daemon_recovery.rs:1–42][C15-a]

继续追到 app-server 的 `daemon_recovery_snapshot`：它排除 pending unload、ephemeral、非根 Agent 或有 parent 的线程；先捕获 interrupted turn，再调用 `persist_thread(Standard)`，失败就跳过恢复候选。成功线程加入 loaded 集合，而只有满足前述资格的 turn 才加入 interrupted 集合。于是“重新加载会话”和“自动继续被打断的 turn”有两个独立集合。[daemon_snapshot.rs:15–51][C15-b]

`ThreadStore` 契约要求 Standard persistence 返回前完成；允许后台提交的 context 则必须被后续 flush/shutdown 隔住并传播错误。`flush_thread` 明确承诺 queued items durable/readable。本地实现的 persist 与 flush 进入各自 `RolloutWriteOp`。本章确认了恢复选择到存储接口的调用链，不把它夸大成所有存储设备上的断电耐久性实验结论。[store.rs:176–194][C15-c] [live_writer.rs:155–167][C15-d]

对教材实例，如果 CSV 工具运行在另一个远程环境，不能依据这条本地 daemon 路径推断它符合继续资格；如果是普通本地任务，仍须检查输入和持久化是否完成。恢复资格通常是条件表达式，文档应该列出条件，而不是只写“支持恢复”。

## 15.5 DeepSeek Harness：接口保证、具体后端与检查点策略

DSH 的 `SessionHandle` 契约刻意区分 append 和 flush。append 确认连续批次被接纳、有序，并在同 backend 实例后续读取中可见；接口允许 backend 缓冲物理写入。flush 才承诺已确认追加持久、空会话也被 materialize。close 则完成必要持久化并释放写所有权，且不可取消。[handle.ts:85–116][D15-a]

具体 JSONL 后端比最低契约更强，但不能把它套到所有 backend：显式 `JsonlSessionHandle.append` 通过串行 mutation chain 调用 `persistContiguous`；底层 `appendLines` 写入后 `sync`，失败时回滚到旧长度再抛错，避免下次重试在残尾之后重复 seq。[storage.ts:187–211][D15-b] [index.ts:1330–1371][D15-c]

Live Session 事件走另一条路径：`enqueueLive` 复制事件并启动 200 ms 的最大刻意批处理等待；这不是承诺 200 ms 内一定落盘，实际调度与 I/O 还可能更慢。[等待常量:35–36][D15-d2] drain 失败会把批次按原顺序放回 buffer 并暂停定时重试。`session/flush` 监听器先 `drainLive`，再 `writer.flush`，因此业务调用 sessions.flush 时，不能只看 handle.flush 在“已 materialized”时早返回，就误判仍有 live buffer 被遗漏。[storage.ts:267–312][D15-d] [storage.ts:534–546][D15-e]

旧专题留下的“到底何时 flush”在此继续追到了实际策略。`session-checkpoint-policy` 对有 live session 的模型请求，在构造下游流之前 flush；对带 agent 的顶层工具调用，在执行工具主体之前 flush，并在等待后再次检查取消；对 `agent/pre-step` 也先 flush。嵌套工具调用复用外层边界。base bundle 明确装配此插件。准确表述是这些语义边界执行检查点，不是每个 token 都落盘，也不是所有自定义 profile 必然加载它。[checkpoint-policy/index.ts:29–82][D15-f] [cordis.patch.yml:414–416][D15-g]

JSONL 迁移也有单独的安全边界：prepare 阶段转换并验证历史日志及相关子 Session 描述；`publishStoredMigration` 在授予写入之前发布已准备的历史转换结果。`persistContiguous` 则在新追加前处理 torn tail，并且只有后端 persistBatch 成功后才推进 cursor。这些机制分别处理格式升级和物理尾部不完整，不意味着可以随意丢弃日志中间的坏数据。[index.ts:638–707][D15-h] [storage.ts:318–342][D15-i]

## 15.6 用故障矩阵推导 CSV 任务的恢复

| 崩溃点 | 可以证明的事实 | 恢复动作 |
| --- | --- | --- |
| 输入仅在 UI 中显示 | 客户端曾准备输入 | 用稳定输入 ID 查询接纳状态 |
| 输入持久，wake 前 | 工作仍存在 | 重新唤醒或由恢复扫描发现 |
| 工具调用意图已持久，写文件前后不明 | 至少计划过修改 | 比较旧/新文件 hash，再决定执行 |
| 修改结果已持久，测试未开始 | 修改已报告完成 | 重新确认工作区后运行测试 |
| 测试真实结束，但结果未持久 | 测试可能执行过 | 在隔离环境中重新验证或查询持久报告 |
| 终态持久，客户端未收到 | 服务器已结算 | 重取状态，不自动重开任务 |

该表假设工具结果的定义可信；日志中“成功”并不自动替代文件后置条件检查。尤其在用户或另一个进程可能修改工作区时，旧结果只能说明过去状态。恢复者需要重新建立当前环境，不能恢复旧聊天后就把所有过去观察当成现在事实。

实现顺序通常是：验证格式和日志连续性；恢复投影；取得合法运行权；识别未结算调用；核对外部后置条件；最后继续推理。快照加载得再快，也不能跳过后三项。可靠性首先是明确恢复后知道什么，而不只是让程序自动再次运行。

## 15.7 练习与参考答案

1. **契约题：** 读取能看到刚追加的事件，是否足以证明重启能看到？<br>
   **参考答案：** 不足。读取可能来自内存或操作系统缓存。要找到接口承诺的持久化屏障及错误传播路径。DSH 的抽象 append 与具体 JSONL append 是分析这一差异的好例子。

2. **时序题：** 为什么 Codex 先捕获 interrupted turn，再 persist，而不是先 persist 再捕获？<br>
   **参考答案：** 所捕获的 turn 输入必须纳入后续持久化边界。若顺序颠倒，捕获可能观察到刚进入 writer、但不在此前 flush 前缀中的输入；仍需遵守调用方并发保护，不能仅靠两行顺序推断整个系统无竞态。

3. **设计题：** 为 CSV 编辑器设计一个能处理“写完文件但未记录结果”崩溃点的最小恢复记录。<br>
   **参考答案：** 至少记录 operation ID、目标路径、旧内容 hash、期望新内容 hash、补丁及授权范围。恢复读当前 hash：匹配新值则补记成功；匹配旧值则可按当前授权重试；两者都不匹配则重新分析并发修改。它解决特定条件下的文件操作协调，不是通用事务系统。

4. **迁移题：** 快照格式能解析，但 reducer 语义改变了，是否继续使用？<br>
   **参考答案：** 只有明确兼容或经过迁移验证才可继续；否则从可信日志重建。把“JSON parse 成功”当成“语义兼容”会把旧错误固化进新投影。

**建议实验（未运行）：** 在表中的每个边界注入受控失败；分别记录内存可见前缀、backend 接纳前缀与恢复可读前缀。测试应覆盖 flush 拒绝、残尾、旧格式和运行权冲突。本章未运行三个上游项目的崩溃恢复测试。进一步阅读旧专题：[Codex 有条件恢复](../../agent-infra-study/codex/07-persistence-reliability.md)、[OpenCode durable inbox](../../agent-infra-study/opencode/07-persistence-reliability.md)、[DSH Handle 契约](../../agent-infra-study/dsh/07-persistence-reliability.md)。

[O15-a]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/inbox.ts#L154-L201
[O15-b]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/bus.ts#L315-L378
[O15-c]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/bus.ts#L395-L443
[O15-d]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L76-L145
[O15-e]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L23-L61
[O15-f]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L75-L98
[C15-a]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/daemon_recovery.rs#L1-L42
[C15-b]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/request_processors/daemon_snapshot.rs#L15-L51
[C15-c]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/thread-store/src/store.rs#L176-L194
[C15-d]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/thread-store/src/local/live_writer.rs#L155-L167
[D15-a]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence/src/handle.ts#L85-L116
[D15-b]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/storage.ts#L187-L211
[D15-c]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/index.ts#L1330-L1371
[D15-d]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/storage.ts#L267-L312
[D15-d2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/storage.ts#L35-L36
[D15-e]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/storage.ts#L534-L546
[D15-f]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-checkpoint-policy/src/index.ts#L29-L82
[D15-g]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/bundle/base/cordis.patch.yml#L414-L416
[D15-h]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/index.ts#L638-L707
[D15-i]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence-jsonl/src/storage.ts#L318-L342
