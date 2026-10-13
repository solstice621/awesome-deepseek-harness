# 第 24 章　测试与评测：从确定性契约到真实任务成功

[教材目录](../README.md)

**先修知识**：工具契约、持久化、多 Agent、长期目标、可观测性。**学习目标**：构造分层测试，明确每类证据能证明什么，设计有预算约束且避免泄漏的离线任务评测，并用 trace 解释失败。

## 24.1 Agent 有两个不同的正确性问题

第一类问题是宿主机制是否正确：取消是否停止后续调用，参数是否按 schema 验证，恢复是否重复接纳消息，预算是否重复扣除。这些大多可以用确定性输入和 mock 模型测试。第二类问题是给定任务时系统能否做出合适决策：能否定位 bug、选择必要工具、理解需求并产出正确补丁。它依赖模型、提示、上下文、工具与环境共同作用，需要任务级评测。

单元测试全绿不能证明 Agent 能完成真实任务；任务评测高分也不能证明取消、持久化和权限边界可靠。优秀的测试体系将这两条证据链连接起来：任务失败可以沿 trace 定位机制问题；机制改动则能通过固定任务集检查行为是否退化。

**测试预言机**是判断结果对错的机制。对 CSV 合计，预言机可以是独立计算的总额、测试断言和补丁约束；不应只是同一个模型自称“完成”。若用模型评审，要保存评分规则、评审模型与输入，并用人工标注子集检查它的偏差。源代码、工具输出或最终回答中的自我评价都只是被评对象提供的信息。

## 24.2 为 CSV 修复建立测试阶梯

| 层次 | 主要对象 | CSV 案例 | 能证明的边界 |
| --- | --- | --- | --- |
| 单元 | 纯函数或小状态机 | 金额解析、取消状态转换 | 局部规则成立 |
| 契约 | 组件交界 | 工具 schema、错误码、持久事件形状 | 双方约定相容 |
| 集成 | 多个真实组件 | mock 模型驱动读文件、补丁、测试工具 | 组件协作路径成立 |
| 端到端 | 产品入口到可观察产物 | CLI 接收任务，输出补丁与测试记录 | 被测环境下整条路径成立 |
| 离线任务评测 | 固定任务分布下的完整 Agent | 多种 CSV bug 及干扰仓库 | 在该任务集上的成功率与成本 |

层次名称不是质量等级。一个使用真实服务和 mock LLM 的集成测试，对并发消息丢失可能比昂贵的真人交互测试更敏感；一个真实模型端到端测试也可能只证明“这次能启动”。应写明哪些部件是真实的、哪些被替换、哪些失败路径没有覆盖。

案例的验收规范先于运行定义：修复 price 漏乘 quantity；pen 3.50×2 与 book 12.00×3 应用 Decimal 得到 43.00，而非错误的 15.50；正常文件、小数价格和空文件符合约定；不修改无关文件；验证发生在最终补丁之后。缺列、非法金额和编码错误可另建压力案例变体，并先给出各自规范，不把未定义行为偷偷加入主任务的隐藏验收。任务输入只给工作需求和允许公开的样例，隐藏测试不放进 Agent 可读目录。否则 Agent 可能只针对已知断言优化，而没有学会一般规则。

教学评测记录可以采用以下结构，字段名不对应某项目的现成 API：

```json
{
  "task_id": "csv-total-017",
  "base_revision": "fixture-v3",
  "attempt": 1,
  "budget": {"wall_seconds": 180, "model_tokens": 12000},
  "outcome": {"functional": true, "scope": true, "verified_final": true},
  "cost": {"estimated_usd": 0.03, "usage_complete": true},
  "trace_ref": "local-artifact-reference",
  "failure_class": null
}
```

成功由预先约定的必要条件合取而成：`functional && scope && verified_final`。超时、取消和基础设施失败各自标记，主成功率分母的处理也在运行前写清；不能事后删掉不利样本。若另报“环境正常时成功率”，应同时展示排除数量与规则。

