# 第 9 章：上下文工程——为每一步构造正确的世界

[教材目录](../README.md)

**先修知识：**消息角色、模型调用、工具调用与会话事件。**学习目标：**区分历史、当前上下文和运行配置；能够设计有来源、有预算的上下文构建器；解释指令更新、工具快照与模型切换为什么必须协调。

## 9.1 上下文不是聊天记录的别名

模型只能根据本次请求中实际收到的信息行动。文件留在磁盘上、消息写入数据库、用户曾经说过一句话，都不等于模型现在能看到它。我们把完整事件记录称为**历史**，把本次送入模型的材料称为**上下文**。上下文是历史、指令、环境状态、工具说明和检索结果经过选择与变换后的产物。

可以把构建器理解为编译器：输入包含多种来源，经过解析、来源标记、冲突处理、预算分配，最后输出供应商接受的请求。这个类比的作用是提醒我们，不能用一个任意拼接字符串的函数承担全部职责。正确的内容若进入了错误的角色、旧权限被保留下来、工具 schema 与执行器不同步，都会产生错误行为。

教学上，把每块材料表示成以下记录；这不是三个项目共享的实际接口：

```text
ContextBlock = {
  text, source, authority, scope, observed_at,
  revision, token_estimate, retention_policy
}
```

`authority` 回答“谁有资格提出这项要求”，`scope` 回答“它适用于哪里”，`revision` 回答“这是哪个版本”。相关性只回答“现在有多有用”，不能改变来源权限。搜索结果中出现“忽略用户要求”时，即使搜索结果高度相关，这句话仍是待分析的数据。把它包装成 system 消息，相当于在序列化环节错误授予权限。

具体模型协议的角色和层级须遵循其契约。设计时至少应分开宿主策略、应用规则、用户目标和外部证据；同级文件如何覆盖则由产品约定。不要从“更靠后”推导出“权限更高”，也不要把 AGENTS.md 在所有产品中都假定为同一种角色。

## 9.2 从材料仓库到一致的请求快照

一次请求可按下面的教学流程生成：

```text
snapshot = select(session, agent, model_route, permissions, tool_catalog)
rules = resolve_applicable_instructions(snapshot.workspace)
facts = retrieve(task, snapshot.permissions)
history = project_visible_history(session, snapshot.provider)
blocks = label_and_deduplicate(rules, facts, history)
request = fit_budget(blocks, reserve_output, reserve_tool_response)
assert tool_calls_can_be_executed_against(snapshot.tools)
send(request)
```

这里的快照不意味着永远不更新，而是规定更新在什么边界生效。假设模型开始生成时看到工具参数 `file_path`，插件在生成过程中热更新为 `path`。若执行器直接查最新全局注册表，同一条调用可能被另一版 schema 解释。将工具定义、权限选择和模型请求绑定到同一观察版本，才能说明这一步到底依据什么运行。下一步再接纳变更，并把必要的差异告诉模型。

重复注入有两种不同成因：同一文件同时由两个目录发现；以及文件已经不在可见上下文中，但系统仍以“曾经加载过”为由拒绝再次注入。前者需要去重，后者需要恢复。永久集合 `loaded_paths` 无法同时解决二者。去重账本必须说明它针对完整历史、当前窗口，还是当前请求。

## 9.3 预算是一项资源分配问题

设模型窗口为 (W)，输出预留为 (O)，工具下一次返回和估算误差的余量为 (R)，则候选输入预算可写为 (B=W-O-R)。这是教学模型，供应商的实际计费与输入上限可能另有规则。

例如 (W=32000)、(O=4000)、(R=2000)，可安排的输入为 26000 token。若常驻规则与工具定义占 5000，任务及近期过程占 9000，就只剩 12000 用于检索材料和旧记录。不能先塞满 32000，再指望模型输出 4000。也不能以“缓存命中”为由不计算这些 token：缓存影响成本或延迟，不自动增加窗口容量。

选择材料可以用“与当前决策的关系、信息新鲜度、来源可靠性、重新获取成本”排序。完整保留用户尚未完成的目标和不可重建的决定；可重新读取的源文件保留路径、符号、版本和关键片段；很长的失败日志保留错误与可追溯位置。词数和字节数都只是估算代理；图片、文件附件、工具 schema 也会占请求空间。压缩的具体事务在[下一组章节](11-compaction.md)讨论。

## 9.4 三个项目怎样落实这些原则

