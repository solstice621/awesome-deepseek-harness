# 原学习计划的核对、修正与未决问题

[返回总目录](README.md)

本文件区分原计划提供的研究方向与当前官方仓库实际支持的事实。八个专题保持不变；源码路径、实现状态与默认值按固定提交重新核对。材料编号及链接见 [SOURCES.md](SOURCES.md)。

## 1. OpenCode：不能继续沿旧 Processor 路径讲当前实现

在 `60a212c...` 下读取 `packages/opencode/src/session/processor.ts` 返回 404。当前已读路径是 `packages/core/src/session/execution.ts`、`runner/llm.ts` 和 `runner/step.ts`。[O02][O04][O05]

修正：执行链按 **SessionExecution → SessionRunner.drain → runStep → attempt** 描述；`runner/index.ts` 是接口而不是 Loop 主实现。该结果只证明这个具体旧文件不存在，不宣称所有旧目录或兼容路径都已删除，也不证明已发布版本都使用这一提交。

## 2. OpenCode：同一提交的重试文档与代码不一致

Session 语义文档写最多 4 次重试；已读 `runner/retry.ts` 使用 `Schedule.recurs(10)`，并设独立的默认超时重试上限 3，插件 hook 还可以覆盖重试决策。[O01][O06]

修正：代码中的默认策略、文档描述、最终插件覆盖后的行为分开记录。不能把重试次数简单乘等待时间得出总任务时延上限；请求耗时、jitter、Retry-After 与 hook 都会影响结果。

## 3. OpenCode：V2 目录不代表每份文档都是当前规范

`catalog-config-plugin-lifecycle.md` 明确标为 Historical decision record。B 是当时选定的方向，A 是被否决的候选；其中 API 片段不能直接当作当前插件 SDK 使用。[O08]

修正：历史记录用于解释取舍，当前机制以 `plugin/supervisor.ts` 与实际插件调用为依据。[O09][O10] 当前 Core 可读源码也不自动证明某个已安装 CLI 的版本相同。

## 4. Codex：Extension Registry 的位置与含义

本轮实际读取的是 `codex-rs/ext/extension-api/src/registry.rs`；少了 `ext/` 的路径不成立。[C08]

修正：类型化 Rust contributor registry、面向用户的插件包、Skills 和 MCP 是不同边界。本套笔记只对已读的 registry 契约作出结论，没有把它解释成通用脚本热加载系统。

## 5. Codex：daemon 恢复不是无条件承诺

`daemon_recovery.rs` 的已读路径只捕获普通、未取消、有 RecordedTurnInput、单一本地执行环境且配置来源受支持的活动 Turn；RecordedTurnInput 还不是 flush 成功的证明。[C10]

修正：明确写出恢复资格、调用方 flush 要求与未覆盖路径。不能从这一局部路径推出“所有 Codex 恢复不支持远程”，更不能反过来说“任何 Agent 任务都能自动恢复”。

## 6. DSH：SandboxMode 不包含网络隔离

当前 Sandbox 契约明确：read-only/workspace-write 描述文件副作用，网络和进程可见性不在该词汇的承诺中；后端还报告 full/partial。[D09]

修正：沙箱分析要描述威胁模型与实际 enforcement。权限许可、路径限制、进程隔离和网络隔离不应互相代称。受限 provider 不可用时 fail closed，也不意味着每个 OS 后端都给出同样完整的隔离。

## 7. DSH：日志接纳、稳定存储与检查点频率分开

SessionHandle.append 成功表示接纳、顺序与 backend 内可见性；flush 才提供契约中的持久化屏障。[D08]

Session 事件文档明确 Loop 不在每个 Turn 边界直接等待 flush；持久化文档又有关于普通 Turn 前 checkpoint 的表述。本轮没有完整追踪 `session-checkpoint-policy` 的实现与 profile 装配，因此**不对统一刷盘频率下结论**。已直接核对 Goal Driver 自身 flush 后复查、失败 disarm 的路径。[D07][D11]

修正：引用具体服务契约与调用点，不把“存在 flush”概括成“每条事件立即持久化”或“每轮一定 fsync”。

## 8. DSH：失败重试的描述需要按调用点理解

默认 `ReactLoopAgent.step()` 内部有 attempt 循环；in-band provider failure 结算为 assistant/attempt 后，经 `agent/request-error` 决定是否在同一 Step 重试。[D03] 其他子系统文档对失败后的阶段可能采用不同概括方式；本套执行图以这段已读调用链为准。

这里不能把一次模型传输失败直接算作 Turn 结束，更不能把失败尝试的诊断记录当成模型可见成功回答。

## 9. 需要长期保留的证据边界

| 原先容易产生的印象 | 本套笔记采用的边界 |
|---|---|
| 有事件日志，所以工具效果 exactly-once | 日志重放不等于外部副作用重放；未知结果单独建模 |
| 有锁/claim，所以能做多节点接管 | 本地协调与集群 lease/fencing 是不同机制 |
| 有测试文件，所以行为已经验证通过 | 本轮只读测试；运行、跳过与失败待实验记录 |
| 微基准更快，所以任务端到端同比变快 | 编码/调度微基准不能替代真实模型与工具工作负载 |
| 遥测 cursor 前进，所以后端已收到 | handoff、delivery、durability 分别确认 |
| 当前分支源码存在，所以稳定产品已上线 | 固定研究提交与发行版、配置、平台分别核对 |

## 10. 后续研究应优先补足什么

重点补：三个项目的动态故障实验；DSH checkpoint-policy 与具体 JSONL/租约后端；OpenCode durable projector/数据库提交实现与插件卸载期间的活动请求；Codex 恢复快照的完整调用方及各 OS 执行后端。这里只说明下一步证据缺口，不把它们写成已经完成的研究。

[O01]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
[O02]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts
[O04]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/llm.ts
[O05]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[O06]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/retry.ts
[O08]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/catalog-config-plugin-lifecycle.md
[O09]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/plugin/supervisor.ts
[O10]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/subagent.ts
[C08]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/extension-api/src/registry.rs
[C10]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/session/daemon_recovery.rs
[D03]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/agent.ts
[D07]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/session.md
[D08]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/persistence.md
[D09]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/subsystems/sandbox.md
[D11]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts
