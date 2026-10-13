# 第 2 章　模型接口：消息、Token 与生成边界

[教材目录](../README.md) · 上一章：[Agent 系统](01-agent-systems.md) · 下一章：[运行时架构](03-runtime-architecture.md)

**先修要求：**第 1 章；能理解 JSON 对象与 HTTP 请求。**学习目标：**能够描述一次模型请求的组成；区分内容、控制参数与使用量；解释结构化输出能保证什么；避免把可见文字、推理数据和预算混成同一概念。

## 2.1 模型调用是一份有边界的请求

一次模型调用可以抽象为“给定输入与生成约束，返回内容以及结束状态”。对 Agent 来说，响应内容可能包含自然语言，也可能包含工具调用。工具调用只是待处理的结构化请求；外部动作是否发生，还取决于宿主验证和执行。

请求通常包含模型选择、指令、按顺序排列的历史消息、工具声明与生成参数。还可能含缓存、路由和传输元数据。这里的“通常”是一种接口设计归纳，不表示所有供应商接受相同字段，也不表示可以把一个项目的对象原样传给另一个项目。

CSV 修复任务的一次中间请求可用下列**教学格式**表示。这里的字段名不承诺与某个供应商 API 完全一致。

```json
{
  "model": "selected-model",
  "instructions": "只修改工作区，结论必须对应验证证据",
  "messages": [
    {"role": "user", "text": "修复 CSV 订单总额漏乘数量的错误并验证"},
    {"role": "assistant", "tool_call": {"id": "c1", "name": "read_file"}},
    {"role": "tool", "call_id": "c1", "text": "total += Decimal(row['price'])"}
  ],
  "tools": [{"name": "apply_patch", "argument_schema": "..."}],
  "generation": {"max_output_tokens": 1200}
}
```

模型看到的是这份请求中的表示，不是自动读取当前磁盘。模型返回新的 `read_file` 请求，也不意味着旧历史会自动更新；Harness 必须执行、记录并重新组装下一份输入。服务端缓存或连续响应机制可能减少重复传输，但不取消这份语义责任。

## 2.2 Token 是预算单位，不是字数

Token 是模型处理文本时采用的离散单位。一个词、汉字、符号或代码片段可能对应不同数量的 token；因此“字数乘固定系数”最多是估算，不是精确计数。多模态输入还可能使用模型特定的计量方式。

应区分三个量。**上下文容量**限制某次请求可容纳多少内容；**单次输出上限**约束这次生成能继续多长；**任务累计预算**限制一串请求花费多少资源。把每次输出上限设得很小，不能阻止 Agent 发起一百次请求。反过来，累计使用很多 token，也不必然意味着当前上下文已满，因为历史可能被压缩或丢弃。

设一次教学请求的指令、历史、工具说明分别消耗 400、2600、500 个输入 token，并预留 1000 个输出 token，则容量规划至少要考虑 4500 个 token 及协议余量。这个加法用于说明各项竞争同一有限空间；真实模型对输入、输出和推理预算的约束必须按对应适配器与服务契约核对。

重复携带历史会导致累计输入量增长：第 2 次请求包含第 1 次的工具结果，第 3 次又可能包含前两次的上下文。缓存能够改变某些输入的计费或处理方式，却不能据此假定“缓存内容不占当前上下文”。因此应分别记录模型可见大小、调用累计量和价格类别，而不是只留一个 `tokens` 数字。

## 2.3 消息角色、来源与内容类型

角色说明一段内容在对话协议中的位置，如用户输入、助手响应、工具结果。来源说明它由谁产生，例如真实用户、运行时注入、检索系统或工具。二者不必一一对应：运行时为了兼容模型协议，可能把某些上下文投影为用户角色，但其来源仍然应单独记录。

这一区分直接影响可信度。源文件里的“忽略所有限制”是待分析的数据，不能因为它被读入上下文就变成宿主指令。工具返回“测试通过”也仍需结合调用对象和退出状态解释。协议角色不是业务真实性证明。

一条助手消息也未必只有字符串：它可以包含文本块、工具调用块，以及供应商允许回传的推理相关块。工程上应保持块类型与关联 ID，避免把所有内容拼成一段文本后再用关键词猜测。工具结果关联的是调用 ID；两个同名测试命令也可能属于不同调用。

## 2.4 推理控制与可见输出不能互相代替

“推理强度”通常是模型或适配器支持的一项控制；可见的解释、推理摘要、内部推理 token 计数和供应商专用回放状态，则是不同对象。存在摘要，不意味着系统取得了全部内部推理过程；文本解释写得长，也不能证明模型消耗了更多内部计算。

对软件工程而言，可审计证据应优先包括请求配置、工具动作、结果、补丁与验证。不要把记录“思考文字”当成完整调试方案。CSV 任务中最有用的问题是“哪个输入复现了漏乘数量”“补丁改了什么”“哪个验证对应这次补丁”，这些问题都能由外部行为回答。

温度和 top-p 等采样参数影响输出选择，推理强度影响模型支持的推理行为，两者不是同一个旋钮。较低温度不能保证事实正确，也不构成跨服务、跨版本的确定性承诺。记录参数有助于复现实验条件，但测试仍应检查允许的结果和不变量。

