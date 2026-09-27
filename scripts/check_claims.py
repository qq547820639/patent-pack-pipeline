#!/usr/bin/env python3
"""权利要求结构门禁 Q1–Q12：把 hard-rules §4 里"形状可机判"的那几条从人记变成实跑。

法源逐字对过《专利法实施细则》（2023 修订，国务院令第 769 号）正文：
  第二十二条「权利要求书有几项权利要求的，应当用阿拉伯数字顺序编号」
            「该标记应当放在相应的技术特征后并置于括号内」
  第二十三条「权利要求书应当有独立权利要求」
  第二十四条「……应当只有一个独立权利要求，并写在……从属权利要求之前」
  第二十五条「从属权利要求只能引用在前的权利要求」
            「……只能以择一方式引用在前的权利要求，并不得作为另一项多项从属权利要求的基础」
条号与原文由本人重开官方页面核对（不是转述）；§4 里"独权须落在区别特征上""设计目标值撤出权要"
这类要读懂技术方案才能判的，仍然归 reviewer，本门禁不冒充。

Q9–Q11 的法源是《专利审查指南》（2023，国家知识产权局令第 78 号）——细则里没有模糊用语、
句号位置这类形式细则，是指南把它们写成了可判的形状。三句逐字抄自本机留底的 613 页 PDF 抽取件
（`.codebuddy/attest/zhinan2023_ahippc.txt`，复算命令见 README §6）：
  第二部分第二章 §3.2.2（PDF p165／印刷页 2-29）「权利要求中不得出现"例如""最好是""尤其是"
    "必要时"等类似用语。」
  同节（PDF p166／2-30）「在一般情况下，权利要求中不得使用"约""接近""等""或类似物"等类似的用语」
  同部分 §3.3（PDF p166／2-30）「每一项权利要求只允许在其结尾处使用句号。」

判据（只判形状，不判内容）：
  Q1 权项编号必须是从 1 起的连续阿拉伯数字，不得重号/跳号（第二十二条）。
  Q2 至少有一个独立权利要求，且每个独立权利要求都排在所有从属权利要求之前
     （第二十三条 + 第二十四条"写在……之前"那一半）。
     "应当只有一个独权"的个数那一半**只出提示不判红**：产品+方法并列独权是常见写法，
     到底算不算同一组独权要读技术方案，机器在这里判红就是误伤。
  Q3 从属权利要求只能引用在前的权项：引用号必须小于自身编号，且必须真实存在
     （第二十五条"只能引用在前的权利要求"）。
  Q4 多项从属权利要求不得以多项从属权利要求为引用基础（第二十五条）。
     认不出"多项"写法时不判（未判），不硬猜。
  Q5 权要里引用附图标记必须写在括号内（第二十二条"置于括号内"）。
     只认那张「标记｜名称」对照表里真实存在的号——正文里的自由数字（"拉脱力 90N"）
     一律不当标记，否则这把尺子只会制造假红。
  Q6 从属权利要求条数落在档位内（hard-rules §4：发明 7–10、实用新型 4–8）。
     **这是房内口径不是法条**：细则没有任何条数区间（超过 10 项只是加收申请费，不是驳回理由）。
     类型从 `--type` 给；没给时退到两型并集 4–10 判——它仍能抓到"少到 3 条"和"多到 11 条"，
  Q7 权利要求书里不得有插图（第二十二条一款"可以有化学式或者数学式，但是不得有插图"）。
     md 认图片语法（`![…](…)`／`<img`）；docx 通道由 check_iron_rules.docx_text 把含
     drawing/object/pict 的段落折算成一行 `![](docx-embedded-object)`——判据作用在文本面上，
     两通道吃同一条正则。**表格里的图不在此列**（表格分支按格取文）：登记为已知盲区，
     不是"已核无图"。
  Q8 权利要求书里不得用"如图…所示／如说明书……部分所述"指回别的文书（第二十二条一款；
     "除绝对必要的外"是法定例外，本判据对带编号的形状判红，无编号的"如图所示"不判、归 reviewer）。
     正确写法是把标记放进括号（Q5），不是用"如图"指过去。
     只是不假装知道该案是发明还是实用新型（README「专利清单」的"类型"列至今只有表头没有值，
     所以类型今天只能由人告知，机器不去猜）。

  Q9 权项内不得出现"例如／最好是／尤其是／必要时"（指南 §3.2.2 逐字点名的四个词：
     这类用语会在一项权利要求中限定出不同的保护范围，导致保护范围不清楚）。
     只收指南逐字点出的那四个，不扩表——同节"厚／薄／强／弱"那支进来就是把尺子变成假红制造机：
     中文没有词边界，"压缩强度"里的"强"会当场开火（该形状已钉在常驻用例的反向档里）。
  Q10 权项内不得用"约＋数字"限定数值、不得出现"或类似物"（指南 §3.2.2"在一般情况下…不得使用"）。
     同句里的"接近"与"等"两个词**不判**："接近开关"是一个真实部件名，"等"是"相等／等待"的构词成分，
     中文侧没有词边界可退，误伤面在本机量不出来（本仓不含任何真实交付包）。
     指南那句自己写着"在一般情况下"，例外（例如权利要求里给出精确定义）归 reviewer。
  Q11 每一项权利要求只允许在结尾处使用句号（指南 §3.3；实用新型侧同文见第一部分第二章 §7.4
     形式要求（1）"分行和分小段处只可用分号或逗号"）。
     **只判"结尾之前出现句号"，不判"结尾没有句号"**——指南那句话是给句号划界，
     不是设定"每项必须以句号收尾"的义务，反过来判会造出一条法条里没有的禁令。
  Q12 权项编号前不得冠"权利要求"或"权项"（指南第一部分第一章 §4.4 逐字：
     「应当用阿拉伯数字顺序编号，编号前不得冠以"权利要求"或者"权项"等词」；前半句由 Q1 判）。
     这条同时补上一个此前静默的形状：通篇写成"权利要求1、权利要求2、…"的权要书，
     CLAIM_ITEM 一行都解析不出，旧顺序下整族报"无项未判"而 Q12 是唯一看得见它的判据——
     所以节面三条（Q7／Q8／Q12）现在都在"无项早退"之前跑。

三态：交付包里没有可识别的"权利要求书"节 ⇒ Q1–Q12 全部未判（有的交付形态把权要交给代理机构写）；
      有节但一行权项都解析不出 ⇒ Q1–Q6、Q9–Q11 未判（连权项都没有，谈不上项内形状），并说清读到了什么；
      但 Q7／Q8／Q12 判在整节文本面上，这一档它们照判——注记里点名是哪几条没判，不写"整族未判"。
      没有标记对照表 ⇒ Q5 未判（括号形状没有可对照的号集）。
      Q9–Q11 判在**每一项权项之内**，所以它们和"有没有解析出权项"同生死；
      Q7／Q8 判在整节文本面，权项切不出来时照判。
退出码: 0 合规或未判 / 1 存在违规 / 2 输入不可用（不是目录、读不动的 docx 等，说清成因）。
用法: python3 scripts/check_claims.py <交付包目录>   # 只接目录，递归找 .md 与 .docx
"""
import argparse
import importlib.util as _ilu
import os
import re
import sys

