# 第 14 章　错误、重试与幂等：面对不确定结果

[教材目录](../README.md)

**先修知识：** 第 13 章的调用生命周期，网络请求与超时。**学习目标：** 为不同失败选择不同恢复动作；区分逻辑任务和物理尝试；能解释为什么自动重试无法单独保证外部副作用恰好执行一次。

## 14.1 超时不是“服务端没有执行”

继续修复 CSV 漏乘 quantity 的错误：pen 3.50×2、book 12.00×3，应从 15.50 修正为使用 Decimal 计算的 43.00。模型请求可能因连接中断而失败；修改工具可能因磁盘满而失败；测试可以正常退出但断言失败。这三种“失败”的处理完全不同。第一种可能需要重新请求，第二种需要改变环境或停止，第三种是新的任务证据，需要继续分析代码。

为故障分类至少问四件事：失败发生在哪层；有没有已经公开或持久化的输出；有没有可能发生外部副作用；当前是否仍有执行授权。用户取消或拒绝授权，不应当作普通瞬时错误无限重试。上下文超限可能需要压缩；输入参数不合法需要修正参数；限流适合等待；服务端内部错误可能重试，但仍受整体预算约束。

| 观察 | 合理动作 | 必须保留的事实 |
| --- | --- | --- |
| 连接建立前失败、没有输出 | 有预算时重试传输 | attempt 次数、耗时、错误 |
| 收到部分文字后流中断 | 结算部分尝试，再决定继续 | 哪些内容已公开、是否完整 |
| 工具发送后超时 | 查询结果或标记结果未知 | call ID、请求、可能副作用 |
| 测试退出码非零 | 把诊断交回推理循环 | 失败断言与实际输出 |
| 取消或权限拒绝 | 停止相关工作，完成清理 | 谁停止、停止边界 |

表格是教学分类，不是某个项目的错误枚举。重点在于恢复动作必须由语义驱动，不能统一包一层 `retry(any_exception)`。

## 14.2 退避、抖动与预算是三个独立旋钮

指数退避可写为 `base(k) = min(cap, initial × 2^(k−1))`。抖动再对等待间隔随机扰动，减少大量客户端在同一时刻重试。服务端的 Retry-After 是另一类约束，可能要求等待到指定时刻；不能换一种传输方式就假装该期限不存在。

次数预算只限制尝试数，不限制总耗时。一次超时已等两分钟，十次重试即便只插入两秒间隔也很昂贵。完善的执行器同时维护总截止时间、尝试数、累计 token/费用、按错误类别的子预算，并让等待可取消。下列为设计示例：

```python
while True:
    outcome = await attempt(operation_id, attempt_id)
    await settle(outcome)
    if outcome.success: return outcome
    decision = classify_and_decide(outcome, remaining_budget)
    if not decision.retry: return outcome
    delay = respect_server_deadline(decision.local_backoff)
    if delay >= remaining_deadline(): return budget_exhausted()
    await cancellable_wait(delay)
```

`settle` 放在下一次重试之前，是为了不把失败尝试抹掉。逻辑任务 ID 应跨尝试稳定，attempt ID 则每次变化。前者支持关联和去重，后者支持追踪到底发出了几次请求。只记录最后一次成功，会把高成本、频繁重试的系统误判为健康系统。

## 14.3 三个项目如何决定重试

### Codex：错误建议、传输回退与条件化无限重连

`handle_response_stream_error` 先通过 `err.retry_delay(retry_count)` 判断是否存在重试路径；普通分支检查 `max_retries`，记录通知与等待时刻。重试耗尽后可尝试由 WebSocket 回退到 HTTPS；回退前仍等待服务端 Retry-After，切换成功后重新计数。这意味着“某一个计数器耗尽”不总等于整个逻辑请求结束。[responses_retry.rs:83–175][C14-a]

同一函数另有受功能开关控制的 `UnboundedConnectionRetries`：仅适用于 Sampling、ConnectionFailed、非内部来源、且非 Bedrock 的条件组合；等待由 5 秒倍增至 60 秒。这不是通用的无界错误重试，也说明不能笼统概括 Codex 为“固定 N 次”。本章只确认该分支，不推断所有安装默认启用该开关。[responses_retry.rs:93–117][C14-b] [退避常量:23–24][C14-b2]

这套代码处理模型 Responses 请求。它没有因此给“创建远程 PR”或“修改 CSV 文件”提供业务去重承诺。源代码阅读必须止于实际职责边界，不能把请求重试能力解释成工具副作用 exactly-once。

### OpenCode：没有输出时重试，已有输出时继续

`SessionRunnerRetry.policy` 的基础 schedule 从 2 秒指数增长，基础间隔封顶 10 秒，使用 `Schedule.recurs(10)` 和 jitter；RateLimit/ProviderInternal 的 Retry-After 上限为 15 分钟。超时有独立默认上限 3；插件 hook 能修改 decision，之后会校验 delay 是否有限且非负。因此这些是本版本基础策略，不是插件不可改变的最终行为。[retry.ts:31–90][O14-a]

更重要的决策在 `SessionStep.attempt`。输出尚未开始时，特定传输错误可 `RecoverFull`；普通可重试错误在 `!recorded.outputStarted` 时返回 `Outcome.Retry`，保留已有 assistant 身份。已经产生输出时，则先记录 assistant/Step 失败并处理未完成工具，再在满足条件时返回 `Outcome.Continue`。Continue 承认历史发生了变化，不能等同于重新运行一段从未开始的计算。[step.ts:184–209][O14-b] [step.ts:220–275][O14-c]

