# 第 4 章　一次任务怎样穿过 Agent 循环

[教材目录](../README.md) · 上一章：[运行时架构](03-runtime-architecture.md)

**先修要求：**前 3 章；理解异常处理与取消信号。**学习目标：**能够手工追踪一个最小 Agent；区分模型请求结束、步骤结算、轮次结束和任务验收；为工具反馈、用户插入输入和异常退出设计明确路径。

## 4.1 循环的核心是重新观察

Agent 的最小闭环只有四件事：构造当前输入，取得决策，执行允许的动作，把结果加入下一次观察。这里最容易遗漏的是最后一项。若执行测试后只在屏幕打印结果，却没有把结果纳入下一次模型请求，那么模型无法据此调整行为；界面上发生了交互，决策闭环却断了。

同样，不能只记录成功工具的结果。路径不存在、参数不合法、权限拒绝和命令失败都是有用反馈。模型可能据此换一个路径、修复参数或承认受阻。但对系统级故障不能机械地当成普通字符串吞掉，例如持久化失败可能使后续恢复承诺失效。错误需要分层；本章先保留其类型，后续可靠性章节再讨论重试条件。

下面是**教学伪代码**。它加入了任务验收门槛，便于本书实验；三个项目的通用循环并不都内置同一套业务验收器。

```python
def run(task, state, budget):
    while True:
        if state.cancelled:
            return end("cancelled", state)
        if budget.exhausted():
            return end("budget_exhausted", state)

        state.admit_pending_input()
        request = build_request(state, task.constraints)
        response = model.generate(request)
        budget.record(response.usage)
        state.record_response(response)

        if response.failed_or_incomplete:
            return recover_or_end(response, state)

        if response.tool_calls:
            for call in response.tool_calls:
                result = validate_authorize_execute(call)
                state.record_tool_result(call.id, result)
            continue

        verdict = evaluate_task_evidence(task, state)
        if verdict.accepted:
            return end("completed", state)
        if verdict.cannot_continue:
            return end("blocked", state)
        state.add_feedback(verdict.missing_evidence)
```

这里的预算只是示意：真实系统还要在耗时工具运行期间处理取消，在请求之前预留输出空间，并限制重试成本。`evaluate_task_evidence` 也不是另一个神奇模型，而是任务特定的检查：存在指定测试结果吗，结果对应当前修改吗，是否还有明确未解决项？无法自动判断时，应交由用户验收或诚实记录不确定性。

## 4.2 把 CSV 修复走完整

设本次任务契约允许读取、修改和本地验证，要求逐行计算单价乘数量后求和，并保留正确的十进制金额。模型开始时只知道用户描述，不知道实现，因此第一步应缩小未知范围。下表是一条**拟定教学轨迹，未运行**；数字结果来自题目设定。

| 阶段 | 可见信息 | 动作与新反馈 | 下一步为什么变化 |
| --- | --- | --- | --- |
| 接纳任务 | “订单总额漏乘数量” | 保存目标、范围和验证要求 | 尚无足够证据直接改代码 |
| 定位实现 | 目录与入口函数 | 读取到逐行只累加 `Decimal(row['price'])` | 怀疑忽略了 quantity 列 |
| 建立复现 | 输入 `pen: 3.50 × 2`、`book: 12.00 × 3` | 用例实际得到 `15.50`，期望 `43.00` | 假设得到可观察支持 |
| 修改实现 | 单价为十进制文本、数量为整数 | 计算 Decimal 单价乘整数数量再累加 | 需要证明修改解决问题且不破坏既有行为 |
| 验证 | 当前补丁与相关用例 | 重跑复现、既有用例及选定边界用例 | 有了支持结论的工具证据 |
| 收束 | 改动、验证与未解决项 | 输出说明与证据引用 | 不再需要新动作，任务进入验收 |

为什么不能看到总额错误就随意改成浮点数求和？已观察到的缺陷是漏乘数量，金额表示、输出格式和无效数据处理还各有契约。模型应保留已有十进制金额语义、修正乘法，并据现有约定处理数量；不应在修复时顺手定义全新的金额规则。循环的价值在于逐步减少不确定性，不在于尽快制造文件差异。

工具反馈还应有足够上下文。一次验证结果至少应关联命令、工作目录、对应调用、退出状态及关键输出；大型输出可截取并保存完整产物引用。不能只把“通过”两个字塞回模型，否则之后无法判断究竟验证了哪个版本。

## 4.3 四种“结束”不是同一件事

一次响应可能因为模型自然停止、要求调用工具、达到输出上限、传输错误或取消而结束。即使响应正常结束，宿主也可能正在等待工具完成。步骤结算之后，若还有工具反馈需要解释或用户新输入需要消费，轮次仍可能继续。轮次正常结束，也不能自动证明业务任务正确。

| 层级 | 所回答的问题 | 不能单独推出的结论 |
| --- | --- | --- |
| 模型响应结束 | 这次生成为什么停止？ | 工具已执行、任务成功 |
| Step 结算 | 这一步的输出和在途动作怎样收尾？ | 没有下一步 |
| Turn 结束 | 当前交互阶段是否继续？ | 用户目标全部达成 |
| 任务验收 | 结果满足约定吗？ | 所有未来输入也都正确 |

设计终止状态时，应至少区分完成、等待用户、受阻、取消、预算耗尽和失败。实际项目的枚举可能合并其中部分状态，但产品报告不能因此把它们都翻译为“成功”。另外，等待一个正在执行的测试不是受阻；它可能只是一个仍活跃的异步阶段。

## 4.4 Codex：继续条件包含模型输出和新增输入

