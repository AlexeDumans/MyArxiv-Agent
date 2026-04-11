# 🏗️ MyArxiv-Agent 项目架构深度解析

本项目是一个基于 GitHub Actions 和 Python 的自动化 arXiv 论文抓取、整理与知识库构建系统。以下提供系统各个模块的全部运转细节与架构剖析，专为您进行个性化改动设计。

---

## 1. 📂 整体目录与存储架构

`MyArxiv-Agent` 的文件流向基于本地 Markdown 与目录结构的变更，全链路均在 Git 管理之下：

- **`config.yaml`**: 系统的**核心自中枢**。绝大多数逻辑（如抓取上限、API 参数、摘要模板、正则表达式识别方式、归档模板排列）都可在此处通过变量调整。
- **`Inbox.md`**: **流转中转站（待读区）**。每日新增的论文会自动追加至此处，等待人工介入打钩评判。
- **`Papers/`**: **数据持久区**。依据论文所属分类在里面生成不同的子目录，里面的 `List.md` 以追加行的方式存档已阅读打钩的论文。
- **`Notes/`**: **知识生产区**。归档的论文会自动在此基于配置内的模板生成一个可交互的 Markdown 模板文件，由您之后补充阅读总结。
- **`Contents.md`**: **全局索引页**。由脚本自动生成，用于在仓库主页汇总所有已归档分类与笔记链接。

> [!TIP]
> **个性化改动点**：如果你想修改生成目录的名字，或增加例如 `PDF_Storage`，请直接在 `config.yaml` 的 `paths` 内修改，整个代码逻辑将自动顺应新路径。

---

## 2. ⚙️ 核心处理工作流 (Python 脚本层)

核心逻辑集中在 `scripts/` 目录下，包含三大脚本支撑主轴。

### 📌 阶段一：自动抓取与去重 (`fetch_arxiv.py`)
- **运行机制**: 被 GitHub Action 的 `daily_scheduler.yml` 驱动（定时任务）。
- **流程解析**:
  1. 通过 `config_loader` 解析 `config.yaml` 的 `fetch` 节点，构建组合查询条件（如按 category、keywords 或 id_list）。
  2. 使用 `feedparser` 向 `export.arxiv.org/api/query` 拉取 Atom 数据，存在重试机制。
  3. **去重与版本检测**: 
      - 对比现有 `Inbox.md`、`Contents.md`、`Papers/*/List.md`，收集所有已存在的 arXiv id 和链接。
      - 系统可智能识别更新的版本（从 `v1` 迭代到 `v2` ），如果在 `config.yaml` 中配置 `features.arxiv_version_update_behavior: "replace"`，会自动更新旧链接并追加版本更新公告。
  4. 把最新论文按可配置的 `formatting.item_template` 组装为 Markdown 字符串，插入到 `Inbox.md` 的分隔符 (`---`) 下方。

### 📌 阶段二：配置加载器 (`config_loader.py`)
- 提供层级安全的属性读取，同时具有**环境变量重写能力** (以 `ARXIV_AGENT__` 开头覆盖 Yaml)。

### 📌 阶段三：筛选后的归档 (`process_inbox.py`)
- **运行机制**: 被 GitHub Action 的 `auto_archive.yml` 驱动（当人为往 Github commit 并推送 `Inbox.md` 更改后触发）。
- **流程解析**:
  1. **正则识别**: 按照配置的复选框逻辑，使用正则表达式扫描 `Inbox.md` 内诸如 `- [x] **[分类]** [标题](链接)` 的行。
  2. **安全处理 (Sanitization)**: 对文章标题及分类剔除非法字符和控制符，确保落盘时不破坏操作系统环境。
  3. **笔记生成**: 在 `Notes/<category>/<title>.md` 自动生成预设的读书笔记模板 (如包含摘要区、实验区、点评区，内容来源于 config)。
  4. **分类合并录入**: 将论文链接与信息写入 `Papers/<category>/List.md` 底部。
  5. **全局目录生成**: 遍历 `Papers/`，更新根目录下的 `Contents.md` 建立起全库的层叠索引。
  6. **剔除**: 用处理过的**新**（去掉了打钩论文的）文本内容将 `Inbox.md` 覆盖。

> [!IMPORTANT]
> **个性化改动点**：
> 1. 如果你在 `Inbox.md` 中需要增加特定的 tag（比如 `- [x] **[CS.AI]** [论文] {Tags: #NLP}`），你必须前往 `config.yaml` 修改 `archive.parsing.entry_regex`，或者同步修改 `process_inbox.py` 获取 group 的下标。
> 2. `fetch_arxiv.py` 内部对于 author 的 `et al.` 处理被硬编码结合了配置文件。你可以调整此处引入大模型根据摘要自动打标签的功能。

---

## 3. 🤖 GitHub Actions 自动化层 (`.github/workflows/`)

- **`daily_scheduler.yml`**: 每天北京时间 8:30 触发抓取脚本。完成后它会构建一个 commit 自动 Push 自己到 `main`。
- **`auto_archive.yml`**: 监听 Push 事件的 paths (限 `Inbox.md`)。一旦发生变动，将触发归档处理，随后用 git 把生成的 `Notes` 等文件提交上去。
- **`deploy-web.yml`**: 假设这在系统里承接使用 Vite 将 `web/` 的内容发布到 GitHub Pages 上的职能。

---

## 4. 🌐 Web 前端可视化层 (`web/`)
这是项目的可视化大屏（或门户浏览器），以单页应用形式实现对 Markdown 知识库的展示。

- **技术栈**: React (`App.tsx` / `main.tsx`) + Vite + TailwindCSS (`tailwind.config.js`) + Typescript。
- **多语言机制**: `i18n/` 文件夹暗示它支持多语言响应。
- **UI 组件**: 各类视图组件封装在 `web/src/components` 和 `web/src/views` 中。
- **读取逻辑**: 它利用当前仓库内的结构，把 GitHub Pages 当作静态文件存储。这意味着如果你在 Python 后端新增了字段或更改了 `List.md` 排列方式，你就需要在 `web/src/` 的对应解析中**同步编写新的截取逻辑**。

> [!WARNING]
> **个性化改动点**：如果你改变了 `Contents.md` 组织大纲的 H2 / H3 书写结构，必须去 `web/src/App.tsx` 或关联的数据解析库（如 `lib/`）中更新您的前台渲染器。

---

## 5. 🧠 Agent (扩展技能模块区)
`agent/` 目录中保留着众多预构建的自动化子系统：
- **DocumentProcessing**: 文件处理（MarkItDown等）。
- **CorePipeline**: 系统化综述、科研规范排版写作（Mermaid / tex）。
- **Metadata & Retrieval**: 包含对 OpenAlex、PubMed 乃至大模型并联接口的支持。

当前阶段，这些 Skill **被独立解耦设计为主流程之外**，作为未来可组装的工作流插件。您可以很方便地运用您的 Agent 代码经验，将这里的逻辑串联进入 `process_inbox.py`，实现诸如“归档论文时自动提取核心图表或翻译摘要”的工作流程进阶。
