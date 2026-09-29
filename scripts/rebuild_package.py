#!/usr/bin/env python3
"""重建交付包 zip，并把"目录↔zip"比到**内容级**（脆文件系统安全模式）。
用法: python3 rebuild_package.py <包目录>   # 产出 同级 <包目录>.zip

为什么比内容而不是比名单：这工具存在的理由就是"脆文件系统会静默写坏东西"
（某次观察、未留命令：zip 重建后目录里少过 4 个文件、拷贝出现过静默部分失败。
  能被复算的那一半做成了判据：P1 字节数／P2 SHA-256／P3 CRC，由 test_rebuild_package 正反夹具钉住）。
只比相对路径集合时，某个文件被写成截断/半截而名字还在——照样读成 "fully synced"，
工具恰好在自己最该起作用的那种故障上失明。

判据（都计入退出码）：
  P1 每条条目的字节数与目录里的源文件一致；
  P2 每条条目的内容与源文件 SHA-256 逐条一致（两边都流式读，不把整包吸进内存）；
  P3 `zipfile.testzip()` 必须返回 None，即每条 CRC 都过；
  P4 全部非 ASCII 条目名必须置 UTF-8 标志位 0x800（见下方"为什么必须用 Python 写包"）。
名单不齐时仍对**交集**做内容比对：名字差集不该把截断这件事一起藏掉。
  P5 §8 固定的五段子目录都在（`PKG_DIRS`，`new_product_package.py` 生成骨架时 import 同一份清单）；
  P6 包根有 README.md 且里面有「专利清单」表；
  P7 02_申请文件 不是空目录；
  P8 「专利清单」每一行的**类型**得是三类之一（第四十四条（六）：专利申请类别（发明、实用新型
     或者外观设计）不明确或者难以确定的，不予受理）。写成【待填写】式占位走未判——占位是"还没定"，
     不是"定错了"，把它判红等于替纪律新增一条"打包时不许留占位"的要求。
  P9 列了**实用新型**的包必须找得到图。法源逐字是第四十四条（一）"发明或者实用新型专利申请缺少
     请求书、说明书（**实用新型无附图**）或者权利要求书的"——括注挂在"说明书"底下，
     意思是实用新型缺说明书附图就按"缺说明书"处理，同一档不予受理。
     图按两处找：包内任意非 0 字节的图片文件，以及任一 .docx 里的 word/media/*
     （只查 figures/ 会漏：交付物是 Word 时图活在 media 里，与 C4 同一条理由）。
P5–P12 看的是**包本身**而不是 zip：P1–P4 全绿而包里本来就缺一整段、或整包是"没附图的实用新型"，
是这两种判据的分界。P9 的判红条件刻意取最强形态（**全包一张图都没有**）——这种时候说明书附图
必然也没有；"有图但说明书没引到"那种弱形态归 T4/T5/T6，不在这里重复判。
  P10 02_申请文件 里三件齐：**说明书摘要**、**权利要求书**、**说明书**（按归一后的节名全等认，
     「说明书摘要」「说明书附图」都不与「说明书」互认）。法源两层：《专利法》第二十六条一
     "应当提交请求书、说明书及其摘要和权利要求书等文件"（三件都应提交），
     《专利法实施细则》第四十四条（一）只把缺 说明书／权利要求书 列进不予受理清单，
     摘要缺失走补正——所以三条都判红，报文里分别写各自的后果层级。md 与 docx 两通道同一套认法
     （docx 的节标题由 w:pStyle 还原成 # 行，与 N/T/Q 族同一条通道）。
  P11 清单列了**外观设计**的那一类申请件齐：02_申请文件 里要有「简要说明」这一件，
     并且包内找得到图片或者照片。法源是同一条第四十四条（一）的**后半句**（第三十轮写 §8 时
     那句被省略号切掉了，于是这一半没人看得见）："……或者外观设计专利申请缺少请求书、
     图片或者照片、简要说明的"——与发明／实用新型缺说明书**同一档：不予受理级**。
     《专利法》第二十七条一（两份留底逐字比对一致）："申请外观设计专利的，应当提交请求书、
     该外观设计的图片或者照片以及对该外观设计的简要说明等文件。"
     细则第三十一条另要求简要说明写明 名称／用途／设计要点 并指定一幅最能表明设计要点的图，
     这四要素**本轮不判红**：节里写"产品用途：…"还是"本设计用于…"是措辞问题，
     误伤面在没有真实交付包语料的本机量不出来（先例：R9 的"置于本节末尾"半条只提示不判红）。
     与 P9 的分工：全包"几张图"这件事只数一次、只报一遍——同时列了实用新型与外观设计而无图时，
  P13 「专利清单」列了外观设计、且 02_申请文件 里确实有「简要说明」这一件时，四项各有其项
     （产品名称／产品用途／设计要点／指定的图片或照片）；缺哪项点哪项。块取不出来走未判。
     判的是标签形状（房内口径，比法条更具体）：内容判不动，见 DESIGN_BRIEF_ITEMS 旁注。
  P12 说明书那**一份**里五节齐：**技术领域／背景技术／发明内容／附图说明／具体实施方式**。
     法源逐字是《专利法实施细则》第二十条一款（"说明书应当包括下列内容：（一）技术领域：写明…
     （二）背景技术：…（三）发明内容：…（四）附图说明：说明书有附图的，对各幅附图作简略说明；
     （五）具体实施方式：…"）与二款（"应当按照前款规定的方式和顺序撰写说明书，并在说明书
     每一部分前面写明标题"）⇒ 认的是**节标题**，不是正文里提到过这几个词。
     三条口径各配一条注入臂，因为它们各自都是最容易写歪的那种：
     ① 五节必须在**同一份**文书里齐——P10/P11 问"包里有这件吗"用并集，这里问"这一份齐不齐"
       要逐份看，混用会把"五节拆成五份文件"的拼盘读成合规；
     ② 「附图说明」是**条件项**（"说明书有附图的"）：只在包里有图或列了实用新型时才要，
       图数看不见（有读不动的 docx）时这一节走未判，既不硬要也不免掉；
     ③ 后果层级与 P8–P11 不同：20 条**不在** 44 条（一）那份不予受理清单里，缺节走的是
       44 条（三）"申请文件的格式不符合规定的"＝补正级，报文里明写，不许蹭不予受理那一档。
     适用域与 P10 共用 need_trio（只列外观设计的包没有说明书这件文书 ⇒ P12 出"不适用"note）；
     02_申请文件 里没有任何一份带「说明书」节时 P12 走未判（那件缺不缺由 P10 报，不重复判）。
三态：清单里没有带「类型」列的表／一条专利都没列／类型格还是【待填写】式占位／包里有读不动的
      docx ⇒ P8、P9、P11 未判（`main()` 逐行打印 note），不折成合规；
      清单里没列外观设计 ⇒ P11 不适用（连"没图"也不报，与 P9 的"没列实用新型"对偶）；
      02_申请文件 目录本身不在 ⇒ P10、P11、P12 未判（缺段已由 P5 报，不重复报成缺件）；
      一份带「说明书」节的文书都没有 ⇒ P12 未判（缺那件由 P10 报，不重复判）；只列外观设计 ⇒ P12 不适用。

退出码: 0 全过或未判 / 1 存在不符（P1–P13 任一）/ 2 输入不可用（zip 打不开等，说清成因）。
注意：必须用 Python zipfile 写包——Info-ZIP zip(1) 在本环境不写 UTF-8 标志位（0x800），
导致中文文件名在 Windows 资源管理器/部分解压软件下显示乱码。Python zipfile 对非 ASCII
文件名自动置 UTF-8 标志位，Windows/macOS/Linux 全兼容。
"""
import hashlib
import os
import subprocess
import sys
import time
import zipfile
import importlib.util as _ilu

