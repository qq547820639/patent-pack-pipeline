#!/usr/bin/env python3
"""生成新产品专利交付包骨架（五段子目录 + 包 README + 六份底稿）。
用法: python3 new_product_package.py <产品代号> <输出父目录>
· 检索_<产品>.md：文件名带"检索"，verify_search_report.py 传包目录即可自动挑到（V1–V3）。
· 01_交底书/交底书_<产品>.md：templates §1 的 §0–§8 结构，其中 §0 那一行 `- 发明名称：`
  是 R7（字数两根轴）与 R15（含糊词／纯笼统两支用词禁令）的**唯一适用域**——从前骨架不写它，
  这两把尺子在生产交付面上走的是"未核"，射程为零；写法由 check_iron_rules.title_field() 给出，
  与判据的 TITLE_FIELD 同源，不在这里另抄一份字面。
· 02_申请文件/说明书_<产品>.md：N1–N4 的载体，附图说明节 + 图中标记说明三列表，
  表头由 check_figure_labels.COLS 生成。
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
_nl = _load('check_figure_labels')
_cft = _load('check_figure_text')        # 摘要附图那一节的节名由 T8 那一侧持有，这里不另抄字面
_rp = _load('rebuild_package')          # P5–P7 的判据侧持有五段清单，这里不另抄一份
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


# 01_交底书 底稿：结构与节名照 references/templates.md §1 的 §0–§8（标题照用、顺序固定）。
# 这一份的存在理由是 §0 那一行 `- 发明名称：`：R7（字数两根轴）与 R15（含糊词／纯笼统两支
# 用词禁令）只判这一个字段，而从前骨架根本不写它——第 44 轮实测 348 份语料里带这行的只有
# 模板自述行与长度夹具，两把尺子在生产交付包上永远走"未核"，射程为零。写法取自
# check_iron_rules.title_field()（与判据的 TITLE_FIELD 同源），查新声明取自
# check_iron_rules.NOVELTY_CLAUSE（R9 的逐字串），附图说明那行提示取自
# check_figure_labels.DOC_SECTIONS——三处都不在这里重抄第二份。
# 三态照旧不折叠：§2 有背景技术节 ⇒ R9 要那句逐字声明（所以这里真带上它）；
# §4 有附图说明节但交底书不是说明书、也不提对照表 ⇒ N1 对它报"未判"而不是判红；
# §6 有权利要求建议稿节而骨架期无权项 ⇒ Q 族走"有节却无项"那一档。
# 占位发明名称取「一种腰部助力外骨骼装置」（12 字，设备级），不取「躯干框架／锁扣」那一族：
#   · 后者在本仓是**部件名**（对照表里的 1=躯干框架、2=锁扣本体），拿部件名当 §0 的
#     整案名称会把一件产品写成它的零件，示范的是错的粒度；
#   · 本仓唯一的示例产品就是这款腰部助力外骨骼（README §2 与生产夹具 E2E 同一件案），
#     设备级名字与它的技术领域／实施方式占位互相咬合，不会自相矛盾；
#   · 这个字面已在常驻档 `test_new_product_package` 里被真判据判过"合规发明名称"（R7 静默），
#     12 字离 25 字软上限还有余量；删尽 §4.1.1 点名的四个笼统词与填充字后剩
#     「腰部助力外骨骼」⇒ R15 两支都不开火；不含含糊词、不含商标／型号形态（R6 不误伤）、
#     不带方括号占位（R2b）、无绝对化措辞（R1）。
DISCLOSURE_TITLE = '一种腰部助力外骨骼装置'

# 摘要占位里必须出现本案发明名称——§4.5.1 逐字「摘要文字部分应当写明发明的名称」，
# 判据 R18 读的就是这一件事。名称与 §0 那一行同一个源（DISCLOSURE_TITLE），
# 两处各写一份迟早对不上——与 #27 把 `- 发明名称：` 那行的写法收到判据侧是同一条纪律。
ABSTRACT_SEED = ('本案发明名称为「' + DISCLOSURE_TITLE + '」；'
                 '【待填写：技术方案要点与主要用途，含标点控制在三百字以内】')

DISCLOSURE = """# {name} 专利技术交底书

（骨架期各节只给结构与占位：内容取自产品定义与检索报告，填了行与句子才谈得上判。）

## 0. 著录项目（建议稿）
   - 专利类型：【待填写：发明专利／实用新型专利】
{title}
   （上一行是骨架期占位名，提交前替换为本案名称；替换后字数与用词都要重新核一遍。）
   - 申请人（建议）：【待填写】；发明人：【待填写】
   - 建议申请时序：与同产品包各件同日提交；务必早于任何产品公开发售/论文投稿

## 1. 技术领域
【待填写：本案所属的直接技术领域，写到该大类下的具体分支】

## 2. 背景技术
   2.1 现有技术现状【待填写：只允许引用检索报告已核验条目，逐条注明出处】
   2.2 现有技术的缺陷【待填写：每条须能被 3.1 的技术问题正面回应】
{novelty}

## 3. 发明内容
   3.1 技术问题【待填写：对应 2.2 列出的缺陷】
   3.2 技术方案【待填写：独立权利要求的全部必要技术特征】
   3.3 有益效果【待填写：逐条可追溯到 3.2 的特征】

## 4. 附图说明
{fig_hint}

## 5. 具体实施方式
【待填写：至少一个完整实施例，参数具体可复现；未知处保留占位符】

## 6. 权利要求建议稿
【待填写：一项独立权利要求加若干从属权利要求，逐条编号顺排】

## 7. 摘要建议稿
{abstract_seed}

## 8. 检索关键词与 IPC 分类建议
【待填写：检索关键词与分类号建议】
"""


def disclosure_doc(name):
    """01_交底书 底稿：§0–§8 的节名与顺序照 templates §1，三句逐字串全部取自判据侧。
    发明名称那一行由 check_iron_rules.title_field() 拼——写宽或写窄一分，R7／R15
    就在这份生产文书上看不见它，所以字面不在这里出现第二次。"""
    fig_hint = dict(_nl.DOC_SECTIONS)['附图说明']
    return DISCLOSURE.format(name=name, abstract_seed=ABSTRACT_SEED,
                             title=_c.title_field(DISCLOSURE_TITLE),
                             novelty=_c.NOVELTY_CLAUSE,
                             fig_hint=fig_hint)


def design_doc(name):
    """03_设计补全 底稿：四张表的表头逐字取自 check_design_completion.SPECS。
    在这里重抄一遍列名，就等于给"模板改了、判据没改"留一条活路——K 门禁会照常绿。"""
    parts = [f'# {name} 缺失机构补全登记与设计决策\n',
             '（骨架期四张表都只有表头：K1–K4 报"未判"而不是判红，填了行才会被判。）\n']
    for title, tag in _dc.DOC_SECTIONS:
        parts.append(f'## {title}\n{_dc.header_row(tag)}\n{_dc.separator_row(tag)}\n')
    return '\n'.join(parts)


def spec_doc(name):
    """02_申请文件 说明书底稿：小节名与对照表表头都取自判据侧常量。
    判据 N1 要的是"有附图说明节就必须有三列对照表"，这张表若在这里手抄一遍，
    列名漂移时判据照绿、底稿照错——正是要防的那种漂移。"""
    # §4.2 要求说明书第一页第一行就写本案发明名称（判据 R16），而骨架期的名称占位
    # 只有一个来源：`DISCLOSURE_TITLE`——交底书 §0 那一行也是它，两处各写一份迟早不一致。
    parts = [f'# {DISCLOSURE_TITLE}\n',
             '（骨架期对照表只有表头：N2–N4 报"未判"而不是判红，填了行才会被判。）\n']
    # 三件应提交的文书先立节、内容留占位：节名由判据侧 rebuild_package.APPLY_SECTIONS 持有，
    # 生成器另抄一份节名就是给"P10 绿而骨架没那节"这种漂移留活路。
    for s in _rp.APPLY_SECTIONS:
        # 摘要那一件要带上本案名称（判据 R18 读的就是"摘要里有没有写明发明名称"），
        # 另外两件留通用占位——与背景技术那节带上 R9 逐字声明是同一类"节内容跟着判据走"。
        if s == '说明书摘要':
            parts.append(f'## {s}\n{ABSTRACT_SEED}')
            # 摘要附图那一节紧接摘要之后（templates §2 的顺序）：指南 §4.5.2 要"说明书有附图的
            # 应当指定其中一幅"，而骨架期一张图都还没有，所以这里**只立节不给号**——给了号
            # T8 就当场判红自家骨架（指定的号根本不在附图里），不给号它走"未判"并点名成因。
            parts.append(f'## {_cft.ABSTRACT_FIG_SECTION}\n'
                         '【待填写：有附图的案在此写明图号，并在请求书中同步写明】')
        else:
            parts.append(f'## {s}\n【待填写：骨架期占位，取自交底书】')
    # 细则第二十条一款那五节同样由判据侧持有（P12 与生成器一份，两端各抄迟早漂）。
    # 背景技术这一节必须带上 R9 那句逐字查新声明：P12 把该节从"没有本节⇒R9 未判"
    # 变成"有节⇒R9 要句"，不带的话骨架自己就过不了铁律门禁——这是设计好的反馈，不是要绕的误伤。
    hints = dict(_nl.DOC_SECTIONS)
    for s in _rp.SPEC_SECTIONS:
        if s == '背景技术':
            parts.append('## 背景技术\n【待填写：最接近的在先技术与本案区别特征】\n'
                         + _c.NOVELTY_CLAUSE)
        elif s in hints:
            parts.append(f'## {s}\n{hints[s]}')
        else:
            parts.append(f'## {s}\n【待填写：骨架期占位，取自交底书】')
    for title, hint in _nl.DOC_SECTIONS:
        if title in _rp.SPEC_SECTIONS:
            continue                      # 附图说明 已按五节发过，重复立节会有两个同名节
        body = hint if hint else f'{_nl.header_row()}\n{_nl.separator_row()}'
        parts.append(f'## {title}\n{body}')
    return '\n'.join(parts) + '\n'


def main(name, parent):
    root = os.path.join(parent, f'{name}_专利交付包')
    for d in _rp.PKG_DIRS:      # 清单来自判据侧（P5），在这里另抄一份就是给漂移留活路
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
    fd_dir = os.path.join(root, '02_申请文件')
    with open(os.path.join(fd_dir, f'说明书_{name}.md'), 'w', encoding='utf8') as f:
        f.write(spec_doc(name))
    td_dir = os.path.join(root, '01_交底书')
    with open(os.path.join(td_dir, f'交底书_{name}.md'), 'w', encoding='utf8') as f:
        f.write(disclosure_doc(name))
    print('created', root)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
