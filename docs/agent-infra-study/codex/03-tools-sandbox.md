# Codex 03｜Tool Execution / Sandbox：权限、调度与进程生命周期

[返回总目录](../README.md) · P0 · 前置：进程、异步任务、读写锁、最小权限

**源码基线：** `openai/codex@a9b0815167c27ab13719dd12d13b63e02b70d221`。已读调度与审批代码、Exec Server 文档及并发测试；没有执行安全测试或开启远程服务。

## 1. 不要把工具执行看成一个函数调用

工具至少经过模型声明、调用解释、执行许可、并发调度、环境执行、结果转换几个边界。**模型提出行动，可信运行时决定能否执行。** 工具报错、审批被拒绝、沙箱阻止访问和执行基础设施故障，也应保持不同分类。

## 2. 源码地图

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `tools/orchestrator.rs`，1–270 行 | ApprovalRequirement、SandboxAttempt、环境与网络审批 |
| [S2] | `tools/parallel.rs`，1–275 行 | ToolCallRuntime、读写锁、取消与结果回收 |
| [S3] | `exec-server/README.md` | RPC、PTY、远程传输和进程管理契约 |
| [S4] | `tests/suite/tool_parallelism.rs`，1–220 行 | mock 模型、同步屏障和并发断言 |

## 3. 两个正交问题：可以执行吗，何时执行？

`ToolOrchestrator` 处理审批、沙箱尝试和策略相关的重试；`ToolCallRuntime` 处理请求快照和并发执行。[S1][S2] 它们不是简单替代关系：允许执行不等于可以与任何其他工具同时执行。

审批存在 Skip、Forbidden、NeedsApproval 等分支；额外的 review 策略可能影响表面上的 Skip。网络审批有开始和延期完成的生命周期，不能只在 Shell 启动前弹一次对话框就认为权限问题结束。[S1]

**沙箱失败后的重试必须再经过策略判断。** 不要将已有重试分支概括成“沙箱失败就自动裸跑”。本篇未穷尽所有 OS 后端，因此不宣称某个本地配置具有完整多租户安全边界。

## 4. 并发设计：共享与独占

`ToolCallRuntime` 保留 `Arc<StepContext>`，并持有一个执行用的读写锁。可并发工具获取共享锁，独占工具获取写锁；执行就绪等待发生在进入执行门之前，且可取消。[S2]

**分析：** 锁在这里表达的是调度约束，不是对工具“只读”的自动证明。一个工具是否被标记为可并发，需要工具定义自己承担语义责任；不能因为拿读锁就认定不会修改文件。

代码分别记录等待与真正开始执行后的时间。结果到达时先发出 ready 证据，采样循环之后再回收结果。由此可把排队时间、执行时间、等待其他工具完成的时间分开分析。[S2]

取消时也不是对所有 task 一律丢弃：已经完成、已经产生终态，或需要在取消后完成收尾的 handler，存在被继续等待的路径；其他任务可被 abort。这里要学习 **取消传播与结果结算的协调**，不是只学习 `tokio::spawn`。

## 5. Exec Server：控制面与执行面分离

文档描述了独立 JSON-RPC 服务、客户端、文件系统/进程 handler 和基于 PTY 的进程执行。`CODEX_THREAD_ID`、`CODEX_TOOL_CALL_ID` 用于关联信息，不是不可伪造的授权凭证，子进程可以修改环境变量。[S3]

远程连接、转发、重连和进程保留必须按部署模式分析。转发器不负责解释、持久化或重放完整业务 RPC；不能从传输重试推出 Shell 副作用 exactly-once。文档中连接关闭与进程生命周期的描述也应回到具体模式验证，不能笼统承诺“断线后命令总会继续”。[S3]

本轮不启动远程监听，也不提供绕过审批的实验配置。

## 6. 待运行实验

**C03-A：并发屏障。** 以 [S4] 的 `read_file_tools_run_in_parallel`、`mixed_parallel_tools_run_in_parallel` 为入口。先理解 barrier 如何证明任务确实重叠，再看耗时断言。测试里的 1.6 秒是带 CI 余量的断言，不是产品延迟指标；测试中的关闭审批配置也不是日常推荐。

**C03-B：取消后清理。** 在临时目录中运行只写测试标记的受控子进程，分别在等待执行门、执行中、结果已产生时取消。检查进程、输出管道、任务句柄和最终记录，避免把“UI 显示取消”当作清理完成。

**C03-C：三类失败。** 分别制造审批拒绝、受限路径写入被阻止、执行后端不可用。比较模型看到的错误、审计原因和是否允许重试。只操作测试目录，不使用真实凭证或生产工作区。

## 7. 验收与岗位关联

产物应包含一张从 tool call 到进程退出的时序图，并给每个节点标注所有者、权限输入、取消通道、输出上限和错误类别。应能解释为何权限、并发、传输和进程隔离是不同层次。

这是三个项目中最适合深入连接 Linux、PTY、资源生命周期和执行环境的专题。进一步做多租户 Agent Infra 时，还需补齐资源配额、网络政策、镜像供应链和跨节点调度；本地执行设计不能替代这些能力。

[S1]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/orchestrator.rs
[S2]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/parallel.rs
[S3]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/exec-server/README.md
[S4]: https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/tests/suite/tool_parallelism.rs
