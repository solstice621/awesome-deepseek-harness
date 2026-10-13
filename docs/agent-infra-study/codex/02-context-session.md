# Codex 02｜Context / Session：历史、压缩与请求重建

[返回总目录](../README.md) · P0 · 前置：[Agent Loop](01-agent-loop.md)

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。静态源码与文档阅读；所有实验均待运行。

## 1. 先区分三种“历史”

研究上下文时至少分清：存储中的历史记录、当前运行时使用的历史、实际送给模型的请求。三者有关联，但不是可以任意互换的同一个数组。`run_turn` 会从历史构造适合当前输入模态的 prompt；压缩会替换活动历史并写入相应记录；ThreadStore 的原始历史追加又与元数据更新分离。[S1][S2][S3]

不要把 Context Engineering 缩小成“写一段总结 Prompt”。工程问题是：**总结以后，系统还能否解释模型看见了什么，保留的工具结果是否完整，重新加载后是否得到同一个历史基线？**

## 2. 阅读入口

| 依据 | 已核对位置 | 学习重点 |
|---|---|---|
| [S1] | `core/src/compact.rs`，1–300 行 | replacement history、压缩元数据、自动/手动入口及钩子 |
| [S2] | `core/src/session/turn.rs`，1–260、360–665 行 | 压缩在主 Loop 中的触发位置 |
| [S3] | `thread-store/README.md` | raw history、LiveThread 与元数据职责 |
| [S4] | `rollout-trace/README.md` | 模型可见历史与运行时证据的区别 |

本篇重点覆盖已读的本地压缩代码。仓库还存在其他压缩路径；不能将 `compact.rs` 的具体行为外推为所有配置和服务端实现。

## 3. 核心机制

### 压缩结果不只是摘要文本

`CompactedHistoryMetadata` 保存压缩检查点相关信息；`build_compaction_replacement_history` 负责把保留历史、初始上下文和 world-state 等拼装成新的活动历史。摘要文本只是这一步的一个输入。[S1]

`replace_compacted_history` 会在持久化 `CompactedItem` 前补齐缺失的标识，代码注释明确指向 live 与 persisted 两边的一致性。**分析：** 若两边分别生成标识，即使文字相同，恢复、引用或增量更新仍可能指向不同对象。因此这里学习的是身份稳定性，而不仅是 token 数量优化。

### 压缩有自己的生命周期

自动与手动入口不同；代码记录 reason、phase、trigger、implementation 等诊断维度，并有 pre/post compaction hooks。前置钩子停止和压缩成功后后置钩子要求停止，是不同结果，不能统一记为“压缩失败”。[S1]

摘要调用使用独立的模型客户端会话，并在其重试范围内复用。它消耗模型请求、时间和潜在费用；不能只比较压缩前后 token 而忽略摘要本身的代价。[S1]

### 活动历史改变不等于所有证据都消失

ThreadStore 文档把原始历史追加和活动线程的持久化协调分开；诊断 trace 又可保存请求与压缩证据。[S3][S4] 但这些事实并不自动证明“每一种原始模型请求都可从任意存储恢复”。应该逐条检查本次使用的后端、压缩路径和诊断开关。

## 4. 需要建立的不变量

| 不变量 | 检查方法 |
|---|---|
| live 与持久化压缩记录中的对象标识一致 | 比较 replacement history 与重载后的条目 |
| tool call/result 不因错误裁剪失去配对 | 检查压缩边界两侧的模型请求 |
| 压缩后的指令基线明确 | 列出保留、重建和重新注入的指令来源 |
| 压缩失败不应无声吞掉已接纳用户输入 | 与 Turn 中失败分支交叉阅读 |
| 文本相同不代表请求完全相同 | 同时检查工具声明、模型配置和消息顺序 |

其中配对、信息保真度属于需要实验验证的目标，本文不声称已证明所有压缩路径满足这些条件。

## 5. 待运行实验

**实验 C02-A：可审计的长任务压缩。** 构造包含目标、约束、未完成工作、已完成有副作用工具和关键文件路径的固定对话。手动触发压缩，逐项比对重建的下一请求；再恢复会话，重复比对。使用 mock 摘要可先验证状态逻辑，真实模型摘要质量另行评估。

**实验 C02-B：压缩前后失败注入。** 在摘要生成前、替换活动历史后、持久化前后分别中止测试进程。记录哪一个检查点能恢复，以及是否出现“内存已换、存储未换”的可观察状态。这里不要把 JSONL 与 SQLite 当作天然的跨存储事务。

**实验 C02-C：成本而非单次 token。** 分别记录摘要输入/输出、后续请求输入、缓存命中、摘要延迟和最终任务成功率。评价依据应是同一任务的总成本与质量，本文不提供未经测量的节省比例。

## 6. 学习重点与验收

重点阅读历史构造与替换，不必先深挖摘要 Prompt。应能解释：为什么压缩需要元数据与稳定 ID；为何 pre/post hooks 的停止含义不同；为什么“会话已保存”不等于“当前请求已完整重建”。

验收产物：一份压缩前后对照表，明确原始记录、活动历史、模型输入三个层次，并给出一个信息丢失或失败恢复反例。

**迁移到 Agent Infra：** 上下文压缩是带质量约束的状态变换；需要版本、审计、成本归因，而不是只有一个压缩比例指标。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/thread-store/README.md
[S4]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/rollout-trace/README.md
