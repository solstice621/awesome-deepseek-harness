# 第 8 章　模型适配与流式协议：把字节变成可信的行动输入

[教材目录](../README.md)

**先修知识：**异步迭代器、JSON、HTTP 请求、工具调用与结果的基本关系。**学习目标：**能画出模型请求的分层边界；实现不会把半截参数交给工具的聚合器；区分正常结束、截断、故障和取消；根据已经产生的输出决定重试范围。本章讨论固定提交中的实现，示例与伪代码是教学模型，不是三个项目共用的 API。

## 8.1　为什么不能把模型当成一个返回字符串的函数

修复 CSV 汇总程序时，模型可能先输出解释，再发起读取文件的调用，再根据结果提交补丁。网络却只给客户端一串陆续抵达的字节：一个汉字的 UTF-8 字节可能跨两个读取批次，一个 SSE 事件可能跨多个批次，一个工具参数对象又可能跨多个事件。它们是三种不同的边界。

**Provider 适配器**负责把内部的消息、工具定义和模型选项翻译为供应商请求，再把供应商事件翻译成内部事件。它不应仅仅换一个 URL：不同协议的结束原因、工具标识、缓存计量和重放信息都可能不同。**传输层**处理连接与字节；**协议层**处理事件语法；**组装层**恢复完整内容；**执行层**决定某个调用是否可以产生副作用。

```mermaid
flowchart LR
  A[内部消息与工具定义] --> B[请求适配]
  B --> C[HTTP 或 WebSocket]
  C --> D[字节解码与事件分帧]
  D --> E[协议事件归一化]
  E --> F[按调用标识聚合]
  F --> G[完成参数与校验]
  G --> H[工具执行策略]
  E --> I[文字或参数预览]
```

这里有一个核心不变量：**预览事件不会自行获得执行资格。**即使补齐引号后“看起来像 JSON”，也不意味着供应商已经完成调用，更不意味着调用通过参数模式、权限或业务前置条件检查。

