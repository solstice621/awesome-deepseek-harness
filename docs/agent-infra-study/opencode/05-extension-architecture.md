# OpenCode 05｜Plugin Architecture：代际替换、就绪屏障与资源卸载

[返回总目录](../README.md) · P1 · 前置：Effect Scope、依赖注入、配置热更新

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。静态分析当前 Supervisor；不把历史设计草案当作 API 文档。

## 1. 先识别材料状态

`catalog-config-plugin-lifecycle.md` 明确标为 **Historical decision record**。其中选择了 B：Location-scoped Catalog transforms；A 是被否决的方案，接口片段也属于历史草图。它适合学习设计取舍，不适合直接复制代码。[S1]

当前生命周期要看 `plugin/supervisor.ts`，当前真实工具装配可看 `tool/plugin/subagent.ts`。[S2][S3]

## 2. 核心阅读入口

| 依据 | 已核对位置 | 学习目标 |
|---|---|---|
| [S1] | `specs/v2/catalog-config-plugin-lifecycle.md`，1–240 行 | 为什么拒绝任意 Config transform + 全服务 reload |
| [S2] | `core/src/plugin/supervisor.ts`，1–270 行 | resolve、generation、activate、失败保留、触发合并 |
| [S3] | `core/src/tool/plugin/subagent.ts`，1–310 行 | tool transform 与 session hooks 的真实调用 |
| [S4] | `core/src/session/runner/llm.ts`，1–280 行 | 执行前 awaitActivation |

## 3. Supervisor 如何管理变化

`resolve()` 处理配置中的增加/移除操作、内建与外部插件、pending 安装、加载失败和重复 ID。新 revision 加载失败时，会保留原来正在运行的 generation；重复 ID 保留启动顺序中的第一项，并把后续冲突单独记为失败，而不是让整代内建插件一起失效。[S2]

`activate()` 先激活本地已经可用的模块，再处理待安装包。异步检查更新时使用 generation 编号，避免旧一轮结果在新一轮已经开始后覆盖状态。[S2]

**分析：** generation 是处理过期异步结果的一种办法，但不是全局配置版本共识。它在这里约束的是一个 Location 的插件管理生命周期。

## 4. 触发合并与就绪不能脱节

Supervisor 使用容量为 1 的 sliding queue 保留最新变更请求，启动阶段立即激活，之后的变更做 debounce。接收到变化时先增加 observed 并 hold registry，让 `awaitActivation` 能看见有待处理工作，而不是变更被合并后短暂呈现“已经就绪”。[S2]

Runner 在执行前等待插件激活。[S4] 这体现了配置更新与执行接纳的连接：不能让一个请求在工具/策略贡献只装了一半时开始。

## 5. 卸载为什么不是删除 Map？

代码为 registry.close 安装 finalizer，要求内建插件在它们捕获的服务关闭前卸载；activation 与依赖资源的生命周期有严格顺序。[S2]

**分析：** 热更新最容易出问题的不是新插件加载，而是旧任务仍引用旧服务、旧回调仍收到新事件、旧释放器误删新注册。应检查代际、Scope 与活动请求快照如何配合，而不能把 HMR 当成 UI 开发便利功能。

## 6. 历史方案的可迁移经验

被否决的任意 Config transform 可以修改任何字段，因此无法安全判断只重载 Catalog 是否足够；每次都全服务 reload 又会扩大影响面。选定的 Catalog transform 将重建范围缩小到 Catalog 的职责。[S1]

这是一项架构取舍记录，不是“任意插件都永远不能修改配置”的普适定律。学习重点是 **把可变能力的影响面限定在有明确所有者的域里**。

## 7. 待运行实验

**O05-A：坏更新保留旧版本。** 做一个只提供合成工具的本地插件，先加载有效版本，再制造导入失败。验证旧 generation 是否仍服务、失败是否独立展示。

**O05-B：配置突发。** 快速连续产生三次不同配置变化，记录 observed、generation 与 activate 次数，检查旧异步更新结果不会覆盖新状态。

**O05-C：运行中卸载。** 让一个工具阻塞，在任务尚未结束时禁用插件，观察已捕获请求、旧作用域和新请求的行为。本文未核验 registry 内部卸载的全部实现，实验用于补足这部分证据。

## 8. 验收

画出“配置变更 → hold → resolve/activate → 代际检查 → release → Runner 可继续”的时序，并对加载失败、重复 ID、卸载失败分别说明故障域。

能回答：历史 ADR 与当前 API 为什么要分开读？为何 failed reload 保留旧 generation？为何事件合并前仍要记录存在未完成激活？

**迁移到 Agent Infra：** 这是学习动态能力装配、配置就绪屏障与升级故障隔离的样本，比单纯编写几个 hook 更接近平台工程。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/catalog-config-plugin-lifecycle.md
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/plugin/supervisor.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/subagent.ts
[S4]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
