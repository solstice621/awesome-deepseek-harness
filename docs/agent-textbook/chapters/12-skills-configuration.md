# 第 12 章：Skills、项目指令与配置——知识的装配和能力的边界

[教材目录](../README.md)

**先修知识：**第 9 章的上下文快照、工具权限检查。**学习目标：**区分过程知识、项目规则与运行配置；理解发现、加载、失效和重新注入；设计可复现的配置作用域，避免把 skill 文本当作权限授予。

## 12.1 三种材料承担不同职责

**项目指令**描述在一个工作区或目录中持续适用的约定，例如测试命令、格式规则和金额计算方式。**Skill**封装某类任务的过程知识，例如怎样定位汇总错误、怎样制作表格；它通常包含名称、路由描述、正文以及按需读取的脚本或模板。**运行配置**选择模型、工具、权限、超时及插件装配，决定宿主实际怎样执行。

三者可以相互引用，但不能相互替代。skill 里写“发布到生产环境”，只是描述一个步骤；能否执行还取决于用户任务范围、工具授权与环境权限。项目文件写“使用 1000000 token”，不会让模型获得超出服务端限制的窗口。反过来，配置允许运行 shell，也不表示用户要求任意修改系统。

| 层 | 典型问题 | 变更后应检查 |
| --- | --- | --- |
| 项目指令 | 这里如何工作 | 目录范围、版本、模型是否看见 |
| Skill | 这一类任务如何完成 | 发现来源、正文、相对资源、适用条件 |
| 运行配置 | 当前有哪些可用能力 | 有效值、来源、权限约束、生效边界 |

设计 skill 时，描述是路由信息，正文是被选中之后的工作方法。把全部正文放进常驻目录会浪费上下文；只给名称不给触发条件，又使模型难以选择。一个合理的渐进加载过程是“摘要目录→所选正文→必要资源”。这只是设计模式，不意味着三个项目都用同一种 tool 或加载时机。

## 12.2 配置作用域不能只靠文件覆盖顺序解释

常见作用域包括组织、用户、项目、目录、会话、回合和步骤。更具体的配置是否覆盖更广配置，必须由每一项的合并契约决定。例如模型选择可按后者覆盖；工具允许列表可能取交集；插件集合可能按 ID 合并；安全要求可能只能收紧。一个泛化的 `deepMerge` 并不能表达这些语义。

应把“文件中写了什么”与“最终有效配置是什么”分开，并保留每个有效值的来源。热更新也要规定边界：当前步骤可完成旧快照，下一步骤使用新配置；或撤销当前步骤并重新选择，但不能让模型看到旧能力而执行器突然解释成新能力。可复现记录至少包含配置版本、工作区、模型路由、指令版本和工具目录观察。

同名 skill 的冲突同样需要明确规则。名称一致不表示内容相同；只按名称去重可能让用户的自定义流程静默覆盖项目流程。来源路径、provider、作用域和优先级都应可以检查。扫描不完整与“确实没有该 skill”也不同：暂时读不到目录时，不应毫无说明地把不完整观察缓存成永久空目录。

## 12.3 三个项目的源码导读

