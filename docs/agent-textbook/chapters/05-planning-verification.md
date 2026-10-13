# 第 5 章：规划、验证与停止——让行动服从可检查的目标

[教材目录](../README.md)

**先修知识：**理解一次模型请求、工具调用和工具结果之间的关系。**学习目标：**能够把模糊任务变成验收条件，选择合适的规划粒度，区分检查表、执行状态与验证证据，并设计不会把“停下”误报为“完成”的控制逻辑。

## 5.1 计划是关于未来的假设，验收是关于现实的判断

设用户要求“修复 CSV 金额汇总错误”。“读取文件、修改代码、运行测试”只是行动顺序，尚未定义正确结果。先写下任务契约：对于合法记录，按约定的金额精度求和；保留既有输入接口；空文件、带表头和小数金额如何处理，必须从已有需求或测试确认；只修改必要文件。若尚不知道非法行应该跳过还是报错，把它登记为待澄清的需求，不能偷偷选择一种语义再宣布成功。

一个有用的计划项包含四部分：**目标状态、输入依赖、行动、验收证据**。例如“定位错误”依赖源码与失败样例，行动是阅读解析和累计路径，证据是一个能重现偏差的输入输出；“修复”依赖已确认的根因，证据是代码差异；“验证”依赖修复后的代码，证据是实际执行的测试及其结果。把任务分成子任务的主要理由是降低不确定性和明确依赖，而不是增加清单长度。

可以将验收写成谓词：`done = functional_ok ∧ regression_ok ∧ scope_ok ∧ evidence_current`。它是本章的**教学设计**，不声称三个项目内置了这组检查。`evidence_current` 尤其容易遗漏：在最后一次测试后再修改源码，旧测试结果就不再覆盖当前状态。计划的 `completed` 标签本身不进入这个逻辑式，因为它是执行者的陈述，不是独立证据。

## 5.2 三种规划粒度与有限反思

最轻量的方式是交错观察与行动：看见测试失败，读取相关函数，作出局部修改，再观察结果。这里用 **ReAct 风格**指“推理、动作、观察交错”的教学模式，不把项目中的任意工具循环直接认定为某篇论文算法的实现。它适合环境反馈频繁、事先难以确定路径的任务，风险是只顾眼前错误而忘记总体约束。

**Plan-and-execute 风格**先建立粗粒度步骤，再逐步执行；执行反馈可触发重规划。它适合依赖明确的工作，但计划过细会迅速陈旧。更稳健的折中是滚动规划：远处写目标，近处写下一项可验证动作。本例先确定“重现—修复—回归”三个阶段，读完源码后才判断差异来自解析、数量处理还是累计逻辑。

“反思”也应落在可观察对象上：预期是什么，工具实际返回什么，二者为何不同，下一次改变哪个假设。不要无限要求模型“再想一遍”。一次测试失败可能是代码错误、测试命令错误、缺依赖或者运行了错误目录的代码，四者需要不同的下一步。反思若没有新证据或新的可证伪假设，就只是重复生成文本。应给它设置次数、时间或费用边界；到边界时报告未解决问题和已知事实。

```text
acceptance = establish_contract(user_request, repository_evidence)
plan = coarse_steps(acceptance)
while budget_available and not cancelled:
    observation = perform_next_authorized_action(plan)
    update_evidence(observation, current_revision)
    if acceptance_satisfied(): return VERIFIED_COMPLETE
    if no_safe_next_action(): return NEEDS_INPUT_OR_BLOCKED
    plan = revise_only_affected_steps(plan, observation)
return INCOMPLETE_WITH_REASON
```

这段伪代码描述控制责任，不要求公开模型内部思维。系统需要保存的是动作、证据、决策摘要和状态转移。

## 5.3 三个项目：同名“计划”背后的不同机制

