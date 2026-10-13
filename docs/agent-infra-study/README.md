# Agent Infrastructure 源码研究笔记

系统学习请从新版 **[Agent 系统原理与工程实践](../agent-textbook/README.md)** 开始：28 章按知识依赖组织，涵盖原理、三项目源码、习题答案与本地实验。本目录保留 2026-10-12 初版的项目专题分析，以下阅读范围与未运行声明描述该初版。

**Codex CLI × OpenCode × DeepSeek Harness（DSH）｜3 个项目 × 8 个专题**

研究日期：2026-10-12。面向从平台工程走向 Agent Harness / Runtime / Infrastructure 的开发者。材料取自三个官方仓库的固定提交。

## 阅读入口

先读 [版本核对与纠错](ERRATA.md)，再按下表横向学习。每篇包括核心问题、源码入口、执行或状态机制、设计分析、失败边界、待运行实验和验收问题。

| 专题 | 学习顺序 | Codex CLI | OpenCode | DSH |
|---|---|---|---|---|
| 01 Agent Loop / Execution Engine | P0 | [Turn、Step 与输入接纳](codex/01-agent-loop.md) | [接纳、协调、Step 与 Attempt](opencode/01-agent-loop.md) | [可替换驱动与输入边界](dsh/01-agent-loop.md) |
| 02 Context / Session Management | P0 | [历史、压缩与请求重建](codex/02-context-session.md) | [可见历史与压缩 Epoch](opencode/02-context-session.md) | [事件日志、Surface 与投影](dsh/02-context-session.md) |
| 03 Tool Execution / Sandbox | P0 | [权限、调度与进程生命周期](codex/03-tools-sandbox.md) | [请求快照与输出约束](opencode/03-tools-sandbox.md) | [滚动并发池与顺序提交](dsh/03-tools-sandbox.md) |
| 04 LLM Integration / Streaming | P0 | [连接复用与请求连续性](codex/04-llm-streaming.md) | [部分输出、重试与结算](opencode/04-llm-streaming.md) | [协议与尝试记录](dsh/04-llm-streaming.md) |
| 05 Extension / Plugin Architecture | P1 | [类型化贡献点](codex/05-extension-architecture.md) | [代际替换与就绪屏障](opencode/05-extension-architecture.md) | [能力接口与可逆生命周期](dsh/05-extension-architecture.md) |
| 06 Task Orchestration / Multi-Agent | P1 | [子 Agent 身份与执行归属](codex/06-task-orchestration.md) | [父子 Session 与结果交付](opencode/06-task-orchestration.md) | [Goal 与调度授权](dsh/06-task-orchestration.md) |
| 07 Persistence / Reliability | P1 | [落盘边界与有条件恢复](codex/07-persistence-reliability.md) | [durable inbox 与执行 claim](opencode/07-persistence-reliability.md) | [Handle、Flush 与保守修复](dsh/07-persistence-reliability.md) |
| 08 Observability / Evaluation | P2 | [运行证据与离线归约](codex/08-observability-evaluation.md) | [事件扇出与背压](opencode/08-observability-evaluation.md) | [Ledger、Live Stream 与遥测](dsh/08-observability-evaluation.md) |

P0/P1/P2 只是学习顺序，不是生产重要性、产品评分或成熟度。

**配套材料：** [横向架构比较](COMPARISON.md) · [八周学习与实验路线](LABS.md) · [官方材料索引](SOURCES.md) · [纠错与未决问题](ERRATA.md) · [机器可读版本锁](source-lock.json)

## 固定研究版本

| 项目 | 研究时分支 | 固定提交 |
|---|---|---|
| [openai/codex](https://github.com/openai/codex) | main | `a9b0815167c27ab13719dd12d13b63e02b70d221` |
| [anomalyco/opencode](https://github.com/anomalyco/opencode) | dev | `60a212c0769acd96b446acbadeb790486830f91d` |
| [deepseek-ai/deepseek-harness](https://github.com/deepseek-ai/deepseek-harness) | master | `d743267388641bc76f17c45ce8b4c231aed1d32c` |

这些是研究快照，不是推荐安装版本，也不证明与某个已发布二进制一致。更换提交后须重新验证路径、接口、策略与默认值，不能只替换链接 SHA。

## 三个项目的研究分工

Codex 重点连接请求快照、工具执行、进程环境、审批与恢复资格；OpenCode 重点研究 durable admission、执行协调、逻辑 Step / 物理 Attempt、插件代际和事件服务；DSH 重点研究能力接口、可替换 Loop、事件投影、顺序提交和 Goal 调度。

这是阅读侧重点，不表示其他项目缺少对应能力。具体依据见各篇引用和 [COMPARISON.md](COMPARISON.md)。

## 证据与完成度

已完成 **24 篇专题静态分析**。材料索引包含 **40 个不同官方文件：39 个主体条目和 1 个补充工具管线文档**；各文件的已读范围与长文档返回截断情况见 [SOURCES.md](SOURCES.md)。这不是全仓库审计或覆盖率声明。

| 证据类型 | 阅读方式 |
|---|---|
| 源码事实 | 可以在固定提交的已读文件、符号与分支中定位 |
| 文档契约 | 官方设计或接口承诺，不自动代表全部实现均已验证 |
| 历史 ADR | 用于理解取舍；被否决方案与旧接口不当作当前 API |
| “分析” | 根据已读机制推导，不冒充作者原话或测量结果 |
| “待运行实验” | 给出验证方法；本轮未运行 |

每篇的 `[S1]` 等编号只在该篇内有效；全局索引用 C01–C12、O01–O12、D01–D16。源码链接固定完整 commit。

**本轮没有编译三个项目，没有执行上游测试、真实模型请求、性能测量或沙箱安全测试。** 测试文件的断言是已读证据，不等于本轮通过；实验预期不是实测结果。未读实现和未解决的文档差异明确保留，不用常识填补。

## 使用与验收

可先按 01 → 03 → 04 → 02 建立请求链，再按 07 → 05 → 06 → 08 深入可靠性与系统能力；完整八周路线仍按 [LABS.md](LABS.md) 的专题安排。

每个专题最终形成四项产物：能回到源码的执行图、模块边界与状态表、有依据的取舍分析、至少一个实际失败场景的验证记录。实验未完成时保留 NOT RUN。

本目录只保存研究分析，不包含私人会话、客户代码或原始运行 trace。后续实验使用临时项目和合成数据，公开证据先脱敏。Prompt、工具输出、终端内容和路径都可能包含敏感信息。
