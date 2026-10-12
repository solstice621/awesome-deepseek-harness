# Codex 06｜Task Orchestration：子 Agent 身份、上下文与执行归属

[返回总目录](../README.md) · P1 · 前置：01/03/07；父子资源生命周期

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。重点分析 `LocalAgentControl` 的 fork、身份恢复与 V2 reload；不是所有多 Agent 模式的完整审计。

## 1. 子 Agent 不是多起一个 LLM 请求

它需要独立身份、明确父子关系、可传递上下文、执行容量、环境权限和结果归属。只追踪工具名 `spawn_agent` 会漏掉大部分系统问题；源码中还存在测试辅助入口，不能把带 `cfg(test)` 的包装函数当成唯一生产入口。

## 2. 核心依据

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `core/src/agent/control/spawn.rs`，1–260、300–540 行 | fork 过滤、元数据恢复、ensure_v2_agent_loaded、parent ownership |
| [S2] | `rollout-trace/README.md` | 父子线程如何关联到同一诊断图 |
| [S3] | `ext/extension-api/src/registry.rs`，1–230 行 | 宿主接纳门的边界 |

## 3. 上下文继承：复制哪些，不复制哪些？

`keep_forked_rollout_item` 是一个具体的历史过滤函数。已读逻辑保留某些用户/系统/开发者信息和回答，排除多种运行时记录、工具细节及父线程累计 TokenUsageRecord；是否保留上下文基线还有参数控制。[S1]

开发者消息也有清理：父角色、特定批准信息、时间提示及多 Agent 使用提示不能不加区分地复制。**分析：** 继承模型理解任务所需的信息，与继承父任务的权限证明和累计指标，是两回事。不能据此宣称所有 fork 模式都使用同一个过滤策略。

`SpawnInitialInput` 将普通 UserInput 与带上下文的 InterAgentCommunication 表达为不同变体，后者把通信与归因上下文一起携带。类型系统在这里用于阻止缺少上下文的通信进入后续生命周期。[S1]

## 4. 身份恢复不等于运行时恢复

`restore_v2_agent_metadata` 明确只恢复持久化身份，不重新打开全部 runtime。存储读取可以并行，但名称和路径预留按图顺序处理。[S1]

这让学习对象分成：持久化 Agent 图、内存 registry、实际加载的线程、正在运行的 Turn。**分析：** 将身份与驻留解耦，有利于控制大量子任务的内存成本；但本篇没有测量这一收益，也没有证明它具有分布式执行能力。

## 5. reload 前的归属校验

`ensure_v2_agent_loaded` 检查调用方提供的父线程是否仍然加载、运行、属于同一个 registry，并核对存储中的 parent 信息。它还保留 residency pin，要求调用者在提交输入前维持该驻留关系。[S1]

恢复配置时并不是把磁盘旧配置原封不动拿回来。代码检查当前父权限、执行策略、环境就绪状态、cwd/workspace roots 等条件；部分远程权限变化会被拒绝。**分析：** 这是“恢复不能扩大当前授权”的实例。旧历史能被读懂，不代表过去的执行授权仍然有效。

## 6. 待运行实验

**C06-A：上下文 fork 对照。** 为父线程准备目标、临时角色提示、一个工具批准和累计 token 信息；触发对应 fork 模式，检查子线程实际收到哪些内容。必须记录所用模式，不能把一个分支结论套到所有子 Agent。

**C06-B：冷身份与热 runtime。** 创建多个子线程后触发卸载/恢复，分别统计 registry 身份、加载线程、运行任务数。验证“列表中存在”是否等于“正在占用运行时”。不要在没有观察数据时宣称节省了多少内存。

**C06-C：恢复时权限变化。** 在隔离环境中收紧父权限或改变执行环境，再尝试恢复子线程；检查错误是否指出归属/策略变化，而不是静默按旧权限启动。

## 7. 学习重点与验收

绘制四层图：持久化 Agent 图 → 本地 registry → resident runtime → active Turn；给每层标出创建、恢复、取消、释放的责任方。再画一次父任务取消与子任务结果返回的竞争时间线，把未追踪的路径标为待研究。

应能解释：为什么身份恢复可以不加载 runtime；为何 fork 不继承累计 token；为什么 parentID 字符串相同还不够，还需要验证当前活对象和 registry 归属。

**迁移到 Agent Infra：** 任务身份、容量、驻留、授权和执行必须拆开建模。这里学到的是本地生命周期设计；跨机器的调度公平性、租约和副作用幂等仍需独立解决。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/agent/control/spawn.rs
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/rollout-trace/README.md
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/extension-api/src/registry.rs
