# 官方源码与文档材料索引

[返回总目录](README.md) · [版本锁](source-lock.json) · [纠错](ERRATA.md)

本套笔记使用下列 **39 个不同官方仓库文件**：Codex 12、OpenCode 12、DSH 15。表中是本轮选定阅读范围，**不是全仓库或全部文件的完整审计**。行号对应固定提交原始文件，不对应检索工具外层 JSON 的行号。

短文件读取到末尾时，请求的结束行可能大于实际文件长度；长文档返回截断时，只使用工具实际展示的内容。未展示片段、仅搜索到但未展开的内容，不据此补出实现结论。每篇笔记的本地 S1/S2 编号与这里的全局编号相互独立。

## Codex｜12 个文件

固定提交：`a9b0815167c27ab13719dd12d13b63e02b70d221`。

| ID | 文件 | 类型 / 已读范围 | 主要支撑专题 |
|---|---|---|---|
| C01 | [core/src/session/turn.rs][C01] | 代码；1–260、360–665 | 01、02、04、05 |
| C02 | [core/src/tools/orchestrator.rs][C02] | 代码；1–270 | 03 |
| C03 | [core/src/tools/parallel.rs][C03] | 代码；1–275 | 01、03、04、08 |
| C04 | [exec-server/README.md][C04] | 官方文档；1–250 的返回内容 | 03、07 |
| C05 | [core/src/compact.rs][C05] | 代码；1–300 | 02、07 |
| C06 | [thread-store/README.md][C06] | 官方文档；1–280 的返回内容 | 02、07 |
| C07 | [core/src/client.rs][C07] | 代码；150–410 | 04、08 |
| C08 | [ext/extension-api/src/registry.rs][C08] | 代码；1–230 | 05、06 |
| C09 | [core/src/agent/control/spawn.rs][C09] | 代码；1–260、300–540 | 06 |
| C10 | [core/src/session/daemon_recovery.rs][C10] | 代码；1–250 的返回内容 | 01、07 |
| C11 | [rollout-trace/README.md][C11] | 官方文档；1–230，复核 raw/reduced graph 类型及隐私契约 | 02、06、08 |
| C12 | [core/tests/suite/tool_parallelism.rs][C12] | 上游测试；1–220；未运行 | 03、08 |

以上相对文件名均以 `codex-rs/` 开头，完整路径见链接。

## OpenCode｜12 个文件

固定提交：`60a212c0769acd96b446acbadeb790486830f91d`，研究分支 `dev`。不把当前 Core 与旧 `packages/opencode/src/session` 路径混用。

| ID | 文件 | 类型 / 已读范围 | 主要支撑专题 |
|---|---|---|---|
| O01 | [specs/v2/session.md][O01] | 官方 Session 语义文档；1–270 的返回内容；重试数字有源码差异 | 01、02、04、06、07、08 |
| O02 | [core/src/session/execution.ts][O02] | 代码；1–280 | 01、06、07 |
| O03 | [core/src/session/runner/index.ts][O03] | 接口；读取至末尾 | 01 |
| O04 | [core/src/session/runner/llm.ts][O04] | 代码；1–280 | 01、02、04、05、07 |
| O05 | [core/src/session/runner/step.ts][O05] | 代码；1–290；150–290 再次核对异常结算 | 01、02、03、04、07、08 |
| O06 | [core/src/session/runner/retry.ts][O06] | 代码；1–240 的返回内容 | 04 |
| O07 | [specs/v2/tools.md][O07] | 官方工具契约；1–260 的返回内容 | 02、03 |
| O08 | [specs/v2/catalog-config-plugin-lifecycle.md][O08] | **历史决策记录**；1–240；不是当前 API 规范 | 05 |
| O09 | [core/src/plugin/supervisor.ts][O09] | 代码；1–270 | 05 |
| O10 | [core/src/tool/plugin/subagent.ts][O10] | 代码；1–310 | 03、05、06 |
| O11 | [specs/v2/event-stream-architecture.md][O11] | 官方事件流架构说明；1–260 的返回内容 | 08 |
| O12 | [server/test/event-feed.test.ts][O12] | 上游测试；1–240 的返回内容；未运行 | 08 |

表中 `core/`、`server/` 均位于 `packages/` 下。`packages/server/src/event-feed.ts` 也被搜索定位，但本轮未将其完整实现计入精读材料；相应行为由 O11 的契约与 O12 已读测试交叉支持。

## DSH｜15 个文件

固定提交：`d743267388641bc76f17c45ce8b4c231aed1d32c`。