固定版本的入口位于 `core/src/session/turn.rs::run_turn`，不是旧资料常见的单文件 `codex.rs`。循环在安全边界提取待处理输入，记录输入后构造模型请求。请求返回后将 `model_needs_follow_up` 与 `has_pending_input` 做或运算，作为是否继续的关键条件。也就是说，模型本来想结束，但用户刚送入补充内容，控制程序仍可能继续推进。见 [`run_turn`，425–447 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L425-L447) 与[采样后状态，544–575 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L544-L575)。

没有 follow-up 时也并非立刻退出：`run_turn_stop_hooks` 可以给出继续用的反馈，控制程序把它记录后再次循环。若 hook 要求继续却没有可用提示，代码会警告并忽略该 block；这说明扩展点也需要定义无效结果的处理方式。见[停止钩子，657–705 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L657-L705)。这不是“Codex 自动证明所有测试都通过”，只是宿主能够在停止边界再次应用政策。

读更内层时还能看到输出项处理将工具 future 加入在途列表，并累计 `needs_follow_up`；因此真实实现不必像教学代码那样，等全部文本收完后才开始串行调用工具。见[输出项处理，2776–2790 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L2776-L2790)。流式并发细节留到第 8 章。

## 4.5 OpenCode：逻辑步骤与请求尝试是两层循环

`SessionRunner.drain` 先通过 `advanceToStep` 准备上下文，再执行 `runStep`，取回是否继续的布尔结果并推进步骤计数。`runStep` 内部又有重试循环，区分 `Completed`、`Retry`、`Continue`、`Compacted` 和 `RecoverFull`。因此读到一个 `while (true)` 时，必须先判断它在重试同一步，还是推进新步骤。见[外层循环，188–195 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts#L188-L195) 与[结果分派，270–295 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts#L270-L295)。

`SessionStep.attempt` 负责响应和工具的结算：它等待工具 fibers，处理拒绝与未完成调用，然后才返回结果；正常返回的 `needsContinuation` 还受 `toolChoice !== none` 限制。见[等待工具，144–157 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L144-L157)、[缺失结果处理，211–235 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L211-L235) 与[最终返回，277–287 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L277-L287)。这将“收到模型结束标记”和“步骤已经收尾”明确分开。

## 4.6 DeepSeek Harness：Turn、Step、Attempt 各有边界

`ReactLoopAgent.kick` 反复调用 `turn`；`turn` 记录 `turn/start`，在循环中记录 `step/start`，并在 `finally` 中记录 `step/end`。执行错误、取消和正常结束都有结构化轮次原因，最终记录 `turn/end`。`max-tokens` 还是一个不会被后续普通完成覆盖的结果。见 [`kick`，252–264 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L252-L264)、[步骤边界，307–365 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L307-L365) 与[轮次结算，368–397 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L368-L397)。这里的记录仍遵守上一章所述 append/flush 区别，不能仅凭 append 认定已刷盘。

`step` 先结算助手消息：达到 token 上限就返回该原因；没有工具调用就返回 completed；存在工具调用则执行工具并判断是否有结果明确 `concludesTurn`，否则返回 `null` 让外层继续。外层在准备停止时仍检查 next-step inbox，并触发 `agent/turn-stopping`。见[步骤结果，537–555 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L537-L555)、[工具结算，146–159 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts#L146-L159) 与[停止边界，360–366 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L360-L366)。普通工具完成不等于 `concludesTurn`；后者是额外语义。

## 4.7 不变量与失败推演

最小循环也应维护四个不变量：下一次模型请求包含应接纳的反馈；每个已开始调用有成功、失败或明确未知的结算；取消与预算耗尽不会伪装成成功；任务结果引用当前产物的验证证据。完整生产实现还需处理并发和恢复，后续章节会扩展这些条件。

典型反例是“模型输出最终答复，但测试仍在后台运行”。若 runtime 立即结束 turn，测试失败就可能永远没有进入决策上下文。另一反例是“工具返回权限拒绝，系统自动原样重试”。这不会新增证据，只会浪费预算。应让拒绝作为新的状态进入决策，选择权限范围内的动作或报告受阻。

## 4.8 练习与参考思路

1. 模型响应包含一句“修好了”和一个测试调用，是否可以立即完成轮次？<br>
   **参考思路：**先执行并结算测试，再按循环规则决定继续；自然语言声明不能覆盖未完成动作。
2. 用户在测试执行期间补充“还要支持负金额”，应立即打断测试吗？<br>
   **参考思路：**没有唯一答案。可排队到步骤边界，也可安全取消后重新规划；应明确哪些输入影响当前 turn、哪些留给下一轮，并避免丢失已有结果。
3. OpenCode 的 `Retry` 与推进下一个 step 为什么需要区分？<br>
   **参考思路：**二者影响步数预算、消息身份和恢复语义。同一逻辑步骤可能有多次尝试，不能把每次传输失败都当作新的任务进展。
4. **设计题：**把教学伪代码扩展成“最多 8 次模型调用、单条命令最多 30 秒、总时长最多 3 分钟”的循环，并说明最后一次调用只产生半个 JSON 时如何结束。<br>
   **参考思路：**维护独立调用计数、命令超时与全局截止时间；重试同样收费。半个 JSON 应以不完整输出结算，保存已有产物和未完成验证，不能标记 completed。此练习为设计任务，未运行。

本章建立可手工追踪的执行骨架。第 5 章讨论动作选择与规划，第 6 章讨论工具执行，第 8 章讨论流式处理；原有 [Codex](../../agent-infra-study/codex/01-agent-loop.md)、[OpenCode](../../agent-infra-study/opencode/01-agent-loop.md)、[DSH](../../agent-infra-study/dsh/01-agent-loop.md) 导读可作为按项目继续阅读的入口。
