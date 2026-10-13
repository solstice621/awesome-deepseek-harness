# 第 7 章：执行环境——文件、进程、工作目录与浏览器

[教材目录](../README.md)

**先修知识：**工具契约、文件路径、进程退出码和 Git 基础。**学习目标：**选择最小而合适的动作接口，管理长任务与交互进程，区分目录组织与安全隔离，并为浏览器和图像动作建立“观察—操作—确认”闭环。

## 7.1 一次动作发生在哪里

同一条 `python -m unittest`，在不同工作目录、代码版本、Python 环境和环境变量下，可能检查完全不同的程序。Agent 不能只记住命令字符串。一个可复现执行至少需要记录：执行环境身份、工作目录、输入代码版本、命令或结构化动作、关键配置、结果以及相关进程身份。敏感环境变量不能为了复现而原样暴露到模型上下文或日志中。

本章贯穿的合成任务是修复 CSV 汇总器漏乘数量的错误：`pen,3.50,2` 与 `book,12.00,3` 使用 `Decimal` 应得 `43.00`，旧代码只累加单价得到 `15.50`。合理的动作链是：读取仓库和失败样例；用局部编辑工具修改累计逻辑；在明确的目录运行测试；必要时启动预览服务，在浏览器导入同一 CSV 并确认总额。文件、shell 和浏览器不是互相替代的三个聊天接口，它们访问不同状态世界。测试工具返回成功，不能代替浏览器确认页面加载了新代码；页面显示正确，也不能代替文件层确认修改保存在预期路径。

## 7.2 编辑接口：把“准备修改”与“已经修改”分开

全文件覆盖简单，但模型必须准确重建所有无关内容。字符串替换容易理解，但旧文本不唯一时可能改错位置。补丁能表达局部差异和上下文，也可能因版本变化无法应用。稳健设计需要在修改前检查目标，在修改后返回实际结果；若有并行作者，还需版本条件或冲突检测。**补丁预览不是应用成功，修改成功不是业务正确，版本控制也不是自动冲突解决器。**

