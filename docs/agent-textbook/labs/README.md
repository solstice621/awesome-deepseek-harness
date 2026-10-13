# 离线综合实验：修复 CSV 总价

[第 28 章：综合实验](../chapters/28-capstone-lab.md) · [教材目录](../README.md)

本实验只使用 Python 标准库，不需要模型账号、API key、网络或额外依赖。Agent 的工具不会运行 shell 或任意代码；“修复”是把 SQLite 工作区中的预定义程序模式从 `unit_only` 切换到 `quantity`。脚本化模型已经知道修复步骤，因此实验验证执行机制，**不能验证真实 LLM 的理解、规划或编码能力**。

文件分工：`agent_lab.py` 是模型夹具、工具、运行器及 CLI；`test_agent_lab.py` 是机制测试；`verification.json` 记录本次实际运行结果。建议 Python 3.9 或更新版本；本次实际使用 Python 3.12.8。

## 最短运行路径

以下命令从本仓库根目录执行：

```sh
python3 docs/agent-textbook/labs/agent_lab.py demo --approve-edit --events
python3 -m unittest discover -s docs/agent-textbook/labs -p 'test_*.py' -v
python3 docs/agent-textbook/labs/agent_lab.py evaluate
```

不传 `--db` 时使用自动清理的全新临时数据库，重复运行互不干扰。正常演示的汇总是：

```json
{
  "status": "completed",
  "spent": 4,
  "max_attempts": 8,
  "decisions": 5,
  "max_decisions": 16,
  "mode": "quantity",
  "revision": 1,
  "total": "43.00",
  "effects": 1
}
```

四次工具尝试依次为检查、修复前测试、修改、修复后测试；第五次模型决策返回停止。初始值是 `3.50 + 12.00 = 15.50`；修复后的值是 `3.50 × 2 + 12.00 × 3 = 43.00`。金额使用 `Decimal`。`completed` 还要求没有待结算调用、最近完成的测试通过且修订号等于当前工作区修订号，以及五项固定独立期望值验证全部通过。

## 观察审批、预算和重试

```sh
# 在新临时数据库中，修改前暂停；spent=2，effects=0。
python3 docs/agent-textbook/labs/agent_lab.py demo

# 可以完成修改，但没预算验证：total=43.00 仍是 budget_exhausted。
python3 docs/agent-textbook/labs/agent_lab.py demo --approve-edit --max-attempts 3

# 第一次 test_total 注入暂态失败，随后重试；最终 spent=5。
python3 docs/agent-textbook/labs/agent_lab.py demo --approve-edit --fail-once test_total --events
```

预算分为两个持久计数。`spent/max_attempts` 计量**实际启动的工具尝试**，不是 token 或费用。拒绝审批和 schema 拒绝发生在启动前，不扣尝试预算；暂态失败和启动后崩溃已经消耗尝试；读取已完成调用的缓存收据不启动工具，不再扣尝试预算。`decisions/max_decisions` 在每次模型决策之前扣减，包含模型重复要求缓存结果和最终返回停止。因此一个不停重放相同调用的策略仍会停止，重启也不能重置这个上限。CLI 用 `--max-decisions` 设置新数据库的决策预算。

`--approve-edit` 只批准 `set_mode(mode="quantity")`，不批准恢复为其他模式、任意路径或任意工具。审批不从模型上下文自动推导，也不持久保存；恢复时如仍有未执行修改，需要重新显式提供此参数。

## 持久恢复与崩溃实验

用新建临时目录保存本实验数据库；下面的命令可直接逐行运行：

```sh
lab_dir=$(mktemp -d)
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/approval.sqlite3"
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/approval.sqlite3" --approve-edit
```

第二次运行继续原有状态，不会重设样本或预算。已有数据库的 `--max-attempts` 和 `--max-decisions` 参数不会提高持久预算。请为不同实验使用不同数据库文件；本教学程序不包含历史数据库格式迁移。

在提交前崩溃：

```sh
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/before.sqlite3" --approve-edit --crash-before repair
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/before.sqlite3" --approve-edit --events
```

第一条命令**预期退出码 86**，它以 `os._exit` 终止子进程。修改事务回滚，启动前预留的预算仍保留；恢复后重试修改，总共花费 5 次尝试，副作用收据只有 1 条。

在提交后、返回工具结果之前崩溃：

```sh
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/after.sqlite3" --approve-edit --crash-after repair
python3 docs/agent-textbook/labs/agent_lab.py demo --db "$lab_dir/after.sqlite3" --approve-edit --events
```

此时修改和收据都已提交。恢复读取持久结果，跳过已完成的修改，只运行剩余测试；最终花费 4 次尝试，仍只有 1 条副作用收据。测试还显式重放相同 `call_id`，确认返回原结果而不再次修改。

这些实验只证明本程序、当前环境下的**进程崩溃**路径，不是断电、磁盘损坏或分布式事务验证。副作用、结果和收据全部位于同一 SQLite 数据库内；不能把这个性质推广成任意外部 API、文件写入、shell 工具的 exactly-once 保证。一个新的 `call_id` 被视为新动作，会新增修订；本实验没有语义去重。

## API 导览

| API | 职责 |
| --- | --- |
| `ToolCall(call_id, name, args)` / `validate_call()` | 关联一次逻辑调用；检查有限工具 schema 子集 |
| `ScriptedModel.next_call(context)` | 选择四步预设计划中第一个没有持久结果的调用 |
| `AgentLab(path, max_attempts=8, csv_text=..., max_decisions=16)` | 创建或恢复本地实验状态；已有状态与两种预算优先 |
| `AgentLab.execute(...)` | schema、审批、幂等收据、预算、工具执行与结果提交 |
| `AgentLab.run(...)` | 循环调用模型夹具；重试暂态失败；根据当前修订验证完成 |
| `AgentLab.build_context()` / `compact_context()` | 构造上下文；保留结构化约束、未完成调用和结果，裁剪事件尾部 |
| `AgentLab.snapshot()` / `events()` | 查看当前状态与带序号的事件 |
| `evaluate()` | 对五个固定数据夹具运行流程，报告分母与独立预期值 |

程序是**单 worker 教学运行器**，没有并发执行租约、跨主机锁或任意工具插件。`compact_context` 保留全部四个工具结果，只裁剪事件；它不是通用 token 预算器，也没有证明自然语言摘要无损。完整日志仍在数据库中。

## 本次验证结果

2026-10-13，在 Darwin arm64、Python 3.12.8、SQLite 3.45.3 上实际运行：23 项 unittest 全部通过，包括真正的子进程提交前/后崩溃、两种预算的持久性、审批、schema、暂态重试、重复 ID 冲突、待处理调用阻止完成、测试完成顺序、旧验证失效和压缩约束保留。正常演示返回 `completed / 43.00 / spent=4 / decisions=5 / effects=1`。

五个固定数据夹具中，错误程序碰巧通过 2/5，脚本化修复流程通过 5/5。这里的 5/5 是已知任务上的机制结果，不是模型能力得分，也不是任意 CSV 正确性的证明。内部 `test_total` 的实际值与期望值共享 `total()` 辅助函数；完成判定及 `evaluate()` 额外使用手工计算的固定期望值，涵盖数量大于一、零数量、空数据和小数金额，防止当前用户样本恰好全为数量一时掩盖漏洞。测试结果按完成事件序号排序，而不是按首次登记顺序排序。仍需更多边界数据与独立实现的 oracle 才能扩大结论。