S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_t = _load('mdtable')
_cir = _load('check_iron_rules')
_cfl = _load('check_figure_labels')

CLAIMS_HEAD = _cir.CLAIMS_HEAD
NEXT_SECTION = _cir.NEXT_SECTION
# CLAIMS_HEAD / NEXT_SECTION 都带 ^ 锚，而整份文书是一个多行串：不带 MULTILINE 的 search
# 只能命中第 1 行，用它挑「哪份文书带权要节」会让整把尺子永远不判——常驻用例的合规档当场抓到。
CLAIMS_HEAD_M = re.compile(CLAIMS_HEAD.pattern, re.M)
NEXT_SECTION_M = re.compile(NEXT_SECTION.pattern, re.M)
# 权项起始行：`1.` / `1、` / `1．`（markdown 的有序列表也是这个形状）
CLAIM_ITEM = re.compile(r'^\s*(\d{1,3})\s*[.、．]\s*(.*)$')
# 引用语：`根据权利要求1` / `如权利要求1所述` / `根据权利要求1、2或3` / `根据权利要求1至3中任一项`
DEP_REF = re.compile(r'(?:根据|如|依照)\s*(?:该|上述)?\s*权利要求\s*(\d[0-9、,，和及或至~～\-–\s]*)')
MULTI_HINT = re.compile(r'[、,，]|或|至|~|～|任一|任意|之一')
PAREN_SPAN = re.compile(r'[（(][^）)]*[）)]')
# Q7／Q8 的两个形状（细则第二十二条一款）。md 图片语法与 docx 的折算行同一条正则；
# "如图…所示"要求带编号——无编号的"如图所示"误伤面没量过，不判（docstring 有记）。
CLAIM_IMAGE = re.compile(r'!\[[^\]]*\]\([^)]*\)|<img\b', re.I)
CLAIM_FIG_REF = re.compile(r'如图\s*[0-9０-９]{1,3}\s*所示')
CLAIM_SPEC_REF = re.compile(r'如说明书[^，。；\n]{0,16}部分所述')