**Codex：项目指令、技能目录与执行能力各有状态。**AGENTS 加载器沿项目根到当前目录收集内容，遵守文档字节预算；当前项目不受信任时跳过项目指令。它也定义了 `AGENTS.override.md` 作为优先本地覆盖文件名，不能照搬别的项目的 `.local.md` 规则。[`agents_md.rs:7–18`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/agents_md.rs#L7-L18)，[`load_project_instructions:42–79`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/agents_md.rs#L42-L79)

`AgentsMdState::render_diff` 比较模型可见的目录和文本；变化时发替换通知，移除时发失效通知，而不是简单追加新文本让模型猜哪个生效。[`agents_md.rs:44–79`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/context/world_state/agents_md.rs#L44-L79)

skills 根加载接口支持调用方管理的解析快照；目录发现带扫描深度、条目上限以及 symlink/隐藏目录策略，且记录扫描是否完整。技能 world-state 代码特别区分“模型已显示过的目录”和“当前可执行授权”：目录显示快照不会代替每一步的实际发现。短的“重新可用”通知也只有在原目录正文仍在历史中时才成立。[`SkillRootSnapshotCache`，`loading.rs:39–46`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/skills/src/loading.rs#L39-L46)，[`discover_skills:65–98`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/skills/src/loader/discovery.rs#L65-L98)，[`world_state.rs:39–46`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/skills/src/world_state.rs#L39-L46)，[`world_state.rs:113–118`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/skills/src/world_state.rs#L113-L118)

配置加载器则枚举 package、管理层、系统、云、用户、profile、项目及 runtime 等层；`TurnContext` 保存回合配置，同时注明模型请求依赖 `StepContext` 快照。读到回合配置字段，不应推断所有设置在整个回合内永不变化。[`loader/mod.rs:123–135`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/config/src/loader/mod.rs#L123-L135)，[`turn_context.rs:321–331`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn_context.rs#L321-L331)

**OpenCode：配置发现与领域插件分工。**`Config.entries()` 声明按低到高优先级返回配置条目，`latest` 从末尾取某键的有效候选；变更流由配置层维护，领域模块自行解析和重建状态。这不意味着每一种集合字段都简单覆盖。[`config.ts:22–40`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/config.ts#L22-L40)

项目指令插件独立控制 global/project，读取全局 AGENTS.md 和向祖先发现的项目文件，并订阅候选路径变化；更新服务可呈现删除、添加，或在短 diff 与完整替换中选择更短者。这里的配置插件与第 9 章的按文件触达动态注入是不同入口。[`ConfigInstructionPlugin:23–55`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/config/plugin/instruction.ts#L23-L55)，[`InstructionDiscovery.renderUpdate:127–147`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/instruction-discovery.ts#L127-L147)

`Skill.available` 按 skill 权限过滤候选；实际 `skill` 工具仍调用 `permission.assert` 后再准备内容，避免把“曾出现在目录”当成当前授权。返回正文带基目录，文件列表最多采样十项，不能据此认定其余资源不存在。[`skill.ts:33–67`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/skill.ts#L33-L67)，[`SkillTool.execute:46–65`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/skill.ts#L46-L65)

**DeepSeek Harness：provider 注册表与文件系统发现分离。**skill 注册表定义 source、provider、locator、rank 和调用策略；低 rank 的同名候选优先，`modelInvocable` 与 `userInvocable` 分别决定模型和用户入口的可用性。这些是 skill 的发现/调用控制，不等于 shell、网络或文件写入的全部权限。[`SkillInvocationPolicy:48–54`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/skill/skill/src/index.ts#L48-L54)，[`SkillCandidate:76–91`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/skill/skill/src/index.ts#L76-L91)

文件系统 provider 从项目 `.dsh/skills`、`.agents/skills`、自定义根、用户根及 bundled 根构建候选；`get` 再从获胜 candidate 的 locator 读取正文。监听启动失败仍可返回可读候选，但标为 incomplete，这个设计没有把“本次看到一些结果”混同于“完整发现”。[`skill-filesystem/index.ts:181–224`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/skill/skill-filesystem/src/index.ts#L181-L224)，[`roots:244–263`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/skill/skill-filesystem/src/index.ts#L244-L263)

它的项目指令候选默认是 `AGENTS.md` 和 `CLAUDE.md`，本地叠加候选是 `AGENTS.local.md` 和 `CLAUDE.local.md`；同目录会加载存在的候选，再按去空白后内容去重，不能误写成“有 AGENTS 就永不读 CLAUDE”。基线身份包含根标记、候选顺序和预算，以判断恢复时旧基线是否仍适用。[`agent-instructions/config.ts:11–34`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/context/agent-instructions/src/config.ts#L11-L34)，[`workspaceBaselineIdentity:60–79`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/context/agent-instructions/src/config.ts#L60-L79)

## 12.4 贯穿案例：把可靠流程写成 skill

CSV 主案例是漏乘数量：pen 的单价 3.50、数量 2，book 的单价 12.00、数量 3，错误总额 15.50，正确总额 43.00。项目 AGENTS.md 规定金额使用 Decimal，用户要求修复并验证。一个 `csv-total-check` skill 可提供过程：确认列和单位→构造最小失败输入→定位聚合公式→补丁→边界用例→报告实际验证结果。

正文应解释为什么同时检查 `price` 与 `quantity`，而不是只给“把 float 换成 Decimal”的机械模板；使用 Decimal 仍可能漏乘数量。资源可以包含教学 CSV 和断言样例，按 skill 基目录解析。若正文引用 `scripts/check.py`，不能相对于当前项目随意拼路径，否则同名脚本可能被误执行。

有效步骤状态应记下选中 skill 的来源与内容版本、项目规则和实际工具权限。skill 更新增加“验证后发布”的步骤时，当前用户只要求修复和验证，该新增文字本身不能扩大任务授权。若 skill 已被删除，旧目录仍在上下文也不能证明它当前可加载。失败时先辨别“发现失败”“正文不存在”“资源路径错”“工具被拒绝”，不要统一报成模型没有遵循 skill。

## 12.5 练习与参考答案

1. **辨析题：**skill 中写“可以访问所有目录”，是否足以获得文件权限？

   **参考答案：**不足。过程文字和发现策略不等于执行许可；有效权限由宿主策略、用户授权与工具执行边界共同约束。

2. **源码题：**把三个项目的本地指令文件名统一为 `AGENTS.local.md` 有什么问题？

   **参考答案：**固定 Codex 实现使用 `AGENTS.override.md`；DSH 有自己的 local 候选与内容去重规则；OpenCode 所引配置插件发现 AGENTS.md。必须逐项核对产品契约，不能套用通用惯例。

3. **推理题：**一个 skill 展示了十个资源文件，可以断言其目录只有十个文件吗？

   **参考答案：**不能。OpenCode 的 `Skill.prepare` 对扫描结果做 `slice(0, 10)`，显示的是采样；需要按需读取实际目录。

4. **设计题（建议实验，未运行）：**创建同名的项目与用户 `csv-total-check`，加载后修改项目版本并移除其中一个资源，怎样验证实现？

   **参考答案：**检查获胜来源是否符合已声明顺序，变更是否在约定步骤边界生效，目录观察是否完整，加载正文与资源基路径是否匹配，失败是否保留可诊断来源。分别测试目录发现、正文读取和工具执行，不能用一次成功回答替代三层验证。

可延伸阅读旧专题：[Codex 扩展架构](../../agent-infra-study/codex/05-extension-architecture.md)、[OpenCode 扩展架构](../../agent-infra-study/opencode/05-extension-architecture.md)、[DSH 扩展架构](../../agent-infra-study/dsh/05-extension-architecture.md)。本章没有运行上游 skill 测试或配置热更新实验。
