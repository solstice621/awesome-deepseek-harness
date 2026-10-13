# 第 27 章 把一次任务从输入追到交付

[教材目录](../README.md)

**前置知识**：前六篇，可在完成第 4 章后先读本章案例，再回到相关机制。读完本章，应能用同一组问题追踪三个项目，并为“已完成”给出独立于模型措辞的证据。

## 27.1 定义任务与验收

贯穿本书的合成任务是：一段 CSV 总价程序只累加 price，漏乘 quantity。用户要求修复逻辑、验证结果，并解释修改。示例数据如下：

```csv
name,price,quantity
pen,3.50,2
book,12.00,3
```

错误结果是 15.50，正确结果是 43.00。为了不把“为一个样本打补丁”误认为修复，还需要空数据总价为 0.00、小数价格正常计算、数量变化影响总价等独立样本。金额以十进制表示；本教学任务只接受约定格式，不延伸为税务、汇率或任意脏数据处理系统。

验收分成四个问题：目标函数是否使用 price 与 quantity，独立测试是否通过，修改是否局限在授权工作区，交付说明是否对应实际产物。这些问题各有证据，不能合并成一句“Agent 已经回答完成”。对于需要发布的真实任务，还要另立发布验收；本案例的“修复”不隐含提交远程仓库或部署。

## 27.2 把自然语言变成状态转换

下表是教学轨迹，**不是本轮运行三个上游项目采集的 trace**。模型可以选择不同路径，但每个实际动作都应有可追踪的原因和结果。

| 时刻 | 当前可见证据 | 选择或动作 | 新状态与检查点 |
|---|---|---|---|
| 1 | 用户目标、授权范围、工作区标识 | 接纳输入 | 任务存在，尚无正确性证据 |
| 2 | 文件清单与程序入口 | 读取函数与 CSV | 发现 price 累加逻辑，记录来源版本 |
| 3 | 正确公式与现有行为 | 运行独立基线测试 | 观察 15.50 与 43.00 的差异 |
| 4 | 失败样本、可修改位置 | 提出并执行有限补丁 | 工作区发生改变，旧观察可能失效 |
| 5 | 新文件版本 | 运行验证集 | 每个样本记录实际与预期 |
| 6 | 测试结果与文件差异 | 检查范围、生成说明 | 形成可审阅产物 |
| 7 | 若验证失败 | 回到定位和修复 | 保留失败证据，消耗预算 |
| 8 | 验证满足或出现真实停止条件 | 报告结果 | 成功、未完成、取消分别记录 |

注意第 4 步已经产生副作用，而第 5 步才产生验证证据。如果第 4 步后崩溃，任务不是“毫无进展”，也不是“已经成功”。恢复应先读取状态，再决定后续动作。

## 27.3 Codex 路径中的请求视图

在固定 Codex 源码中，`run_turn` 接纳待处理输入后，记录相关输入标识，再捕获 `StepContext`。注释说明同一个请求视图用于上下文、公布的工具与工具调用；随后从历史构造模型输入并调用 `run_sampling_request`。完成一次采样及其工具后，再检查待处理输入与上下文预算，决定是否继续。[输入到采样](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L438-L541)、[采样后状态检查](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L544-L590)

映射到案例，模型决定读取文件时，公布的工具与实际调用的执行条件应属于同一次 step 捕获的视图；新用户输入可能在下一次边界重新影响这个视图。**这不是说文件系统会被冻结**：工具读取后，用户仍可能编辑 CSV，因此修改动作仍需检查其自己的版本前提。

继续沿第 6、13、17 章进入工具路由、并发与审批后，还要回到这条循环检查结果如何驱动后续采样。只停在 shell handler，就只能说明命令如何执行，无法说明为何再次请求模型或为何结束 turn。第 15 章的恢复资格另有条件，不能从主循环看见历史对象就推断任意中断都能自动重放。

## 27.4 OpenCode 路径中的执行所有权

OpenCode 的 `SessionExecution` 先取得 session，再把 `runner.drain` 放到该 session 选中的 instance 中执行。runner 可以返回 Complete、Moved 或 Reloaded，执行层据此结束或继续 drain。这说明会话执行路径包含实例选择和生命周期协调，不只是直接循环调用模型。[drain 与实例](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L87-L109)

更关键的是，开始执行时把 durable claim 与 Started 事件绑定提交；成功和一般失败释放 claim，shutdown interruption 保留它供恢复使用。用户主动停止与宿主停机在这里具有不同语义。[claim 与结算](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L76-L86)、[终态分支](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L111-L148)

