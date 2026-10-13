# 第 16 章　服务、事件与界面：让用户看到可恢复的执行事实

[教材目录](../README.md)

**先修知识：**异步迭代、队列、Agent 的会话与工具执行，以及持久化与恢复。**学习目标：**区分命令、事件和快照；解释序号的作用域；设计没有快照交接缺口的订阅；分析慢客户端；使界面在断线、重试和旧响应到达时仍然表达正确状态。

本章把 Agent 看成一个持续运行的服务。浏览器只是其中一个观察者：关闭窗口不一定停止测试，窗口重新打开也不能靠旧气泡推断测试结果。本章的通用协议与 CSV 时序是教学设计；三个项目的实现说明以固定提交的源码为依据，不能把教学伪代码当作它们共同提供的 API。

## 16.1　为什么一个执行循环需要三种接口

设用户要求修复 CSV 汇总程序：程序只累加 price，漏乘 quantity；`3.50 × 2 + 12.00 × 3` 应得 `43.00`，旧程序却得到 `15.50`，金额用 Decimal 表示。Agent 要读文件、修改、运行测试、解释结果。若 HTTP 请求必须等全部步骤完成才返回，连接寿命便与任务寿命绑在一起；若只返回“已收到”，界面又需要另一条途径知道后续发生了什么。

因此可以把服务边界分成三类：

| 接口 | 回答的问题 | CSV 案例中的含义 |
|---|---|---|
| 命令 command | 希望服务做什么？是否已受理？ | 提交修复、取消本轮、回答审批 |
| 事件 event | 服务刚刚发生了什么？ | 工具启动、补丁完成、测试结束 |
| 快照 snapshot | 在某个边界上，当前状态是什么？ | 此会话有哪些消息、哪个工具还在运行 |

命令响应成功不自动等于任务成功；事件送达不自动等于落盘；界面渲染完成更不等于副作用完成。服务应定义每个确认的含义，界面应分别表达“提交中”“已受理”“执行中”“需要用户输入”和“结束”。测试卡片必须由测试执行结果更新，不能因模型输出“我将验证”就显示通过。

