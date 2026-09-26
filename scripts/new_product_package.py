#!/usr/bin/env python3
"""生成新产品专利交付包骨架（五段子目录 + 包 README + 四份底稿）。
用法: python3 new_product_package.py <产品代号> <输出父目录>
· 检索_<产品>.md：文件名带"检索"，verify_search_report.py 传包目录即可自动挑到（V1–V3）。
· 04_EVT验证/EVT_<产品>.md：E1–E4 的载体，投产总则从 check_iron_rules import 同一份常量，
  不在这里重抄一遍——重抄的那份迟早和判据漂移。
· 05_法规与裁决/法规_<产品>.md：G1–G5 的载体（适用性判定/逐条映射/缺口/送检/裁决五张表）。
· 03_设计补全/补全_<产品>.md：K1–K4 的载体，四张表的表头由 check_design_completion.SPECS 生成。
"""
import importlib.util as _ilu
import os, sys

_S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_c = _load('check_iron_rules')
_dc = _load('check_design_completion')
PRODUCTION_CLAUSE = _c.PRODUCTION_CLAUSE

README = """# {name} 专利交付包

打包日期：____｜内容：__ 件专利的技术交底书 + CNIPA 申请文件草稿 + 附图/视图

## 专利清单
| 编号 | 类型 | 名称 | 附图/视图 | 定位 |
|---|---|---|---|---|

## 目录
- `01_交底书/`：交底书/交底材料（md+docx）
- `02_申请文件/`：CNIPA 格式申请文件草稿 + figures/（白底黑线，PIL 彩色像素=0）
- `03_设计补全/`：缺失机构设计补全文档（决策依据+约束条件）
- `04_EVT验证/`：EVT 分析报告（分析级；物理实测清单全部 Not Run）
- `05_法规与裁决/`：法规适用性分析 + 冲突裁决书

## 提交前须知
1. 同包各件同日提交；务必早于产品公开发售/展会公开。
2. 数值口径：以处置表裁决值为准，全部带版本/状态标注。
3. 投产门禁：任何设计内容在对应物理实测全部通过前不得投产。
"""

# S2 的产出物在包里需要一个载体，否则"已核验条目"散落在代理会话里、
# R5 的 --search-report 也没有规范路径可指。表头即 templates §10 的列名。
SEARCH = """# {name} 检索报告

## 1. 检索式与数据源
- 数据源：【待填写】
- 检索式：【待填写】
- 检索日期：【待填写】

## 2. 已核验条目
| # | 类型 | 标识符 | 标题 | 关键日期 | 核验出处 | 核验日期 |
|---|---|---|---|---|---|---|

## 3. 未检出声明
本轮检索未检出与交底书 §2.2 每条缺陷逐条对应的在先方案；未检索到 ≠ 不存在。
"""

# 结构照 templates §5 的五节；两张表都只给表头不给行，
# 因为 E1/E3 认的是"有判定列的表"，空表在骨架期合法（有行没填才会红）。
EVT = """# {name} EVT 分析报告（分析级；不含物理实测数据）

## 1. 验证总表
| # | 设计项 | 验证方法 | 分析结论 | 物理实测项 | 判定 |
|---|---|---|---|---|---|

## 2. 逐项详细验证
（验证项目 → 方法 → 结果含可复算过程 → 结论 → 判定 → 投产判定）

## 3. 冲突项验证处置
（分析证据 + 裁决建议；证据不足则"维持冻结值，转 EVT 实测裁决"）

## 4. 物理实测总清单
| # | 测试 | 工装 | 样本量 | 合格判据 | 预测值 | 状态 |
|---|---|---|---|---|---|---|

## 5. 投产判定
{clause}
"""

# 05 段同样需要载体：G1–G5 读的是表，规程 §4/§5 要求裁决与判定以表落地。
# 五张表都只给表头不给行——空表在骨架期是"未判"，填了行才会被判红（列名与
# templates 的法规/裁决文书格式节同源）。
REG = """# {name} 法规适用性与冲突裁决

## 1. 适用性判定
| 标准/法规 | 判定 | 依据 |
|---|---|---|

## 2. 逐条映射
| 条款 | 要求 | 结论 |
|---|---|---|

## 3. 合规缺口清单
| 编号 | 缺口 | 修订建议 | 实测规程 |
|---|---|---|---|

## 4. 送检包清单
| 项目 | 费用 | 周期 |
|---|---|---|

## 5. 裁决总表
| 冲突项 | 结论 | 依据 | 约束 | 生效范围 |
|---|---|---|---|---|
"""


def design_doc(name):
    """03_设计补全 底稿：四张表的表头逐字取自 check_design_completion.SPECS。
    在这里重抄一遍列名，就等于给"模板改了、判据没改"留一条活路——K 门禁会照常绿。"""
    parts = [f'# {name} 缺失机构补全登记与设计决策\n',
             '（骨架期四张表都只有表头：K1–K4 报"未判"而不是判红，填了行才会被判。）\n']
    for title, tag in _dc.DOC_SECTIONS:
        parts.append(f'## {title}\n{_dc.header_row(tag)}\n{_dc.separator_row(tag)}\n')
    return '\n'.join(parts)


def main(name, parent):
    root = os.path.join(parent, f'{name}_专利交付包')
    for d in ['01_交底书','02_申请文件','03_设计补全','04_EVT验证','05_法规与裁决']:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    with open(os.path.join(root, 'README.md'), 'w', encoding='utf8') as f:
        f.write(README.format(name=name))
    with open(os.path.join(root, f'检索_{name}.md'), 'w', encoding='utf8') as f:
        f.write(SEARCH.format(name=name))
    evt = os.path.join(root, '04_EVT验证')
    with open(os.path.join(evt, f'EVT_{name}.md'), 'w', encoding='utf8') as f:
        f.write(EVT.format(name=name, clause=PRODUCTION_CLAUSE))
    reg_dir = os.path.join(root, '05_法规与裁决')
    with open(os.path.join(reg_dir, f'法规_{name}.md'), 'w', encoding='utf8') as f:
        f.write(REG.format(name=name))
    dc_dir = os.path.join(root, '03_设计补全')
    with open(os.path.join(dc_dir, f'补全_{name}.md'), 'w', encoding='utf8') as f:
        f.write(design_doc(name))
    print('created', root)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