`RESULT_MISSING` 与 `INPUT_INCOMPLETE` 还明确区分 provider 没有给出工具结果和工具参数没有形成完整调用。不能把半截参数“尽力解析一下”就执行，这会使故障恢复产生新的副作用。[step.ts:231–235][O14-c]

### DeepSeek Harness：同一个 Step 中的尝试、可替换的策略

DSH `Agent.step` 使用 `firstAttempt` 只在第一次提交本批已接纳的普通用户消息，避免重试重复输入；每个请求有独立 assistant attempt。模型以流内错误结束时，先记录 `assistant/attempt`，再走 `agent/request-error` waterfall；返回 retry 才进入下一次尝试。若 adapter 或扩展直接抛异常，则另一路结算并抛出，不能把两条路径混称“任何异常都会自动重试”。[agent.ts:408–441][D14-a] [agent.ts:462–526][D14-b]

`llm-retry` 插件按 provider 和 policy key 维护当前 Step 的重试投影，支持 normal 与 always；normal 检查代码集合和 maxRetries，always 可持续恢复但仍观察 Agent 及插件生命周期的取消。它还处理 providerRetryAfterMs 超过本地 maxDelayMs 的情况：normal 交给后续策略，always 回到本地退避。卸载时先停止监听，再 abort 并等待活动恢复操作。[llm-retry/index.ts:194–258][D14-c]

这里有一个值得练习的证据边界：`backoff` 在等待前 `session.append('llm/retry', …)`，但这段代码没有直接 await flush。它确实先留下会话日志事件，却不能仅凭文件头“durable”措辞声称该事件在等待前一定已经完成磁盘屏障；物理保障要接着检查持久化后端和第 15 章的 checkpoint policy。[llm-retry/index.ts:149–191][D14-d]

## 14.4 幂等不是“再执行一遍大概没问题”

幂等操作满足重复应用不改变首次成功后的预期结果。`set_total(30)` 可以设计为幂等；`increment_total(30)` 通常不是。修改代码也未必幂等：再应用同一补丁可能失败、重复插入或覆盖别人的编辑。对 CSV 实例，更稳健的操作是携带预期旧文件 hash，并验证“旧内容匹配才应用；新内容已匹配则返回已完成；两者都不匹配则拒绝并重新读取”。

考虑四个时刻：A 记录修改意图，B 写入文件，C 记录工具完成，D 回应模型。进程在 B 与 C 之间崩溃，重启看到的日志与“尚未写入”可能相同，但文件世界已经不同。仅靠重新请求，无法区分这两种状态。要获得一次性的业务效果，需要副作用接收方支持稳定幂等键，或把副作用和去重记录放进同一事务，或恢复时通过可验证后置条件进行协调。单纯把去重记录放在本地数据库、远程副作用放在另一个系统，并没有消除这道缝隙。

OpenCode 的恢复代码直接把其恢复语义写为 at-least-once：本地协调避免同时 drain，不避免崩溃后的重复外部副作用。它还说明恢复 sweep 假设旧 owner 已死亡，不能把进程内互斥当成通用分布式租约。[restart.ts:46–61][O14-d]

工程上经常需要“未知”状态。远程服务可能成功但响应丢失，此时应先按 operation ID 查询；若无法查询，就记录不确定性并交给专门的协调流程。把未知强行归类为失败，再无限重试，会把网络不确定性变成重复写入。

## 14.5 练习与参考答案

1. **分类题：** CSV 测试返回退出码 1，模型接口却返回 HTTP 429，二者能用相同重试逻辑吗？<br>
   **参考答案：** 不能。测试失败是任务证据，要改变代码或假设；429 是模型调用可用性问题，应遵守限流等待与预算。反复运行同一失败测试不会修复代码。

2. **计算题：** 不含 jitter 与服务端建议，初始 2 秒、封顶 10 秒，10 次重试等待总和是多少？<br>
   **参考答案：** `2 + 4 + 8 + 7×10 = 84` 秒。还要加 11 次物理请求本身的耗时；84 秒不是整体最坏耗时。

3. **设计题：** 上传测试报告已成功，客户端却超时。如何防止恢复后生成两份？<br>
   **参考答案：** 用跨 attempt 稳定的 operation ID 调用支持幂等的上传端；恢复先查询该 ID。若服务端不支持，使用内容 hash/目标路径等后置条件协调，并明确并发覆盖风险。不能宣称只增加本地 retry counter 就实现 exactly-once。

4. **源码题：** 为什么 OpenCode 分开 Retry 和 Continue，DSH 则保留 assistant attempt？<br>
   **参考答案：** 都在承认物理尝试可能已有可观察内容。前者显式区分无输出重试与有输出后的后续推理，后者保留失败尝试并限制输入重复接纳；具体 history 投影与下一请求组装仍要按各项目阅读，不能认为二者完全等价。

**建议实验（未运行）：** 在“零输出”“文字后”“完整 tool call 后”“副作用成功但结果写日志前”四处注入失败，逐项核对 attempt 数、工具执行次数、历史、成本与恢复判断。该实验最有价值的结果可能是暴露一个无法自动判断的状态，而非让所有用例最终变绿。旧专题可参见 [OpenCode 流与重试](../../agent-infra-study/opencode/04-llm-streaming.md)。

[C14-a]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/responses_retry.rs#L83-L175
[C14-b]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/responses_retry.rs#L93-L117
[C14-b2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/responses_retry.rs#L23-L24
[O14-a]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/retry.ts#L31-L90
[O14-b]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L184-L209
[O14-c]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L220-L275
[O14-d]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L46-L61
[D14-a]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L408-L441
[D14-b]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts#L462-L526
[D14-c]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-retry/src/index.ts#L194-L258
[D14-d]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/llm/llm-retry/src/index.ts#L149-L191