## 24.3 三项目测试源码提供了哪些证据

**Codex：由会计单元测试上升到公共 API 的状态测试。** `goal_accounting_uses_turn_start_baseline_for_exact_deltas` 从初始累计 usage 与后续累计 usage 计算增量，并断言两个计账 delta；邻近测试明确 Plan turn 不计入这条预算记账。测试不是简单断言“函数被调用”，而是锁定计量语义。[Codex：goal accounting 测试](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/tests/accounting.rs#L19-L60)。

`execution_failures_do_not_transfer_to_a_replacement_goal` 构造两个目标交替归属，断言旧目标的失败不污染新目标。另一个测试确认工具脚本返回不成功、以及 handler 尚未执行的失败，不被当成同一类运行基础设施连续失败。这说明失败分类本身也要测试，不能把所有异常计入同一个断路器。[Codex：目标更换与失败分类](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/ext/goal/tests/accounting.rs#L135-L188)。

公共 API 测试 `empty_goal_continuations_block_after_three_without_activity` 构造 Responses SSE 序列、启动 `TestAppServer`、通过 `thread/goal/set` 建目标，最后等待 blocked 通知并验证 mock 服务。它覆盖跨协议的续轮状态链，却仍用模拟模型响应，不能证明真实模型能够自行判断 CSV bug。[Codex：响应夹具与 mock server](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/tests/suite/v2/thread_goal_empty_responses.rs#L28-L86)，[公共 API 与通知断言](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/app-server/tests/suite/v2/thread_goal_empty_responses.rs#L132-L176)。

**OpenCode：用可控制的异步屏障测试竞态。** `SessionRunCoordinator` 测试用 `Deferred` 把 drain 停在指定位置，启动两个并发 resume，断言实际只运行一次；另一测试在运行期间并发发送三个 wake，断言只追加一次 drain。与 `sleep(100)` 相比，显式屏障描述的是因果顺序，降低对机器快慢的依赖。[OpenCode：并发 resume 合并](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/test/session-run-coordinator.test.ts#L9-L28)，[wake 合并](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/test/session-run-coordinator.test.ts#L161-L188)。

`subagent-lifetime.test.ts` 使用真实 Session/Job 等服务组合，替换 LLM 为 `TestLLM`、模型目录为离线配置；它移动 child 的目录并可驱逐父 location，然后断言父会话恰好收到一条 synthetic 完成/取消通知，pendingBackground 清空，重新激活也不重复通知。这个测试名中的 `live` 不能解读为调用真实在线模型，应阅读 layer 替换才能知道测试边界。[OpenCode：依赖替换](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/test/subagent-lifetime.test.ts#L27-L53)，[生命周期场景与断言](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/test/subagent-lifetime.test.ts#L55-L140)。

**DeepSeek Harness：验证故障时“没有做什么”。** goal-round-driver 测试向 `session/flush` 注入拒绝，断言 goal 仍 active、activation 已 disarmed、轮次为零且模型请求为零；另一测试允许创建 checkpoint 成功，却让第一轮后的 checkpoint 失败，断言只产生一次请求。第三个测试记录 flush 时已经发出的请求数，验证两轮之间存在 checkpoint。这些断言直接检验“存储失败后不再自行推进”的安全边界。[DSH：checkpoint 故障及顺序测试](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/tests/goal-round-driver.spec.ts#L569-L614)。

存储校验的测试又覆盖 header 身份匹配、新旧格式版本拒绝、未知事件类型拒绝，以及 writer 显式标记 ignorable 的未知事件保留。它们验证读取边界的协议处理，不能仅凭文件名叫 storage-contract 就声称任意后端的崩溃持久性已经证明。[DSH：身份与版本](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence/tests/storage-contract.spec.ts#L47-L88)，[未知事件处理](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/session-persistence/tests/storage-contract.spec.ts#L121-L147)。

以上证据是本次读到的测试定义及断言，**未执行上游测试，也未验证它们在当前机器通过**。它们说明项目把哪些行为写入回归契约，不构成测试覆盖率排名。

## 24.4 失败注入与 trace 验收

错误路径应围绕状态边界设计。对 CSV 案例可注入：模型流在工具参数中途断开；工具已经改文件但结果尚未写入时进程终止；测试输出被截断；两个 child 同时请求修改同一文件；预算在下一次模型请求前耗尽；用户在 checkpoint 期间取消。每种注入都应规定最终状态、允许的副作用、恢复动作及不得发生的后续调用。

工具异常的测试可用可控制 promise，进程崩溃则需要另设真实进程实验。用 `throw` 模拟写入失败不能证明 fsync 后断电的行为；同样，mock 远程成功不能证明网络超时后远端是否重复执行。应按层次扩大真实性，并明确实验成本。这些都是建议实验，未在本教材编写中运行。

trace 评价不应要求 Agent 逐字遵循一个“标准思考过程”，也不应依赖不可见的内部推理。可验收的是可观察行为：修改前是否读取目标文件；测试是否在最终修改之后；失败工具是否被错误标记成功；是否访问越界路径；是否在 child 未完成时宣布整体完成。合理的替代路径应允许通过，否则评测会惩罚比参考流程更好的方案。

## 24.5 评价集、泄漏与统计

评价集要覆盖任务类别、难度、仓库规模和失败类型，并保留版本。开发集用于反复改进提示和工具，冻结测试集用于最后比较；若反复查看失败答案再调参，测试集事实上已成为开发集。相同模板只改变量名的题目可能高度相关，随机拆分文件不足以防止泄漏，应按任务来源或模板族划分。对公开题目无法轻易确认模型预训练未见过，因此应说明暴露风险，并补充新构造、私有或时间后移的任务。

比较 A、B 两个方案时，应在同一任务上配对，固定预算和环境，分别报告成功率、每成功任务成本、延迟分布及失败分类。随机性明显时每题多次运行，但同一题的多次尝试不能简单当成完全独立的新题。重采样置信区间时可以以任务为单位保留成组尝试；样本小或相关性强时，结论应更谨慎。

例如 A 在 100 题上成功 80 题，B 成功 82 题，单看 2 个百分点不能判断 B 稳定更好。还要看它们在哪些题上互相胜负、重复运行方差和成本。若允许每题最多三次重试，报告“至少一次成功”时还应报告总花费和重试策略；不能拿三次机会的成功率与一次机会方案直接比较。

## 24.6 练习与参考答案

1. **证据题**：mock 模型驱动一次完整 CLI 修复并通过测试，证明了什么？**参考答案**：该脚本响应下产品路径与验收机制能够协作；不能证明真实模型会生成同样正确的调用。还需真实模型任务评测。
2. **竞态题**：如何验证十次并发 wake 不会启动十个同时运行的 drain？**参考答案**：用屏障停住首次 drain，发出十次 wake，记录并发数和运行次数，再释放屏障；分别断言最大并发为 1、待处理唤醒按约定合并。不要仅延时后检查某个瞬间。
3. **评测题**：Agent 修改后测试通过，随后又改了一行代码，最终算成功吗？**参考答案**：若规范要求验证最终产物，则不算已验证成功。应补跑受影响检查或明确结果未验证；旧 trace 中绿色结果不能替新文件背书。
4. **设计题**：设计 30 题 CSV 修复评价集。**参考答案**：按解析、金额语义、空值/缺列、编码与输出格式等族划分；每族同时有正常和反例，固定 base 与隐藏 oracle，按族隔离开发/测试材料；固定模型与预算，保留每次补丁、结果和 trace，并另做恢复/取消故障集。题目数量本身不保证代表性，必须说明目标使用场景。

完成本章后，读者应能把“存在断言”“断言已运行通过”“真实任务通过”“在目标分布上稳定有效”写成四种不同结论，并为每一种结论提供相应证据。
