# 第 22 章　长期目标：调度、预算与崩溃后的继续执行

[教材目录](../README.md)

**先修知识**：会话、turn、持久化、取消和多 Agent。**学习目标**：区分目标状态与运行状态，设计不会重复启动的续轮调度器，并理解 checkpoint、预算和外部副作用对恢复的约束。

## 22.1 Goal 不是一个特别长的 turn

**Goal** 表示用户希望最终成立的结果及完成条件；**turn** 是一次被宿主接纳的执行周期，内部可能有多次模型请求和工具调用。一个 goal 可以跨越多个 turn、多个上下文窗口甚至多个进程；一个 turn 结束只表示当前执行周期停止。模型输出“继续处理下一步”并不能替代宿主真正安排下一轮。

长期任务至少需要三个独立状态面。第一是目标：active、paused、blocked、complete 等业务状态。第二是执行：idle、running、stopping 等资源状态。第三是调度资格：这个进程此刻是否获准自动推进。目标 active 而进程 idle 可能是等待外部结果；目标 active 而自动续轮被关闭可能是恢复后等待重新激活。把三者压成一个 `isRunning` 会使暂停、恢复和展示互相误导。

还要区分**进展**与**活动**。发送消息、调用工具、消耗 token 是活动；新增了一个被验证的事实或完成了一个验收项才是进展。活动检测可防止空响应死循环，但不能证明任务在接近成功。教学系统可以保存进度账本：验收项、状态、证据、所基于的版本、下一动作。它应记录“未验证”，而不能用一个漂亮的完成百分比替代证据。

## 22.2 案例：CSV 修复跨越三个生命周期

第一个 turn 复现漏乘 quantity：pen 3.50×2 与 book 12.00×3 被算成 15.50，而 Decimal 计算应得 43.00，保存输入、错误输出和定位。第二个 turn 补上数量乘法并启动测试；进程在测试结束后、报告写入前崩溃。第三个 turn 恢复时，不能仅因旧对话说“已测试”就认定完成，应检查当前文件 hash、测试命令及结果是否持久记录。若没有可靠结果，重新运行可重复的测试比猜测便宜。

checkpoint 是一个能恢复工作的**一致边界**，可以由日志与快照共同提供，不必是单个大文件。建议记录：目标身份与修订号、当前工作版本、已完成及未完成项、外部 job ID、预算消费、待投递消息、最近可靠证据。仅保存自然语言摘要会丢失调用身份；仅保存工具日志又可能丢失为什么选择某个修复。

```text
on_wakeup(goal_id):
  获取该目标的调度所有权
  读取最新目标、预算、输入队列
  若已暂停/完成/失去资格：退出
  若已有执行：登记一次待处理唤醒，然后退出
  将上一轮必要状态写入可靠存储
  再检查目标修订号、取消信号和普通用户输入
  接纳至多一个新 turn，并记录触发来源
```

“再检查”不可省略：存储写入期间用户可能修改目标或暂停任务。调度器必须防止旧目标读出来之后、新目标写进去之前启动过时工作。多个唤醒也不必对应多个 turn；它们可合并为“有新工作待检查”，真正的工作内容应从可靠队列读取。

## 22.3 Codex：锁住目标读取与空闲启动窗口

