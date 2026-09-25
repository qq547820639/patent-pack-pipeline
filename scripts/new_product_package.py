#!/usr/bin/env python3
"""生成新产品专利交付包骨架（五段子目录 + 包 README + 检索报告底稿）。
用法: python3 new_product_package.py <产品代号> <输出父目录>
底稿文件名带"检索"，因此 verify_search_report.py 传包目录即可自动挑到它。
"""
import os, sys

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

def main(name, parent):
    root = os.path.join(parent, f'{name}_专利交付包')
    for d in ['01_交底书','02_申请文件','03_设计补全','04_EVT验证','05_法规与裁决']:
        os.makedirs(os.path.join(root, d), exist_ok=True)
    with open(os.path.join(root, 'README.md'), 'w', encoding='utf8') as f:
        f.write(README.format(name=name))
    with open(os.path.join(root, f'检索_{name}.md'), 'w', encoding='utf8') as f:
        f.write(SEARCH.format(name=name))
    print('created', root)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
