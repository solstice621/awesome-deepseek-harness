# 三项目横向分析：比较契约，不比较功能清单

[返回总目录](README.md)

本文基于 24 篇专题中已经标注的固定源码与文档；每个单元格链接到含官方来源的详细分析。这里的取舍解释属于研究分析，不是作者原话、产品排名或性能评测。

## 1. 八个主题的对应关系

| 主题 | Codex | OpenCode | DSH |
|---|---|---|---|
| 执行循环 | [Turn 协调与 StepContext 快照](codex/01-agent-loop.md) | [admission/execution/runner/attempt 分层](opencode/01-agent-loop.md) | [公共 Agent 契约与默认 Loop、inbox 边界](dsh/01-agent-loop.md) |
| 上下文 | [活动历史替换与持久化标识一致性](codex/02-context-session.md) | [指令准备、输入提升、活动 context 与 provider 状态](opencode/02-context-session.md) | [append-only log、Surface 与纯消息投影](dsh/02-context-session.md) |
| 工具与执行 | [审批/沙箱 orchestrator 与共享/独占执行门](codex/03-tools-sandbox.md) | [请求捕获工具、typed output/content、终态结算](opencode/03-tools-sandbox.md) | [有界滚动池、动态分类、模型顺序提交](dsh/03-tools-sandbox.md) |
| 模型流 | [连接、认证、路由状态与增量续接](codex/04-llm-streaming.md) | [Step 内 Attempt、部分输出与重试决策](opencode/04-llm-streaming.md) | [共享流协议、绑定路由与完整尝试记录](dsh/04-llm-streaming.md) |
| 扩展 | [宿主类型化 contributor registry](codex/05-extension-architecture.md) | [插件代际、就绪屏障与失败保留旧版本](opencode/05-extension-architecture.md) | [服务定义/实现/消费者与可逆作用域](dsh/05-extension-architecture.md) |
| 编排 | [身份图、fork 过滤、runtime 驻留与当前父权限](codex/06-task-orchestration.md) | [父子 Session、Job、前后台结果交付](opencode/06-task-orchestration.md) | [Goal 状态/自动授权分离与 child activation](dsh/06-task-orchestration.md) |
| 可靠性 | [ThreadStore/LiveThread 与有条件 daemon 恢复](codex/07-persistence-reliability.md) | [durable inbox、write-ahead claim、终态释放](opencode/07-persistence-reliability.md) | [单写者 Handle、append/flush 与保守修复](dsh/07-persistence-reliability.md) |
| 可观察性 | [本地原始证据与离线语义图](codex/08-observability-evaluation.md) | [一次编码、连接级背压与 volatile feed](opencode/08-observability-evaluation.md) | [ledger/live/telemetry 分层与交接语义](dsh/08-observability-evaluation.md) |

## 2. 第一条贯穿线：决定使用哪个版本的能力

Codex 让模型产生的工具调用携带该 Step 的上下文快照。OpenCode 的工具契约在请求时捕获声明及实际执行的工具值。DSH 的调度器会在启动未运行的调用前重新判断其并发模式，尤其在 barrier 或结果观察者修改注册后。

这些设计回答的并非完全相同的问题：请求语义一致性、工具实现身份和并发策略的动态变化要分开讨论。**不能把三者简化成“快照好还是动态好”。** 应用同一个实验：模型已经看见某工具声明、实际执行尚未开始时改变配置，然后分别观察执行实现、权限、并发模式和记录的版本。详见三个项目的 03。

迁移到平台层时，应考虑 request configuration version、policy version、tool implementation identity；它们是否一起冻结，需要根据可撤回权限和安全要求设计，本文没有替三项目补出未读的版本协议。

## 3. 第二条贯穿线：接受了工作与完成了工作之间有哪些 ACK？

OpenCode 的 durable inbox 让接纳和 wake 分开；Codex RecordedTurnInput 区分已入记录路径与 flush；DSH Handle 区分 append 接纳/可见与 flush 持久。三者都提醒：一个成功返回值只有在说清所处层次后才有意义。

建议统一画下列问题，而不是强迫三个项目使用同名状态：

```text
用户提交 → 接纳记录 → 执行权获得 → 模型请求
          → 工具副作用 → 工具结果记录 → 任务终态 → 通知交付
```

在每两个节点之间问：崩溃后可以证明什么？谁负责恢复？重复调用如何识别？权限是否可能已改变？有些节点在具体实现中合并，有些没有 durable 保证，必须据实标注。

## 4. 第三条贯穿线：取消不是一个 bool

Codex 工具取消可能继续等待必须清理或已有终态的 handler；OpenCode 区分 interrupt acceptance、当前 execution settlement 与 idle；DSH 停止补充工具、等待已启动 dispatch、补齐未启动调用的结果，还要处理 factory 创建资源迟到。

**分析：** 对于 Agent Runtime，取消是一个协议：撤回继续授权、传播信号、停止新工作、处置现有工作、记录结果、释放资源。只在最外层把任务状态设置为 cancelled，会掩盖进程仍在运行或旧回调污染新任务的问题。具体证据见三个项目的 01/03/07。

## 5. 第四条贯穿线：模型可见历史不是所有运行证据

Codex trace 将 model-visible conversation 与 runtime objects 分开；OpenCode 区分临时机器 output、持久 content 和 UI metadata；DSH 将 log-only attempt、Surface message 和实时帧分开。

共同学习问题是：训练样本里记录的“模型看见什么”是否真实？如果从某个内部结果 JSON 重建输入，而实际工具只把摘要返回给模型，就会生成错误轨迹。原始证据和派生视图应有明确转换链，见三个项目的 02/04/08。

## 6. 第五条贯穿线：扩展性首先是所有权问题

Codex 的类型化 contributor 限定宿主可插入的职责；OpenCode Supervisor 管理 generation、配置 readiness 与失败旧版保留；DSH 将服务提供方、消费方及可逆作用域明确拆开。

比较扩展机制时，至少回答：谁允许注册，谁可覆盖，何时对当前请求生效，卸载要等谁，失败隔离在哪一层。插件个数、是否有 Marketplace 或某个 hook 名称不是充分的架构评价。

## 7. 不能从这些仓库直接推出的结论

本轮没有证明任何项目具备万级多租户执行性能，没有证明跨节点 exactly-once，也没有测量哪套 Harness 让模型得分更高。独立进程、文件沙箱、容器和 VM 的威胁模型不同；已有本地 claim/lock 不是集群 lease/fencing。

三个仓库主要帮助建立 Harness 与 Runtime 理解。下一层 Agent Infra 还要研究环境分配、资源配额、远程 Sandbox 生命周期、调度公平性、租约、轨迹数据质量和训练/评测吞吐。但应先用本轮实验确认所依赖的单任务语义。

## 8. 最推荐写出的综合研究作品

完成第一轮后，写一份题为《一个工具结果未知的 Agent 任务如何恢复》的分析。固定一个无敏感数据的工具，在效果发生后、结果记录前中断，分别记录三个项目能证明什么、不会做什么、仍缺哪些证据。

这比把三个 README 改写成术语表更能检验是否真正理解：模型请求、工具执行、状态记录、恢复权限与外部世界之间的关系。实验模板见 [LABS.md](LABS.md)。