# Q9–Q11 的三张表逐字取自《专利审查指南》（2023，国家知识产权局令第 78 号）第二部分第二章，
# 留底与复算命令见 README §6（PDF 613 页抽取件 .codebuddy/attest/zhinan2023_ahippc.txt）：
#   p165（印刷页 2-29）§3.2.2「权利要求中不得出现"例如""最好是""尤其是""必要时"等类似用语。」
#   p166（2-30）§3.2.2「在一般情况下，权利要求中不得使用"约""接近""等""或类似物"等类似的用语」
#   p166（2-30）§3.3「每一项权利要求只允许在其结尾处使用句号。」
# 指南只写了"等类似用语"，所以这里只收它逐字点出的那几个词，不自造扩展表——
# 同一节里"厚／薄／强／弱"那支不进来：中文没有词边界，"压缩强度"里的"强"会把这把尺子变成假红制造机。
VAGUE_TERMS = ('例如', '最好是', '尤其是', '必要时')
# 「约」单用会撞"约定／预约"，「接近」撞"接近开关"（那是个真实部件名），「等」撞"相等／等待"
# ——所以只收"约＋数字"这一种形状和「或类似物」这一个逐字短语；另两个词登记为不判，理由同上。
APPROX_SHAPE = re.compile(r'约\s*[0-9０-９]')
APPROX_PHRASE = '或类似物'
# Q12：《专利审查指南》第一部分第一章 §4.4（PDF p26／印刷页 1-10，书内页 22）逐字
# 「权利要求书有几项权利要求的，应当用阿拉伯数字顺序编号，编号前不得冠以"权利要求"或者"权项"等词。」
# 后半句是这一条的全部内容，前半句（顺序编号）已由 Q1 判；
# 形状上这类行不会被 CLAIM_ITEM 解析成权项（它以"权"字起头），所以 Q1 常常照样绿——
# 也就是说：**不判这一句，整份"权利要求1、权利要求2…"的权要书会读成"一行权项都没解析出"而未判**。
CLAIM_NUM_PREFIX = re.compile(r'^\s*(?:权利要求|权项)\s*\d{1,3}\s*[.、．]')


def read_any(path):
    try:
        return _cir.read_text(path)
    except Exception as e:
        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')
        sys.exit(2)