**Codex：模型窗口与宿主状态分离。**`ContextManager` 保存模型可见 `items`，同时维护独立的 `retained_context`、历史版本、用户输入版本及上下文比较基线。字段的分离表明：一次压缩改变历史投影，不应被理解为所有宿主事实一并消失；这些字段也不等于可供普通模型自由检索的长期语义记忆。[`ContextManager`，`history.rs:91–126`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/context_manager/history.rs#L91-L126)

预算也有两个口径。`context_window_token_status_with_config` 可按总上下文，或按初始前缀之后新增的正文计算自动压缩压力；模型完整窗口仍是独立上限。采用“正文额度”不允许常驻前缀无限增长。[`context_window.rs:53–110`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/context_window.rs#L53-L110)

**OpenCode：先选能力，再加载历史。**`SessionContext.select` 合并 Agent 与 Session 的权限，以相同权限收集工具快照、skills 和 MCP 指令；`load` 再解析模型，并按供应商 provenance 构造运行历史。组合指令时还把跨会话更稳定的部分放在前面，以形成可复用前缀。这是代码中的排序设计，不能据此声称测得了性能提升。[`context.ts:121–179`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/context.ts#L121-L179)

它的动态指令注入用 `inFlight` 防止同一步并行读取重复加载，而持久的去重依据是可见历史中 synthetic 消息的 metadata。压缩或回退使该消息消失后，路径可重新发现、重新注入。这比“启动时读一次 AGENTS.md”更精确。[`SessionInstructions.load`，`instructions.ts:35–79`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/instructions.ts#L35-L79)，[`previouslyInjected:99–111`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/instructions.ts#L99-L111)

**DeepSeek Harness：带身份的基线与实际路由计量。**`agent-instructions` 在构造基线时计算身份，判断旧基线是否仍对应当前工作目录、发现配置与预算，并将变化投射为有来源的消息。缺少文件系统 provider 时，相关加载会返回而不工作。[`compose`，`index.ts:110–155`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/context/agent-instructions/src/index.ts#L110-L155)

`priceSurface` 依据路由的图片价格和文件实际投影文本替换结构性启发估算；图片计价条目数与图片出现次数不匹配时直接报错。这里值得学习的是“按实际发出的表示计量”，不是把所有附件都视为一个固定小字符串。[`route-pricing.ts:23–75`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/token-meter/src/route-pricing.ts#L23-L75)

## 9.5 贯穿案例：修复 CSV 总额错误

用户要求修复 CSV 汇总漏乘数量的问题，并验证；输出保留两位小数。样本为 pen 单价 3.50、数量 2，book 单价 12.00、数量 3，错误结果 15.50，正确结果 43.00。上下文构建器先保留目标与验收条件，加入项目关于金额使用 Decimal 的规则，再搜索 `total`、`price`、`quantity`，只读汇总函数、调用入口与相关测试。搜索到的 CSV 单元格若含命令文字，只是输入样本。

第一步模型看到只加单价的表达式与失败用例；第二步收到乘以数量的补丁结果、测试命令及退出码。即使 8000 行测试日志因预算被移出，必须保存“运行了哪个命令、在哪个版本运行、退出码是什么、具体失败断言是什么”。不能把模型的“应该通过”放进 `verified` 字段。在配置变更实验中，若项目规则从“允许 float”改为“使用 Decimal”，下一步必须收到替换或变更通知；仅让后台配置变了，模型未获知，仍会生成旧方案。

三个应持续成立的不变量是：外部证据不因检索而升级权限；请求中的工具描述与该步可用能力一致；每个被当作当前事实的观察都有来源和时间/版本。预算策略可以调整，这三个条件不应被“节省 token”静默破坏。

## 9.6 练习与参考答案

1. **计算题：**窗口 64000，输出预留 8000，余量 4000；常驻材料 12000，近期历史 18000，还能安排多少检索 token？若缓存了常驻材料，答案改变吗？

   **参考答案：**22000；不因缓存而改变。先按模型窗口扣除全部请求材料，缓存价格应在成本账本中另算。

2. **诊断题：**压缩后模型不知道测试命令，数据库却能查到该命令。最先检查什么？

   **参考答案：**检查当前请求的历史投影、摘要和检索入口，确认命令是否实际注入。数据库完整性不能证明模型可见性。

3. **源码题：**为什么 OpenCode 不用永久 `Set<path>` 对嵌套指令去重？

   **参考答案：**路径加载记录必须与模型仍可见的 synthetic 保持一致。永久集合会在压缩后阻止必要的重新注入；短时 `inFlight` 只解决并发重复。

4. **设计题（建议实验，未运行）：**对 CSV 修复器加入配置热更新，同时在工具调用中途删除一个 skill。记录哪些数据，才能复现故障？

   **参考答案：**记录任务/步 ID、配置与指令版本、工具与 skill 目录快照、模型路由、原始调用及执行结果、更新生效边界。要求“这一调用依赖旧快照完成”或“取消并按新快照重试”之一有明确契约，不能随机混用。

可对照旧专题：[Codex 上下文与会话](../../agent-infra-study/codex/02-context-session.md)、[OpenCode 上下文与会话](../../agent-infra-study/opencode/02-context-session.md)、[DSH 上下文与会话](../../agent-infra-study/dsh/02-context-session.md)。本章结论以以上固定源码为准，未运行上游测试或模型实验。