CHUNK = 1 << 20
S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_t = _load('mdtable')                  # 专利清单按列读，读表实现由 mdtable 唯一持有
_ck = _load('check_claims')            # 专利类别清单由 Q 族一处持有，这里不抄第二份
_cir = _load('check_iron_rules')         # 文书读取（md＋docx 两通道）共用它的 read_text。
# 不用 check_claims.read_any：那一层把「读不动」直接 sys.exit(2)，而 P10 要的是
# 「这块读不动就计成未核、继续读其余文书」，不是整包不收。
IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp')
import re

# 02_申请文件 必须交出的三件（按节名认）。法源两层，别混着写：
# 《专利法》第二十六条第一句（逐字，两份源各读过一遍）："申请发明或者实用新型专利的，
# 应当提交请求书、说明书及其摘要和权利要求书等文件。"——三件都是"应当提交"；
# 《专利法实施细则》第四十四条（一）只把"缺少请求书、说明书（实用新型无附图）或者权利要求书"
# 列进不予受理清单，摘要缺失不在那一档（走补正）。所以三条都判红，但后果层级在报文里分别写。
# 节名一律**归一后全等**才认：模板 §2 里「说明书摘要」「说明书附图」「说明书」是三个并列节，
# 用"包含"会把"只写了摘要"的包读成"有说明书"。
APPLY_SECTIONS = ('说明书摘要', '权利要求书', '说明书')
# P11：外观设计那一支应交的两件里，本仓交付物里存在的只有「简要说明」
# （图片／照片由 image_count 在全包数，节名认不出来——照片不是 markdown 标题）。
# 认法与 APPLY_SECTIONS 同一条：归一后**全等**，"简要说明建议稿"不与"简要说明"互认。
DESIGN_SECTION = '简要说明'
# P13：细则第三十一条一款那四项（指南 txt:3055-3070＝PDF p87-88／印刷页 1-72，逐字见 docstring）。
# 判的是**标签形状**：法条要的是内容（名称／用途／设计要点／指定一幅最能表明设计要点的图片或照片），
# 而内容判不动——判"有没有各自一行以该事项名称打头的声明"。这是**比法条更具体的房内口径**：
# 标签齐而正文空不算这一条的事（占位符由 R2/T 族兜），漏标签才是本条要点出的那种"整项没写"。
DESIGN_BRIEF_ITEMS = (
    ('产品名称', re.compile(r'(?:产品名称|产品的名称)\s*[:：]')),
    ('产品用途', re.compile(r'(?:产品的?)?用途\s*[:：]')),
    ('设计要点', re.compile(r'设计要点\s*[:：]')),
    ('指定的图片或者照片', re.compile(r'指定[^。\n]{0,24}?(?:图片或照片|图片、照片|视图|照片)'
                                 r'|最能表明[^。\n]{0,16}?(?:图片|照片|视图)')))