def claims_body(text):
    """返回权利要求书节的 (起始行号, 该节正文行)；找不到节返回 (None, [])。

    起始行号是**1-based**（节标题自己那一行），与 check_iron_rules.section_body 同一口径——
    今天全仓的 `路径:行号` 都按 1-based 报，这里返回 0-based 会让整族位点短一行，
    把 reviewer 指到上一行去（常驻的绝对坐标档 qabs 钉住它）。
    """
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if CLAIMS_HEAD.match(ln):
            start = i
            break
    if start is None:
        return None, []
    body = []
    for ln in lines[start + 1:]:
        if NEXT_SECTION_M.match(ln):
            break
        body.append(ln)
    return start + 1, body


def split_items(body):
    """把节正文切成 [(编号, 起始行下标, 该项文本)]；非列表行并入上一项。"""
    items = []
    for idx, ln in enumerate(body):
        m = CLAIM_ITEM.match(ln)
        if m:
            items.append([int(m.group(1)), idx, m.group(2)])
        elif items and ln.strip():
            items[-1][2] += '\n' + ln.strip()
    return items


def refs_of(txt):
    """返回 (引用号列表, 是否像多项引用)。"""
    nums, multi = [], False
    for m in DEP_REF.finditer(txt):
        seg = m.group(1)
        got = [int(x) for x in re.findall(r'\d+', seg)]
        nums += got
        if MULTI_HINT.search(seg):
            multi = True
    return nums, multi


def mark_set(docs):
    """对照表里的 名称→标记号 映射（与 N3 同一形状）；另报表是否在场。"""
    name2num, found = {}, False
    for path, text in docs:
        for header, rows in _t.table_blocks(text):
            jm, jn = _t.col(header, '标记'), _t.col(header, '名称')
            if jm is None or jn is None:
                continue
            found = True
            for cs in rows:
                v = (cs[jm] if jm < len(cs) else '').strip()
                nm = (cs[jn] if jn < len(cs) else '').strip()
                if v.isdigit() and nm:
                    name2num.setdefault(nm, v)
    return name2num, found


# Q6 的档位（hard-rules §4）。细则没有任何条数区间，这是房内口径，别冒法条。
TYPE_BANDS = {'发明': (7, 10), '实用新型': (4, 8)}
UNION_BAND = (4, 10)          # 类型没告知时的兜底：两型区间的并，仍能抓"太少/太多"
# 《专利法实施细则》第四十四条（六）点的就是这三类：类别不明确或者难以确定 → 不予受理。
# 这份清单由本模块一处持有，`rebuild_package.py` 的 P8 import 它（两处各抄一份迟早漂）。
PATENT_TYPES = ('发明', '实用新型', '外观设计')


def type_of(cell):
    """从一格文本里认专利类别；认不出返回 None，不猜。
    按名字长短从长往短试：类别名之间今天互不为子串，但"某类的写法里含另一类三个字"
    这种形状一旦出现，长名先赢才不会被短名抢走。"""
    txt = (cell or '').strip()
    for key in sorted(PATENT_TYPES, key=len, reverse=True):
        if key in txt:
            return key
    return None


def band_of(ptype):
    """返回 (下界, 上界, 命中的类型键)。认不出、或认成外观设计（没有从属条数档位这说）时走并集。"""
    key = type_of(ptype)
    if key in TYPE_BANDS:
        band = TYPE_BANDS[key]
        return band[0], band[1], key
    return UNION_BAND[0], UNION_BAND[1], None