Codex 的请求构造同时设置模型、输入、工具、工具选择、推理配置、流选项和缓存键；这体现了适配器的输入面远大于提示词字符串。其 `stream()` 根据能力和会话状态选择 Responses WebSocket 或 HTTP，两种连接承载同一类模型请求。[Codex 请求构造](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs#L1067-L1084)、[传输选择](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs#L2332-L2370)

## 8.2　流式工具参数是一台状态机

以调用 `read_file({"path":"totals.py"})` 为例，模型的输出可先后包含调用标识 `call_7`、名字 `read_file`、参数片段 `{"path":"tot` 和 `als.py"}`。不能按“最后一个工具”存参数，因为两个调用的片段可能交错。至少需要：流内键、最终调用 ID、工具名、原始参数缓冲区、是否结束、是否已发出执行事件。

“流内键”与“最终调用 ID”也不是必然相同：供应商可以使用内容块序号关联片段，另用 `call_7` 关联工具结果。OpenCode 的 `ToolStream.State<K>` 为此允许字符串或数值键；`inputDelta` 的宽容解析用于提供局部预览，而最终 `toolCall` 走 `parseToolInput`。本地工具参数解析失败时产生 `toolInputError`，不会把预览对象当成正式调用。[状态与预览](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/protocols/utils/tool-stream.ts#L19-L98)

教学实现可以保持这样的分工：

```text
on_delta(stream_key, fragment):
    pending[stream_key].raw += fragment
    publish_preview(pending[stream_key].raw)   # 不能在这里执行

on_call_done(stream_key, authoritative_args?):
    p = pending[stream_key]
    raw = authoritative_args ?? p.raw
    args = strict_json_parse(raw)
    validate_tool_schema(p.name, args)
    emit_ready_call(p.call_id, p.name, args)
    close(stream_key)

on_eof():
    if protocol_terminal_not_seen:
        fail_attempt("incomplete stream")
```

这段伪代码刻意没有规定“完整调用一到就执行”还是“整条模型响应结束后执行”。前者降低等待时间，后者把失败恢复集中在响应边界；它们都必须把未完成参数与可执行调用分开。还要规定重复关闭、未知键、关闭后的片段、缓冲区上限以及取消后的资源清理，否则状态机只覆盖了正常路径。

一个容易漏掉的情况是，结束事件再次携带完整参数。若把它追加到缓冲区，将得到两个 JSON 对象连在一起。OpenCode 的 `finishWithInput` 明确让最终参数覆盖已累计的片段；Responses 的 `function_call` 完整项存在 `arguments` 时走这条路径。它还支持只收到 done 项而没有 start 的调用。[最终参数覆盖](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/protocols/utils/tool-stream.ts#L202-L231)、[Responses 完整项处理](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/protocols/open-responses.ts#L1236-L1266)

注意一个明确的兼容例外：OpenCode 的 `parseToolInput` 将空字符串按 `{}` 解析，以容纳没有参数片段的零参数工具。这是协议适配决定，后续工具模式仍应决定空对象是否有效。[空参数规则](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/ai/src/protocols/shared.ts#L178-L185)

## 8.3　三个项目如何决定“现在完整了”

### Codex：用完成项承接调用，用增量承接展示

在本次固定版本的 Responses SSE 映射中，`response.output_item.done` 转为 `OutputItemDone`，文字 delta 转为文字事件；`response.function_call_arguments.delta/done` 被列入未处理事件。与此同时，custom tool 的 input delta 会转为 `ToolCallInputDelta`。因此不能笼统声称“Codex 把所有函数参数 delta 拼接起来执行”。这个具体路径依赖完成项提供普通函数调用内容，custom tool 的增量又有独立展示机制。[事件映射](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/codex-api/src/sse/responses.rs#L353-L375)、[忽略的参数事件](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/codex-api/src/sse/responses.rs#L480-L491)

主循环收到 `OutputItemDone` 后，把它交给 `handle_output_item_done`；若返回工具 future，就放入在途集合。这证明完成项可以成为下游处理边界，不需要把“整条回答停止”误当成唯一执行边界。这里的证据不等于所有工具都立即执行，具体还取决于处理器、权限和调度。[完成项进入后续处理](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L2776-L2790)

### OpenCode：归一化的调用事件进入 Step

本次版本应从 `packages/ai` 的协议模块与 `packages/core/src/session/runner/step.ts` 阅读，不能套用旧版 processor 路径。`SessionStep.attempt` 先发布事件，只对 `tool-call` 且非 `providerExecuted` 的事件启动本地工具；流消费会持续到结尾。收尾时没有变成可执行调用的工具输入被记为 `tool.input-incomplete`，消息明确要求重新发起完整参数调用。[调用事件与执行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L107-L142)、[未完成输入收尾](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L231-L236)

这展示了协议层和执行层的接口价值：执行层不必认识 SSE 的 `content_block_stop`，但必须能区分 `tool-input-delta`、`tool-call` 与供应商已执行的调用。

### DeepSeek Harness：严格消息结束，再由共享组装器形成结果

DSH 的当前 DeepSeek 适配器直接请求 Messages API。`parseSse` 使用 `TextDecoderStream` 与事件分帧器，不把没有结束分隔符的尾部当成完整事件；JSON 解析失败和 event/type 不一致会报错，心跳注释可刷新活跃计时。[分帧与格式检查](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/sse.ts#L8-L27)、[请求与翻译入口](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/adapter.ts#L124-L152)

`translate` 把供应商 block index 映射为按到达顺序分配的内部 index，累计 `partial_json`，在 block stop 输出完整块。只有已获得 stop reason 且所有块关闭，`message_stop` 才能产生 usage 和 finish；缺少 `message_stop` 的 EOF 是 `STREAM_CLOSED`。非 max-tokens 的工具参数还必须解析为 JSON 对象；对象检查明确排除 null 和数组。[片段累计](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/translate.ts#L82-L86)、[完整性检查](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/translate.ts#L121-L165)、[对象检查](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/replay.ts#L17-L21)

共享 `BlockAssembler` 接受最终 block-end 的内容，第一次关闭生效，后续增量不再修改它。若 finish 为 `max-tokens`，该版本会剔除**全部工具调用块**，并同步过滤 replay metadata 的对应块，而非只剔除 JSON 语法损坏的调用。Agent 消费完整条流后形成消息，再挑选调用执行。[组装规则](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/assembler.ts#L62-L92)、[截断过滤与重放一致性](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm/src/assembler.ts#L130-L149)、[消费结束后执行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L529-L555)

## 8.4　贯穿例题：CSV 修复过程中断了一次流

教学任务：`totals.py` 本应以 `Decimal` 求 `sum(quantity × price)`，实际只累加单价。两行输入分别为 `pen,3.50,2` 与 `book,12.00,3`，错误结果是 `15.50`，预期金额为 `43.00`。Agent 的工作应依次取得源文件、修复乘法、运行验证，再报告观测到的结果。本节关注第一次读取工具的协议轨迹；下列帧是合成示例，没有调用真实模型。

|时刻|输入事件|组装器中的状态|执行资格|
|---|---|---|---|
|t1|start：index=2，id=call_7，name=read_file|已知身份，参数为空|无|
|t2|delta：`{"path":"tot`|保存原始片段，可显示预览|无|
|t3|delta：`als.py"}`|文本已经能解析成对象|仍需协议规定的完成边界|
|t4|call done：完整参数 `{"path":"totals.py"}`|使用最终参数，不重复追加|完成校验后可交执行策略|
|t5|模型响应正常 finish|本次生成结束|并不证明读取成功或 CSV 已修复|

若在 t2 后断线，绝不能猜测剩余文件名后读取。若 t4 后读取已完成、但 t5 前断线，重新发送原请求可能产生重复调用；若此调用换成写文件或提交订单，后果更明显。恢复需要知道**请求是否开始、输出是否发布、调用是否执行、结果是否记录**，而不是只判断“网络恢复了吗”。

对本例，一个可审查的恢复记录应保留失败 attempt 与 `call_7` 的执行状态。读取尚未执行时可以按重试策略重新请求；补丁已写入时应先检查当前文件差异，再决定是否继续。CSV 正确性的最终证据仍应来自测试输出，例如断言总额为 `43.00`，不能来自模型 stream 的 finish。金额的精确十进制处理属于程序实现问题，也不能由流协议代为保证。

## 8.5　结束、失败与取消：四种边界不能合并

**正常结束**表示供应商完成本次输出；**长度截断**表示输出预算用尽；**传输故障**表示无法确认后续事件；**取消**表示调用者要求停止继续工作。EOF 只说明没有更多输入，不能自行解释为成功。DSH 明确拒绝缺少消息终止事件的 EOF；Codex SSE 也在未收到 Completed 时把流关闭变为错误。Codex 对 `response.incomplete` 又更细：`interrupted` 可以映射为 `Completed` 且 `end_turn=false`，content filter 和其他原因另行处理。[Codex EOF 与空闲超时](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/codex-api/src/sse/responses.rs#L535-L570)、[incomplete 分类](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/codex-api/src/sse/responses.rs#L418-L455)

重试也有不同层次。重连 socket、重新生成同一响应、依据已记录历史继续生成，是不同操作。OpenCode 的 Step 用 `outputStarted` 区分未输出时的 `Retry` 与已有输出后的 `Continue`；后者还受错误类型、重试决策及工具取消状态限制。Runner 接到 Continue 后加入中断续写提示并创建新的 assistant message ID。它没有把已经输出的内容当作从未发生。[Step 恢复条件](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L184-L209)、[Continue 条件](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L267-L275)、[Runner 续写](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts#L270-L294)

Codex 的共享恢复函数先检查错误是否允许重试，再应用预算和服务器建议的等待时间。预算耗尽时若能够激活 WebSocket 到 HTTP 的降级，会重置该重试计数；另有受功能开关、请求种类、会话来源和供应商条件约束的连接失败重试分支。因而“Codex 一律最多重试 N 次”或“一律无限重试”都不准确。外层等待还接受取消 token。[错误分类和特殊连接分支](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/responses_retry.rs#L87-L118)、[降级与预算](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/responses_retry.rs#L120-L175)、[可取消的恢复等待](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L1707-L1732)

取消必须走到资源层。DSH 合并消费者和上游 AbortSignal，以 watchdog 控制空闲时间；finally 主动 abort 以拆除连接，清理迭代器时不等待可能永远挂起的 drain。Agent 取消时另把安全的已生成内容记录为 interrupted 消息或 attempt。这些是不同职责：停止传输不会自动撤销已经发生的文件修改。[适配器取消和超时](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-deepseek/src/adapter.ts#L51-L74)、[取消后的记录](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L462-L503)

设计自己的适配器时，还应分别测量首字节、首个可见内容、完整调用与整体结束时间。更早显示参数预览改善的是反馈时间，不会自动降低工具执行耗时。队列上限、单参数大小、消费端背压和日志脱敏也应作为明确设计项；本章没有据此声称三个项目拥有相同实现或相同性能。

## 8.6　练习与参考解答

1. **两次读取返回半个 UTF-8 字符和半个 SSE 事件，在哪一层拼接？** 参考：字符解码器保留不完整字节；事件分帧器保留不完整事件；参数聚合器只处理已解码、已分帧事件中的片段。不能用一次网络读取充当一次事件。
2. **流中累计参数为 `{"path":"old.py"}`，done 项给出 `{"path":"totals.py"}`，应如何处理？** 参考：依据该协议的完整项契约使用最终参数，不能追加；OpenCode Responses 的 `finishWithInput` 就采用最终值。应记录异常差异供诊断，执行前仍做模式校验。
3. **为什么 DSH 的 max-tokens 处理不能描述为“自动修复半截 JSON”？** 参考：translator 保留截断文本进入共享流，assembler 在该结束原因下过滤全部工具调用并同步过滤重放块；没有替模型猜参数。完整语法也不改变这一过滤规则。
4. **为 CSV 补丁工具设计断线恢复方案。** 参考：给 attempt 和调用稳定标识；记录补丁前置文件摘要、调用状态与结果；失败后检查当前摘要和差异。若补丁已应用则复用已记录结果或继续验证；状态不明先读取现场，不直接重放修改。仅有 call ID 不足以保证跨进程恰好执行一次。
5. **设计最小故障注入矩阵。** 参考：覆盖片段交错、重复 done、未知块、JSON 截断、合法参数后的长度截断、终止事件缺失、等待时取消、工具执行后断线。分别断言“显示了什么、执行了几次、留下什么记录、连接是否收束”；三项目的预期需按各自上述边界编写，不能共享一套成功假设。

**验证状态：**本章结论来自固定源码阅读。上述合成轨迹、故障注入、真实模型请求及三个上游项目测试均**未运行**；练习是建议实验，不能作为已通过的工程验证证据。

按项目复习协议入口可对照原笔记：[Codex](../../agent-infra-study/codex/04-llm-streaming.md)、[OpenCode](../../agent-infra-study/opencode/04-llm-streaming.md)、[DSH](../../agent-infra-study/dsh/04-llm-streaming.md)。