| ID | 文件 | 类型 / 已读范围 | 主要支撑专题 |
|---|---|---|---|
| D01 | [docs/architecture.md][D01] | 官方架构；请求 1–280，长返回截断，只使用可见的组合、事件域、Turn/Session/capability 部分 | 01、02、05 |
| D02 | [core/agent-loop/README.md][D02] | 官方默认驱动文档；请求 1–245，长返回按可见范围使用 | 01、04、05、07 |
| D03 | [core/agent-loop/src/agent.ts][D03] | 代码；1–230、260–530 | 01、02、04、06、07 |
| D04 | [core/agent-loop/src/index.ts][D04] | 代码；1–260 | 01、05、07 |
| D05 | [core/agent-loop/src/tool-calls.ts][D05] | 代码；1–320 的返回内容 | 03、08 |
| D06 | [core/agent-loop/tests/tool-calls.spec.ts][D06] | 上游测试；1–225；未运行 | 03、08 |
| D07 | [docs/subsystems/session.md][D07] | 官方事件契约；请求 1–290，返回截断，只引用已见事件与请求/Surface 规则 | 02、04、07 |
| D08 | [docs/subsystems/persistence.md][D08] | 官方持久化契约；请求 1–270，返回截断，已见 Handle、flush、修复与迁移部分 | 07 |
| D09 | [docs/subsystems/sandbox.md][D09] | 官方 Sandbox 契约；1–240 的返回内容 | 03 |
| D10 | [goal/README.md][D10] | 官方包组说明；读取至末尾 | 06 |
| D11 | [goal/goal-round-driver/src/index.ts][D11] | 代码；1–300 | 05、06、07 |
| D12 | [docs/subsystems/llm-streaming.md][D12] | 官方共享流契约；1–235 | 04、08 |
| D13 | [docs/subsystems/compaction.md][D13] | 官方 Compaction 契约；1–190 | 02 |
| D14 | [docs/subsystems/subagent.md][D14] | 官方 Activation/能力契约；1–175 | 06 |
| D15 | [docs/subsystems/session-telemetry.md][D15] | 官方遥测契约；1–210 | 08 |

表中 `core/`、`goal/` 均位于 `packages/` 下。另有工具流水线官方图文 `docs/tool-execution-pipeline.md` 已实际阅读并用于 DSH 03；它是下方补充材料，不计入以上 39 个主体条目。

## 补充材料与计数口径

[DSH Tool Execution Pipeline][D16] 是一份由仓库脚本维护的官方图文，说明 pre-execute、guard、execute、post-execute、finalizeContent 与 result 的顺序。本轮已读其全部返回内容。**因此本套笔记实际引用的不同官方文件为 40 个：39 个主体条目 + 1 个补充管线文档。** README 中的“39 份材料索引”指主体清单；完整证据口径以本段为准。

资料统计不是覆盖率指标：读了一个文件片段不代表理解整个模块，也不能用文件数衡量研究质量。实际论断仍需回到每篇给出的符号、范围和证据等级。

## 引用与更新纪律

所有源码链接固定完整 SHA，避免上游移动导致引用自动变义。新增结论应先定位固定提交文件，再标注是代码、契约还是设计推断；仅有搜索摘要不足以支撑复杂调用链。

更新版本时保留旧基线，新增新旧行为差异记录，尤其检查输入接纳、取消、工具顺序、持久性和权限。不要只把所有 URL 的 SHA 全局替换后宣称笔记已更新。

[C01]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/turn.rs
[C02]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/orchestrator.rs
[C03]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs
[C04]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/exec-server/README.md
[C05]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/compact.rs
[C06]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/thread-store/README.md
[C07]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/client.rs
[C08]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/extension-api/src/registry.rs
[C09]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/agent/control/spawn.rs
[C10]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/daemon_recovery.rs
[C11]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/rollout-trace/README.md
[C12]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/tests/suite/tool_parallelism.rs
[O01]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
[O02]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts
[O03]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/index.ts
[O04]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
[O05]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[O06]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/retry.ts
[O07]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/tools.md
[O08]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/catalog-config-plugin-lifecycle.md
[O09]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/plugin/supervisor.ts
[O10]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/subagent.ts
[O11]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/event-stream-architecture.md
[O12]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/server/test/event-feed.test.ts
[D01]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/architecture.md
[D02]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/README.md
[D03]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
[D04]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/index.ts
[D05]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/tool-calls.ts
[D06]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/tests/tool-calls.spec.ts
[D07]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session.md
[D08]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/persistence.md
[D09]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/sandbox.md
[D10]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/README.md
[D11]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts
[D12]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/llm-streaming.md
[D13]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/compaction.md
[D14]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/subagent.md
[D15]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session-telemetry.md
[D16]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/tool-execution-pipeline.md