**Codex 的 `update_plan` 是进度工具。**`PlanHandler::handle_call` 对函数参数反序列化，发送 `EventMsg::PlanUpdate`，返回“Plan updated”；它明确在 `ModeKind::Plan` 下拒绝调用。工具说明要求最多一个 `in_progress`，但本次检查的 handler 和 schema 中，前者只做类型反序列化，后者没有跨列表项的计数约束。因此，应将“描述中的纪律”和“此边界实际强制的不变量”分别记录，不能看到描述就声称已做运行时校验。[handler：65–111 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/plan.rs#L65-L111)，[schema：42–55 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/plan_spec.rs#L42-L55)

Codex 的停止逻辑也比“模型写完一句话”更丰富：`run_turn` 将模型后续需求与待处理输入合并；没有后续需求时运行 Stop hooks。若 hook 阻止停止且提供续行提示，提示会记录到会话并继续循环；若只要求阻止、却没有提示，则发出警告并忽略该阻止。这里提供了接入验收逻辑的位置，却不证明默认 hook 已检查 CSV 业务正确性。[后续判断：545–574 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L545-L574)，[停止门：657–705 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L657-L705)

**OpenCode 的 Plan 是受限的 Agent 模式。**`PlanPlugin` 配置编辑权限：默认拒绝编辑，仅允许计划目录；上下文 hook 会检查进入或退出 Plan 的提醒是否缺失、过期，再补入当前请求。这说明模式具有权限层和上下文层两个面，不能只靠一段历史提示永久维持。[PlanPlugin：14–40 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/plugin/plan.ts#L14-L40)，[提醒对齐：55–73 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/plugin/plan.ts#L55-L73)

OpenCode 还把步数上限落在执行边界：runner 达到配置上限后加入收尾提示并设置 `toolChoice: "none"`；`SessionStep` 若仍收到执行请求，会返回工具禁用错误。这里的“达到最大步数”是预算终止，必须与任务完成分开记录。[runner：223–242 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts#L223-L242)，[本地执行检查：95–104 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L95-L104)

**DeepSeek Harness 的 `todo_write` 是每 Agent 会话的整表替换。**它裁剪内容空白、拒绝空项和重复项，并按部署配置决定是否允许多个 `in_progress`；工具体将完整列表追加为 `todo/write` 事件。投影取最新列表，在下一次 `turn/start` 清空，而 `turn/end` 保留已完成清单可见。这里的 `append` 是日志 API 调用，不应据此推断本章未检查的磁盘刷写完成时机。[校验：80–99 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/todo/tool-todo/src/index.ts#L80-L99)，[投影：117–134 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/todo/tool-todo/src/index.ts#L117-L134)，[执行：192–208 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/todo/tool-todo/src/index.ts#L192-L208)

它的循环在没有工具调用时可以得到 `completed`，工具也可声明结束回合；但最终停止前还会分发 `agent/turn-stopping`，并重新检查 next-step inbox。`max-tokens` 在回合内保持“黏性”，后续正常结束不会把该原因覆盖成完成。这里的 `completed` 是协议/控制层结果，仍不是业务验收证书。[step 结果：547–555 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L547-L555)，[回合停止与原因：338–365 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L338-L365)

## 5.4 把 CSV 修复做成证据链

统一贯穿案例的输入是 `pen,3.50,2` 和 `book,12.00,3`，金额使用 `Decimal`。读源码后发现累计时漏乘 `quantity`，所以错误结果为 `15.50`，正确值应为 `3.50 × 2 + 12.00 × 3 = 43.00`。第一步保存该失败样例；第二步修正单价乘数量后再累计；第三步运行相同样例及已有回归测试；第四步查看最终差异，确认没有顺手改变非法行策略。这个根因是**合成教学设定**，不是三个上游项目的缺陷。

验证集应区分“能发现当前错误”与“限制意外变化”。可先写下以下预期，再修改程序，避免根据修改后的结果倒推正确答案：

|验证样例|预期|它能说明什么|
|---|---|---|
|只含 `pen,3.50,1`|`3.50`|基本解析可用，但单独使用会漏掉数量错误|
|含两条贯穿记录|`43.00`|直接检测漏乘 quantity|
|交换两行顺序|仍为 `43.00`|检查累计结果不依赖输入顺序|
|保持既有非法行样例|维持已有明确约定|防止修复意外改变输入契约|

这是待运行的验证设计，不是测试结果。若第三项失败，不应立即扩大修复范围；先检查是否存在依赖上一行状态的另一个缺陷，再决定它是否属于当前需求。每次重规划都应该说明新增事实如何改变依赖，而不是机械重新生成一份完整清单。

设计一个验收账本，比勾选清单更可靠：每个条件记录“证据来源、执行时间、代码版本、结果、剩余限制”。命令退出码为零但实际发现零个测试，只能证明命令结束正常；测试通过但遗漏小数输入，覆盖结论仍有限。代码审查可检查范围和逻辑，运行测试检查具体行为，二者互补。若环境缺依赖，记录“修复已写入，验证受阻”，而不是反复更改正确代码以迎合环境错误。

需要保持三个不变量：改变需求就同步改变验收；改变代码就重新判断证据是否仍适用；任何停止原因都可追溯。一个常见失败场景是 Agent 把最后一项 todo 标为完成后才发现测试挂住，此时应恢复验证项状态，保存进程标识和未完成事实，而不是让界面的全绿掩盖执行状态。

## 5.5 练习与参考解法

1. **辨析题：**`todo_write` 全部标为完成且模型输出 final，是否满足 CSV 修复验收？**参考：**不满足。两者都是状态或陈述；还需当前代码版本上的行为与回归证据。
2. **源码题：**比较 Codex 与 DSH 的“至多一个正在执行项”。**参考：**Codex 本章检查的工具描述提出要求；DSH `toTodoList` 在禁用并行时实际计数并拒绝。不能推广成所有入口或所有版本的结论。
3. **故障题：**第 4 步达到预算上限，第 3 步刚提交测试进程，尚无退出码，应该怎样报告？**参考：**报告预算终止、已完成修改、验证仍在运行及可恢复的进程信息；不要报告测试通过。异步任务的回收策略见下一章与执行环境章。
4. **设计题：**给上述 CSV 任务设计一个“允许结束”的外部检查器。**参考：**检查器接收需求版本、代码摘要、测试结果与范围审查结果；验证证据绑定同一代码摘要；成功返回允许，缺证据返回具体待办。它应有自身超时和失败状态，避免失败检查器把整个 Agent 永久锁死。

本章没有执行三个项目的测试或真实模型任务。上述 CSV 路径与检查器是拟议实验，读者可在教材综合实验中实现。

纵向复习可对照原项目笔记的任务编排入口：[Codex](../../agent-infra-study/codex/06-task-orchestration.md)、[OpenCode](../../agent-infra-study/opencode/06-task-orchestration.md)、[DSH](../../agent-infra-study/dsh/06-task-orchestration.md)。本章事实判断以上述固定版本源码为准。
