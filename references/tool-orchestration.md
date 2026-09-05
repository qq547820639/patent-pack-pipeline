# 技能与插件编排图谱（外部能力调用规则）

> 本图谱规定流水线各阶段可调用的外部技能/插件、用途、可用性检查与回退路径。**总原则：优先用指定技能/插件；调用前做可用性探测，失败立即回退到通用通道（web_search / CrossRef API / arXiv API / 代码自绘），并在交付记录中注明实际通道。**

## 目录
检索与核验类｜写作与评审类｜数据与统计类｜图表与设计类｜文档产物类｜外部技能库｜可用性纪律

---

## 1. 检索与核验类

| 技能/插件 | 调用阶段 | 用途 | 可用性与回退 |
|---|---|---|---|
| **yuandian_law 插件（元典法律数据库）** | S12 法规适用性分析 | 中国大陆法律/法规/司法解释/案例的语义+关键词检索与效力核验 | 法规适用性分析的中国法规主通道；仅覆盖中国大陆法域 |
| **legal:legal-research 技能** | S12 | 法条效力核验、类案检索、域外法律 | 与 yuandian_law 互补 |
| **tianyancha 插件（天眼查）** | S2/FTO | **专利权人工商实体核查**——专利登记主体不明时按工商主体名补查（如"虎贝尔"类品牌 vs 登记公司名不一致场景）、竞品企业工商/知识产权/司法信息 | 企业信息仅作情报，不作法律结论 |
| **CNIPA 著录检索工具**（外部仓库 handsomestWei/patent-disclosure-skill 的 patent-search 包，Playwright） | S2/FTO | CNIPA 公布公告高级查询（发明人/申请人/分类号/名称字段） | **本环境 epub.cnipa.gov.cn 不可达（2026-09-04 实测超时）**——在 CNIPA 可达环境直接复用；不可达时回退 web_search+二手库并声明局限 |
| **scholar 插件** | S2 现有技术排查、论文引用池 | 学术论文检索（标题/作者/摘要/引用数/年份）、作者画像 | **本环境曾不可达（serper.dev 连接失败）——调用前先用一条探测查询验证；失败立即回退 CrossRef API / arXiv API / web_search，并在排查报告中注明实际通道** |
| **pubmed 插件** | S2（生物医学/康复/临床方向） | PubMed/PMC 文献检索与元数据、OA 全文获取 | 仅生物医学域可用；跨域（机器人/材料）回退 CrossRef/web_search |
| **CrossRef API** | S2 全程 | DOI 核验（`curl -s "https://api.crossref.org/works?query=..."`） | 默认通道，零依赖 |
| **arXiv API** | S2 | 预印本核验 | 预印本条目必须标"预印本" |
| **web_search / web_open_url** | S2、FTO、竞品、法规 | 专利号/产品/价格/标准核实 | 无直接专利库权限时的主通道；CNIPA/Espacenet 不可达时如实声明局限 |

## 2. 写作与评审类

| 技能 | 调用阶段 | 用途 | 可用性与回退 |
|---|---|---|---|
| **sci-paper-cn** | 论文成稿 | 论文结构与成稿规范（分章节起草、图表、叙事逻辑、投稿前打磨） | 结构约束以本 skill 的 companion-papers 为准，冲突时以项目纪律（零虚构/三层信息分离）优先 |
| **research-writer** | 论文成稿 | 大纲协作、逐节反馈、引用管理、迭代打磨 | 用于论文写作过程管理 |
| **research-paper-refiner** | 英文稿/英文摘要 | 学术英语五维审查（语法/用词/语态/衔接/句式）与润色 | 中文稿定稿后英文版或英文摘要必过此关 |
| **research-advisor** | 选题与方案评审 | 研究选题构思、风险评估矩阵、决策树（Fischbach & Walsh 框架） | 用于选题决策的独立第二视角 |
| **deep-probe** | 设计评审 | 对设计方案连环追问、逐分支压力测试直至共识 | 一次只问一个问题；配合独立 reviewer 使用，不替代 reviewer |
| **cross-examine**（内置技能） | 设计评审 | 交叉质询（与 deep-probe 互补：deep-probe 逐分支追问、cross-examine 横向对质） | 二者配合覆盖设计评审两轴 |
| **academic-paper-reviewer / paper-review-coach / scholarly-writing-refiner**（内置技能） | 论文成稿后 | 论文同行评审模拟、审稿视角辅导、学术写作打磨 | 投稿前最后一轮模拟审稿 |
| **weighted-scoring** | 量化决策 | 多准则加权评分模型（如指南方向 100 分制适配度评分） | 权重须任务书给定或显式声明依据；评分过程留痕可复核 |
| **auto-stat-test / auto-hypothesis-test**（内置技能） | 论文实验设计 | 统计检验自动选型、假设检验方案 | 论文统计方法与样本量论证时使用 |
| **dataset-quality-audit / dataset-health-audit**（内置技能） | 数据集构建 | 数据集质量/健康度审计 | 数据集类交付物的验收层 |
| **compliance-review-planner / regulatory-audit-generator / legal-risk-analyzer**（内置技能） | S12 合规评审 | 合规评审计划、监管审计生成、法律风险分析 | 与法规适用性分析配合使用 |

## 3. 数据与统计类

