# Agent 系统原理与工程实践

以 Codex、OpenCode、DeepSeek Harness 固定版本源码为贯穿案例的中文教材。

本书面向会编程、但尚未系统开发过 Agent 的读者。学习目标是从一个模型调用出发，逐步设计能够调用工具、管理上下文、处理失败、遵守权限、持续运行并接受独立评测的系统。三个项目用来解释真实工程取舍；主线按知识之间的依赖组织。

学完后，你应能回答五个问题：模型依据什么作决定，动作由谁执行，事实保存在哪里，失败后怎样继续，以及什么证据足以说明任务完成。

## 全书结构

| 篇 | 章节 | 学习结果 |
|---|---|---|
| 第一篇 基础模型 | 1—4 | 区分模型、Agent、运行时与应用，画出一次任务的状态变化 |
| 第二篇 决策与行动 | 5—8 | 将计划转成受约束动作，理解工具与流式模型协议 |
| 第三篇 上下文与知识 | 9—12 | 构造请求上下文，设计检索、记忆、压缩和指令加载 |
| 第四篇 可靠执行 | 13—16 | 处理并发、取消、重试、持久化与事件交付 |
| 第五篇 权限与扩展 | 17—20 | 分清授权、隔离、信任和扩展生命周期 |
| 第六篇 协作与质量 | 21—24 | 组织多 Agent 和长任务，用证据评估质量、费用与性能 |
| 第七篇 综合工程 | 25—28 | 设计部署、接入新能力、追踪完整任务并运行本地实验 |

## 第一篇 基础模型

1. [Agent 是怎样的一种系统](chapters/01-agent-systems.md)
2. [模型接口与生成边界](chapters/02-model-interface.md)
3. [运行时架构与状态模型](chapters/03-runtime-architecture.md)
4. [从最小循环到完整 Agent Loop](chapters/04-agent-loop.md)

## 第二篇 决策与行动

5. [规划、分解与验证](chapters/05-planning-verification.md)
6. [工具契约与执行生命周期](chapters/06-tool-contracts.md)
7. [文件、进程与执行环境](chapters/07-execution-environments.md)
8. [模型适配与流式协议](chapters/08-model-streaming.md)

## 第三篇 上下文与知识

9. [上下文工程与指令层级](chapters/09-context-engineering.md)
10. [检索与长期记忆](chapters/10-retrieval-memory.md)
11. [压缩与长上下文管理](chapters/11-compaction.md)
12. [Skills、项目指令与配置](chapters/12-skills-configuration.md)

## 第四篇 可靠执行

13. [并发调度与取消](chapters/13-concurrency-cancellation.md)
14. [错误、重试与幂等性](chapters/14-retry-idempotency.md)
15. [持久化与故障恢复](chapters/15-persistence-recovery.md)
16. [事件流、API 与用户界面](chapters/16-events-ui-api.md)

## 第五篇 权限与扩展

17. [权限与人工批准](chapters/17-authority-approvals.md)
18. [沙箱与执行隔离](chapters/18-sandbox-isolation.md)
19. [提示注入与敏感信息](chapters/19-injection-secrets.md)
20. [MCP 与插件生命周期](chapters/20-mcp-plugins.md)

## 第六篇 协作与质量

21. [多 Agent 协作](chapters/21-multi-agent.md)
22. [长任务、目标与调度](chapters/22-long-running-goals.md)
23. [可观测性、性能与成本](chapters/23-observability-performance.md)
24. [测试与评测](chapters/24-testing-evaluation.md)

## 第七篇 综合工程

25. [从本地运行到可运营服务](chapters/25-deployment-operations.md)
26. [为 Agent 增加一种能力](chapters/26-extension-design.md)
27. [把一次任务从输入追到交付](chapters/27-end-to-end-case.md)
28. [综合实验与课程设计](chapters/28-capstone-lab.md)

## 如何学习

第一次学习按章节顺序阅读，每章先理解例子，再沿链接查看相应源码，最后独立回答习题。每章答案用于核对推理，建议先写自己的答案。只看源码路径和术语不能代替理解“为什么需要这个机制”。

若希望先看到系统全貌，可读第 1、4、27 章，再运行[本地实验](labs/README.md)，随后回到完整课程。已有 Agent 开发经验的读者，可以从[主题与三项目映射](appendices/coverage-map.md)直接进入关心的问题。

配套材料包括[十六周课程安排](appendices/course-plan.md)、[术语表](appendices/glossary.md)、[源码证据索引](appendices/source-index.md)、[进阶方向与范围边界](appendices/further-study.md)、[验证记录](VALIDATION.md)和[版本锁](source-lock.json)。原有 [24 篇项目专题笔记](../agent-infra-study/README.md)保留为深入导读，并不充当新教材源码事实的唯一依据。

## 贯穿案例

主案例是修复 CSV 总价程序遗漏 quantity 的缺陷：`3.50 × 2 + 12.00 × 3 = 43.00`，而只累加 price 会错误得到 `15.50`。读取、规划、编辑、测试、取消和恢复围绕同一任务展开。个别章节使用明确标注的金额精度、字符串拼接或空值变体，帮助读者迁移概念。

第 28 章实验使用确定性的模拟决策器与合成数据，无需 API 密钥，也不执行任意 shell 命令。它验证运行机制，不能证明真实模型的编程能力。

## 版本与证据

研究基线沿用 PR 初版的三个固定提交，教材扩充日期为 2026-10-13。

| 项目 | 固定提交 |
|---|---|
| openai/codex | `a9b0815167c27ab13719dd12d13b63e02b70d221` |
| anomalyco/opencode | `60a212c0769acd96b446acbadeb790486830f91d` |
| deepseek-ai/deepseek-harness | `d743267388641bc76f17c45ce8b4c231aed1d32c` |

全书用文字明确区分：固定源码中的行为、官方文档契约、已读但未运行的上游测试、教学抽象与设计建议，以及本次实际运行的教学实验。引用中的文件、符号和行号用于复查，源码文件数量不代表全仓库覆盖率。

没有构建或运行三个上游项目，也没有进行真实模型、性能或沙箱安全实测。书中上游实验与开放课程实验标为 NOT RUN 或未运行。本地实验的实际结果单独记录在[验证记录](VALIDATION.md)。这里的“完整”指从原理到工程的课程链条；模型训练、强化学习、机器人控制等领域在进阶附录中给出边界，不用三个编码 Agent 代表全部智能体研究。
