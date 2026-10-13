# Codex 08｜Observability / Evaluation：先保存证据，再解释执行

[返回总目录](../README.md) · P2（学习顺序，不表示生产优先级低） · 前置：01/03/04/07

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。已读诊断契约与上游测试，没有生成真实 trace 或发布性能测试成绩。

## 1. 本篇核心结论

聊天记录不足以解释所有失败。模型看到的内容、工具执行时发生的事情、终端输出和子 Agent 通知，并不总在同一个层次。Codex 的 Rollout Trace 采用先记录原始运行证据、再离线归约为语义图的设计。[S1]

## 2. 阅读入口

| 依据 | 已核对位置 | 用途 |
|---|---|---|
| [S1] | `rollout-trace/README.md` | 本地 bundle、writer/reducer、隐私与不变量 |
| [S2] | `core/src/tools/parallel.rs`，1–275 行 | 工具等待、执行、结果就绪诊断边界 |
| [S3] | `core/tests/suite/tool_parallelism.rs`，1–220 行 | mock SSE、barrier、并发断言 |
| [S4] | `core/src/client.rs`，150–410 行 | 受控原因标签与连接状态诊断 |

## 3. 运行记录与离线解释

文档定义的 bundle 包含 `manifest.json`、`trace.jsonl`、`payloads/*.json` 和可选的 `state.json`。writer 分配有序 seq，并先写 payload，再写引用它的事件。离线 reducer 产生线程、Turn、模型请求、工具、终端、压缩和交互边。[S1]

关键区别是：`ConversationItem` 表示模型可见内容；运行时 ToolCall、CodeCell、TerminalOperation 等对象解释这些内容如何产生。某个工具返回了完整 JSON，不证明模型收到了同样的 JSON；Code Mode 内部嵌套调用尤其需要区分。[S1]

**分析：** 先收集证据、后解释可降低热路径分析负担，也便于修复 reducer 后重新解释既有记录。但 reducer 正确性、schema 版本与证据完整性都需要单独验证。

## 4. 诊断不能成为任务状态真源

Rollout Trace 默认不上传；只有配置 `CODEX_ROLLOUT_TRACE_ROOT` 才生成本地记录。记录可能含 Prompt、回答、工具输入输出、终端内容和路径，应当作为敏感数据处理。[S1]

文档明确诊断启动和写入是 best-effort，不应因录制失败导致 Codex Session 失败。因此 **缺少某条 trace 不证明那个工具未执行**；同样 trace 写入成功不是业务存储已提交的证明。

子线程可以共享 root writer，使一次父子 rollout 成为同一图；独立根线程仍是独立 bundle。`trace_id` 与 `rollout_id` 也不是同一个概念。[S1]

## 5. 如何读测试，而不是只看绿色通过

上游并发测试使用 mock SSE 预先决定模型输出，再用测试工具屏障证明多个调用重叠。[S3] 这种设计把模型随机性从调度正确性测试中移走。

测试中存在 warmup、CI 时间余量和平台/网络条件。一个测试跳过不能记成验证通过；一个 1.6 秒断言也不能记成性能 SLO。应首先确认实际执行了哪个用例，然后解释断言覆盖的性质。

## 6. 建议的评估分层（本笔记分析）

| 层次 | 测什么 | 不应混淆 |
|---|---|---|
| 协议与状态正确性 | call/result 配对、终态、取消后收尾 | 模型是否聪明 |
| 调度性能 | gate 等待、执行重叠、结果回收延迟 | 只看总耗时 |
| 任务质量 | 补丁正确性、测试结果、约束满足 | 只看模型自述完成 |
| 成本 | 物理模型请求、摘要、重试与工具开销 | 只看最终一次 usage |
| 可诊断性 | 能否定位失败源及缺失证据 | 日志数量越多越好 |

这些是从源码边界推导的实验框架，不是仓库已发布的统一 benchmark。

## 7. 待运行实验

**C08-A：本地 trace。** 在不含凭证的临时项目中按官方变量开启记录；使用文档给出的 `codex debug trace-reduce <bundle>` 离线归约。选择一条工具调用，逐项核对来源请求、执行证据和模型可见结果。不得把原始 trace 上传到公开仓库。

**C08-B：诊断故障。** 使用测试 seam 让诊断 writer 失败，确认主要任务是否按契约继续，同时错误是否可见。不要用破坏系统磁盘的方式模拟。

**C08-C：一次失败复盘。** 固定 mock 流，加入工具超时与父子消息，整理“已知事实／推断／证据缺口”。验收是能找到 causal path，不是生成漂亮图。

## 8. 验收与迁移

最终产物：一个脱敏后的事件索引、一份测试覆盖说明、一份失败归因报告。必须说明哪些信息来自源码、哪些是实测、哪些仍不确定。

**迁移到 Agent Infra：** 可观察性应服务于训练/评测失败复现、成本归因和环境故障定位。日志、恢复数据和训练轨迹可共享某些原始事实，但可靠性、隐私和采样策略不同，不应无条件合并成一套“万能日志”。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/rollout-trace/README.md
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/tests/suite/tool_parallelism.rs
[S4]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs
