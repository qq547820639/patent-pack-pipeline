# 平台级数字优先自主执行（master-execution）
> 适用：超大型研发任务（"能数字化的全部数字化，只把真正不可数字化的留给线下"类 MASTER 指令）。
> 来源：步行康复平台项目（178 节执行提示）实测固化。

## 1. 总则
- 约束转计算：每个抽象要求（"安全""有效""适合谁"）必须转成可计算判据+阈值+数据源，否则视为未完成定义。
- 不设人工审批 Gate：用自动质量门替代；人类行动（法律/伦理/签署/高风险人体操作）进 HUMAN ACTION QUEUE，不得阻塞数字研发。
- 执行循环：OBSERVE→ANALYZE→IMPLEMENT→TEST→VALIDATE→IMPROVE→FREEZE；禁止"方案无限循环"——方案足够明确立即实现。
- MODULE COMPLETE 六判据（缺一不可）：Implemented / Tested / Stress-Tested / Sensitivity-Tested / Documented / Offline-Test-Ready。

## 2. 证据分级与标注
- DIGITAL EVIDENCE：D0 无证据 / D1 理论 / D2 仿真 / D3 历史数据 / D4 多数据库 / D5 高鲁棒验证。
- REAL-WORLD EVIDENCE：R0–R5 另行记录；二者严禁混写。仿真≠临床、预测≠实测、算法跑通≠验证完成。
- 合成数据全程标 SYNTHETIC；假设标 ASSUMPTION 并给依据+反转条件；文献标 LITERATURE 含可核验出处。

## 3. 质量门（自动判定模式）
- 每个门定义**可执行判据**（文件存在+关键测试实跑通过+关键指标达标），写 gate_check.py 实跑出报告，不接受"文档宣称"。
- 典型门序列：研究定义→数据架构→传感模型→数字孪生稳定→训练引擎稳定→安全压测→效能指数稳定→虚拟临床收敛→线下验证包就绪。
- FAIL 处理：Root Cause→Hypothesis→Fix→Re-run→Comparison，直到 PASS 或达到明确理论边界（如实冻结并声明）。
- 实测教训：门脚本自身也会有缺陷（正则取错列/pytest 多目标传参），修复记录必须留痕；资产笔误（如计数 47 vs 实测 46）授权小修并注明。

## 4. 决策与比较纪律
- 任何需要选择的地方不默认问人：建立 Candidate A/B/C，按 Evidence/Performance/Safety/Robustness/Interpretability 比较后采用最优。
- 临床/安全相关：正式验证前默认选**可解释且安全**的候选（如规则型），ML 型外罩确定性安全层（VETO 门控），限影子/离线研究。
- Decision Log 七字段：Decision/Options/Evidence/Reason/Chosen/Confidence/Reversal Condition；重大结论标 High/Medium/Low。
- FALSIFY 优先：主动寻找反驳证据；不达标如实判（实测案例：预测模型跨队列 AUC=0.497→禁止外推；聚类不支持预设类别数→如实报告+降级方案+裁决规则）。

## 5. 数字孪生与虚拟临床（VCT）
- 虚拟队列≥1000 例，覆盖全维度+四类患者：Typical/Boundary（边界值精确落界）/Rare（合法低概率）/High-Risk（极端，仅数字探索，禁真人复现）。
- 全量 schema 校验通过；地形/场景矩阵运行无 NaN、物理量在包络内、能量残差<5%。
- VCT：对照设计+脱落（MAR）+依从稀释+噪声+异质性；100/500/1000 三规模跑收敛（点估计跨规模差、CI 宽比≈理论 √n 比、效能单调）。
- SAP 必须实跑一遍：数据源接口抽离 load_data(source)，"真实数据进入后只需 Replace Data Source"——用≥2 个异构数据源零改动跑通验证。
- 样本量：公式法+蒙特卡洛双轨（每格≥2000 reps）；脱落可被公式膨胀吸收，**依从性稀释是主侵蚀源**（实测使效能 0.90→0.84）。
- 反事实四臂（NoTx/PT/Device/PT+Device）估计增量效应；排序若由假设乘子驱动须标注"假设生成"。

## 6. 鲁棒性与消融
- 鲁棒四压：加噪声（1/2/5/10% 翻转率）/缺数据（10/20/30% 优雅降级）/延迟/错误传感器（卡死/漂移/反相）。脆弱点必须点名并加固（输入校验/置信度门控/时序检测器），加固后复测。
- "看似合法"故障（生理范围内卡死、单帧不可见）是最大风险放大器——FMEA 中探测度 D 权重最高，时序检测器可 100% 检出。
- 消融目的=识别真正必要数据（证明技术贡献），非省预算；输出模态-指标可用性矩阵与最小必要集。

## 7. 线下验证就绪包（终态判据）
- 唯一 Offline Validation Matrix（14 字段：ID/Stage/Module/Hypothesis/Digital Evidence/Physical Test/Population/Equipment/Protocol/Data/Endpoint/Pass Criterion/Safety/Failure Action）；每冻结项+每假设≥1 行；Pass Criterion 必须量化可判定；Failure Action 指回具体数字模块。
- 递进验证：台架（机械/传感/控制/安全优先，含人体放行硬门）→首次人体（仅可穿戴/基本运动/基本安全/数据质量，锁死最低档参数）→患者验证（直接验证数字预测，不重新探索）。
- 高风险边界（跌倒/极端患者/危险环境）仅台架/假人/数字队列，严禁真人剧本。
- 模型校准协议：Reality vs Prediction→预测误差→V2 更新；现实不符合预测时优先改模型，不是改事实。

## 8. 组织与主控文档
- 主控五件：Decision Log / Issue Tracker（OPEN→…→CLOSED）/ Risk Register（分类+等级+缓解+复查条件）/ Status Board（Completed/Running/Failed/Blocked/Next）/ 验收追溯矩阵（Requirement→Design→Implementation→Test→Evidence→Conclusion）。
- 验收问题证据化：每个验收问题给 直接答案+证据指针（文件+关键数字）+证据等级+缺口；证据不足的问题如实指向线下，不得硬答。
- 冻结声明模板：数字设计冻结≠临床有效性结论；逐项列 版本/证据/局限/仍可调范围；投产总则逐字写入。
