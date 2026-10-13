# 第 23 章　可观测性与性能：解释一次任务为何成功、缓慢或昂贵

[教材目录](../README.md)

**先修知识**：模型请求、工具执行、事件存储、多 Agent。**学习目标**：设计可关联的执行记录，明确延迟、token、成本和成功率的口径，并在不泄露不必要内容的前提下定位瓶颈。

## 23.1 先确定你要解释的对象

“Agent 很慢”可能指首个可见字符慢、工具执行慢、等用户授权慢，或虽不断输出却迟迟没有正确结果。只统计模型 tokens/s 无法区分这些情况。可观测性的目的，是让可见现象能被关联到执行过程和最终产物，而不是收集尽可能多的文本。

本章采用四个教学定义。**事件**是一个已发生的事实，如 tool started、goal paused；**日志**是供诊断的记录，可能包含结构化字段，也可能是自由文本；**span**描述有开始和结束的一段操作，多个有父子关系的 span 组成 **trace**；**指标**是按确定口径汇总的数值。持久会话日志可能承担恢复职责，遥测系统可能允许采样或丢弃，两者的可靠性要求不同。看到遥测事件并不等于动作已持久保存，没看到遥测也不必然说明动作没有发生。

身份设计通常比字段数量重要。至少考虑 task/goal、session、turn、step、model request、tool call、attempt、child session。`call_id` 标识一次逻辑调用，重试的 `attempt_id` 标识一次尝试；两者混用会把重试算成新任务。父子关系让你把多 Agent 的总成本归到一个目标，同时保留哪个分支产生消耗的解释。真实系统的命名会不同，跨系统映射应显式记录。

## 23.2 案例：CSV 修复的时间账与成本账

设一轮教学观测如下，数字为人工构造，不是三个项目的性能结果：排队 1 秒，首次模型请求 4 秒，读文件工具 0.2 秒，第二次模型请求 3 秒，修改及测试 2 秒，最终回答 1 秒。严格串行时总时长是 11.2 秒。若两个只读子任务并行，不能简单把子任务 span 相加当作用户等待时间；应找依赖图上的关键路径。用户审批停留时间也应独立记录，避免把人类响应速度归因给模型。

| 指标 | 本教材建议的口径 | 常见误判 |
| --- | --- | --- |
| 任务成功率 | 在固定任务集上满足全部验收条件的任务数 / 已启动任务数 | 排除超时或失败，使分母缩小 |
| 端到端延迟 | 接纳任务到交付可验收产物 | 只测模型请求，漏掉工具与重试 |
| 首次可见输出延迟 | 接纳输入到首个用户可见内容 | 与首个模型 token 混为一谈 |
| 工具成功率 | 按工具契约判定的成功调用数 / 尝试数 | 退出码 0 等同于修复正确 |
| 每成功任务成本 | 全部尝试总成本 / 成功任务数 | 只统计成功分支花费 |
| 缓存读取占比 | 缓存读取输入 token / 明确口径的全部输入 token | 分母是否已含缓存说不清 |

一个简化成本式为 `C = (I×pI + O×pO + R×pR + W×pW) / 10^6`，其中 I 是非缓存输入，O 是计费输出，R/W 是缓存读取/写入 token。价格与计费分类必须随 provider、模型、上下文档位记录；reasoning 可能是输出的子集，也可能是标准化后单列的部分，不能不看协议就相加。API 账单、宿主估算和预算记账也可能使用不同口径。

例如一个纯教学请求有 I=1000、O=200、R=4000、W=0，假定每百万单价分别为 2、8、0.2、2，则估算为 `(2000+1600+800)/10^6=0.0044`。即使缓存读取占比达到 80%，该请求也仍有模型输出和工具执行成本；缓存命中率不能单独证明整个任务变快。

## 23.3 三个项目如何提供观测事实

