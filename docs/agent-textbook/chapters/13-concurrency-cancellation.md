# 第 13 章　并发、顺序与取消：让异步工作有主人

[教材目录](../README.md)

**先修知识：** 异步函数、Promise/Future、锁，以及工具调用与工具结果的区别。**学习目标：** 能把启动顺序、完成顺序、提交顺序分别画出来；能设计有界调度器；能说明收到取消请求之后还有哪些工作必须完成。

## 13.1 为什么 Agent 的并发不能只写成 Promise.all

设用户要求修复 CSV 汇总程序漏乘 quantity 的问题：pen 的 price=3.50、quantity=2，book 的 price=12.00、quantity=3；错误总额 15.50，正确总额 43.00，金额使用 Decimal。Agent 想读取 `sum.py`、读取 `test_sum.py`、补上乘法、运行测试。这四项工作不是四个独立函数：前两项可以重叠；修改依赖读取结果；测试必须看见修改完成后的文件。并发的第一步是建立依赖关系，而不是增加线程数。

把任务画成有向无环图：节点是一次工具调用，边 `A → B` 表示 B 的前置条件要求 A 已经达到指定状态。这个状态可能是“计算完成”，也可能是“结果已进入会话历史”，还可能是“写入已经持久化”。三者不能互换。读取任务计算完，但结果尚未提交，模型就不能依据它构造可靠的修改请求。

还要区分三种顺序。**启动顺序**是执行器放行工具的顺序；**完成顺序**由网络、磁盘和进程决定；**提交顺序**是结果进入可重放历史、触发后处理的顺序。允许完成顺序变化，同时固定提交顺序，能兼顾等待重叠与历史的可解释性；代价是前面的慢任务会阻塞后面已完成结果的提交，这叫队首阻塞。

## 13.2 有界滚动池与独占屏障

教学调度器给每个工具标记 `parallel` 或 `exclusive`。标记不是对所有场景的永久承诺：读取同一静态文件通常容易并发；修改文件、切换工作目录、更新工具注册表则需要按具体语义判断。独占屏障要求此前一组已启动任务先结束，再独占执行，然后才放行后组。

```text
模型顺序： read(source)  read(test) | edit(source) | test(unit)  inspect(diff)
执行顺序： ├───── A ─────┤         |──── C ──────| ├── D ──┤
           ├── B ──┤              |            | ├─ E ─┤
提交顺序：       等 A → A → B      |     C      |    D → E
```

图中 D、E 仅在两者均不修改相互依赖资源时才能并行；例如测试会重写 golden files，就应重新分类。一般依赖图比两个类别更精细，但类别屏障容易检查，也更适合作为最小实现。

有界滚动池在任意任务完成后释放名额，补入下一项；固定批次则等整批完成再补。滚动池减少空槽时间，却需要处理结果缓存、重分类与取消。以下为教学伪代码，不是三个项目共有实现：

```python
while remaining or running:
    while not cancelled and capacity_available() and next_is_admissible():
        running.add(start(next_call()))
    result = await any_finished(running)
    ready[result.index] = result
    while next_commit_index in ready:
        await finalize_and_append(ready.pop(next_commit_index))
        next_commit_index += 1
# 取消后仍须等待已启动任务达到可记录的终态
```

`capacity_available` 不宜只有任务数。还可以同时约束子进程数、文件描述符、输出字节、模型并发与剩余时间。若一个工具输出 100 MB，任务数只有 4 仍然可能耗尽内存。资源预算应在准入时预留、终态时归还；重试属于原任务的成本，不能凭新建 attempt 绕过额度。

## 13.3 精读三个实现：相似目标，不同顺序承诺

### Codex：读写门闩与有序回收

`ToolCallRuntime` 保留广告工具列表所属的 `StepContext`，避免晚执行的调用误用后来一轮的工具配置。[parallel.rs:45–65][C13-a2] 在 `handle_tool_call_with_source` 中，支持并行的调用获取读锁，其他调用获取写锁。等待工具 readiness 和等待锁都受取消控制。锁保护的是执行准入区间，不是“所有 shell 命令天然安全”的证明。[parallel.rs:202–239][C13-a]

执行函数返回时释放锁并记录 `result_ready`；采样层用 `FuturesOrdered` 的 `drain_in_flight` 按顺序取结果并调用 `record_annotated_conversation_items`。因此“工具已经算完”与“会话已经收到结果”可以相隔一段时间，性能诊断应该分别记录这两个时刻。[parallel.rs:239–253][C13-b] [turn.rs:2461–2488][C13-c]

取消也有分支：若 handler 声明取消时需要自行完成、已达到终态，或任务已经结束，就等待它的结果；否则 abort 子任务，并合成被中止的工具结果、发出终态通知。`AbortOnDropHandle` 让丢弃持有者时也能约束子任务生命周期。这里证明的是该调度层的处理规则，外部进程和远程服务能否立刻停止，还要阅读各 handler。[parallel.rs:258–317][C13-d]

### OpenCode：作用域内子任务与执行清理窗口

`SessionStep.attempt` 在 `Tool.Called` 发布完成后才 `forkScoped` 本地工具；provider 流与各工具 fiber 保留各自来源的顺序，没有共同的工具结果顺序队列。它会等待全部工具 fiber，并在流被中断时传播 interrupt。最终工具与 Step 事件放在不可中断的清理区域，工具主体则通过 `restore` 保持可取消。不要把 Codex 的有序回收保证移植成 OpenCode 的实现描述。[step.ts:90–157][O13-a]