def check_text(path, text, name2num, marks_found, ptype=None):
    """返回 (违规, 未判/提示, 实判判据集合)。"""
    bad, notes, seen = [], [], set()
    cstart, body = claims_body(text)
    if cstart is None:
        return [], [f'{path}: 没有「权利要求书」节 → Q1–Q12 未判'
                    f'（权要由代理机构撰写时本就没有这一节）'], seen
    where = lambda off: f'{path}:{cstart + 1 + off}'

    # Q7／Q8／Q12：判在**这一节内**的文本面，与权项解析无关。
    # 这段必须在 `if not items` 之前跑——注释一直写着"就算一行权项都切不出来也判得动"，
    # 而代码把它放在早退之后，那句是假的；第 39 轮加 Q12 时才撞上：一份通篇写成
    # "权利要求1、权利要求2、…"的权要书，CLAIM_ITEM 一行都解析不出，整族读成"无项未判"，
    # 而 Q12 恰恰是唯一看得见这种写法的那一条。顺序换过来之后这条红才出得来。
    for off, ln in enumerate(body):
        if CLAIM_IMAGE.search(ln):
            bad.append(f'{where(off)}: 权利要求书里出现插图（md 图片语法／docx 嵌入对象折算行）'
                       f' → Q7（第二十二条一款"不得有插图"）')
            seen.add('Q7')
        if CLAIM_FIG_REF.search(ln) or CLAIM_SPEC_REF.search(ln):
            bad.append(f'{where(off)}: 权利要求书里用"如图…所示／如说明书…部分所述"指回别的文书'
                       f' → Q8（第二十二条一款；正确写法是把标记放进括号，见 Q5）')
            seen.add('Q8')
        if CLAIM_NUM_PREFIX.search(ln):
            bad.append(f'{where(off)}: 权项编号「{ln.strip()[:12]}…」前冠了"权利要求／权项"字样'
                       f' → Q12（指南第一部分第一章 §4.4"编号前不得冠以\'权利要求\'或者\'权项\'等词"）')
            seen.add('Q12')

    items = split_items(body)
    if not items:
        # 节面三条（Q7/Q8/Q12）已经判过，不能跟着整族说"未判"——说整族就是假话。
        return bad, notes + [
            f'{path}: 有权利要求书节但一行权项都没解析出（不以「N.」起头？）'
            f' → Q1–Q6、Q9–Q11 未判（有节却无项，那几条判不起）'], seen

    # Q9／Q10／Q11：这三条的主语都是"权利要求中／每一项权利要求"，所以判在**每一项之内**，
    # 与 Q7／Q8 那张整节文本面分开——节标题下面写了"例如"而权项没写，不该报某一项的位点。
    # 行号报到触发那一行；权项被软回车切成多行时，先把该项的行拼回一段再找词，
    # 免得"例\n如"这种跨行写法被静默漏掉（拼回后仍按原行反查位点）。
    for k, (n, off, _) in enumerate(items):
        end = items[k + 1][1] if k + 1 < len(items) else len(body)
        # 表格行不算权项正文（与 T4"正文（表格行之外）"同一口径）：
        # 权要是自然段，把「标记｜名称」表尾巴卷进最后一项，表里一个"例如"就够造一条假位点。
        ilines = [(off + j, ln) for j, ln in enumerate(body[off:end])
                  if ln.strip() and not ln.lstrip().startswith('|')]
        if not ilines:
            continue
        joined = '\n'.join(ln for _, ln in ilines)

        def _at(pos, _lines=ilines):
            acc = 0
            for li, ln in _lines:
                acc += len(ln) + 1
                if pos < acc:
                    return li
            return _lines[-1][0]

        seen |= {'Q9', 'Q10', 'Q11'}
        for term in VAGUE_TERMS:
            pos = joined.find(term)
            if pos != -1:
                bad.append(f'{where(_at(pos))}: 权利要求 {n} 里出现「{term}」→ Q9'
                           f'（指南 §3.2.2：这类用语会在一项权利要求中限定出不同的保护范围，'
                           f'导致保护范围不清楚）')
        m = APPROX_SHAPE.search(joined)
        if m:
            bad.append(f'{where(_at(m.start()))}: 权利要求 {n} 里「{m.group(0)}」用"约"限定数值'
                       f' → Q10（指南 §3.2.2"在一般情况下…不得使用"；数值边界因此不清楚）')
        elif APPROX_PHRASE in joined:
            bad.append(f'{where(_at(joined.find(APPROX_PHRASE)))}: 权利要求 {n} 里出现'
                       f'「{APPROX_PHRASE}」→ Q10（同上，逐字点名的短语）')
        last_line, last_txt = ilines[-1][0], ilines[-1][1].rstrip()
        for li, ln in ilines:
            for pos, ch in enumerate(ln):
                if ch != '。':
                    continue
                if li == last_line and pos == len(last_txt) - 1:
                    continue        # 结尾那一个句号正是指南允许的写法
                bad.append(f'{where(li)}: 权利要求 {n} 在结尾之前出现了句号'
                           f'（该行第 {pos + 1} 字）→ Q11（指南 §3.3"每一项权利要求只允许'
                           f'在其结尾处使用句号"；分行处只可用分号或逗号）')
                break
            else:
                continue
            break

    nums = [n for n, _, _ in items]
    seen.add('Q1')
    if sorted(nums) != list(range(1, len(nums) + 1)):
        dup = sorted({n for n in nums if nums.count(n) > 1})
        miss = sorted(set(range(1, max(nums) + 1)) - set(nums))
        bad.append(f'{where(items[0][1])}: 权项编号不是从 1 起的连续号'
                   f'（重号 {dup}／缺号 {miss}）→ Q1（第二十二条"用阿拉伯数字顺序编号"）')

    deps = [(n, off, txt) for n, off, txt in items if DEP_REF.search(txt)]
    ind = [n for n, off, txt in items if not DEP_REF.search(txt)]
    seen.add('Q2')
    if not ind:
        bad.append(f'{where(items[0][1])}: 权利要求书里读不到独立权利要求'
                   f'（每一项都带"根据权利要求…"）→ Q2（第二十三条"应当有独立权利要求"）')
    else:
        first_dep = min((n for n, _, _ in deps), default=None)
        late = sorted(x for x in ind if first_dep is not None and x > first_dep)
        if late:
            bad.append(f'权利要求 {"/".join(map(str, late))} 是独立权利要求，却排在从属权利要求'
                       f'（自 {first_dep} 起）之后 → Q2（第二十四条"写在…从属权利要求之前"）')
        if len(ind) > 1:
            notes.append(f'{path}: 读到 {len(ind)} 项独立权利要求（{"、".join(map(str, ind))}）'
                         f'→ 个数那一半不判红，需要人判是不是同一组（第二十四条）')

    lo, hi, used_type = band_of(ptype)
    seen.add('Q6')
    ndep = len(deps)
    if not (lo <= ndep <= hi):
        bad.append(f'{where(items[-1][1])}: 从属权利要求 {ndep} 项，不在 {lo}–{hi} 之内'
                   f'（{used_type or "两型并集"}口径，hard-rules §4；房内口径非法条）→ Q6')
    elif used_type is None:
        # 两型都容得下（7–8 项）时这一档其实已经判完，不必制造噪声；
        # 只有一型容得下时才说清"没判红是因为不知道是哪一型"。
        fits = [f'{k}的 {a}–{b}' for k, (a, b) in TYPE_BANDS.items() if a <= ndep <= b]
        if len(fits) != 2:
            why = ('未给 --type' if not ptype else
                   f'--type 给的是「{ptype}」，既不是发明也不是实用新型')
            notes.append(f'{path}: 从属权利要求 {ndep} 项在两型并集内、只落在 {"、".join(fits) or "两档之外"}；'
                         f'{why}，所以这一半不判红（README「专利清单」的类型列至今无值）→ Q6 部分未判')

    maxn = max(nums)
    for n, off, txt in deps:
        seen.add('Q3')
        refs, multi = refs_of(txt)
        for r in refs:
            if r > maxn:
                bad.append(f'{where(off)}: 权利要求 {n} 引用了不存在的权利要求 {r} → Q3'
                           f'（第二十五条"只能引用在前的权利要求"）')
            elif r >= n:
                bad.append(f'{where(off)}: 权利要求 {n} 引用了在后的 {r} → Q3'
                           f'（第二十五条"只能引用在前的权利要求"）')
    dep_multi = {}
    for n, off, txt in deps:
        _, dep_multi[n] = refs_of(txt)
    for n, off, txt in deps:
        refs, multi = refs_of(txt)
        if multi:
            seen.add('Q4')
            bases = [r for r in refs if dep_multi.get(r)]
            if bases:
                bad.append(f'{where(off)}: 权利要求 {n} 是多项从属，却引用了同为多项从属的 '
                           f'{"/".join(map(str, bases))} → Q4'
                           f'（第二十五条"不得作为另一项多项从属权利要求的基础"）')

    if marks_found and name2num:
        seen.add('Q5')
        bare = 0
        for n, off, txt in items:
            # 先抠掉括号段与"根据权利要求N"整段：那个 N 是权项号，不是附图标记
            stripped = PAREN_SPAN.sub(' ', DEP_REF.sub(' ', txt))
            for m in _cfl.NUM_RUN.finditer(stripped):
                pre, num = m.group(1), m.group(2)
                if _cfl.UNIT_TAIL.match(stripped[m.end():m.end() + 6]):
                    continue
                if [nm for nm in name2num if pre.endswith(nm) and name2num[nm] == num]:
                    bad.append(f'{where(off)}: 权利要求 {n} 里「{m.group(0).strip()}」的标记 {num} '
                               f'写在括号外 → Q5（第二十二条"置于括号内"）')
                    break
                bare += 1
        if bare and not any('Q5' in b for b in bad):
            notes.append(f'{path}: 权要里 {bare} 处"名称+数字"都不在标记对照表里 → '
                         f'不当附图标记处理，Q5 未核（不折成合规）')
    else:
        notes.append(f'{path}: 文书里没有「标记｜名称」对照表 → Q5 未判')
    return bad, notes, seen


