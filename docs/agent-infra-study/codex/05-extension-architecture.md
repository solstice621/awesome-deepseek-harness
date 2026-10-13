# Codex 05｜Extension Architecture：类型化贡献点与生命周期边界

[返回总目录](../README.md) · P1 · 前置：Rust trait、Arc、依赖注入；先完成 01/03

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。静态源码分析，不等同于已经验证某个外部插件的兼容性。

## 1. 首先纠正一个路径与概念

本次固定提交的类型化扩展注册表位于 **`codex-rs/ext/extension-api/`**，不是 `codex-rs/extension-api/`。`ExtensionRegistry` 是宿主安装的 Rust 类型化贡献机制；不能因为名字包含 Extension，就把它与任意热加载脚本、Skills、用户插件包、MCP Server 视为同一种扩展。[S1]

本篇聚焦内核扩展契约。MCP 和 Skills 在哪里接入，是进一步追踪各 contributor 的问题，不在未读代码处补出一套统一插件系统。

## 2. 关键入口

| 依据 | 已核对位置 | 作用 |
|---|---|---|
| [S1] | `ext/extension-api/src/registry.rs`，1–230 行 | builder、immutable registry、typed contributors、turn admission |
| [S2] | `core/src/session/turn.rs`，已读入口和主循环段 | 消费钩子与贡献的实际时机 |
| [S3] | `core/src/tools/parallel.rs`，1–275 行 | 扩展与异步执行的作用域关联 |

## 3. 注册表的设计

`ExtensionRegistryBuilder<C>` 收集贡献者，`build()` 生成不可变注册表。已读类别包括线程/Turn 生命周期、配置、token usage、skills、审批审查、上下文、MCP、输入、工具、工具生命周期、模型请求和 Turn item。[S1]

重要的不是接口数量，而是**每个接口对应的修改权限和执行时机**。例如上下文贡献者不必知道工具进程内部实现，工具生命周期贡献者也不应自行重复调用 Turn 输入接纳。研究时给每种接口标注：输入、返回值、是否可能影响控制流、是否允许产生副作用。

`to_builder()` 复制既有 contributor 的 Arc，供宿主增加贡献。**分析：** 注册表不可变减少运行时结构变化，但不保证 contributor 内部无可变状态；Arc 共享也不自动保证调用方的业务幂等。真正的并发安全仍须阅读实现者。

## 4. 一个值得深挖的入口：TurnStartAdmission

`admit_turn_start()` 返回宿主提供的 permit；缺少 permit 会在 Core 消费 pending input 之前拒绝启动。未配置 gate 时，存在默认允许的路径。[S1]

这说明资源接纳应该发生在**消费工作之前**，而不是拿走输入、做到一半才发现没有执行额度。**分析：** 这个 seam 适合挂接本地容量控制或宿主策略；但它本身没有证明跨节点的租约、配额一致性或租户隔离已经实现。

学习时追问 permit 的所有者、释放时间、取消时的 drop 行为，以及扩展是否能在读取完输入以后抛错。仅理解注册方法不够。

## 5. 与 DSH / OpenCode 比较时的正确粒度

Codex 本篇展示的是强类型、宿主装配的贡献接口；DSH 将服务与默认 Loop 本身置于可配置插件树；OpenCode 当前实现还有按 Location 管理的插件代际。[分别参见 DSH 05](../dsh/05-extension-architecture.md) 与 [OpenCode 05](../opencode/05-extension-architecture.md)。

比较应该围绕：何时可以替换、谁拥有资源、卸载是否等待正在执行的工作、失败会影响谁。不要用“插件多/少”评价基础设施设计。

## 6. 待运行实验

**C05-A：接纳失败不丢输入。** 在测试宿主中安装可控 TurnStartAdmission，让第一次返回无 permit，第二次允许。检查拒绝期间 pending input 是否保留，并确认同一输入只被接纳一次。此为实验设计，不代表已运行该接口。

**C05-B：贡献者生命周期。** 安装一个只记录事件的 contributor，执行正常完成、取消和错误三种 Turn，比较回调顺序与资源释放；记录实际顺序，不凭 vector 存放顺序推定全部调用顺序。

**C05-C：共享状态风险。** 为同一 contributor 模拟两个会话并发调用，检查是否把上一会话信息泄漏到下一会话。只用合成数据，避免把真实 Prompt 写入公开日志。

## 7. 学习重点与验收

应产出一张扩展点权限表，至少覆盖 input、context、tool、model request、lifecycle、admission。每个点都能说明什么适合放进去，什么不应放进去。

核心自测：不可变 registry 为什么仍需审查 contributor 线程安全？接纳 gate 为什么放在消费输入前？类型化内核扩展为何不等于面向用户的热加载插件？

**迁移到 Agent Infra：** 把容量控制、审计和策略插入稳定 seam，通常比在 Loop 中不断增加特殊分支更可维护；这是一项设计分析，不是对任何未读扩展的功能保证。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/extension-api/src/registry.rs
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs
