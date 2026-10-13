# DSH 04｜LLM Streaming：协议词汇、Prepared Call 与尝试记录

[返回总目录](../README.md) · P0 · 前置：判别联合、async iterator、不可变数据

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。已读共享流协议和默认 Loop 消费逻辑；未逐个验证供应商 adapter。

## 1. 应学习的不是某个 API 参数表

DSH 将 durable Message、ContentBlock、StreamChunk、adapter capability 与失败描述分开。协议层需要表达工具参数的部分输出、reasoning、媒体、usage 和终止原因；Loop 再决定什么成为模型历史、什么只留下尝试记录。[S1][S2]

## 2. 入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/subsystems/llm-streaming.md`，1–235 行 | block/message/stream、replay metadata、compact stream |
| [S2] | `agent-loop/src/agent.ts`，260–530 行 | preparedCall、firstAttempt、stream settlement、retry |
| [S3] | `agent-loop/README.md` | prepareCall 绑定路由与失败处理契约 |
| [S4] | `docs/subsystems/session.md`，已读事件部分 | assistant/message 与 assistant/attempt |

## 3. StreamChunk 的设计

流使用 index 关联交错 block 的 delta；block-end 携带完整 block。工具 arguments 保持模型产生的原始 JSON 字符串，到工具边界再解析，而不是在每个 delta 到达时尝试执行。[S1]

流是封闭的判别联合，新增分支要推动消费者显式处理；ContentBlockMap 则允许扩展，但新增模态仍必须考虑 adapter、UI、compaction 和 durable replay。类型可扩展不意味着端到端能力自动存在。[S1]

usage 在 finish 前，finish 是终态；provider 私有 replayState 保持不透明，并按历史 provider 与目标 adapter 的所有权条件暴露。共享 Harness 不应偷读私有协议字段来承担供应商特定逻辑。[S1]

## 4. Prepared Call 解决什么问题？

Loop 先经过 request hook 和请求准备，再以 preparedCall 的能力构造系统提示更新和请求；实际调用使用该绑定对象的 stream。[S2][S3]

**分析：** 如果先查询 A adapter 能力，稍后 provider 注册变化后却由 B adapter 执行，就可能构造错误请求。绑定 prepared call 将能力判断、默认值和执行路由连接起来。具体 runtime 注册行为还需阅读 LlmRuntime 实现，本篇不声称已经审计其所有竞态。

## 5. 一次尝试如何结算？

模型流期间产生进程本地 `agent/assistant-stream` 帧；结束后形成一个完整 compact stream，嵌入 `assistant/message` 或 `assistant/attempt`。后者保留没有形成模型可见消息的失败/重试尝试。[S1][S2][S4]

取消后若已有可见前缀，Loop 可记录 `interrupted:true` 的 assistant/message；没有可见内容则保留 attempt。硬进程丢失发生在 settlement 前，不能保证已经展示给用户的每个 delta 都已持久化。[S2][S3]

失败后通过 `agent/request-error` 策略决定是否 retry；`firstAttempt` 使已接纳用户消息不重复提交。Loop 不应把重试策略与流解析绑成一个不可拆分的模块。[S2]

## 6. 两种“压缩”不要混淆

Compact Assistant Stream 把连续 delta 的重复封装压缩成带时间差和逐 delta 数组的记录，要求能恢复原始 timed chunk 序列；它不是对话摘要，不应该丢掉 token/delta 边界。[S1]

Context compaction 则改变下一请求的活动历史，具有语义损失风险。两个都叫 compression，但验收标准完全不同：前者关注无损重建，后者关注任务信息保真。

## 7. 待运行实验

**D04-A：交错流。** 用 mock adapter 交错两个 tool-call delta 和文字 block，验证组装依据 index/id 而非相邻顺序。

**D04-B：compact stream round-trip。** 构造确定时间戳的 chunks，经过 accumulator 后再 expand；检查 chunk 值和时间一致。不要把“拼接文本相同”当作无损证明。

**D04-C：重试与部分输出。** 一次尝试输出后失败，下一次成功；分别检查 durable attempts、实际模型 history 和 usage，确认失败记录不冒充成功回答。

## 8. 验收

画出 adapter raw stream → runtime normalization → Loop live frames → durable settlement → derived history 的转换图。能解释为什么工具结果不是普通 ContentBlock、为什么 replay metadata 需要所有权、为什么流压缩与上下文摘要的正确性标准不同。

**迁移到 Agent Infra：** 明确物理尝试与模型可见输出，有助于统计真实重试成本、构造训练轨迹和复现环境失败；不能只保存最终回答文本。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/llm-streaming.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/README.md
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session.md
