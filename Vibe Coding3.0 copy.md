请你作为基于 Vibe Coding 体系的首席架构师，执行以下“项目初始化”指令，用于为我的项目生成完整的 `AGENTS.md` 项目上下文：

**配置源（Knowledge Sources）**：

1. **本地知识库** (Local Knowledge): `/Users/weihui/Desktop/tools/vibe-coding-cn-main` 与 `/Users/weihui/Desktop/tools/skills-main`（优先，作为一切推理与模板匹配的主数据源）
2. **社区技能市场** (Community Skills Marketplace): `https://skillsmp.com/`（扩展，补充本地缺失技能）
3. **MCP 服务器仓库** (MCP Servers Registry): `https://github.com/modelcontextprotocol/servers`（动态连接外部工具与服务）

**任务目标（Mission）**：

围绕我的【需求描述】，构建用于日常开发协作的全栈项目上下文文档 `AGENTS.md`。文档必须完整覆盖以下三个维度，并保持结构清晰、可被智能体直接消费：

- **知识 (Skills)**：需要或推荐安装的 AI Skills / Prompts / 工作流
- **架构 (Templates)**：项目整体架构、代码模板与目录结构
- **工具连接 (MCP)**：通过 MCP 服务器连接到的外部系统（数据库、Git、浏览器等）

**我的需求描述（Project Requirements）**：

<开发一个获取btc历史数据和实时数据的程序，程序集成了量化模型（程序可以训练模型）可以实时判断当前btc价格下一个十分钟（10min、30min、60min）的涨跌概率，并提供简单可视化界面
>

**执行步骤**：

1. **需求解构（Decomposition）**：从我的【需求描述】中系统性提取以下信息：

   - 目标用户与业务场景（如：SaaS 落地页、内部后台、移动端应用）
   - 目标平台与技术栈（如：Next.js、Vue、React Native、Python、Go）
   - 非功能性诉求（如：可观测性、多租户、合规、安全要求、国际化）
   - UI / UX 相关需求（如：品牌风格、暗色模式、设计系统、一致性要求）
2. **多维资源匹配（Resource Matching）**：

   - **Skill Match**（技能匹配）：

     - 优先检索本地知识库（如 `vibe-coding-cn-main/i18n/zh/skills/` 或 `skills-main/skills/`）中与本项目相关的 Skills。
     - 若项目存在明显的 UI / UX 设计或前端界面需求：
       - 将 `ui-ux-pro-max-skill`（Antigravity Kit UI/UX 设计智能工具包）作为优先推荐 Skill；
       - 若本地不存在对应 Skill 文件，则：
         - 给出在 SkillsMP 搜索 `ui-ux-pro-max-skill` 的建议；
         - 给出官方 GitHub 仓库链接：`https://github.com/nextlevelbuilder/ui-ux-pro-max-skill`；
         - 简要说明该 Skill 在本项目中的典型用途（如：生成设计系统、选择配色/字体、避免常见 UX 反模式）。
     - 对于其他缺失的核心能力（如：Auth、数据同步、可观测性），生成对应的 SkillsMP 搜索链接。
   - **MCP Match**（MCP 服务器匹配）：

     - 识别项目是否需要以下能力，并为每类能力标注候选 MCP Server：
       - 数据库（如 PostgreSQL、MySQL、SQLite 等）
       - 版本控制与协作（如 Git / GitHub / GitLab）
       - 浏览器自动化与爬虫
       - 云平台或第三方 API（如 OpenAI、Stripe、发送邮件服务）
     - 对于每一类需要的能力，在 `AGENTS.md` 中输出：
       - 推荐的 MCP Server 名称
       - 官方仓库链接
       - 最小可用的 JSON 配置示例片段（方便直接复制到 IDE 配置中）
   - **Architecture Match**（架构模板匹配）：

     - 从本地 `/Users/weihui/Desktop/tools/vibe-coding-cn-main` 中匹配合适的架构模板与示例项目；
     - 给出推荐的项目结构、模块划分与关键技术选型；
     - 如存在多种可选方案（如 Monolith vs Microservices），说明各自适用场景并给出推荐。
3. **生成 `AGENTS.md`（Agent Context 构建）**：
   请输出一份**全中文**的 Markdown 文档（专有名词保留英文），包含：

   - **# 项目概览 (Project Overview)**
   - **# 资源索引 (Resource Index)**: 本地 Skills 和 Prompts 路径。
   - **# 缺失技能与获取 (Missing Skills & Acquisition)**: SkillsMP 下载链接。
   - **# 推荐 MCP 服务器 (Recommended MCP Servers)**:
     - 列出建议配置的 MCP Server 名称及官方仓库链接。
     - **关键**：为每个推荐的 Server 生成一段 `配置示例`（JSON格式），方便用户直接复制到 IDE 配置文件中。
   - **# 实施路线图 (Implementation Roadmap)**

**输出要求**：
直接输出 `AGENTS.md` 的完整内容。确保所有说明性文字均为**中文**。