Codex 的 `ApplyPatchHandler` 接受自定义 patch 文本，先解析，再选择执行环境，使用该环境的文件系统、cwd 和 sandbox context 验证，最后调用 `execute_verified_patch`。这是一个明确的“解析—环境选择—验证—执行”路径；另有流式差异消费者发布预览事件，两条路径不能混淆。[正式应用：317–364 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/apply_patch.rs#L317-L364)，[流式预览：83–104 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/apply_patch.rs#L83-L104)

OpenCode 的 edit 工具先读文件，统一待替换文本的换行风格；匹配依次尝试精确文本、特定 Unicode 归一化、行尾容错。默认匹配数必须为一，显式 `replaceAll` 才允许多个位置，写入后还可能运行 formatter。因此不能只用模型发出的替换片段推断最终文件字节，应检查返回的实际差异或读回文件。[匹配与写入：149–207 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/edit.ts#L149-L207)

DSH 的 edit 工具经 `fs/edit-intent` 获取可选的观测版本，再将目标、替换规则、intent、取消信号和 sandbox policy 交给 `fs.editText`。插件可要求“先读后改”并提供版本条件；裸默认返回 `undefined`，因此不能把这个可扩展接口描述成所有部署都强制版本检查。[edit 执行：119–147 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/fs/tool-fs/src/edit.ts#L119-L147)

## 7.3 进程不随一次工具返回自动结束

shell 适合调用已有构建、测试与系统工具，却具有宽泛的表达能力。结构化 `cwd` 优于在命令字符串中拼接 `cd`；用户提供的文件名需要正确引用；输出应保留退出码、超时、信号和截断信息。管道成功也可能只代表最后一个子命令成功，具体 shell 语义必须纳入判断。

需要区分四件事：**启动成功、暂时有输出、进程退出、任务验证成功**。长测试返回进程句柄意味着第一件事成立，不意味着后两件事成立。一次等待的时间用尽，可以选择杀进程，也可以把进程转为后台作业；必须从具体工具契约判断。不要把所有名为 timeout 的字段理解成同一种终止保证。

Codex 的 `exec_command` 在准备完成后分配进程 ID，向管理器传入 cwd、执行环境、TTY、输出预算与等待时间；既可走等待完成的入口，也可走通常的管理器执行入口。沙箱拒绝路径明确不返回可继续操作的进程 ID。随后 `write_stdin` 将会话 ID 映射到已有进程，空输入用来轮询，非空输入继续交互。[启动：394–457 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/unified_exec/exec_command.rs#L394-L457)，[继续进程：97–108 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs#L97-L108)，[空写语义：144–158 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs#L144-L158)

OpenCode shell 工具暴露 foreground/background 和 timeout，执行前解析目录与命令权限，并在可能较长的批准过程结束后重新验证目录仍存在。默认前台超时为两分钟，后台默认不设超时；结果分别有 `running`/`completed`、退出码、信号与 shellID 等字段。背景完成通知由作业机制处理，不能把它简化为每隔一秒重新执行原命令。[输入输出：24–75 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/shell.ts#L24-L75)，[执行前检查：117–154 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/shell.ts#L117-L154)，[启动与通知：157–188 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/shell.ts#L157-L188)

DSH 的 bash 工具更直接展示组合条件的重要性：有 JobRegistry、启用后台能力且开启 `promoteOnTimeout` 时，可把等待超时的前台进程提升为后台作业并返回 jobId；如果等待超时时准备还没产生进程，则停止准备并返回超时。调用者取消则停止自己的作业并等待收尾。这些分支意味着“超时”必须携带准确状态，不能只返回一行模糊错误。[功能条件：202–206 行、257–264 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/shell/tool-bash/src/index.ts#L202-L264)，[等待与提升：295–352 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/shell/tool-bash/src/index.ts#L295-L352)

**PTY（伪终端）**用于依赖终端行为的交互程序：它有屏幕大小、控制字符和输入流，输出常带光标控制序列。普通管道更适合机器读取。OpenCode 的 `PersistentPty.Interface` 独立提供创建、写入、resize、snapshot、attach、handoff 等能力，attachment 中有回放 offset 与 truncated 标志；这说明终端会话还需要处理重连与输出缺口。该接口是服务契约，不能据此断言每个方法都直接作为模型工具暴露。[终端服务：37–50 行、60–114 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/persistent-pty/index.ts#L37-L114)

## 7.4 Workspace、worktree 与权限是三个概念

工作目录决定相对路径如何解释；workspace 是应用组织项目资源的概念；Git worktree 是同一仓库的另一个检出目录。worktree 适合让两个作者分别修改文件，但通常仍共享机器、网络和部分 Git 管理状态，它本身不是安全沙箱。创建了隔离目录，也不能推出模型无法访问目录之外。

本章检查到的 OpenCode `WorktreeGit` 策略会发现源仓库，以目标目录与 branch/ref 调用 Git worktree 创建，再规范化目录。它把检出组织交给策略层；不能从这个入口单独推出未提交文件复制、依赖安装或安全隔离保证。[Git 策略：14–36 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/worktree/git.ts#L14-L36)

对应地，Codex 上文的编辑与进程入口按所选 environment 取文件系统和 cwd；DSH `WorkingDirectoryService` 从会话投影获取目录，启动上下文组装时确保目录可用，并提供会话级目录更改。其 `set` 的契约明确不改变已有进程或权限。比如测试进程已在目录 A 启动，再把会话 cwd 切到 B，该进程不会自动搬到 B。[DSH 目录状态：81–109 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/working-directory/src/index.ts#L81-L109)，[目录更改：154–169 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/session/working-directory/src/index.ts#L154-L169)

## 7.5 浏览器与多模态：观测是有时效的

网页读取、浏览器操作、图像查看属于不同动作。HTTP fetch 得到响应内容，不等同于执行网页脚本后观察已登录页面；图像工具使模型获得像素，不自动获得点击能力；浏览器点击改变远端或本地 UI 状态，需要再观察确认。对本例，先观察上传控件和当前页面，再导入 CSV，最后读取汇总结果；不能用一次旧截图的坐标连续点击多个状态未知的页面。

OpenCode 本章检查的 `webfetch` 通过 HTTP GET 取内容，限定 HTTP/HTTPS，并对响应体设上限；它是网页内容获取的实际对应点，不是完整浏览器交互的证据。[请求与边界：67–82 行](https://github.com/anomalyco/opencode/blob/60a212c0769acd96b446acbadeb790486830f91d/packages/core/src/tool/plugin/webfetch.ts#L67-L82) Codex 的 `view_image` 则从选择的环境解析路径、检查文件并读取字节，解码验证图像后进入后续模型图像路径；这里也没有鼠标动作。[图像读取：145–186 行](https://github.com/openai/codex/blob/a9b0815167c27ab13719dd12d13b63e02b70d221/codex-rs/core/src/tools/handlers/view_image.rs#L145-L186)

DSH 提供了本章检查到的真实浏览器连接实例：实验性 Playwright MCP provider 可启动 isolated Chromium，也可通过 CDP endpoint attach；attach 路径要求独占资源。共享运行时按 Session 建 scope，检查调用所属 Agent，使用当前会话目录启动 stdio MCP，并在释放时等待资源关闭。这里的会话日志不等同于浏览器状态持久化；恢复文本历史后仍应重新观察浏览器。[启动/连接：27–50 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/experimental/browser-use-playwright-mcp/src/index.ts#L21-L50)，[会话资源：128–178 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/experimental/browser-use-runtime/src/mcp.ts#L128-L178)，[调用归属：196–213 行](https://github.com/deepseek-ai/deepseek-harness/blob/d743267388641bc76f17c45ce8b4c231aed1d32c/packages/experimental/browser-use-runtime/src/mcp.ts#L196-L213)

以上是所检查模块的边界映射，不是三个项目全部插件的能力清单。选择动作接口时，应优先选能表达当前意图并返回明确证据的入口：修改一个文件用局部编辑；运行现有测试用 shell；检查交互页面用浏览器；判断图片内容用图像输入。

## 7.6 练习与参考解法

1. **状态题：**测试命令返回 `jobId` 和少量日志，能否标记验证完成？**参考：**不能；需取得终态、退出原因和测试内容，并确认代码版本没有随后变化。
2. **并发题：**两个 Agent 修改同一 CSV 模块，唯一字符串匹配是否足够？**参考：**不一定。唯一匹配能避免位置歧义，不能防止丢失另一个作者的修改；还需独立工作目录、版本条件或串行写入策略。
3. **辨析题：**会话 cwd、已有 shell 进程 cwd、worktree 与 sandbox 是否同一状态？**参考：**不是。分别对应后续路径基准、进程启动状态、Git 检出组织与权限边界。
4. **设计题：**浏览器点击“计算”后连接断开，恢复时如何避免重复动作？**参考：**先重新观察当前页面与结果；若操作有远端副作用，查询操作记录或幂等键；只在确认未执行或安全可重复时重试。记录请求发送与结果确认之间的不确定窗口。

本章未启动上述上游执行器、浏览器或 PTY，也未进行沙箱安全测试；CSV 与断线场景是拟议实验。
