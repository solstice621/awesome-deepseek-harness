# OpenCode 03｜Tools / Permission：请求快照、调用身份与输出约束

[返回总目录](../README.md) · P0 · 前置：Schema、Effect 中断、输入输出契约

**源码基线：** `anomalyco/opencode@60a212c0769acd96b446acbadeb790486830f91d`。重点核对当前工具语义及 Step 执行边界；本文没有审计某个 OS sandbox backend。

## 1. 为什么标题不直接叫“安全沙箱实现”

工具类型、权限判断、进程隔离是不同机制。[S1] 说明可信工具自行捕获服务并发起权限请求；它并不证明所有第三方工具自动被沙箱隔离。第一轮应该学习真实授权和数据边界，而不是给工具注册表套一个 Sandbox 名字。

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `specs/v2/tools.md` | typed tool、scoped registration、request snapshot、输出裁剪 |
| [S2] | `session/runner/step.ts`，1–290 行 | Tool.Called、并发 Fiber、取消、终态 |
| [S3] | `tool/plugin/subagent.ts`，1–310 行 | 一个真实工具如何做权限与归属校验 |

文档中的接口示意和当前插件包装 API 不应机械混用；如 [S3] 的工具通过 `ctx.tool.transform` 安装。读实现时应沿当前调用方继续追踪。

## 3. 一个工具结果包含什么？

[S1] 区分三个部分：schema 验证的 `output` 是临时机器值，可供 Code Mode 使用；`content` 是持久化、模型可见的规范表示；`metadata` 是小型 UI 附加信息。

**分析：** 这种拆分避免一个巨大、包含内部对象的 JSON 同时承担模型输入、机器调用和 UI 展示。风险是各层必须明确转换责任，不能从 metadata 偷偷绕开模型输出上限。

输入先 decode，再 execute；有 output schema 的工具还需验证输出。无效输入不应执行，无效输出不应发布成功。[S1，契约]

## 4. 注册与执行快照

文档的 scoped registration 支持同名覆盖，卸载最新注册只移除它自身，旧注册可以重新显露。更重要的是：**一次模型请求同时捕获公开给模型的定义和将被执行的实际工具值**；注册变化作用于后续请求，不应让当前调用悄悄执行另一个工具。[S1]

这与 DSH 的活跃调度模式重新分类形成值得研究的对照，但不能只凭一个接口名字断言二者优劣。比较见 [横向分析](../COMPARISON.md)。

## 5. 从模型调用到执行结算

Step 读取完整 tool-call 事件；先完成 `publisher.publish(event)`，再启动本地工具 Fiber。`providerExecuted` 标识的调用不在本地再次执行。工具结果经过 truncation 后发布，工具定义的可预期错误与运行时中断分开处理。[S2]

工作本身可中断，但末尾工具和 Step 事件放在受保护的结算路径中。工具参数没有完成、provider 缺少工具结果、用户拒绝等情况会形成不同错误，不应全部包装成“模型失败”。[S2]

**注意：** 先发布调用事实并不证明外部副作用 exactly-once。进程仍可能在效果已发生、结果未记录时崩溃。

## 6. 输出上限也有两层

工具生产方可能在采集进程输出时已经限流或丢弃数据；registry 在完整结果形成后再约束模型可见文本。后者不能恢复前者已经丢弃的字节。文档要求 oversized content 的完整保留失败时报告操作错误，不能假装产生了可恢复的完整成功结果。[S1]

后置 hook 可以转换结果，但转换后还要再次规范化和约束。原生媒体与 metadata 有独立规则；“文本已截断”不等于整体内存使用已受控。

## 7. 待运行实验

**O03-A：注册快照。** 模型请求发出后、返回 tool-call 前替换同名工具。记录实际执行的实现，并核对它与请求声明是否一致。

**O03-B：三种结果表示。** 做一个合成工具，返回机器值、简短 content 和 UI metadata；检查哪些进入 durable Session、哪些进入下一 provider 请求。

**O03-C：输出保留故障。** 返回超大测试文本，分别让生产端提前截断、让后端完整保留失败，观察错误与 omission 信息是否准确。不要在生产目录制造磁盘写满。

**O03-D：取消不被吞掉。** 工具处理中断时，确认取消没有被普通 `ToolFailure` 当作成功可恢复输出吞掉。

## 8. 验收

产出“声明快照 → 调用身份 → decode → permission → execute → bound → terminal”流程表；每个阶段标注由契约还是实际代码支持。能解释为什么注册接口相同不表示权限相同、为什么 canonical content 是模型历史的依据、为什么普通权限审批不能替代 OS 隔离。

[S1]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/specs/v2/tools.md
[S2]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/session/runner/step.ts
[S3]: https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/subagent.ts