事件驱动并不要求所有信息都成为永久日志。打字效果、心跳、光标位置通常可以丢弃；测试退出码、已接纳的用户输入与工具结果则需要更强的恢复语义。OpenCode 在类型层区分 `DurableDefinition` 与 `EphemeralDefinition`；持久事件另带 `aggregateID / seq / version`，普通 `id` 与 `created` 不代替这些字段。[源码：`Event.Payload` 与持久事件信封](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/schema/src/event.ts#L16-L78)

## 16.2　序号是坐标，不是万能保证

事件序号表示某一条逻辑日志中的位置。若会话 A 和会话 B 都有 `seq=17`，二者并不冲突；若旧 Agent 和新 Agent 的临时输出计数都从零开始，则必须同时比较 attempt 身份。设计恢复游标时，至少要明确：属于哪个对象、哪个日志世代，以及表示“最后已经应用”还是“下一个期待”。时间戳可以辅助展示，不能证明事件连续：时钟可能回拨，同一毫秒也可以有多个事件。

设快照覆盖到 `c`，增量流随后提供 `c+1, c+2, …`。客户端的教学不变量是：

- 已确认快照表示 `State(c)`，增量必须从这个边界衔接。
- `seq <= c` 的重发不能再次产生应用副作用；`seq > c+1` 表示缺口，不能装作完整。
- 每一条日志单独保存游标；临时流使用自己的 attempt、revision 或 index。
- 重放只重建显示与派生状态，绝不重新运行已完成的 shell 命令。

“只要带序号就可靠”是错误推论。还必须有保留策略、缺口检测，以及补齐或重新取快照的动作。OpenCode 的 `Seq` 注释明确将其限定为一个 aggregate 的持久日志位置；它不是整个服务器事件流的统一计数器。[源码：`Event.Seq`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/schema/src/event.ts#L16-L35)

## 16.3　贯穿实例：修复已完成，界面为什么一直转圈

假设测试开始为事件 42，测试结束为 43。浏览器在 42 后断线。一个有缺陷的恢复流程先读快照，再注册监听：快照读到 42，事件 43 恰好发生在两者之间，订阅之后永远没有新的测试结束事件。TCP 没有丢包，业务事实仍然丢了。

一种教学方案是先注册并缓冲，再获得带游标的一致快照，最后处理边界之后的事件：

```text
subscription = subscribe_and_buffer(session)
(snapshot, c) = read_consistent_snapshot(session)
publish(snapshot)
expected = c + 1
for e in subscription:
    if e.seq < expected: continue       # 快照已包含或重复送达
    if e.seq > expected: rebaseline()   # 明确修复缺口
    else:
        apply_to_view(e)
        expected += 1
```

这里最难的步骤是 `read_consistent_snapshot`：投影值和游标必须对应同一个边界。若投影已经包含 43，而游标却标成 42，随后应用 43 仍可能重复计数。另一个可行方案是把“构造恢复响应并加入订阅”放进同一个串行执行通道，而不是暴露游标交接给客户端。

DeepSeek Harness 的 `SessionHistoryController.follow` 给出第一种方案的具体实现：先监听 `session/event` 并放入 deque，随后取得 source、cursor 和开场 snapshot；它还监听 `session/created`，补入不会产生普通通知的构造种子后缀。[源码：`follow` 的监听与开场快照](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/history.ts#L120-L203) 进入增量阶段后，从 `cursor + 1` 起步，跳过旧序号，并在新事件不等于期望序号时抛出错误，而非默默继续。[源码：连续性检查与清理](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/history.ts#L213-L240)

注意，这里的 snapshot 含分页记录、`hasMore`、投影与可选临时输出基线；“开场状态完整”不代表把全部历史正文一次性下载。控制器也将 `page` 和流式 `follow` 分为两个方法。[源码：`SessionController.page/follow`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/index.ts#L477-L498)

## 16.4　三种实现策略：串行恢复、重新读取与双轨流

### Codex：把运行中恢复放进线程监听器

Codex 的 `ThreadListenerCommand::SendThreadResumeResponse` 表达“发送运行中线程历史并原子订阅新更新”的意图。对应 listener 在同一循环中选择处理 listener command 或 `conversation.next_event()`，并等待当前处理完成。由此，恢复交接和正常事件处理获得明确的串行边界。[源码：命令定义](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/thread_state.rs#L62-L75)、[源码：listener 循环](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L298-L329)

`handle_pending_thread_resume_request` 读取活跃 turn 的 snapshot；它随后与 pending unload 串行检查，线程正在关闭则返回错误，连接已经关闭则停止加入订阅，成功后发送 `ThreadResumeResponse`。这使“重连观察仍在运行的测试”有专门路径，不能简单等同于重新发送一次修复命令。[源码：活跃 turn 读取](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L721-L745)、[源码：关闭检查与连接订阅](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L846-L871)、[源码：响应发送](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/request_processors/thread_lifecycle.rs#L915-L937)

这段证据支持运行中线程的恢复交接，不证明进程崩溃后的所有副作用都可恢复，也不构成“每条 UI 通知都有可续传全局序号”的保证。两类问题必须分开验证。

### OpenCode：实时通知配合重新读取，处理读取期间的新变化

OpenCode `EventHandler` 先发送 `server.connected`，再发送 live feed，并每 15 秒合入 SSE 心跳注释。客户端 `createClientConnection` 要求首事件是 `server.connected`，以任何收到的字节更新空闲监测，默认空闲超时为 45 秒；流失败后进入重连循环。心跳说明连接仍有活动，不说明 CSV 测试成功。[源码：SSE handler](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/src/handlers/event.ts#L8-L35)、[源码：超时参数与连接读取](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/client/src/solid/connection.ts#L32-L38)、[源码：心跳活动、首事件及读取循环](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/client/src/solid/connection.ts#L84-L134)、[源码：重连循环](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/client/src/solid/connection.ts#L147-L182)

数据层在连接不是 connected 时令同步缓存失效。收到 `server.connected` 后，会重新查询活跃 session；查询尚未返回时，将新生命周期变化记录到 `activeUpdates`，响应返回时用这些变化覆盖旧 snapshot。因此“session 已结束”的实时变化不会被稍晚到达的旧“仍在运行”列表覆盖。[源码：`createData` 缓存失效](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/client/src/solid/data.ts#L1965-L1973)、[源码：`handleEvent` 的 hydration 合并](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/client/src/solid/data.ts#L599-L632)

以上观察限于公共 SSE 与这段客户端恢复路径。`EventFeed.frame` 输出 `data:` 帧，此处不能据 durable envelope 的存在，推导公共 SSE 会依据 `Last-Event-ID` 自动重放所有遗漏事件。[源码：帧编码](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/src/event-feed.ts#L23-L38)

### DeepSeek Harness：持久事实与临时展示分轨，再显式结算

DSH 的 `follow` 同时支持有序会话事件和可选 assistant 临时流。临时流不能推进持久游标，所以开场时另外取 accumulator baseline 与同步 ordinal cut；cut 之前的临时帧已被基线代表或替代，只发送之后的帧。[源码：双轨开场与筛选](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/history.ts#L165-L203)、[源码：临时帧分支](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/history.ts#L213-L232)

客户端 `ClientAssistantStream.replace` 接纳重连 baseline；`acceptDurable` 可以暂存与活跃 attempt 对应的结算事件。`acceptFrame` 检查 attempt 与 chunk index，发现跳号时要求 `rebaseline`；结束帧还必须找到对应的持久结算事件。于是打字过程中看到的“测试通过”文本与最终提交的 assistant 内容有明确合并规则。[源码：baseline 重建](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/client/sessions/assistant-stream.ts#L52-L101)、[源码：结算与连续性验证](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/client/sessions/assistant-stream.ts#L109-L188)

这还提供一个很好的反例：`replace` 为展示中的临时行构造小数 `seq`，用于放在两个持久位置之间。它是展示排序值，不能拿来当服务端持久日志游标。读类型和使用地点，比只看字段名字可靠。

## 16.5　背压：慢界面不能变成无限内存

若生产速率为每秒 λ 条、消费速率为 μ 条，且 λ 长期大于 μ，任何有限缓冲最终都会满。扩大队列只推迟问题；解决方法必须改变生产、消费或溢出后的恢复策略。

| 策略 | 得到什么 | 必须承担什么 |
|---|---|---|
| 生产者等待消费者 | 保留顺序与内容 | 慢界面可能拖慢执行链 |
| 合并可替代状态 | 减少无用刷新 | 只适用于有明确合并规则的数据 |
| 断开慢观察者，重新取基线 | 隔离执行与展示速度 | 必须能检测失败并恢复视图 |
| 无界缓存 | 暂时不丢消息 | 长时拥塞时内存持续增长 |

Codex 的 `send_message_to_connection` 对可断开的连接用 `try_send`，队列满即移除并请求断开；没有 disconnect token 的路径则等待 `writer.send`。因此不能笼统写成“Codex 总会丢弃慢客户端”或“Codex 永远阻塞生产者”。[源码：`can_disconnect`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/transport.rs#L68-L101)、[源码：分支策略](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/src/transport.rs#L140-L177)

OpenCode `EventFeed` 默认每订阅者容量 4096。虽然底层创建的是 dropping queue，发布逻辑检查 `offerUnsafe` 的结果：放不进去就移除该订阅者，并以 `SubscriberOverflowError` 使其失败。这与“静默丢一条后继续”不同；编码失败则会使当前所有订阅者失败。[源码：容量与错误类型](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/src/event-feed.ts#L8-L21)、[源码：发布与队列生命周期](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/src/event-feed.ts#L39-L80)

DSH 本章检查的 `SessionHistoryController.follow` 局部使用 deque，未在这个函数里设置容量阈值。这只是该边界的观察，不能据此断言整个传输系统没有流控。扩展实验应继续追踪 Remote carrier，并对慢消费者测量队列长度、进程内存和取消后的释放。

## 16.6　界面是一份投影，成功必须回到执行证据

界面可以缓存派生状态，但要有统一入口，让渲染代码不直接拼接网络消息。DSH 的 `Session.subscribe/getSnapshot` 提供订阅与稳定快照读取；快照在需要时通过 notifier 刷新。[源码：`Session` 的读接口](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/api/session-controller/src/client/sessions/session.ts#L503-L518)

在 CSV 案例中，建议同时保留三类 UI 状态：连接是否健康；任务是否运行；验证结果是否已确认。断线应显示“状态待同步”，不能直接写“测试失败”；重新连上也不能直接写“测试成功”。最终通过状态应能够追溯到命令、退出码及输出摘要。模型的解释可以链接这些事实，不能覆盖它们。

取消也有两个层次：取消观察流和取消 Agent 执行。DSH `follow` 的 finally 会清理监听，说明观察者生命周期有释放动作；它不意味着每次浏览器断线都会撤销 CSV 修改。产品若需要“关页面即停止”，必须把这一语义明确设计成执行控制协议，而不是寄希望于 socket 自然关闭。

可继续对照旧笔记中的 [DSH 流式输出](../../agent-infra-study/dsh/04-llm-streaming.md) 与 [Codex 持久化](../../agent-infra-study/codex/07-persistence-reliability.md)。本章源码说明不依赖旧笔记作证。

## 16.7　练习与参考答案

1. **判定题：**UI 收到“测试完成”的 assistant token 后，可以把测试标为通过吗？<br>
   **参考答案：**不能。token 是模型输出，既可能未最终结算，也不证明测试退出码。应由对应工具执行的确认结果决定，并保留失败、取消及尚未同步的区别。

2. **时序题：**快照 cursor 为 42；缓冲事件按顺序为 41、43、43、45。按教学算法，哪些能应用？<br>
   **参考答案：**41 被跳过；第一次 43 被应用；第二次 43 被去重；45 暴露缺少 44，必须补齐或重新取基线，不能将 cursor 直接改成 45。前提是这些都是同一日志的持久事件。

3. **源码解释题：**为什么 OpenCode 使用 dropping queue，却不能描述成“慢客户端自动丢消息直到追上”？<br>
   **参考答案：**因为 `publish` 检查入队失败，并移除、失败化该订阅者。队列类型的名字没有完整表达应用层溢出语义。还要分别分析单订阅者溢出与编码错误。

4. **设计题：**为 CSV Agent 设计一次断线恢复测试，覆盖“测试结束恰好发生在读快照期间”和“旧快照响应迟到”。<br>
   **参考答案：**用可控屏障暂停快照读取，先确认监听已建立，再提交测试结束事件，然后释放快照；最终状态应包含一次结束结果。另让第一次查询在重连后才返回，第二次查询已确认结束；通过查询世代或读取期间更新覆盖阻止旧结果恢复成 running。断言工具命令只执行一次、持久游标不越过缺口、取消观察后监听数回到初始值。仅断言“页面有文字”不足以验证恢复正确性。

**验证边界：**本章进行了固定提交源码精读，没有运行上游测试、真实模型请求或慢网络压测；练习 4 与背压测量均为待执行实验。