| 插件 | 调用阶段 | 用途 | 可用性与回退 |
|---|---|---|---|
| **materials_project** | S2.5/S9 材料选型（无机材料） | DFT 带隙、热力学稳定性（energy above hull）、密度、晶体对称性、按元素/化学式/性质窗口筛选 | **仅无机晶体材料**；工程金属/聚合物（TPU、PP、铝合金等）回退 web_search 查数据手册（TDS） |
| **igo_open_data** | 背景论证/考核基准 | WHO/Eurostat/ECB/OECD/FRED/UNICEF 官方统计（患病率、卫生资源、宏观指标） | 需要官方统计佐证时用；无对应指标时回退文献口径 |
| **data-aggregator-mcp**（外部 MCP：musharna/data-aggregator-mcp，2026-09-04 评估 awesome-mcp-servers 吸收） | EVT 公开数据集实证层 | 跨 Zenodo/DataCite/Figshare/Dataverse/OSF/NCBI（GEO/SRA）/PubMed/OpenAIRE 的研究数据集聚合检索+DOI 去重+校验和下载——公开数据集发现的主通道 | 安装 `uvx data-aggregator-mcp`；不可达时回退 web_search 定向检索 Figshare/Zenodo |
| **TimesFM（google-research）** | ~~时序预测~~ | **拒绝纳入（2026-09-04 评估）**：3.0 权重为非商用许可（timesfm-non-commercial-license-v1.0，与产品商业属性冲突）；HF 本环境不可达；≤2.5 为 Apache-2.0 留作备选记录 | 时序预测需求（负荷/疲劳趋势）用自训模型或统计方法 |

## 4. 图表与设计类

| 技能/插件 | 调用阶段 | 用途 | 可用性与回退 |
|---|---|---|---|
| **chart-gen** | 论文/报告数据图 | 数据图表生成 | 仅用于论文/报告插图；**专利附图一律 matplotlib 代码手绘线条图（白底黑线、PIL 扫描彩色像素=0），禁止 AI 生成** |
| **image_generation** | 封面/示意图/展示图 | AI 文生图（产品氛围图、展示海报） | 同上——不得用于专利附图；输出需人工核查不含有歧义结构 |
| **musepool** | 网页/演示设计 | 设计灵感库，避免默认 AI 美学 | 仅用于 HTML/演示类产物的设计参考 |

## 5. 文档产物类（按交付格式选择）

| 插件 | 调用阶段 | 用途 |
|---|---|---|
| **kimi-word** | docx 创建/编辑/修复 | Word 文档创建、原位编辑、批注修订、格式校验修复（表格模板填充法的首选工具） |
| **kimi-pdf** | PDF 产物 | PDF 报告/论文创建与处理（公式、图表、引用、合并拆分） |
| **kimi-excel** | xlsx/csv 产物 | 电子表格创建分析、公式驱动、图表、条件格式（BOM 成本表/考核指标表/预算表的首选） |
| **scholar-sidekick-mcp**（外部 MCP：mlava/scholar-sidekick-mcp，2026-09-04 吸收） | 论文参考文献 | 标识符（DOI/PMID/arXiv 等）→CSL JSON、10000+ 引文样式（含 GB/T 7714 类）格式化、批量导出 BibTeX/RIS | 安装 `npx -y scholar-sidekick-mcp`；不可达时用文献底稿的手工著录格式 |
| **viznoir**（外部 MCP：kimimgo/viznoir，2026-09-04 吸收，备用） | EVT 仿真可视化 | CFD/FEA/SPH 科学可视化（OpenFOAM/VTK/CGNS 渲染/切片/云图/动画） | 流场/结构仿真可视化需求出现时才启用 |

## 6. 外部技能库：scientific-agent-skills（K-Dense，163 技能，2026-09-04 评估）

**仓库**：`github.com/K-Dense-AI/scientific-agent-skills`（MIT 许可；**各子技能许可各异，用前核对 SKILL.md 的 license 字段**；数据库类依赖网络可达性；官方建议做安全扫描 `skill-scanner scan`）。
**安装**（需要时才装，勿全量装）：`npx skills add K-Dense-AI/scientific-agent-skills` 或 `gh skill install K-Dense-AI/scientific-agent-skills <skill名>`。

**与本流水线相关的高价值子集**（其余生物医学/基因组学技能与本领域无关）：

| 子技能 | 补本流水线哪一环 |
|---|---|
| paper-lookup（PubMed/arXiv/OpenAlex/Crossref 等 10 库）+ literature-review + paperclip（全文语料） | S2 学术排查通道扩容 |
| scientific-writing（证据可溯写作）+ peer-review（本地保密模拟审稿）+ citation-management / pyzotero | 论文产线写作与投稿前模拟审稿 |
| regulatory-standards（ISO 13485/14971/17025/15189 就绪证据）+ analytical-method-validation（ICH Q2/USP/CLSI） | **S12 法规适用性分析**（医疗器械/康复产品标准映射的现成技能） |
| uncertainty-units（GUM 不确定度预算）+ statistical-power（样本量）+ experimental-design（DOE） | EVT 公差/不确定度分析、测试样本量论证 |
| database-lookup（78 库**含 USPTO**） | FTO 美国专利通道 |
| pymoo（多目标优化）+ aeon（时序）+ shap + scikit-learn | 设计补全的优化算法（HITL 在线优化备选） |

**吸收的工程纪律**：凡带 scripts/ 的技能必须带 tests/ 测试套件（本 skill 自 v6 起执行，见 scripts 旁 tests/）。

## 7. 可用性纪律（强制）

1. **先探测后调用**：任何插件首次调用前做一条最小探测请求；失败立即回退并在交付记录写明实际通道（如"scholar 不可达，已用 CrossRef 核验"）。
2. **渠道分层**：官方/原厂（S 级）> 数据库/API（A 级）> 权威媒体（B 级）> 聚合站（C 级，仅作参考锚点并标注）。
3. **不回退零虚构**：任何通道不可用都不得编造来源——写"本轮检索未检出"。