映射到案例，补丁阶段服务停机后还保留执行意图，能帮助系统知道“存在待续工作”。但 claim 没有证明补丁没有执行，也没有替外部工具实现幂等。第 14 章分析的结果未知窗口仍然存在。恢复的正确问题是“数据库告诉我什么需要继续，工具世界告诉我什么已经发生”，两者需要协调。

若用户在修复中追加“不要改变 CSV 格式”，执行层的 steering 与排队输入也不能随意互换。源码在 interrupt-resume 分支区分 next-turn prompts 与可提升的 steer/control 工作，并通过 coordinator 唤醒。[中断后接纳边界](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L150-L174)

## 27.5 DSH 路径中的记录与投影

DSH `ReactLoopAgent.step` 从准备好的 assembly 生成 prompt，刷新运行上下文，确定请求序列边界，把 system/user message 以相应投影意图加入 session，然后 `buildRequest`。流式阶段由 `AssistantStreamAttempt` 接收 chunk，成功时结算为 assistant message，异常或中止时按分支保留 attempt 或中断内容。[请求构建](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L400-L460)、[流失败与结算](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L462-L527)

正常消息结算后，代码检查 max-tokens 和 tool-call 块：没有工具调用时返回 completed；有工具时交给 `executeToolCalls`，再根据 concluded 决定完成或继续。[消息到工具阶段](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L529-L559)

这里的 completed 描述循环停止原因，不能直接等同于“CSV 修复正确”。模型即使给出一段漂亮的最终说明，仍需要案例的验证器判断目标是否达成。另一个重要边界是 `Session.append` 与持久化 checkpoint：记录进入当前 session 的语义，不应自动读成已经完成存储 flush，详见第 15 章。

## 27.6 三种架构用同一组问题比较

| 问题 | Codex 本章观察点 | OpenCode 本章观察点 | DSH 本章观察点 |
|---|---|---|---|
| 执行上下文的主要观察点 | 捕获 StepContext | session 对应 instance 与 runner | assembly、request config、请求序列 |
| 下一轮由什么触发 | 模型 follow-up 或待处理输入等状态 | runner drain 与 coordinator | 工具结果后继续 step 或 concluded |
| 生命周期记录在哪里看 | turn/step 与历史和扩展路径 | Started、claim、terminal event | turn/step、assistant attempt/message |
| 什么不能由此推断 | 工作区静止、任意恢复成功 | 外部动作 exactly-once、租户隔离 | append 已 flush、completed 已验收 |

这些观察点是选择阅读路径的地图，不是产品功能清单。比较要保持同一层次：不要拿一个项目的操作系统隔离与另一个项目的工具 schema 做优劣比较，也不要把某个默认组合扩展为整个框架的唯一运行方式。

## 27.7 三个故障窗口

**模型看到了不完整工具参数。** 如果执行层把流中的半个 JSON 当作动作执行，后续流修复不了已经发生的副作用。正确边界是调用完整性与校验，具体实现见第 8 章。

**补丁完成，但结果回注失败。** 模型下一轮可能重新提出同样补丁。应结合操作身份、文件版本及结果持久记录确认发生了什么；若操作不幂等，直接重试会放大故障。第 28 章将演示在一个事务边界内如何处理这一问题，并明确该保证不能推广到外部服务。

**上下文压缩后丢失“不改格式”。** 压缩摘要保留了进度，却丢了约束，后续模型可能“优化” CSV。恢复用户限制、开放问题、来源与未完成事项应是压缩验收的一部分。压缩速度和摘要长度不能单独衡量压缩质量。

## 27.8 练习与参考答案

1. **追踪题**：一次任务中记录了三次模型请求，两次重试、四个工具调用。它有几个逻辑 step？<br>
   **参考答案**：信息不足。必须先确认该项目的 step/attempt 定义与重试记录方式；三次请求不必等于三个 step，多工具也可能属于同一步。
2. **证据题**：日志显示“测试命令已启动”，能否报告测试通过？<br>
   **参考答案**：不能。至少检查进程完成、退出状态和测试结果；还要确认运行的是修改后的产物及目标样本。
3. **设计题**：任务最终输出“我已完成”，但验证集有失败，应给什么状态？<br>
   **参考答案**：保留模型最终文本作为观察，把任务标为未通过验收或待修复；模型停止与业务成功分开记录。
4. **源码实验，NOT RUN**：选一个项目，在本章入口处设置断点，用临时 CSV 任务观察接纳、请求、执行和结算四个边界。<br>
   **验收要点**：保存固定版本、事件身份与观察到的分支。不要把本章教学轨迹当作已经观测到的上游 trace；可先运行下一章的本地实验学习记录方法。