**Codex：同一语义分别进入 metric、log 与 trace。** `record_turn_ttft` 接收一个 duration，同时记录时间指标与 `codex.turn_ttft` 事件。该函数不定义计时起点，若要比较首次用户可见输出，必须继续追踪调用者，不能仅凭函数名宣称它涵盖全部排队和 UI 时间。`record_responses` 在 Completed 携带 usage 时把 input、cache read/write、output、reasoning 和 total 分开写入 span，展示了为何“只有 total_tokens”不够诊断。[Codex：`record_turn_ttft`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/otel/src/events/session_telemetry.rs#L381-L393)，[`record_responses`](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/otel/src/events/session_telemetry.rs#L637-L674)。

`record_turn_cost` 将估算美元字符串转成微美元计数，保留 turn、conversation 和 interrupted 等维度；名称本身是 estimated cost，不能把它直接称为最终收费。多 Agent 创建失败记录则用受限分类和关联 ID，metric tags 没有照搬全部错误文本。[Codex：估算成本](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/otel/src/events/session_telemetry.rs#L395-L450)，[创建失败分类](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/otel/src/events/session_telemetry.rs#L293-L324)。教学上的建议是把高基数身份放在可查询明细中，对汇总维度控制基数；实际项目的每条指标是否这样做，应逐个检查，不能据此宣称所有 metric 都是低基数。

**OpenCode：先标准化 usage，再按价格档位计算。** `SessionUsage.tokens` 把非缓存输入、可见输出、reasoning、缓存读写拆开，并把缺失、非有限值及负值规范到非负数；`calculateCost` 用 input+cache read+cache write 判断上下文档位，按所选档位为输出加 reasoning 计价，最后除以一百万。它依赖 `@opencode/ai` 已规范化的 usage 语义，而不是随便对任意 provider 的原始字段做相同相加。[OpenCode：`SessionUsage.tokens/calculateCost`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/usage.ts#L8-L35)。缺失 usage 被归零便于计算，但分析端若要区分“零消耗”与“未知消耗”，需要额外保存数据完整性标记，这是本教材提出的改进设计。

`EventLogger` 只订阅一个指定事件集合，如 agent/provider/model/config 更新，并注册清理监听器；它不是完整会话轨迹。阅读叫 `logger` 的文件后，应继续追踪事件总线和执行路径，不能把名称当成覆盖面证明。[OpenCode：`EventLogger.layer`](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/event-logger.ts#L7-L19)。本章对此项目的观测映射限定在已读取的事件日志入口和 usage 计算，没有作出全仓库无 trace 的结论。

**DeepSeek Harness：把捕获、脱敏与后端交接分开。** `SessionTelemetryCoordinator.captureEvent` 克隆 canonical event 的 envelope 和 data，附 session/event 身份后送入 record waterfall；这样后续序列化不受原事件对象变动影响。`deliver` 在 backend.emit 成功返回后推进 cursor。这个 cursor 表示已交给后端，不表示远端已经收到；因此它不是端到端投递确认。[DSH：捕获与交接](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry/src/coordinator.ts#L179-L218)，[cursor 语义](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry/src/coordinator.ts#L47-L58)。

Coordinator 的 `session/flush` 监听不返回 SDK flush promise，避免把遥测传输等待加入 turn 结束延迟；后端异常由 capture 侧包含处理。注意这是遥测边界，不能推广成会话持久化 flush 无需等待。此版本 OTel 后端只有 feedback-only 与 disabled 模式，默认在显式反馈时按需捕获；它暴露 byte/count queue、每请求 watchdog 和总 shutdown 上限等配置。[DSH：遥测 flush 监听](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry/src/coordinator.ts#L104-L120)，[后端模式与队列配置](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry-otel/src/index.ts#L80-L107)，[模式接线](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry-otel/src/index.ts#L138-L150)。

## 23.4 优化前先测量，测量前先定义边界

优化顺序可以是：定位慢阶段，检查是否有重复工作，检查模型输入和工具输出是否过大，再考虑缓存和并发。模型 prompt 缓存与工具结果缓存不能混为一谈：前者一般要求输入前缀符合 provider 条件；后者还必须把文件版本、配置和权限等纳入 key。CSV 文件变化后继续复用旧测试结果，会更快地产生错误结论。

背压意味着生产者不能无限快地向消费者堆积工作。对待执行模型任务可用并发信号量和有界等待队列；对遥测可用有界字节队列、采样、聚合或丢弃策略。两者策略不相同：丢一条非关键性能日志可能可接受，丢一个已经接纳的用户任务通常不可接受。观测系统本身也需要记录 dropped count、队列深度和导出失败，才能判断图表里的低流量是否只是数据丢失。

比较性能时固定任务集、环境、模型设置、缓存冷热状态和工具依赖。报告中至少分开成功与失败任务的延迟，并给 p50/p95 与样本量；只报告平均数会掩盖少量长时间卡住的任务。并发测试还需报告吞吐和饱和时的队列等待，否则“单请求快”不代表服务在负载下稳定。

## 23.5 隐私是字段与生命周期的设计

日志可能包含源代码、文件路径、用户输入和工具返回中的凭据。可行设计是先分类字段，再决定是否采集、脱敏、保留期限和访问权限；仅哈希一个低熵邮箱或路径不一定消除可识别性。脱敏应在导出前完成，并对失败采用明确策略。

Codex 的 `user_prompt` 在 `log_user_prompts` 为 false 时把详细日志内容替换为 `[REDACTED]`，trace 侧记录长度及输入类型数量，没有放入正文。这个局部策略不能证明所有工具日志都已脱敏。[Codex：用户输入日志与 trace](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/otel/src/events/session_telemetry.rs#L1152-L1192)。DSH coordinator 则明确其 waterfall 不自带脱敏规则；未装规则时直接传递，规则抛错时本条记录被拦住。是否有“redact”方法与是否已经部署有效脱敏是两件事。[DSH：`redact`](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry/src/coordinator.ts#L197-L207)，[异常包含](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-telemetry/src/coordinator.ts#L241-L250)。

## 23.6 练习与参考答案

1. **计算题**：五个任务总花费 0.50，四个成功，每成功任务成本多少？**参考答案**：0.125。失败任务的成本也应计入；只平均四个成功任务自身花费会低估系统代价。
2. **口径题**：输入总量已包含缓存读取 token，又把缓存读取加到 total，问题是什么？**参考答案**：重复计数。必须先确认 provider 原始字段和标准化字段的包含关系，再计算缓存占比和预算。
3. **源码题**：DSH handoff cursor 增长能否证明 collector 收到记录？**参考答案**：不能，只证明 backend.emit 已接受交接。远端确认、重试和丢弃需看后端 transport 协议。
4. **设计题**：CSV 内容不能上传，但要诊断错误，如何记录 trace？**参考答案**：保存关联 ID、工具名、输入行数、schema 版本、错误分类、执行耗时、代码 revision 和本地证据引用；默认不上传单元格内容。若需要样本，设计显式许可和有界脱敏流程，并测试失败时是否拦截导出。

本章数值均为教学构造；未执行三项目性能基准、负载测试或遥测隐私验证，不能据此为项目排名。