会话级别还有一层并发控制。`SessionRunCoordinator.make` 对同一 key 串行、不同 key 允许并发。`pendingWake` 像门铃：执行中收到新工作就再次 drain；在判定即将结束之后收到的 wake，则在 settle 时启动后继执行，修补“最后一次检查”和“转为空闲”之间的竞态。[run-coordinator.ts:74–119][O13-b]

`interrupt` 先接纳中断，清理可以异步继续；`awaitSettlement` 等被中断的这一代执行完成，`awaitIdle` 还会跟随后继执行。若用户一边停止旧任务一边提交新任务，后者可能迟迟不满足，所以 API 必须说明等待的是哪种状态。[run-coordinator.ts:147–195][O13-c] 在已读 Step 启动路径中没有发现统一并发数门槛，不能据此宣称整个项目没有限流；只能确认本层的重点是作用域与终态协调。

### DeepSeek Harness：有界池、动态重分类、顺序提交

`executeToolCalls` 每次分组前查询 `executionMode`。[tool-calls.ts:83–100][D13-a2]`runGroup` 读取 `maxParallelToolCalls`，只让 dispatch/body 重叠；prepare 和结果 finalize 依模型顺序进行。`commitReady` 只推进连续的已完成槽位，同时提交 additionalContexts。后续尚未启动的调用会重读 mode，注册表变更可能产生新屏障。[tool-calls.ts:132–213][D13-a]

取消时停止补入新任务，排空已启动任务，再为未启动调用记录带 `TOOL_ABORTED_BEFORE_DISPATCH` 的合成错误结果。调度器内部异常同样先 `allSettled` 排空，但向拥有者抛出失败，交由 Step 处理缺失结果。两者都维护调用与结果可以对应的历史，却不能把合成错误理解成“撤销已经发生的写文件”。[tool-calls.ts:216–259][D13-b]

## 13.4 结构化并发是一份生命周期合同

所谓结构化并发，核心不是用了某个库，而是子工作有明确拥有者：父作用域退出前，必须知道子工作已完成、已取消，还是被明确转交给后台服务。否则，一个已经取消的 CSV 修复任务可能在用户开始下一次编辑后继续写文件。

最小取消协议包含：关闭新任务准入；向已启动任务传播信号；等待其清理；给每个已宣告调用记录终态；释放资源；最后发布父任务完成。取消请求的确认可以很快，清理完成的确认需要更晚。UI 应呈现“正在停止”，而不能在收到请求响应的一瞬间宣称所有活动都结束。

取消不等于回滚。若 C 已把逐行 `Decimal(price) × quantity` 的逻辑写入文件，再取消 D 的测试，文件依然变更。正确结果是“修改已完成，验证被取消”，而非“任务没发生”。记录这一区别，既帮助下一次 Agent 接续，也避免用户依据错误终态作决定。

## 13.5 练习与参考答案

1. **时序题：** A、B 为并行读取，耗时分别 5 秒、1 秒，提交要求 A 在 B 前。第 2 秒能否向下一模型请求提供 B？<br>
   **参考答案：** 若请求只读取已提交前缀，不能。B 可在诊断 UI 中显示 ready，但模型可见性要等 A。若要提前使用 B，必须改变协议，允许分组提交或显式乱序关联，不能偷偷跳过 A。

2. **取消题：** 工具已经完成写文件，但结果发布尚未完成时收到取消，该怎么处理？<br>
   **参考答案：** 保存实际完成结果并完成必要的终态发布，不能重写为“未执行”。清理区可以短暂屏蔽取消；若发布失败，恢复状态应承认副作用可能已经发生。

3. **设计题：** 在并发上限 4 的池中，第一个任务永久挂起，后三个不断完成并补入，结果缓存会怎样？<br>
   **参考答案：** 并发上限不限制已完成但未提交的积压，缓存可能持续增长。另设 ready-result 字节/数量上限、截止时间，必要时停止补入；不能只靠 semaphore。

4. **源码题：** 为什么 OpenCode 同时需要 `awaitSettlement` 和 `awaitIdle`？<br>
   **参考答案：** 前者等待特定执行代际清理，后者等待整个 key 无活动，包含新接纳工作的后继。两者回答的业务问题不同。DSH 的 drain started calls、Codex 的等待终态分支，也体现“取消已接纳”和“清理已完成”的区分。

**建议实验（未运行）：** 用可手动释放的 barrier 构造两读、一写、两检查；记录 dispatch、ready、commit、cancel、settled 五种时间戳。用 barrier 证明重叠与屏障，不把机器上的偶然耗时当作正确性证明。进一步对照旧专题：[Codex 工具调度](../../agent-infra-study/codex/03-tools-sandbox.md)、[DSH 工具调度](../../agent-infra-study/dsh/03-tools-sandbox.md)。

[C13-a]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs#L202-L239
[C13-a2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs#L45-L65
[C13-b]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs#L239-L253
[C13-c]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs#L2461-L2488
[C13-d]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs#L258-L317
[O13-a]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts#L90-L157
[O13-b]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/run-coordinator.ts#L74-L119
[O13-c]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/run-coordinator.ts#L147-L195
[D13-a]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts#L132-L213
[D13-a2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts#L83-L100
[D13-b]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts#L216-L259
