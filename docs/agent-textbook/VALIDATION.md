# 验证记录

[教材目录](README.md)

验证日期：2026-10-13。这里分别记录教材文档检查、源码复核和本地教学实验，避免把其中任何一项当作另一项的证明。

## 文档与源码引用

教材包含 28 章，前 27 章分别映射三个项目的固定提交，第 28 章将机制汇成可运行实验。证据索引记录 **382 条阅读证据、175 个不同上游文件**；文件内容哈希、阅读范围和所属章节见 [source-lock.json](source-lock.json)，论断说明见 [evidence.json](evidence.json)。

以下命令检查章节编号、目录入口、练习与答案入口、本地链接、固定源码提交、引用行范围及源码文件哈希。`SOURCE_ROOT` 应为三个固定源码归档的解压父目录，子目录名称见版本锁；不提供该参数仍可做文档结构与已记录范围检查。

```sh
python3 docs/agent-textbook/scripts/verify_textbook.py --sources-root "$SOURCE_ROOT"
```

实际执行结果为零错误，机器记录见 [structural-validation.json](structural-validation.json)。此检查确认引用可定位，不自动证明自然语言解释正确。

各章节另做了重点结论的交叉复核，覆盖请求视图、token 统计口径、规划约束、参数校验、记忆/检索边界、取消结算、恢复资格、批准键、文件与网络沙箱区别、插件代际、goal 续轮和评测断言等。第 26 章的版本前提与第 27 章的比较层级在复核后修正。它是有范围的源码审阅，不是逐分支全仓库审计。

## 本地教学实验

运行环境：Darwin arm64，Python 3.12.8，SQLite 3.45.3。命令从仓库根目录执行：

```sh
python3 -m unittest discover -s docs/agent-textbook/labs -p 'test_*.py' -v
python3 docs/agent-textbook/labs/agent_lab.py demo --approve-edit
python3 docs/agent-textbook/labs/agent_lab.py evaluate
```

**23 项测试全部通过。** 覆盖参数校验、批准范围、暂停恢复、工具与决策预算、暂态失败、调用身份冲突、缓存回执、事务提交前后真实子进程崩溃、过期测试、未结算动作阻止完成、压缩约束保留及固定样本评测。

正常演示得到 `completed`、总价 `43.00`、4 次工具尝试、5 次决策、1 次修改效果。五个固定样本中，错误程序碰巧通过 2/5，脚本化修复流程通过 5/5。详细环境、命令、结果与限制见 [labs/verification.json](labs/verification.json)。

这些结果只说明当前实验程序在固定合成数据上的机制行为。决策器预先知道修复步骤；修改、结果和收据处于同一 SQLite 数据库；没有并发 worker；进程崩溃不等于断电或磁盘损坏。它不提供真实模型能力得分，也不保证任意外部工具的 exactly-once。

## 未执行的验证

没有构建或执行 Codex、OpenCode、DSH 上游测试；没有真实模型调用、上游性能测量、部署演练或沙箱安全实测。章节中的上游测试断言只作为已读证据，所有建议的上游与开放课程实验仍标为 NOT RUN 或未运行。

## 复用与更新

源码变化时，应重新下载固定提交、阅读关键分支并更新证据，而不是仅替换 SHA。教学实验变化时，应重新执行对应测试并刷新记录。新增章节后运行文档检查；更改证据清单后，可用下列命令重建索引与哈希，再运行验证：

```sh
python3 docs/agent-textbook/scripts/build_source_index.py --sources-root "$SOURCE_ROOT"
```
