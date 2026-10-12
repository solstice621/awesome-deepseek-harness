# Codex 07｜Persistence / Reliability：落盘边界与有条件恢复

[返回总目录](../README.md) · P1 · 前置：日志、事务、幂等、进程崩溃

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。本篇是恢复边界的静态分析，没有执行 kill、断电或存储故障实验。

## 1. 必须拆开的四个承诺

“可以恢复”可能只表示能重新显示聊天记录，也可能表示能恢复下一次模型请求、接管正在运行的任务，或者避免外部操作被重复执行。这四个承诺逐级增强；源码证明前一个，不自动证明后一个。

## 2. 阅读入口

| 依据 | 已核对位置 | 证据性质 |
|---|---|---|
| [S1] | `thread-store/README.md` | 官方存储职责契约 |
| [S2] | `core/src/session/daemon_recovery.rs` | 实际恢复快照的资格判断 |
| [S3] | `core/src/compact.rs`，1–300 行 | live/persisted 压缩历史一致性 |
| [S4] | `exec-server/README.md` | 远程传输与进程的独立生命周期 |

## 3. ThreadStore 与 LiveThread 的分工

文档规定 ThreadStore 的原始历史追加不隐式推断元数据，元数据通过明确的 patch 更新；活动线程优先由 `LiveThread` 协调持久化策略，先处理历史再同步元数据。LocalThreadStore 可结合 JSONL 历史和 SQLite 元数据。[S1]

**分析：** 这避免底层 append 同时承担隐藏的业务推断。但 JSONL 与 SQLite 并置不意味着二者天然具备同一个事务提交点。审计恢复时，需要进一步检查写入顺序、错误返回和重建策略，不能从 README 推出跨存储原子性。

## 4. daemon_recovery 的准确边界

`interrupted_turn()` 已读代码只在下列条件下返回可捕获的活动工作：[S2]

| 条件 | 为什么值得学习 |
|---|---|
| 是普通 Regular task | 不把所有后台/特殊任务都按同一恢复路径处理 |
| 尚未取消 | 用户主动停止与意外中断不是同一种恢复意图 |
| 有 RecordedTurnInput | 避免恢复还没有形成记录基线的输入 |
| 只有一个且为本地执行环境 | 此路径不保存远程身份/配置到 daemon 重启后 |
| 环境配置为 FromThread | 恢复快照依赖明确、受支持的配置来源 |

代码注释要求调用者在捕获后、持久化快照前 flush rollout。**RecordedTurnInput 只说明进入 writer，不等于稳定存储已经确认。** 这是本篇最重要的区分。

以上是这一条代码路径的条件，不是“Codex 所有恢复都不支持远程”的全局结论。

## 5. 故障窗口表

| 中断位置 | 能直接推导什么 | 不能直接推导什么 |
|---|---|---|
| 输入尚未记录 | 该 marker 不存在，不能按本路径捕获 | 用户界面是否另有暂存 |
| 输入已入 writer、尚未 flush | 内存路径知道输入 | 重启一定能看到输入 |
| 历史已落盘、外部工具结果未知 | 可读到某些历史事实 | 工具没有执行，或可以安全再执行 |
| 元数据与历史更新之间 | 存在多阶段更新需要检查 | JSONL/SQLite 已统一原子提交 |
| 远程连接丢失 | 传输失效 | 远程进程必然停止或必然继续 |

最后两列是证据边界，不是断言这些问题一定构成产品缺陷。

## 6. 待运行实验

**C07-A：按检查点崩溃。** 仅在合成测试会话中，分别在记录前、记录后 flush 前、flush 后、快照保存后结束进程。记录恢复后可见的输入、Turn 标识与选项。没有直接可控注入点时，先补测试 seam，不要靠随机 kill 得到含糊结论。

**C07-B：重复副作用。** 让测试工具向独立计数文件执行一次带 invocation ID 的写入，在结果回传前中断。恢复后检查是否重做、是否需要人工确认、外部计数是否与历史一致。此实验的作用是暴露 ambiguity，不是假定系统具备 exactly-once。

**C07-C：元数据重建。** 对测试副本制造历史与索引不一致，观察读取路径的错误或修复。不要直接删除真实用户的数据库或会话文件。

## 7. 学习重点与验收

应能画出最小提交时间线：输入接纳 → writer 接收 → flush → 恢复快照 → 重启重建。每个步骤都标注失败返回如何传播。

验收文档必须写出“本系统在哪些前提下恢复什么、不恢复什么”，而不是只写支持 checkpoint。进一步阅读时应定位 flush 调用方、snapshot 存储方和工具副作用处理方；本文尚未完成这些路径的端到端动态验证。

**迁移到 Agent Infra：** durable intent、恢复资格和结果不确定性，是 rollout 平台、长任务执行器和故障接管系统都必须显式建模的问题。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/thread-store/README.md
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/daemon_recovery.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs
[S4]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/exec-server/README.md
