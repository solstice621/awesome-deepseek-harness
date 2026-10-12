# DSH 05｜Plugin Architecture：能力接口、组合与可逆资源生命周期

[返回总目录](../README.md) · P1 · 前置：依赖注入、资源所有权；先读 01/03

**源码基线：** `deepseek-ai/deepseek-harness@d743267388641bc76f17c45ce8b4c231aed1d32c`。本篇核对官方组合契约与默认 Agent factory；没有替换真实执行后端。

## 1. “一切皆插件”必须落到三个具体问题

谁声明能力？谁提供实现？谁消费能力？DSH 官方将 capability seam 拆成 Service Definition、Service Provider、Consumer。单有一个工具注册接口，还没有形成可替换的执行环境。[S1]

例如 filesystem 与 subprocess 需要处于同一个 execution world；只把文件访问切到远程，却让 Shell 仍在本地执行，会形成路径和副作用错位。该一致性是设计要求，不能因两个 provider 都能独立调用就认为组合正确。[S1]

## 2. 阅读入口

| 依据 | 已核对位置 | 重点 |
|---|---|---|
| [S1] | `docs/architecture.md`，1–280 行可见部分 | Cordis、profile/bundle、事件域、capability seams |
| [S2] | `agent-loop/src/index.ts`，1–260 行 | FactoryOwnership、PreparedAgent、取消资源获取 |
| [S3] | `agent-loop/README.md` | publication、scope、teardown 契约 |
| [S4] | `goal-round-driver/src/index.ts`，1–300 行 | 只依赖公开服务的具体插件 |

## 3. 配置组合不是另一套硬编码入口

Profile 定义要堆叠的 bundles 和 patch；bundle 提供配置行与代码分发。架构文档明确了有序层覆盖和统一 `dsh --profile ...` 启动方式，`sdk-minimal` 是显式例外，不应随意推断所有 profile 都继承同一 base。[S1]

文档提供 `dsh --profile web --dump-config` 观察实际插件树。学习应以实际 dump 为准，区分“仓库存在一个插件”“profile 挂载了它”“本次 Agent 作用域可使用它”三个状态。

## 4. 事件域不同，可靠性也不同

Session events 是应当随日志保留的事实；Agent events 表达执行中状态/拦截；Capability events 是 fs/tools/telemetry 等服务边界。[S1]

waterfall 的 listener 通过 next 委派，可以变换路径；serial、同步通知等模式不是同义词。若把一个必须持久的状态只放在 live event，重启后会丢失；若把每个瞬时 UI delta 都当业务日志，又会增加写放大。

**分析：** 选择事件域相当于选择一致性、持久性和控制权契约，不只是给事件取名。

## 5. 插件卸载是资源收敛

`FactoryOwnership` 先停止接受新启动，取消工厂信号，然后等待活 Agent 的 teardown 和已开始的 startup tasks。`raceAbortCall` 在取消后仍追踪异步迟到结果，必要时释放它。[S2]

PreparedAgent 在 publication 前拥有未发布资源；README 描述 create/resume 的 setup、registry publication、creation listeners 以及失败回滚。卸载要等待机器停止和作用域清理，旧对象的 disposer 不能误伤同 ID 的新对象。[S2][S3]

这是学习异步资源安全的主线。只会 `ctx.on` 注册一个 callback，还没有掌握插件架构。

## 6. 一个良好的消费方样本：Goal Driver

`goal-round-driver` 依赖 `agents`、`goals`、`sessions`，通过公开事件和 inbox 操作驱动长期目标，而不是导入 ReactLoopAgent 的私有方法。[S4]

**分析：** 这验证了能力边界的价值：调度策略可以是插件，默认循环只维护通用输入/状态协议。不过 Goal Driver 仍需依赖这些公共协议的精确时序，并非可以和任何 Loop 无条件互换。

## 7. 待运行实验

**D05-A：配置可见性。** dump 一个只含 mock 能力的 profile，标注每条服务来自哪个 bundle/patch；替换同一 provider 后确认实际消费者都在同一个 execution world。

**D05-B：可逆注册。** 挂载一个只观察事件的插件，卸载后运行同一任务，确认无残留 callback；再检查它创建的 timer、连接与异步操作。

**D05-C：启动/卸载竞态。** 阻塞 Agent setup，开始 factory unload，再让 setup resolve。检查资源释放、registry 是否存在半初始化 Agent、错误是否完整暴露。

## 8. 验收与岗位关联

交付 capability 三方图、profile composition 图和一次卸载时序。能回答：配置覆盖与服务隔离分别解决什么；为什么需要 PreparedAgent；为什么 live event 不能承担 durable state；为什么旧 disposer 必须绑定旧 lifecycle。

**迁移到 Agent Infra：** 把本地/远程工作区、模型后端、日志后端和评测策略放在可替换边界，能降低系统耦合；代价是必须严格维护能力兼容、生命周期和版本契约。

[S1]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/docs/architecture.md
[S2]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/src/index.ts
[S3]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/core/agent-loop/README.md
[S4]: https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/goal/goal-round-driver/src/index.ts
