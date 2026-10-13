# 第 11 章：上下文压缩——有损信息变换与安全续接

[教材目录](../README.md)

**先修知识：**上下文预算、会话事件、工具调用关联 ID。**学习目标：**设计压缩触发与保留策略；理解摘要、裁剪和重建基线的区别；解释为什么压缩必须维护工具配对、来源与事务边界。

## 11.1 压缩究竟改变什么

任务很长时，完整历史无法永远进入模型窗口。**上下文压缩**是把当前模型输入替换为较短表示的操作；它可以产生摘要、删去可重取的工具输出、保留近期原文，或启动新的窗口。它通常不等于删除审计日志，更不等于任务已经完成。

把当前历史写为 (H=P+O+T)：(P) 是常驻规则与环境，(O) 是较旧过程，(T) 是近期尾部。一个常见教学方案是 (H'=P'+S(O)+T)。(S) 是摘要，(P') 是重建后的当前规则。重新建立这个基线可称为 context rebase：后续差分必须相对于新基线解释。这里是概念描述，不是三个项目都调用同名函数。

为什么需要 (P')？旧摘要可能说“当前允许联网”，但权限已变；若把这句话当作当前配置，就把历史观察误用为执行授权。稳定宿主状态应由宿主重新提供，任务事实则由摘要和可追溯原始证据恢复。摘要可以记录“过去曾获某次批准”，不能自然推出今后所有操作都被批准。

## 11.2 什么时候压缩，保留什么

触发策略有三类：达到预设压力阈值；供应商明确拒绝超长请求后的恢复；用户主动要求整理。压力阈值应留出输出、下一次工具结果、摘要请求和估算误差的空间。压缩本身也需要模型资源；等到窗口完全装不下时才开始摘要，可能连摘要请求都无法发送。

优先保留的不是“最精彩的内容”，而是继续工作的充分条件：未完成的用户要求、已接受的约束、关键决定与理由、已执行动作及结果、当前文件版本、未解决问题、下一步及原文入口。可重新读取的文件大段内容通常可省略；无法重新推导的用户偏好和一次性故障现象成本较高。结构化摘要帮助发现遗漏，但“包含所有标题”不证明语义完整。

重复压缩具有累积风险。若第一轮把“只测试了金额相加”写成“测试通过”，第二轮再写成“功能完成”，限定条件逐渐消失。评价压缩应使用任务恢复问题，例如“测试是否真的运行”“还有什么未验收”“哪些文件已修改但未提交”，而不能只看摘要长度。保留原始记录入口，可让 Agent 在有疑问时重新查证。

## 11.3 一次压缩需要像事务一样思考

以下是教学伪代码，展示必须核对的边界：

```text
selection = choose_old_region(visible_history, keep_recent)
require balanced_tool_pairs(selection.boundaries)
snapshot = capture(selection, context_revision)
summary = summarize(snapshot)
require summary_is_smaller(summary, snapshot)
require replacement_target_still_valid(snapshot)
append_checkpoint(summary, source_refs=snapshot.event_ids)
replace_visible_region(selection, checkpoint)
persist_required_barrier()
rebuild_current_instruction_baseline()
```

工具调用与结果通过 ID 关联。若保留结果却丢掉调用，或保留调用却丢掉结果，供应商可能拒绝请求，模型也无法解释它。可在选择边界时整组保留；也可在投影阶段规范化缺失输出。但合成的“aborted”是协议修复，不是工具成功的证明，更不能因为上下文重建而重跑一次有副作用的工具。

摘要生成可能耗时。期间用户追加要求、分支发生回退、其他操作替换了同一历史区间，摘要就可能基于过时快照。提交时必须检查整个窗口或被选片段仍有效；失败后重新选择，或报告无法压缩。真正的持久性屏障还要看存储接口：往内存日志 append 成功，不能自动推出进程崩溃后一定可恢复。

## 11.4 三个实现的不同选择

**Codex 有多种压缩路径。**本地 `compact.rs` 的摘要路径生成较短历史后，调用 `build_compaction_replacement_history` 重建初始上下文并返回新的 world-state 基线；再替换历史并重算 token。不要只讲“把旧消息换成一段 summary”，漏掉基线重建。[`compact.rs:79–110`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs#L79-L110)，[`compact.rs:383–417`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs#L383-L417)

在这个本地摘要调用自身遭遇 `ContextWindowExceeded` 时，若输入不止一项，会删去最老历史项再尝试；中断与会话预算耗尽直接返回，其他失败受重试上限控制。这是特定路径的恢复策略，不能概括成所有请求失败都会压缩或必然恢复。[`compact.rs:323–367`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs#L323-L367)

另外，`compact_token_budget.rs` 的路径跳过模型/服务端摘要，调用 `start_new_context_window`，仍执行压缩生命周期钩子。因此“压缩总会自动生成摘要”并不成立。历史规范化的 `ensure_call_outputs_present` 可为缺失的 function output 补入 `aborted`，强调的是协议配对，而不是恢复执行结果。[`compact_token_budget.rs:16–39`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact_token_budget.rs#L16-L39)，[`compact_token_budget.rs:48–65`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact_token_budget.rs#L48-L65)，[`normalize.rs:46–67`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/context_manager/normalize.rs#L46-L67)

**OpenCode 区分本地摘要与供应商原生压缩。**`compact` 先检查 auto 设置、触发原因和模型能力，再选择 native 或 summarize；关闭 auto 时 overflow 也不会自动触发。摘要模板保留目标、约束、决定、工作状态、下一步及关键路径；生成规则把 AGENTS.md 等设置排除在摘要之外，因为后续会单独接收当前设置。[`compaction.ts:205–239`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/compaction.ts#L205-L239)，[`compaction.ts:104–151`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/compaction.ts#L104-L151)

摘要路径把较旧部分压缩，近期尾部以文本带入 checkpoint；`recentStart` 将边界移到用户消息处，使同一交流中的工具调用与结果保持在一起。若摘要不含要求的模板标题，会补一次提醒，但这个检查只验证很弱的结构条件。[`compaction.ts:272–309`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/compaction.ts#L272-L309)，[`recentStart:716–737`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/compaction.ts#L716-L737)

供应商原生压缩保存的可能是只有对应 endpoint 能重放的加密项，不是可阅读的 Markdown 摘要；这解释了模型/供应商切换时，不能直接假设任何 checkpoint 都可移植。[`compactNatively` 前的协议说明，`compaction.ts:312–322`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/compaction.ts#L312-L322)

**DeepSeek Harness 把选择、计价和替换显式关联。**`BasicCompactionEngine` 先按已路由模型和输出预留计算压力，允许可选的工具结果裁剪先落地，再重新测量；仍超阈值才选择摘要区间并在有限次数内检查是否降到阈值以下。[`index.ts:304–345`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/index.ts#L304-L345)

`selectCompactableRange` 校验计量节点与当前 surface 对齐，保留最近尾部，移动切点直到工具配对平衡，且不把开头 system 节点放进压缩区间。摘要完成后检验带包装的摘要确实比被替换内容更小；提交追加 `compaction/summary` 和带 `surfaceOp: replace` 的消息，保存 `sourceEventSeqs`，而不是改写旧日志。[`region.ts:117–154`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/region.ts#L117-L154)，[`region.ts:410–420`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/region.ts#L410-L420)，[`commitCompactionBody:491–509`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/region.ts#L491-L509)

其事务在异步摘要返回后做稳定性检查，再写替换及结束标记；手动 idle 压缩还显式传入 `sessions.flush`。所以“已追加结束标记”和“已越过物理持久性屏障”应分别读代码确认。[`region.ts:210–239`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/region.ts#L210-L239)，[`compactNow:383–414`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/compaction/compaction-basic/src/index.ts#L383-L414)

## 11.5 贯穿案例：补丁已写，测试尚未运行

CSV 修复任务经过多次搜索后，模型窗口接近阈值。此时已经在 Decimal 金额聚合中补上数量乘法：pen 的 3.50×2 与 book 的 12.00×3 应由错误的 15.50 变为 43.00，但测试工具尚未执行。坏摘要是：“已修复金额错误，一切正常，继续提交。”它把实现、验证与提交三个阶段合并了。

可用的教学 checkpoint 应写成：目标为按单价×数量汇总并保留两位小数；已在 `sum_amount` 补上数量乘法，金额用 Decimal，改动未提交；尚未运行测试；下一步执行现有测试入口并检查空行、零数量与小数；证据是编辑工具成功及补丁位置，暂无测试结果。恢复后先检查文件与工作树是否仍对应记录，再运行验证。若原始工具结果已被压缩，读取日志或重查文件；不凭摘要推断执行结果。

要验证这个设计，可提出四个恢复问题：用户还要求什么、最后确定成功的动作是什么、下一项未完成动作是什么、哪里能找原始证据。若摘要答不上其中任一项，压缩成功事件仍不足以表示任务可以可靠继续。

## 11.6 练习与参考答案

1. **判断题：**摘要从 10000 token 缩至 1000 token，是否证明压缩正确？

   **参考答案：**只证明长度下降。还需检查未完成要求、实际动作与验证结果、配对结构和来源入口；语义保真无法由长度推出。

2. **协议题：**切点把 `call(id=7)` 放进旧区间，把 `result(id=7)` 留在近期区间，该怎么办？

   **参考答案：**优先移动边界，使二者一起保留或一起转为摘要。不能把结果挂到另一调用，也不能为了补记录而重做有副作用动作。

3. **源码题：**Codex token-budget 路径与 OpenCode native 路径，为什么不能都用“摘要文本”描述？

   **参考答案：**前者可直接创建新窗口而跳过摘要；后者可保存供应商绑定的加密压缩项。恢复契约、可读性与移植性不同。

4. **设计题（建议实验，未运行）：**摘要生成期间，用户追加“不要提交”。怎样阻止旧摘要导致提交？

   **参考答案：**保留新用户消息作为更晚且未被覆盖的输入，验证摘要目标区间/版本，重新构造当前指令基线；行动前重新检查授权。测试应刻意把新输入放在摘要请求与提交 checkpoint 之间。

本章依据固定源码解释机制；未执行上游压缩测试、模型调用或故障注入实验。
