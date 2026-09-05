---
name: patent-pack-pipeline
description: >
  产品专利交付包全流程流水线：从工程素材到可提交代理机构的全套专利文书。覆盖技术特征提取、现有技术排查（含 FTO）、参数矛盾/缺失处置、专利地图布局、技术交底书撰写（发明/实用新型/外观设计）、代码绘制专利线条附图、CNIPA 申请文件组装、多轮独立审查、缺失机构的设计补全（运动学/结构/电气）、EVT 分析级工程验证（含公开数据集实证第三验证层）、法规适用性分析、冲突裁决与打包交付；查新方法纪律（两段式召回-分类号收口+保底规则，吸收自 handsomestWei/patent-disclosure-skill）与案件边界收敛 intake；含配套论文产线（专利+论文双产出，三层信息分离：公开数据集验证/合成样本验证/预测口径）、格式零差异申报文书重构（叙述表单+官方表格模板填充法+经费勾稽）、执行就绪包模式（测试 SOP/拿来即签模板/单页填报表/申报直交通道）与外部技能插件编排图谱（scholar/pubmed/materials_project/igo_open_data/sci-paper-cn/research-writer/research-paper-refiner/research-advisor/deep-probe/weighted-scoring/chart-gen 等的阶段化调用与回退）。当用户要求为产品申请专利、制作技术交底书/专利交付包/申报书、做专利挖掘布局、进行现有技术/FTO 排查、要求"设计补全缺失机构/执行 EVT 验证/法规评审"、专利论文同步产出、或把申报材料做到"填名即报"程度时使用。适用于消费/工业硬件产品（含外骨骼、背带、机电产品、训练机器人）与科技项目申报。不适用于纯软件方法专利的代理撰写、正式法律意见或向 CNIPA 的实际提交动作。
---

# 专利交付包流水线（patent-pack-pipeline）

## 铁律（任何阶段不可违反）

1. **零虚构**：任何未在素材/已核验检索中出现的数值、结构、文献、测试结果一律不得写成事实；缺失机构按"设计补全"流程补齐（见 references/design-completion.md），严禁以占位冒充已确认结构。
2. **引用纪律**：背景技术/现有技术只允许引用检索报告中已核验条目（专利号逐字核对）；检索报告外的公开号禁止出现；"未检索到≠不存在"，统一写"本轮检索未检出……，正式申请前以全库查新为准"。
3. **防御性措辞**：禁"首次/填补空白/国际领先/首创/国际先进"；差异化写"与 X（公开号）相比区别在于……（可核验事实）"。
4. **商标禁令**：发明名称、权要、正文不出现产品型号/商标（统一用通用名）。
5. **时序铁律**：同产品包各件建议同日提交；务必早于产品公开发售/展会公开/论文投稿。

## 流水线总览（阶段不可合并、各有质量门禁）

```
S0 素材评估与渲染 → S1 技术特征提取 → S2 现有技术排查（含FTO） → S2.5 矛盾/缺失处置表
→ S3 专利地图（默认最大化，见下） → S4 交底书撰写（并行写手） → S5 独立审查+修订
→ S6 附图+申请文件（并行） → S7 二轮审查+修订 → S8 打包交付
→ S9 设计补全（缺失机构） → S10 集成回写 → S11 EVT 分析级验证+更正
→ S12 法规适用性分析+冲突裁决 → S13 收口交付
```

- **默认规则（本项目方已确认）**：专利地图取最大化方案（不问件数）；缺失机构默认设计补全而非占位；遇到的问题先处置再往下执行；设计内容不加 AI 来源标注、不写"须代理人复核"类备注；每项关键设计决策给出依据+约束条件；允许与冻结参数冲突但须显式登记。
- 各阶段详细程序：读 `references/pipeline-stages.md`。
- 各文书模板（交底书 §0–§8/申请文件/处置表/登记表/EVT 报告/决策卡）：读 `references/templates.md`。
- 硬规则细则（权要写法/实用新型纯结构/防御性划界/占位判定树/权要数值口径与算术自洽/25 条客体锚点）：读 `references/hard-rules.md`。
- 设计补全方法与 EVT/法规评审规程：读 `references/design-completion.md` 与 `references/evt-and-regulatory.md`。
- **配套论文产线**（专利+论文双产出：骨架稿/完整稿预测口径决策、论文结构、时序铁律）：读 `references/companion-papers.md`。
- 工具与环境陷阱（pandoc locale、像素扫描、修订波后图片复扫、zip 同步时机、脆文件系统对策）：读 `references/tooling-pitfalls.md`，并优先使用 `scripts/` 下已验证脚本。
- **外部技能与插件编排**（scholar/pubmed/materials_project/igo_open_data/sci-paper-cn/research-writer/research-paper-refiner/research-advisor/deep-probe/weighted-scoring/chart-gen/image_generation/musepool/kimi-word/kimi-pdf/kimi-excel）：读 `references/tool-orchestration.md`——各阶段调用谁、可用性探测与回退路径、渠道分层纪律。

## 关键操作纪律（低自由度，照做）

1. **多代理协作**：提取/写手/附图各阶段用并行子代理（foreground 同块并发）；审查必须独立（reviewer 只审不改）；修订派 fix 代理（不内联修补他人稿件）；审查轮次不可跳过（两轮：交底书轮+申请文件轮）。
2. **附图**：代码绘制（matplotlib）白底黑线；彩色像素=0（用 `scripts/check_figures.py` 强制）；阿拉伯数字标记+引线，同部件跨图同号；dpi≥200、图宽 14–16cm；不嵌图题；附图标记说明对照表必备。
3. **docx 转换**：一律 `LC_ALL=C.utf8 LANG=C.utf8 pandoc`（POSIX locale 丢中文路径图片）；批量转换与验证用 `scripts/regen_docx.py`；转后必须 python-docx 验证+`unzip -l` 核对媒体数=附图数。
4. **打包**：包结构固定为 `README.md + 01_交底书/ + 02_申请文件/ + 03_设计补全/ + 04_EVT验证/ + 05_法规与裁决/`（可用 `scripts/new_product_package.py` 生成骨架）；zip 重建后必须做"目录↔zip 全文件比对"（`scripts/rebuild_package.py` 自带）；脆文件系统环境下禁止长链 glob 拷贝，逐目录拷贝+哈希核验。
5. **EVT 诚实边界**：分析/仿真验证可执行；物理实测严禁编造——输出测试规程+预测值+判据+"待物理实测"；投产总则逐字写入报告："任何设计内容在对应物理实测全部通过前不得进入投产阶段；分析验证结论不构成投产依据"。