# P12：细则第二十条一款列的五节，二款要求"按照前款规定的方式和顺序撰写…并在每一部分前面写明标题"
# ⇒ 判的是**节标题**（不是正文里提到这几个词），且必须在**同一份**说明书里齐。
# 「附图说明」是条件项（20 条（四）"说明书有附图的，对各幅附图作简略说明"），单独按有无图定。
# 五节名的**定义**在判据侧 check_iron_rules（R11/R10 的说明书区域与 P12 判的是同一份法条清单），
# 这里从 `_cir` 取而不是另抄一份：箭头只能 rebuild_package → check_iron_rules（本文件第 93 行
# 已经 `_cir = _load('check_iron_rules')`，反方向 `_load('rebuild_package')` 就是循环导入）。
# "同一个对象"由 tests/test_scripts.py 的 `is` 断言钉住——两份各自可改的元组迟早分叉，== 看不见。
SPEC_SECTIONS = _cir.SPEC_SECTIONS
SPEC_UNCONDITIONAL = ('技术领域', '背景技术', '发明内容', '具体实施方式')
SPEC_FIG_SECTION = '附图说明'
# 节名归一（剥尾部括注＋剥编号前缀）与铁律侧共用**同一份定义**：以前这里另抄了一遍正则，
# 于是"改一处、另一处照旧读不出"——中文编号那一式（「一、技术领域」）就是这么被拖住的。
# 现在 P12 判的五节与 R10／R11／R34 认的那些节，是同一条认法读出来的同一批节名。
head_title = _cir.head_title


def files_of(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            out.append(os.path.join(dp, f))
    return sorted(out)


def sha256_of(fp):
    h = hashlib.sha256()
    with fp:
        for chunk in iter(lambda: fp.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


# §8 固定的五段（README.md 另算，见 P6）。这张清单**由判据侧持有**：
# new_product_package.py 生成骨架时 import 它，于是"生成器写了第六段而判据不知道"这种漂移
# 从两端同时消失——和 补全表头取自 check_design_completion.SPECS、对照表表头取自
# check_figure_labels.COLS 是同一条纪律。
PKG_DIRS = ('01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决')
README_HEAD = '专利清单'


def shape_state(pkg):
    """P5–P12 包形状，返回 (违规, 未判/提示)。
    这些条不依赖 zip：zip 对得上而包本来就缺一整段，P1–P4 会全绿——那正是它们看不见的那种坏。
    txt 先给 None：README 根本不存在时下面那段读表不能拿一个没赋过值的变量当"读不出"。"""
    bad, notes, txt = [], [], None
    # declared 提到函数开头：P10 也要看它（44 条（一）把发明／实用新型与外观设计两支
    # 分写在同一项的两半句里，要件各不相同）。只在**真认出类别**时才往里加，
    # 所以"空"的含义是"还没定"，不是"定了别的一支"。
    declared = []
    for d in PKG_DIRS:
        if not os.path.isdir(os.path.join(pkg, d)):
            bad.append(f'P5 缺 §8 固定段 {d}（目录不存在，整段交付物无从谈起）')
    rd = os.path.join(pkg, 'README.md')
    if not os.path.isfile(rd):
        bad.append('P6 包根没有 README.md（§8 六件套之一）')
    else:
        try:
            with open(rd, encoding='utf8', errors='replace') as f:
                txt = f.read()
        except OSError as e:
            bad.append(f'P6 README.md 读不出，未判（不当成合规）：{e}')
            txt = None
        if txt is not None and README_HEAD not in txt:
            bad.append(f'P6 README 里没有「{README_HEAD}」表（提交前须知与清单都挂在这张表上）')
    app = os.path.join(pkg, '02_申请文件')
    if os.path.isdir(app):
        # 「一个非空文件都没有」而不是「目录里有东西」：放一个 0 字节的 说明书.md 进去
        # 照样能骗过前者——那种包打开就是空的，判据不该被一个文件名哄住。
        if not any(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(app) for f in fs):
            bad.append('P7 02_申请文件 里没有任何非空文件（要交的那一段根本没写，打包只会交出一个空壳）')

    # 02_申请文件 只走一遍：P10/P11 问"包里有这件吗"（取并集），P12 问"说明书那一份里五节齐吗"
    # （必须逐份看）。三处各写一份 walk 迟早漂，漂了的表现是同一张包在一边齐、在另一边缺。
    adocs = read_apply_docs(app)                    # None ⇒ 目录不在，那是 P5 的地盘
    if adocs is None:
        aseen, aunread = set(), []
    else:
        aunread = adocs[1]
        aseen = set()
        for _f, _s in adocs[0]:
            aseen |= _s

    # P8／P9：读「专利清单」的类型列。没表、没行、或 docx 读不动 ⇒ 未判，不折成合规。
    if txt is None:
        notes.append('P8／P9 未判：包根没有可读的 README.md，类型列与附图要求都判不起')
    else:
        header, rows = claim_rows(txt)
        if header is None:
            notes.append('P8／P9 未判：「专利清单」里没有带「类型」列的表'
                         '（P6 只核表在不在，列名对不对归这里）')
        elif not rows:
            notes.append('P8／P9 未判：「专利清单」一张专利都没列（没声明类型，'
                         '第四十四条（一）（六）两条都判不起）')
        else:
            ti = _t.col(header, '类型')
            for i, row in enumerate(rows, 1):
                cell = row[ti] if ti is not None and ti < len(row) else ''
                # 占位要先认，再认类别：底稿写的是「【待填写：发明/实用新型】」，
                # 里面真含着"发明"两个字——顺序反过来就把"还没定"读成"定了发明"（与 C5 那条
                # "不请求保护色彩"含子串是同一个文本面陷阱）。
                if '【' in cell and '】' in cell:
                    notes.append(f'P8 第 {i} 行类型还是占位「{cell}」→ 未判：'
                                 f'还没定类别，第四十四条（六）要等定了才判得动')
                    continue
                key = _ck.type_of(cell)
                if key:
                    declared.append(key)
                    continue
                if not cell.strip():
                    bad.append(f'P8 专利清单第 {i} 行没写类型（类别不明确＝第四十四条（六）不予受理级）')
                else:
                    bad.append(f'P8 专利清单第 {i} 行的类型「{cell}」不是 '
                               f'{"／".join(_ck.PATENT_TYPES)} 之一'
                               f'（第四十四条（六）：类别不明确或者难以确定＝不予受理级）')
            # "全包几张图"只数一次：P9（实用新型）与 P11（外观设计）引的是同一个事实，
            # 两处各自 os.walk 一遍再各报一遍，同一件坏会占掉两个原告（P3 同一条纪律）。
            n_img = image_count(pkg) if ({'实用新型', '外观设计'} & set(declared)) else None
            if '实用新型' in declared:
                if n_img is None:
                    notes.append('P9 未判：包里有读不动的 docx，无从确认"全包没图"（不猜）')
                elif n_img == 0:
                    bad.append('P9 专利清单列了实用新型，可全包找不到一张图'
                               '（图片文件与 docx 内嵌件都是零）——第四十四条（一）'
                               '"说明书（实用新型无附图）"按缺说明书处理，不予受理级')
            # P13：这一件在，不等于四项齐——细则第三十一条一款列了名称／用途／设计要点／
            # 指定一幅最能表明设计要点的图片或照片四项，缺哪项点哪项。
            # 取不到块（节名认得出但块起点找不到，例如只写成一级标题）走未判，不折成"四项全缺"：
            # 那是判据读不动，不是文书没写。
            # 第 48 轮把这一支从 P11 那个 `if '外观设计' in declared:` 里提出来各立一支：
            # 两条规则法源不同（P11 管"这一件交没交"＝第四十四条（一）后段与法 27 条一，
            # P13 管"四项齐不齐"＝细则 31 条一款），同骑一个守卫时电池里"只关 P11"的臂
            # 会把 P13 一起关掉，先红的是 P13 的原告——看着像红因不对，其实是守卫没分开。
            if adocs is not None and '外观设计' in declared and DESIGN_SECTION in aseen:
                for bf, bset in adocs[0]:
                    if DESIGN_SECTION not in bset:
                        continue
                    bstart, bbody = _cir.section_body(
                        adocs[2].get(bf, '').splitlines(), _cir.BRIEF_DESC_HEAD)
                    if bstart is None:
                        notes.append(f'P13 未判：{bf} 里「{DESIGN_SECTION}」这一节的块取不出来'
                                     '（节名认得出、块起点找不到——不猜正文）')
                        continue
                    btxt = '\n'.join(bbody)
                    miss = [lab for lab, rex in DESIGN_BRIEF_ITEMS if not rex.search(btxt)]
                    if miss:
                        bad.append(f'P13 {bf}：「{DESIGN_SECTION}」缺 {len(miss)} 项：'
                                   + '／'.join(miss)
                                   + '——细则第三十一条一款那四项（产品名称／产品用途／设计要点／'
                                     '指定一幅最能表明设计要点的图片或者照片），'
                                     '指南 txt:3055-3070 逐字；判的是标签形状，见 DESIGN_BRIEF_ITEMS 旁注')
            if '外观设计' in declared:
                if adocs is None:
                    notes.append('P11 未判：02_申请文件 目录本身不在（缺段已由 P5 报，'
                                 '这里不重复报成缺件）')
                else:
                    if DESIGN_SECTION not in aseen:
                        bad.append(f'P11 02_申请文件 里找不到「{DESIGN_SECTION}」节'
                                   '（md 与 docx 两通道都读过了）——第四十四条（一）后段'
                                   '"外观设计专利申请缺少请求书、图片或者照片、简要说明的"，'
                                   '不予受理级；专利法第二十七条一也列了它')
                    if aunread:
                        notes.append(f'P11 未核：{len(aunread)} 份文书读不动（{"、".join(aunread[:3])}），'
                                     f'{DESIGN_SECTION}这条不能替它们担保')
                    if n_img is None:
                        if '实用新型' not in declared:
                            notes.append('P11 未判：包里有读不动的 docx，'
                                         '无从确认"外观设计的图没交"（不猜）')
                    elif n_img == 0:
                        if '实用新型' in declared:
                            notes.append('P11 的"没图"这一半已由 P9 报出（同一件事实：'
                                         '全包 0 张图），不重复判')
                        else:
                            bad.append('P11 专利清单列了外观设计，可全包找不到一张图片或照片'
                                       '（图片文件与 docx 内嵌件都是零）——第四十四条（一）后段'
                                       '缺"图片或者照片"，不予受理级')

    # P10：02_申请文件 的三件齐不齐（专利法 26 条一；不予受理级那一半另引细则 44 条（一）前段）。
    # 三件是**发明／实用新型那一支**的要件：44 条（一）同一项里给外观设计单写了后一段
    # （请求书／图片或者照片／简要说明），所以"清单只列外观设计"的包若被按发明口径要摘要·权要·说明书，
    # 是造假红——那一支本来就不交这几件。类型判不起（没表／没行／占位／读不动）时**照旧要三件**：
    # "不知道是哪一支"不等于"这一支不受要求"，把看不见折成豁免是反方向的错——
    # 这就是判据用 declared 而不是"表在不在"的原因：类型格还是占位时 declared 为空，照旧要三件。
    need_trio = (not declared) or bool({'发明', '实用新型'} & set(declared))
    miss = [s for s in APPLY_SECTIONS if s not in aseen]
    if not need_trio:
        notes.append('P10 不适用：「专利清单」只列外观设计，那一支的法定件（简要说明＋图片或者照片）'
                     '归 P11 判，这里不按发明口径要件')
    elif adocs is None:
        notes.append('P10 未判：02_申请文件 目录本身不在（缺段已由 P5 报，这里不重复报成缺件）')
    else:
        for s in miss:
            tier = ('细则第四十四条（一）：不予受理级' if s != '说明书摘要'
                    else '专利法第二十六条一：应提交而未提交（补正级，不在 44 条清单里）')
            bad.append(f'P10 02_申请文件 里找不到「{s}」节（md 与 docx 两通道都读过了）——{tier}')
        if aunread:
            notes.append(f'P10 未核：{len(aunread)} 份文书读不动（{"、".join(aunread[:3])}），'
                         f'缺件这条不能替它们担保')

    # P12：细则第二十条一款那五节必须在**同一份说明书**里齐（二款要求每部分前面写明标题）。
    # 「附图说明」是条件项：20 条（四）写的是"说明书有附图的…"，所以只在包里有图（或实用新型——
    # 44 条（一）本来就强制有图）时才要；图的数目看不见（读不动的 docx）时**这一节走未判**，
    # 既不硬要也不免掉。适用域与 P10 同一条 need_trio（外观设计那一支没有说明书）。
    if not need_trio:
        notes.append('P12 不适用：「专利清单」只列外观设计，那一支交的是图片或者照片＋简要说明，'
                     '本仓没有"说明书"这件文书，五节这条判不上')
    if need_trio and adocs is not None:
        n_fig = image_count(pkg)
        specs = [(f, sset) for f, sset in adocs[0] if '说明书' in sset]
        if not specs:
            notes.append('P12 未判：02_申请文件 里没有一份带「说明书」节的文书'
                         '（那一件缺不缺由 P10 报，这里不重复判五节）')
        else:
            for f, sset in specs:
                if n_fig is None:
                    judged, want_fig = list(SPEC_UNCONDITIONAL), None
                    notes.append(f'P12 {f}：「{SPEC_FIG_SECTION}」这一节未判——'
                                 f'包里有读不动的 docx，看不出这份说明书有没有附图（不猜）')
                else:
                    want_fig = bool(n_fig) or '实用新型' in declared
                    judged = list(SPEC_SECTIONS) if want_fig else list(SPEC_UNCONDITIONAL)
                for sec in judged:
                    if sec not in sset:
                        bad.append(f'P12 说明书（{f}）缺细则第二十条一款那一节的「{sec}」'
                                   f'（二款要求每部分前面写明标题）——44 条（三）格式不合，走补正')
    return bad, notes


def head_names(text):
    """把 markdown 标题行归一成节名集合：去井号后交给判据侧那份 `head_title`（去尾部括注、去编号前缀）。
    docx 通道由 check_iron_rules.docx_text 按 w:pStyle 还原成同样的 # 行，两通道一套认法。"""
    out = set()
    for ln in text.splitlines():
        if not ln.strip().startswith('#'):
            continue
        h = ln.strip().lstrip('#').strip()
        h = head_title(h)
        if h:
            out.add(h)
    return out


def read_apply_docs(app):
    """02_申请文件 里**逐份文书**读到哪些节名 → ([(文件名, 节名集合)], 读不动的文件名)。
    目录本身不在返回 None：那是 P5 的地盘。
    这一层是 P12 的前提：20 条一款要的是"说明书"这一件文书内部五节齐，
    把整个目录的节名并成一个集合会让"摘要在一个文件、技术领域在另一个"的拼盘读成合规。"""
    if not os.path.isdir(app):
        return None
    docs, unread, bodies = [], [], {}
    for dp, _, fs in os.walk(app):
        for f in sorted(fs):
            low = f.lower()
            if not low.endswith(('.md', '.docx')):
                continue
            try:
                text = _cir.read_text(os.path.join(dp, f))
            except Exception as e:
                unread.append(f'{f}（{type(e).__name__}）')
                continue
            docs.append((f, head_names(text)))
            bodies[f] = text
    return docs, unread, bodies


def claim_rows(text):
    """「专利清单」节里第一张带「类型」列的表 → (表头, 数据行)；整行全空的行不算一条专利。
    找不到带类型列的表返回 (None, [])，由调用方按未判处理而不是"零违规"。"""
    for title, body in _t.sections(text):
        if README_HEAD not in title:
            continue
        for header, rows in _t.table_blocks(body):
            if _t.col(header, '类型') is None:
                continue
            return header, [r for r in rows if any(c.strip() for c in r)]
    return None, []


def image_count(pkg):
    """包里有几张看得见的图；碰到读不动的 docx 返回 None——看不见不等于没有。"""
    n = 0
    for dp, _, fs in os.walk(pkg):
        for f in fs:
            low = f.lower()
            if low.endswith(IMG_EXT) and os.path.getsize(os.path.join(dp, f)):
                n += 1
            elif low.endswith('.docx'):
                try:
                    with zipfile.ZipFile(os.path.join(dp, f)) as z:
                        n += sum(1 for i in z.infolist()
                                 if i.filename.startswith('word/media/') and i.file_size)
                except (OSError, zipfile.BadZipFile):
                    return None
    return n


def shape_violations(pkg):
    """只要违规清单（未判/提示在 shape_state 的第二项）。verify() 消费这一份，
    返回形状不许改——它被 6 处常驻断言直接当列表用。"""
    return shape_state(pkg)[0]


def verify(pkg, zfin):
    """比对 目录↔zip，返回不符清单（空＝全过）。
    单独成一个函数，是因为 main() 每次都重打包：真要在"名单对得上而内容不对"这种
    zip 上验证过判据，只能把成品交进来比对——否则 P1/P2 永远是绿的说谎话。"""
    base = os.path.basename(pkg.rstrip('/'))
    try:
        z = zipfile.ZipFile(zfin)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"输入不可用，未做任何判定: {zfin}（{type(e).__name__}: {e}）")
        sys.exit(2)
    bad = shape_violations(pkg)                                  # P5–P12：包形状先看
    with z:
        crc_bad = z.testzip()                                   # P3
        if crc_bad is not None:
            bad.append(f"P3 CRC 校验失败: {crc_bad}")
        infos = {i.filename: i for i in z.infolist() if not i.filename.endswith('/')}
        want_rel = sorted(os.path.join(base, w) for w in
                          (x[len(pkg.rstrip('/')) + 1:] for x in files_of(pkg)))
        got = sorted(infos)
        for x in sorted(set(want_rel) ^ set(got)):
            bad.append(f"{'目录有、zip 里没' if x in want_rel else 'zip 有、目录里没有'}: {x}")
        for rel in sorted(set(want_rel) & set(got)):            # P1/P2 只看两边都在的
            src = os.path.join(pkg.rstrip('/'), rel[len(base) + 1:])
            sz = os.path.getsize(src)
            if infos[rel].file_size != sz:
                bad.append(f"P1 字节数不符: {rel}（目录 {sz}／zip {infos[rel].file_size}）"
                           f"——脆文件系统截断的典型形状")
                continue
            a, b = sha256_of(open(src, 'rb')), None
            try:
                b = sha256_of(z.open(rel))
            except zipfile.BadZipFile as e:
                # testzip() 只报第一个坏条目；其余的在真读时才露头。
                # 不接住就是带着 traceback 退 1，等于把"包坏了"伪装成"发现违规"之外的一回事。
                # 已经被 testzip 点过名的不再报第二遍——同一件事报两次会淹掉别的原告。
                if rel != crc_bad:
                    bad.append(f"P3 条目读不出（CRC/格式坏）: {rel}（{e}）")
                continue
            if a != b:
                bad.append(f"P2 内容不符: {rel}（目录 {a[:12]}…／zip {b[:12]}…）")
        # P4 编码验证：全部非 ASCII 条目必须置 UTF-8 标志位
        non_ascii = [i for i in z.infolist() if any(ord(c) > 127 for c in i.filename)]
        noflag = [i.filename for i in non_ascii if not (i.flag_bits & 0x800)]
        if noflag:
            bad.append(f"P4 {len(noflag)} 个非 ASCII 条目未置 UTF-8 标志位: "
                       f"{'、'.join(noflag[:3])}{' 等' if len(noflag) > 3 else ''}")
    return bad


def main(pkg):
    pkg = pkg.rstrip('/')
    base = os.path.basename(pkg)
    ztmp = pkg + '_v2.zip'
    zfin = pkg + '.zip'
    for z in (ztmp, zfin):
        if os.path.exists(z):
            os.remove(z)
    subprocess.run(['sync'])
    time.sleep(1)
    # Python zipfile：非 ASCII 文件名自动置 UTF-8 标志位（0x800），Windows 兼容
    with zipfile.ZipFile(ztmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files_of(pkg):
            zf.write(f, os.path.join(base, os.path.relpath(f, pkg)))
    os.rename(ztmp, zfin)

    for n in shape_state(pkg)[1]:
        print('  note ' + n)                       # 未判单独说，不混进不符清单
    bad = verify(pkg, zfin)
    if bad:
        print("MISMATCH（P1–P13）:")
        for b in bad:
            print('  ✗', b)
        sys.exit(1)
    n = len([f for f in files_of(pkg)])
    print(f"OK {zfin}: {n} files, {os.path.getsize(zfin)} bytes, "
          f"名单+逐条字节数+逐条 SHA-256+CRC+UTF-8 标志位全过")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"用法: python3 {os.path.basename(sys.argv[0])} <包目录>（实得 {len(sys.argv) - 1} 个参数）"
              f" → 未做任何判定")
        sys.exit(2)
    target = sys.argv[1]
    if not os.path.isdir(target):
        print(f"输入不可用，未做任何判定: {target}（本工具只接包目录）")
        sys.exit(2)
    main(target)
