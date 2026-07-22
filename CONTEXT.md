# Dev Time Product Context

Dev Time 的共享产品领域词汇。它定义三个服务共同使用的业务语言，避免把产品概念、界面形态和 Agent 实现混为一谈。

## Language

**Delivery Owner**:
对一个或多个 GitHub 项目的交付结果负责，并需要决定当前优先处理什么的人。Delivery Owner 可以是独立开发者或小团队技术负责人，但不泛指所有参与编码的人。
_Avoid_: 所有开发者、GitHub 用户、Agent 使用者

**Risk Workspace**:
用户无需先提问就能看到当前最高优先级交付风险、支持证据和最小下一步的主要产品入口。
_Avoid_: Chat 首页、通用 Dashboard、Agent Playground

**Workspace Data Boundary**:
每个 Risk Workspace 必须属于已认证的 Delivery Owner。用户只能访问其 GitHub 授权范围内、并主动加入该 Workspace 的仓库；GitHub 凭据、Delivery Gate 配置、风险历史、执行记录和设置都必须按 Workspace 隔离。未登录用户不能读取任何 Workspace 数据。
_Avoid_: 全局共享项目、匿名项目接口、跨用户复用 GitHub token、未标识的演示数据

**Personal Risk Workspace**:
首个 MVP 中由一个 GitHub 身份独占的私有 Risk Workspace。Delivery Owner 可以连接个人或组织仓库，但 Acknowledged、Dismissed 和执行记录只属于该用户；首版不包含成员邀请、角色权限、共享状态、评论或任务分配。
_Avoid_: 团队协作平台、组织级共享看板、多人任务管理

**Connected Repository**:
Delivery Owner 从当前 GitHub 授权身份可访问的仓库中，主动加入 Risk Workspace 并允许 Dev Time 同步交付事实的仓库。
_Avoid_: 授权后自动导入全部仓库、前端硬编码项目、用户无权访问的仓库

**Repository Monitoring State**:
Connected Repository 的风险检测准备状态，只包含 Needs Setup 和 Monitoring。它表达系统是否具备判断 Delivery Risk 的必要配置，不表达仓库本身是否健康。
_Avoid_: 把同步成功当作健康、用绿色状态掩盖配置缺失、项目执行进度

**Needs Setup**:
尚未配置任何 Delivery Gate、因此不能生成 Delivery Risk 的 Connected Repository。Dev Time 必须明确提示用户完成门禁选择，不能把该状态展示为“无风险”。
_Avoid_: Healthy、风险为零、同步完成

**Monitoring**:
至少存在一个有效 Delivery Gate、Dev Time 可以持续验证 Merge Target 是否被阻塞的 Connected Repository。GitHub branch protection 或 ruleset 明确要求的检查可以自动成为门禁；否则必须由 Delivery Owner 主动选择。
_Avoid_: 仅连接 GitHub、仅完成一次同步、没有判断依据的监控

**Demo Workspace**:
与真实用户数据完全隔离、明确标记为演示环境的只读 Risk Workspace。示例数据只能出现在 Demo Workspace 中。
_Avoid_: 在真实 Workspace 注入假项目、匿名暴露生产数据、把 fallback 数据当作同步结果

**Risk Queue**:
Risk Workspace 中按处理优先级排列的活跃 Delivery Risk 集合。Project 只作为风险的归属、分组和筛选维度，不是风险判断或排序的最小单位。
_Avoid_: 项目排行榜、仓库列表、风险项目列表

**Attention Priority**:
Delivery Owner 用来判断处理顺序的可解释优先级，面向用户呈现为 Now、Next 或 Watch。它由对 Delivery Target 的影响、时间紧迫度以及证据可信度与新鲜度共同决定；内部可以保留数值用于稳定排序，但数值不是产品语言。
_Avoid_: 项目风险分、不透明的 0–100 分、仅凭 severity 排序

**Now**:
已经阻塞 Delivery Target，或若当前不处理，极可能错过下一个交付节点的 Attention Priority。低可信度信号不能仅因截止时间临近而自动进入 Now，必须先核实证据。
_Avoid_: 所有失败事件、仅因截止日期临近的推测、最高 severity

**Next**:
证据可信、可能影响 Delivery Target，但尚未形成当前阻塞，可以安排在当前工作之后处理的 Attention Priority。
_Avoid_: 当前阻塞、无证据的担忧、普通待办事项

**Watch**:
潜在影响或证据仍不充分，目前只需观察、等待变化或补充证据的 Attention Priority。
_Avoid_: 已确认阻塞、必须立即执行的事项、被忽略的风险

**Current Delivery Blocker**:
阻止 Delivery Target 进入下一交付状态的当前 GitHub 可见条件。对 Merge Target 而言，只有当必要 review、merge conflict 等更早合并前提已经满足时，Gate Failure 才是 Current Delivery Blocker。
_Avoid_: 任意失败检查、未来可能的问题、与下一交付状态无关的异常

**MVP Priority Mapping**:
CI Blocked Risk 在 Gate Failure 已确认且 CI 是 Current Delivery Blocker 时为 Now；Gate Failure 已确认但仍有更早合并前提未满足时为 Next；检查可能停滞但历史样本不足时为 Watch。前提变化使 CI 成为当前阻塞后，风险必须自动升级，并在 Risk Brief 中说明原因。
_Avoid_: 所有红色检查都是 Now、固定优先级、无法解释的升级

**Risk Lifecycle**:
Delivery Risk 的状态变化，只包含 Open、Acknowledged、Resolved 和 Dismissed。它表达风险是否需要用户注意以及证据是否仍然成立，不表达工作的执行进度。
_Avoid_: 任务看板、In Progress、Done、开发进度跟踪

**Open Risk**:
系统已检测到且仍有 GitHub 证据支持、用户尚未确认处理的 Delivery Risk。
_Avoid_: 普通未读通知、未验证信号

**Acknowledged Risk**:
Delivery Owner 已看到并决定处理，但 GitHub 证据尚未证明风险条件消失的 Delivery Risk。
_Avoid_: 正在开发、已完成、手动关闭

**Resolved Risk**:
最新 GitHub 证据确认原风险条件已经消失的 Delivery Risk。用户不能仅通过手动操作把风险标记为 Resolved。
_Avoid_: 用户声称已完成、隐藏风险、停止提醒

**Dismissed Risk**:
Delivery Owner 明确判断为不相关、可接受或误报，并从活跃 Risk Queue 中移除的 Delivery Risk。Dismissed 不表示底层 GitHub 条件已经消失。
_Avoid_: Resolved、Done、删除历史证据

**Risk Episode**:
由 Merge Target、当前 head SHA 和风险类型共同标识的一次 Delivery Risk 事件。Dismissed 只对当前 Risk Episode 有效；新 commit、风险恢复后再次出现或失败门禁集合发生实质变化时，需要创建新的 Open Risk。
_Avoid_: 永久忽略 PR、跨 commit 复用 Dismiss、用 Dismiss 关闭 Delivery Gate

**Dismiss Reason**:
Delivery Owner 在 Dismiss Risk Episode 时必须记录的判断，只能是误报、已接受风险或与当前交付无关。记录用于审计和衡量误报率；首版不能据此让 Agent 自动改变确定性风险规则。
_Avoid_: 无理由隐藏、自动学习规则、删除风险证据

**Contextual Agent**:
围绕 Risk Workspace 当前风险提供解释、追问和行动草稿的辅助角色；它不独立定义工作目标。
_Avoid_: 通用聊天机器人、产品首页、自治项目经理

**Risk-Scoped Conversation**:
绑定单个 Risk Episode 的 Contextual Agent 会话。Agent 自动获得对应 PR、head SHA、失败门禁、job 日志与风险历史，回答必须引用 GitHub 证据并区分事实和推断；证据不足时必须明确无法判断。新 head SHA 创建新 Risk Episode 后，旧会话只能作为历史保留。
_Avoid_: 全局聊天入口、跨仓库漫游、无证据根因、旧对话控制新风险

**Deterministic Risk Core**:
仅依赖 GitHub 事实和可解释规则生成 Delivery Risk、Attention Priority、Risk Lifecycle 与 Risk Brief 的产品核心。它不依赖 LLM 或 Agent，因此在智能能力不可用时仍能提供完整的风险工作区。
_Avoid_: 由 LLM 判断风险是否存在、Agent 启动后才生成首页、聊天记录作为风险事实

**Risk Brief**:
每条 Delivery Risk 的结构化说明，至少包含受影响的 Delivery Target、观察到的阻塞、证据来源与更新时间、Attention Priority 的理由、当前最小下一步和 Risk Lifecycle 状态。Risk Brief 由 Deterministic Risk Core 生成，Contextual Agent 可以解释和扩展，但不能改变其中的事实判断。
_Avoid_: 一段不可追溯的 AI 总结、聊天回答、只有风险分的卡片

**Evidence Freshness**:
Dev Time 最近一次成功向 GitHub 验证某项事实的时间。Risk Brief 必须显示 last verified at；首次同步完成前不能展示 Risk Queue 结论。
_Avoid_: 仅显示本地更新时间、把同步任务成功当作事实已验证、没有时间戳的证据

**Stale Monitoring**:
Monitoring 仓库超过 20 分钟未成功验证 GitHub 状态的降级状态。此时保留既有风险，但不能显示“全部正常”、不能自动 Resolved，并必须明确提示数据已经过期。GitHub webhook 是主要更新来源，每 15 分钟 reconciliation 一次以修复丢失或乱序事件；用户确认执行操作后需要主动跟踪结果。
_Avoid_: 把旧数据当作当前事实、同步失败时清空风险、等待定时任务才确认操作结果

**All Clear**:
至少一个 Connected Repository 处于 Monitoring、首次同步完成、所有监控数据均未 Stale，且当前不存在 Open 或 Acknowledged 的 CI Blocked Risk 时，Risk Workspace 才能展示的已验证空状态。界面必须同时显示已检查的活跃 Merge Targets、Delivery Gates 数量和最后验证时间。
_Avoid_: 风险分为 0、项目健康、Needs Setup、Stale、没有活跃目标

**Primary Product Moment**:
用户打开 Risk Workspace 后，在没有输入问题的情况下理解今天最需要处理的交付风险及下一步。
_Avoid_: 首次发送消息、首次工具调用、首次生成回答

**In-App Risk Update**:
首个 MVP 唯一的风险通知形式，在 Risk Workspace 内展示新出现、升级为 Now 以及自用户上次访问以来发生变化的风险。首版不发送邮件、Slack、Teams 或其他外部通知。
_Avoid_: 重复 GitHub CI 通知、所有信号都推送、在核心闭环验证前扩展通知渠道

**Delivery Target**:
GitHub 中一个明确、可判断是否达成的交付结果，例如合并目标、milestone 或 release。Delivery Target 是判断某个状态是否会影响交付的必要前提。
_Avoid_: 项目、任意开发活动、隐含截止时间

**Delivery Gate**:
Delivery Target 达成前必须满足的可验证条件。Merge Target 的 Delivery Gate 来自 GitHub branch protection 或 ruleset 明确要求通过的检查，也可以由 Delivery Owner 主动指定为合并前必须通过的 workflow/check。
_Avoid_: 所有 CI 检查、任意失败事件、Agent 推测的重要检查

**Delivery Risk**:
有 GitHub 证据支持、可能妨碍一个明确 Delivery Target 达成的状态。每个 Delivery Risk 必须绑定一个 Delivery Target。
_Avoid_: 任意失败事件、一般代码问题、未关联目标的仓库异常

**Health Signal**:
有 GitHub 证据支持、值得关注但尚未关联明确 Delivery Target 的仓库状态。Health Signal 可以促使用户调查，但不能声称会影响交付。
_Avoid_: Delivery Risk、风险分、交付阻塞

**Gate Failure**:
Delivery Gate 的最新 GitHub 证据显示条件未通过或异常停滞。Gate Failure 可以生成对应 Delivery Target 的 Delivery Risk；非 Delivery Gate 的检查失败只能生成 Health Signal。
_Avoid_: 所有 check failure、历史失败、非必要检查自动升级为风险

**CI Blocked Risk**:
一个 Merge Target 因一个或多个 Delivery Gate 未通过而形成的聚合 Delivery Risk。每个 Merge Target 在 Risk Queue 中最多显示一条 CI Blocked Risk；Risk Brief 在详情中列出全部失败门禁、各自证据和可执行范围。
_Avoid_: 每个失败 job 一条风险、按 CI 事件数量占满队列、隐藏底层失败证据

**Gate Runtime Baseline**:
同一仓库、同一 Delivery Gate 最近 20 次成功运行时长形成的历史基线。至少有 5 次成功样本时，异常停滞阈值为 30 分钟与历史 P95 两倍中的较大值。
_Avoid_: 全局统一超时、混用不同 workflow 的时长、用失败运行计算正常时长

**Stalled Gate**:
Delivery Gate 持续处于 queued 或 in_progress，并超过其 Gate Runtime Baseline 阈值的状态。历史成功样本不足时，运行超过 30 分钟只能产生 Watch，不能直接产生 Now 或 Next；GitHub 已明确返回 failure、timed_out 或 action_required 时无需等待阈值。
_Avoid_: 普通运行中、首次长任务直接判定阻塞、由 Agent 猜测停滞

**Merge Target**:
一个非 Draft、已进入 ready-for-review 状态且目标是成功合并的 Pull Request。它不需要关联 milestone 或 release，也可以独立成为 Delivery Target。
_Avoid_: Draft PR、任意分支、任意 commit

**Milestone Target**:
一个有明确工作范围和截止时间、目标是按期完成的 GitHub milestone。
_Avoid_: Issue 列表、无截止时间的主题集合

**Release Target**:
一个已计划但尚未完成、目标是成功发布的 GitHub release。
_Avoid_: 已发布版本、任意 tag、部署记录

**MVP Delivery Scope**:
首个可交付版本只解决 Merge Target 的 CI 阻塞闭环：发现 ready-for-review PR 的必要检查失败或异常停滞，展示证据与影响，提供最小行动，在用户确认后重新运行检查，持续验证结果，并在 GitHub 证据确认阻塞消失后自动标记为 Resolved。Milestone Target 和 Release Target 保留在产品模型中，但不属于首个 MVP 的实现范围。
_Avoid_: 同时实现全部 Delivery Target、通用 GitHub 助手、只展示失败状态而不验证结果

**Time to Verified Unblock**:
从 Dev Time 首次检测到 Gate Failure，到 GitHub 证据确认相关 Delivery Gates 全部恢复通过的时间，简称 TTVU。TTVU 是首个 MVP 的核心结果指标；首轮内测先建立基线，再判断产品是否真正缩短解除阻塞的时间。
_Avoid_: 功能完成数量、Agent 调用次数、聊天消息数、未验证的处理完成时间

**MVP Metric Guardrails**:
与 TTVU 同时观察的质量指标，包括 Detection Latency、因误报产生的 False-positive Dismiss Rate、Confirmed Rerun Resolution Rate，以及未进入 Stale 的 Fresh Monitoring Coverage。
_Avoid_: 只优化解除速度、忽略误报、忽略数据过期、把重跑请求当作成功解除

**MVP Product Exclusions**:
首个 MVP 明确不包含项目级风险分与排行榜、全局聊天、跨仓库通用问答、提问前强制风险评估、手动项目状态管理、面向用户的 Agent 技术轨迹、Confirmed Rerun 以外的写操作、未标识示例数据、Milestone 或 Release 风险、团队协作和外部通知。Agent 轨迹可以保留为内部诊断与审计数据。
_Avoid_: 把旧功能换皮迁移、为未来范围预建用户入口、仅修改本地状态的成功操作

**MVP Executable Action**:
首个 MVP 中 Dev Time 唯一可以执行的 GitHub 写操作，是在 Delivery Owner 明确确认具体目标和执行范围后，重新运行发生故障的 GitHub Actions workflow。Agent 可以读取证据、解释失败并生成建议，但不能推送代码、修改或合并 PR、发表评论、关闭 Issue，或执行其他 GitHub 写操作。
_Avoid_: 通用 GitHub 自动化、静默重试、自主修改代码、把建议显示为已执行

**Confirmed Rerun**:
Delivery Owner 在看到仓库、PR、workflow、失败 jobs 和执行范围后明确批准的一次 GitHub Actions 重跑。默认只重跑失败 jobs；如果 GitHub 只能重跑整个 workflow，必须提示范围扩大并再次确认。同一 workflow run 正在重跑时不能重复创建执行。
_Avoid_: 自动重试、模糊确认、重复执行、默认重跑全部 jobs

**Action Audit Record**:
Confirmed Rerun 的不可省略记录，包含发起人、目标、GitHub run ID、确认时间、实际执行范围、结果和错误。执行请求失败时，原 Delivery Risk 保持 Open 或 Acknowledged，不能显示为成功，也不能自动 Resolved。
_Avoid_: 仅修改本地状态、无 GitHub 执行证据、失败后伪装完成