`GoalRuntimeHandle::continue_if_idle` 先检查工具可用性，在目标状态许可锁内查询 continuation deferral，取得 live thread 并重读持久 goal；只有状态为 `Active` 才构造继续输入，并调用 `start_turn_if_idle`。成功接纳后记录 continuation turn ID，便于后续停止判定识别自动轮次；线程不可用、目标非 active 或启动被拒绝都不会假装已经继续。[Codex：`continue_if_idle` 前置条件](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/runtime.rs#L436-L479)，[原子空闲启动与来源登记](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/runtime.rs#L480-L516)。这说明存在自动续轮机制，但这段代码本身不证明任意关闭的线程都会在桌面应用重启后自动恢复。

目标变更也有单独的会计边界：`prepare_external_goal_mutation` 在持久 objective/status 改变前结算活动或空闲阶段的进度，并重置空响应追踪。`apply_external_goal_set` 对 active、budget-limited 及其他终止/暂停状态分别处理。[Codex：外部目标变更前结算](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/runtime.rs#L164-L188)，[目标状态处理](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/runtime.rs#L225-L253)。

`GoalAccountingState::progress_snapshot` 将当前 turn 尚未结算的 token 增量与 descendant token 增量相加，并按同一 goal 的墙钟基线计算时间。更换目标时重设基线，避免把前一个目标的消耗转嫁给新目标。读者应特别注意“累计表值”与“本次增量”的区别，否则周期性结算会重复扣预算。[Codex：更换目标基线](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/accounting.rs#L332-L357)，[进度快照](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/src/accounting.rs#L404-L450)。

## 22.4 OpenCode：以持久执行声明恢复被打断的工作

在已检查的 `SessionExecution` 与 `SessionRestart` 边界中，最接近本章问题的是执行恢复，而不是一个可直接等同于 Codex goal 的接口。`SessionExecution` 将运行开始事件与 `store.claim(sessionID)` 放在同一提交中；正常成功或失败会释放声明，用户中断也释放，shutdown 中断保留声明。这个 write-ahead claim 表示“有一个执行尚未可靠结束”，使恢复不依赖进程最后能否运行清理代码。[OpenCode：claim 与 drain](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L76-L110)，[终态释放规则](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts#L111-L145)。

`SessionRestart.prepareResume` 在真正恢复前持久增加尝试计数；超过配置上限会发失败事件并释放 claim。默认上限是 10，且计数针对被恢复的 turn，不是整个 session 的终身限制。它防止“每次进程重启都把重试次数归零”的崩溃循环。[OpenCode：恢复计数语义与默认值](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L23-L33)，[`prepareResume`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L77-L98)。

源码明确限定恢复是 **at-least-once**：本地协调防止并发 drain，却不能消除崩溃后的重复外部副作用；恢复扫描还假定旧 claim 的拥有进程已死亡，并由 managed-server 协议保证该前提。教学系统若增加 cron 唤醒或跨机器调度，必须另外解决租约、旧 worker fencing 和幂等，不能把进程内协调器当成分布式锁。[OpenCode：恢复保证与部署前提](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution/restart.ts#L35-L61)。

## 22.5 DeepSeek Harness：持久 phase 与本地 armed 分离

DSH 的 `GoalRef` 包含稳定 ID 与递增 revision，`GoalSnapshot` 保存 objective、phase、轮次上限；`GoalActivation` 则是 `armed/disarmed`，只存在于活进程中，不进入持久投影。恢复得到 active goal，并不等于自动获得续轮资格。这是一种把“任务尚未完成”与“现在可以自动执行”分开的具体设计。[DSH：goal 类型与修订号](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal/src/types.ts#L19-L72)，[投影与 activation 边界](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal/src/types.ts#L89-L115)。

`goal-round-driver` 只在确切的 live Agent、idle 且没有竞争普通输入时推进；若需要 checkpoint，先 `await ctx.sessions.flush`，失败就 disarm；flush 后再检查条件。随后要求 goal 同时 active 与 armed，达到 `maxGoalRounds` 则以 `round-limit` blocked。它为下一轮保留 `{goalId, revision, round, messageId}`，并通过 followup 送入 inbox；同一 Agent 的触发由一个串行 driver 合并处理。[DSH：可推进条件](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts#L96-L114)，[checkpoint 与轮次接纳](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts#L137-L192)，[合并调度触发](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts#L207-L235)。这里的 `maxGoalRounds` 是轮次预算，不能当作 token 或金额预算。

## 22.6 预算与恢复的工程判断

预算应先定义单位和覆盖范围。token 预算涉及缓存输入是否计入、输出是否包含 reasoning、子任务如何归属；轮次预算限制自动续轮次数，但一次轮次仍可能很贵；墙钟预算包含等待，CPU 时间不包含网络等待；并发预算只限制同时占用的资源。运行时通常在响应或工具边界得到确切消耗，因此最后一次不可分割调用可能造成超额，设计应预留收尾空间并报告实际用量。

“预算用完”应保留为预算停止，不能标成完成；“暂时没有新证据”也不应自动标成永久 blocked。blocked 应带可操作的原因和解除条件。若换成需求没有说明金额精度的案例变体，缺少这条规则可能需要人工决定；测试服务暂时不可用可在有限退避后重试；语法错误则通常能由 Agent 在本地修正。将三者统一成无限重试会消耗预算而不增加信息。

外部副作用需要独立恢复策略。读文件、运行无副作用测试通常可以重做；发布版本、发送邮件和扣款不能凭“日志没有结果”就重做。应保存操作 ID，向外部系统查询结果；若远端支持幂等 key，用同一逻辑操作身份重试。checkpoint 能说明宿主记住了什么，不能让不支持事务的远端动作自动具备 exactly-once 语义。

## 22.7 练习与参考答案

1. **概念题**：为什么 active goal 可以同时是 idle execution？**参考答案**：目标仍未完成，但可能等待输入、检查点或调度资格；业务状态与执行资源状态是两个轴。
2. **竞态题**：目标 revision 7 在 flush 期间被用户改成 8，调度器是否可以继续执行已准备的第 7 版提示？**参考答案**：不可以；需在接纳前比较修订号，撤销过时预约，再读取新目标。保持读取到接纳的锁或 CAS 都是可选机制。
3. **恢复题**：测试实际通过但日志没写入，邮件实际发出但日志没写入，二者应同样重试吗？**参考答案**：测试可在确认无副作用后重跑；邮件先查询发送系统或操作 ID，避免重复通知。恢复策略取决于副作用而非调用名称。
4. **设计题**：为 CSV 修复设计一个最多 20 分钟、最多 8 个自动 turn 的任务。**参考答案**：分别记录墙钟与已接纳轮次，预留最终验证和写报告时间；checkpoint 保存 revision、diff、测试证据和待办；任一预算停止均保留未完成项，只有最终版本通过约定测试才 complete。新用户输入具有独立接纳规则，不能由旧的自动预约覆盖。

本章是固定源码的静态分析；恢复、预算超额和崩溃注入实验均未执行。