## 2.5 结构化输出只解决一部分问题

让模型输出 JSON 有三个不同层次：文本可以解析；对象符合 schema；对象在业务上正确。前两项可以机械检查，第三项仍需事实与业务规则。

例如要求模型给出 `{ "expected_total": "43.00", "tests_passed": true }`，schema 可以约束总额为字符串、测试结果为布尔值，却无法证明测试真的执行过。更好的设计让测试工具产生不可混淆的结果对象，模型报告引用该结果，而不是让模型自行声明一个布尔值。

工具参数也遵循这条原则。即使 `path` 是字符串、`patch` 符合格式，也仍需检查路径范围、文件当前版本和操作权限。结构化输出提高机器消费的可靠性；它不把模型内容升级为执行授权。工具执行细节在第 6 章展开。

## 2.6 三个项目的接口映射

**Codex 将输入内容与输出要求分开。**`Prompt` 包含 `input`、工具声明、基础指令与可选 `output_schema`；`output_schema_strict` 默认值为 `true`。实际请求构建时，`build_reasoning` 依据模型能力选择是否携带摘要参数，随后将 schema 与 verbosity 转成 `text` 配置。这说明“模型能力”必须参与请求生成，不能只把 UI 设置机械复制过去。见 [`Prompt`，21–54 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client_common.rs#L21-L54)、[`build_reasoning`，929–947 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs#L929-L947) 与[请求构建，1022–1048 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs#L1022-L1048)。这些代码表明客户端发送什么，不单独证明远端每一种 schema 的行为。

**OpenCode 建立独立的请求与生成选项类型。**`LLMRequest` 分开保存 `system`、`messages`、`tools`、`toolChoice`、`generation` 与 provider 选项；`GenerationOptions` 列出 `maxTokens`、温度、top-p、seed、stop 等字段。统一类型便于上层表达请求，但具体字段能否被目标模型使用仍由下游路由处理，不能从“类型里有”推断“所有模型都支持”。见 [`LLMRequest`，385–409 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/schema/messages.ts#L385-L409) 与 [`GenerationOptions`，94–103 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/schema/options.ts#L94-L103)。

**DeepSeek Harness 显式保存角色之外的来源。**`MessageBase` 带稳定 ID、内容块和 source；工具消息另有 `toolCallId` 与 `isError`。`GenerateOptions` 包含 provider、model、messages、tools、`reasoningEffort`、temperature 与 maxTokens。推理块和可见文本块也分型定义。这里观察到的是共享抽象和类型契约，而非每个 provider 的全部 wire 协议。见[消息类型，138–179 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/message.ts#L138-L179)、[内容块，61–71 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/types.ts#L61-L71) 与 [`GenerateOptions`，510–541 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/types.ts#L510-L541)。

一个特别容易踩坑的差异是 **同名 token 字段口径不同**。OpenCode 的 `Usage.inputTokens` 是包含缓存读写的输入总数；DSH 的 `TokenUsage.inputTokens` 仅含未缓存输入，缓存另列。见 [OpenCode Usage 契约，23–39 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/schema/events.ts#L23-L39) 与 [DSH TokenUsage 契约，167–188 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/types.ts#L167-L188)。若同一次教学请求有 900 个新输入 token、2100 个缓存读取 token、无缓存写入，那么前者的 input 是 3000，后者的 input 是 900。比较之前应归一口径，不能认为后者节省了 70% 的上下文。

## 2.7 不变量、失败场景与练习

建议维护三项不变量：模型输入中的每个工具结果关联已有调用；统计字段保留计量口径；停止原因和业务成功分别保存。典型失败是把 `max-tokens` 截断响应当成完整答案，继而尝试解析半个 JSON 或宣告修复完成。正确处理应先检查响应状态，再决定重试、继续或报告未完成。

1. 字符串长度为 1000，能否据此判定它恰好需要 1000 个 token？<br>
   **参考思路：**不能。需要对应 tokenizer 或供应商返回的使用量；估算结果应标注为估算。
2. 前述 3000 个输入 token 中有 2100 个缓存命中，模型“只看见了 900 个”吗？<br>
   **参考思路：**不是。缓存改变处理或计量分类，不能从中删掉逻辑输入。OpenCode 与 DSH 的数值差别是统计口径差别。
3. schema 要求 `tests_passed` 为布尔值，返回 `true` 是否可以关闭任务？<br>
   **参考思路：**不能。schema 检查结构，工具执行证据与任务验收检查真实性。
4. **设计题：**为 CSV 修复结果设计一个可审计的数据对象。<br>
   **参考思路：**至少有变更文件、复现输入、期望输出、验证调用 ID、退出状态、终止原因与未解决项。由工具层提供执行事实，模型填写解释；避免只有一个 `success` 字段。

进一步阅读现有的 [Codex](../../agent-infra-study/codex/04-llm-streaming.md)、[OpenCode](../../agent-infra-study/opencode/04-llm-streaming.md)、[DSH](../../agent-infra-study/dsh/04-llm-streaming.md) 接口导读。流式协议与故障处理将在后续专章展开；本章算例为静态教学推演，未发出付费模型请求。