def check_package(root, ptype=None):
    docs = []
    for dp, _, fs in os.walk(root):
        for f in sorted(fs):
            if f.lower().endswith(('.md', '.docx')):
                docs.append((os.path.join(dp, f), read_any(os.path.join(dp, f))))
    name2num, marks_found = mark_set(docs)
    bad, notes, seen = [], [], set()
    hit = 0
    for path, text in docs:
        if CLAIMS_HEAD_M.search(text):
            hit += 1
            b, n, s = check_text(path, text, name2num, marks_found, ptype)
            bad += b
            notes += n
            seen |= s
    if not hit:
        notes.append(f'{root}: 包内没有任何文书带「权利要求书」节 → Q1–Q12 未判')
    return bad, notes, seen


def main():
    ap = argparse.ArgumentParser(description='权利要求结构门禁 Q1–Q12（只接目录）')
    ap.add_argument('targets', nargs='+', help='交付包目录')
    ap.add_argument('--type', default=None,
                    help='本案专利类型（发明／实用新型），决定 Q6 的从属条数档位；'
                         '不给则退到两型并集 4–10，并把它少判的那一半说出来')
    args = ap.parse_args()

    roots = []
    for p in args.targets:
        if os.path.isdir(p):
            roots.append(p)
        else:
            print(f'输入不可用，未做任何判定: {p}（本门禁只接目录，实得不是目录）')
            sys.exit(2)
    if not roots:
        print('输入不可用，未做任何判定: 没有可看的目录')
        sys.exit(2)

    total = judged = 0
    for root in roots:
        bad, notes, seen = check_package(root, args.type)
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if seen else 0
        total += len(bad)
        print(f'{root}: 违规 {len(bad)}｜实判判据 {len(seen)} 条')
    print(f'合计违规 {total}（规则 Q1–Q12，判据见脚本 docstring）；实判 {judged} 个包')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
