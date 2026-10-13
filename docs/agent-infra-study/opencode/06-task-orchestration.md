# OpenCode 06｜Subagent：父子 Session、前后台与结果交付

[返回总目录](../README.md) · P1 · 前置：01、03、07

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。重点阅读真实 `subagent` 工具；未完整审计 Job/SubagentJob 的全部恢复实现。

## 1. 当前入口与旧计划不同

本次实际工具在 `packages/core/src/tool/plugin/subagent.ts`，不是原计划的 `packages/opencode/src/tool/task.ts`。它把父子 Session、模型选择、深度、权限、任务阻塞/后台化和结果表示连接起来。[S1]

## 2. 核心依据

| 依据 | 已核对位置 | 用途 |
|---|---|---|
| [S1] | `tool/plugin/subagent.ts`，1–310 行 | 输入、父子校验、创建/继续、prompt、job、hooks |
| [S2] | `session/execution.ts`，1–280 行 | 中断与执行归属 |
| [S3] | `specs/v2/session.md` | durable admission 与继续语义 |

## 3. 执行前必须完成哪些检查？

工具先沿 parent 链计算深度，默认配置读取的深度限制为 1；再解析 agent，拒绝 primary-only 的 Agent 类型作为 subagent，执行权限检查。继续一个已有 Session 时，必须验证它的 parentID 就是当前 Session。[S1]

模型选择有显式覆盖、Agent 配置、父模型继承的优先级；显式模型还要校验 provider/model/variant 是否存在。输入 schema 里的“只有用户明确要求才设置 model”属于描述性引导，不应误称为代码已经实施了用户意图证明。[S1]

**分析：** 多 Agent 的关键不是能否调用另一个模型，而是把委派限制在当前调用者真正拥有的范围内。

## 4. 新建和继续不是一回事

新子 Session 使用 fresh context，工具描述要求在任务 Prompt 中传入必要信息；指定 `sessionID` 则继续那个子会话。继续时如果 Agent 类型改变，代码会处理 Agent/模型切换，而不是无条件创建另一个子任务。[S1]

这与复制整个父上下文的 fork 模式不同。比较时必须使用相同实验输入，并注明是 fresh、fork 还是 resume，不能把三者统称为“子 Agent 继承”。

## 5. 为什么先 prompt，再 Job.start？

源码专门说明：向子 Session 提交 prompt 放在 job 的 run effect 外面。因为加入一个已运行 job 可能跳过其 run effect，如果把输入藏在那里面，新任务就可能没有被接纳。[S1]

新建后台子任务可先使用 `resume:false` 记录输入，再由 SubagentJob 接管启动；继续已有子任务则可通过正常 prompt 接纳/steer。随后记录恢复描述，再选择前台等待或后台通知。[S1]

**分析：** 输入接纳、工作执行和结果通知必须分开，才能正确处理“加入正在运行的任务”这类情况。

## 6. 前台取消与后台交付

前台路径通过 `jobs.block` 等待；该等待被中断时，会请求中断子 Session 并取消 job。后台路径返回 running 状态，并交给后续通知机制。失败返回中保留 sessionID，以便之后继续定位子会话。[S1]

`status:completed` 是编排结果的一种表示，不是补丁正确性、测试通过或业务目标达成的证明。任务质量必须另行评估。

模型看到的 content、供机器使用的 output、UI metadata 分开生成，这也是 [03](03-tools-sandbox.md) 的真实例子。

## 7. 待运行实验

**O06-A：归属检查。** 构造两个独立父 Session，尝试从 B 继续 A 的 child，验证明确拒绝，而不是仅凭已知 child ID 获得控制权。

**O06-B：继续正在运行的 child。** 让子任务阻塞，再提交第二条 prompt；核对输入确实被记录，不因 Job.start 加入旧任务而丢失。

**O06-C：前后台取消矩阵。** 分别测试前台 wait 中断、显式子任务取消、后台任务完成后父任务已停止。检查实际通知与清理顺序；后两者涉及未完全阅读的 Job 实现，不能从工具入口直接断言结果。

## 8. 验收

产出 child 生命周期图，包含创建、接纳、执行、后台化、通知、继续、取消；每条边标明由 Session、Job 还是 SubagentJob 负责。

应能解释为什么 prompt 不放在 Job.run 内、为什么 parentID 校验是权限问题、为什么 fresh child 不等于 fork、为什么完成通知与任务正确性不同。

**迁移到 Agent Infra：** Agent 编排平台需要可追踪的委派身份、有限深度、执行与交付分离，以及取消传播；这些都比堆叠更多子 Agent 更基础。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/subagent.ts
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/execution.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/session.md
