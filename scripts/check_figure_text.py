#!/usr/bin/env python3
"""图↔文书对账 T1–T8：把 hard-rules §5 最后两条纯承诺变成能实跑的判据——
「图中数值与文书逐字一致」「不得出现交底书没有的部件/参数」——
外加《专利法实施细则》点名却全仓无人核的图号对账（T4 缺图 / T5 图未被引用 / T6 跳号 / T7 标记号反向）。

为什么要有 manifest：PNG 是像素，事后没有任何东西记录图上画了什么字（F4 量完字数就丢），
而 parts.json 在本仓**只有读者没有生产者**——由代理手抄。拿手抄件去和文书互比，
只能证明两份抄得像，证明不了图上真写着这个。所以留底由画图那段代码自己产出
（见 patent_figure.Figure.write_manifest），本门禁读的是那份产出。

判据：
  T1 图上的部件名（标记所指部件 + 框内不含数字的文字）必须能在文书池里逐字找到；
     找不到＝图上出现了文书没有的部件。
  T2 框内文字里的量值（含 ≤/≥/±/~ 与单位）必须逐字见于文书；比较前只把
     符号与数字之间的空白归一（"≤ 25mm/s" 与 "≤25mm/s" 视为同一种写法），
     数字、单位、符号本身一个都不许差。图上没有任何带数值的文字 ⇒ T2 未判。
  T3 图上的 标记号→部件 必须与文书里那张「标记｜名称｜所在图号」对照表一致。
     跨图同号同件归 patent_figure 的 F3 管，而图↔表这一头此前没人管：
     图写 12=底座、表写 12=支架，两道门各自都能绿。
  T4 正文（表格行之外）声明的 图N 必须在包里真有一张 图N.png ——缺整批与缺其中几张都判红。
     出处：《专利法实施细则》第四十六条（说明书中写有对附图的说明但无附图或缺少部分附图，
     须限期补交附图或声明取消该说明）。
  T5 包里每张 图N.png 都要被正文引用过——图存在却没人提到，等于交付物里多出一张说明书写不到的图。
     出处：hard-rules §5 / pipeline-stages「每图被附图说明与实施方式引用」。
  T6 包里实存的图号必须是从 1 起的连续号，不得跳号（正文声明只参与 T4，不参与 T6 的分母）。
     出处：《专利法实施细则》第二十一条（几幅附图应当按照"图1，图2，……"顺序编号排列）。
  T7 那张对照表里写的每个标记号，必须真出现在至少一张有留底的图上。T3 只管"图有的号表里必须有"
     这一向，反着来没人管：表里凭空多写一行 15=缓冲垫 而任何图都没标 15，N2/N3 只核表内自洽、
     T3 也不回头看，整包照样绿。
     出处：《专利法实施细则》第二十一条（附图中未出现的附图标记不得在说明书文字部分中提及）。
     文书侧号集合只取对照表的标记列，不取正文里"名称+数字"的自由数字——那支抽取（N3 用的 NUM_RUN）
     会把"拉脱力 90N"的 90 当标记号，误伤面不可控；N3 敢用它是因为那里有表名做锚。
  T8 摘要附图指定的图号必须是说明书附图之一。
     出处：《专利审查指南》（2023）第一部分第一章 §4.5.2，本机留底 txt:860-868＝PDF p27／印刷页 1-11
     （同页页眉 txt:845-846 抄引文要跳过），逐字「说明书有附图的，申请人应当指定其中一幅……作为
     摘要附图，并在请求书中写明图号」＋「指定的摘要附图不是说明书附图之一的，审查员可以通知申请人补正」。
     两句各判各的：后一句拿包内写出的图号去对真实存在的图号；前一句的"指定"落在**请求书**上，
     载体就是第 48 轮落进骨架的那件 `02_申请文件/请求书著录项_*.md`（第 47 轮登记"判不动"时
     还没有这件载体，那句理由已随 `8b93842` 作废）。所以：有说明书附图而包内读不到任何指认 ⇒ 违规；
     那一处写着占位 ⇒ 未判（还没定不等于没指定）；那一处填完了却没号 ⇒ 违规；
     包里一张附图都没有 ⇒ 不适用（法条那句的主语是"说明书有附图的"）。
     认法：命中「摘要附图」那一行，若它是标题行则再吃掉本节正文（止于下一个标题行）——
     指认写在本行括注里（模板那种「## 摘要附图（指定图 X）」）或另起一行都读得到。

三态：没有 figures 目录 ⇒ 未判（有的交付形态本就没有图）；
      图文件名认不出图号（主视图.png 之类）⇒ T4–T6 未判，不去猜号——猜错会把缺号判成不缺；
      T8 同一条：拿猜出来的图号去对"指定的摘要附图"，对上了也不说明明，所以一并走未判；
      figures 里有 PNG 却没有 manifest ⇒ rc=2 说"图不是本库出的，无从对账"——
      这不是违规，但绝不是"核过了"。这一条与"有没有别的图带着清单"无关：
      12 张图里混 1 张手画 PNG，那张图上写着什么同样没人核过，包级对账就不完整。
      有这种手画图时 T7 走未判：表里那个号也许正画在那张没留底的图上，"看不见"不许折成违规。

退出码: 0 合规或未判 / 1 存在违规（判出的违规优先于"不完整"上报）/
        2 输入不可用，或有 PNG 无清单可做对账（无论其余图是否已判）。
"""
import importlib.util as _ilu
import json
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

# 图号从文件名侧的认法：只认「图N.png / 图 N.png」。认不出的（如 主视图.png、fig1.png）
# 一律进"未判"注记而不是猜一个号——猜错会把 T4 的缺图判成不缺，方向上就是假绿。
FIG_NUM_NAME = re.compile(r'^图\s*(\d+)$')

# 摘要附图那一节的节名由判据侧持有：生成器另抄一份字面，改了这里而那份字面没跟着改，
# T8 就在生产包上永远读不到指认——"未判"与"没判"在报告里同形，正是要防的那种漂移。
ABSTRACT_FIG_SECTION = '摘要附图'
ABSTRACT_FIG_NUM = re.compile(r'图\s*(\d+)(?!\d)')
MD_HEAD_LINE = re.compile(r'^\s*#{1,6}\s')
# 占位符的形状只有 R2b 那一份定义（`check_iron_rules.PLACEHOLDER_TOKEN`）：本门禁借它，不抄第二份。
# T8 的"写了节却没指认"到底算违规还是算没填完，全靠这一枚正则分开——另抄一份就是给漂移留活路。
PLACEHOLDER_TOKEN = _cir.PLACEHOLDER_TOKEN

# 量值 token：可带比较符号、数字（含区间/小数）、紧跟的单位串。单位刻意只列常见工程写法，
# 认不出的写法一律不判而不是判红——宁可漏报，也不拿一张永远缺一种写法的豁免表去追。
NUM_TOKEN = re.compile(r'[≤≥<>±~约]?\s?\d+(?:\.\d+)?(?:[–\-~至]\d+(?:\.\d+)?)?'
                       r'(?:\s*(?:mm|cm|μm|um|kg|g|N·m|Nm|N|MPa|kPa|Pa|℃|°|Hz|rpm|'
                       r'mm/s|m/s|rad/s|次|圈|级|%|V|A|W|Hz))?[A-Za-z/·]*')
SPACE_AROUND_SIGN = re.compile(r'([≤≥<>±~约])\s+')


def norm(txt):
    """只归一"符号与数字之间的空白"，别的一个字都不动。"""
    return SPACE_AROUND_SIGN.sub(r'\1', txt)


def read_any(path):
    try:
        return _cir.read_text(path)
    except Exception as e:
        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')
        sys.exit(2)


def find_manifests(root):
    """返回 (清单路径, 有 PNG 却无清单的图名)。清单与 PNG 并排，命名 <图名>.manifest.json。

    配对不能用 os.path.splitext：'.manifest.json' 是双后缀，splitext 会把
    '图1.manifest.json' 切成 '图1.manifest'，于是永远配不上 '图1.png'，
    合规的包也会报"两张 PNG 没有清单"。这条只在"有清单同时有孤儿"时才露头，
    而旧写法恰好在有清单时不看孤儿——两个缺陷互相遮着，端到端出图才把它俩一起掀开。
    """
    mans, orphan = [], []
    suffix = '.manifest.json'
    for dp, _, fs in os.walk(root):
        pngs = [f for f in sorted(fs) if f.lower().endswith('.png')]
        for f in sorted(fs):
            if f.endswith(suffix):
                mans.append(os.path.join(dp, f))
        have = {f[:-len(suffix)] for f in fs if f.endswith(suffix)}
        orphan += [p for p in pngs if os.path.splitext(p)[0] not in have]
    return mans, orphan


def load_manifest(p):
    """读之前先验形状：键名/类型不对就是清单坏了，说清是谁坏了，而不是 KeyError 崩在半路。"""
    try:
        d = json.load(open(p, encoding='utf8'))
    except Exception as e:
        return None, f'{p}: 清单读不出来（{type(e).__name__}: {e}）'
    if not isinstance(d, dict) or 'figure' not in d or 'marks' not in d or 'texts' not in d:
        got = sorted(d) if isinstance(d, dict) else type(d).__name__
        return None, (f'{p}: 清单缺键 figure/marks/texts（实得 {got}）——'
                      f'这份不是 patent_figure 写的，还是格式改过没同步？')
    if not isinstance(d['marks'], dict) or not isinstance(d['texts'], list):
        return None, f'{p}: 清单里 marks 应为对象、texts 应为数组，实得不符'
    return d, None


def present_figures(root):
    """figures 侧真实存在的图号：{号: 路径}，外加"收进来但文件名认不出图号"的清单。

    外观设计/views 目录走渲染图与照片，不参与线条图的图号对账（与 C1 的跳过同一口径，
    两边各写一份豁免迟早漂移）。"""
    have, unnamed = {}, []
    for dp, _, fs in os.walk(root):
        if 'views' in dp or '外观设计' in dp:
            continue
        for f in sorted(fs):
            if not f.lower().endswith('.png'):
                continue
            m = FIG_NUM_NAME.match(os.path.splitext(f)[0])
            if m:
                have.setdefault(m.group(1), os.path.join(dp, f))
            else:
                unnamed.append(os.path.join(dp, f))
    return have, unnamed


def number_reconcile(root, docs):
    """T4–T6：正文声明的图号 ↔ 包里真实存在的图号。

    这三条此前全仓没人管：N4 只核"对照表里的所在图号被正文声明过"（方向是表→正文），
    T1–T3 只看有清单的那几张图——于是"说明书写了 图3 为……，而 figures 里只有图1、图2"
    这种交付物今天能一路全绿，而它正是《专利法实施细则》第四十六条要点名补交的情形。
    """
    bad, notes, seen = [], [], set()
    declared = _cfl.figure_numbers(_cfl.prose_only('\n'.join(t for _, t in docs)))
    present, unnamed = present_figures(root)
    named = '、'.join(os.path.basename(p) for p in unnamed[:3]) + (' 等' if len(unnamed) > 3 else '')
    if not present:
        if declared and not unnamed:
            seen.add('T4')
            for n in sorted(declared, key=int):
                bad.append(f'{root}: 正文声明了 图{n}，包里却没有任何 图N.png → T4'
                           f'（实施细则第四十六条：说明书中写有对附图的说明但无附图，'
                           f'须限期补交附图或声明取消该说明）')
        else:
            notes.append(f'{root}: {"图文件名认不出图号（" + named + "）" if unnamed else "包内既无图也无图号声明"}'
                         f' → T4–T6 未判（不折成合规）')
        return bad, notes, seen
    seen.update({'T4', 'T5'})
    for n in sorted(declared - set(present), key=int):
        bad.append(f'{root}: 正文声明了 图{n}，figures 里没有这张图 → T4'
                   f'（实施细则第四十六条：缺少部分附图须补交或声明取消对附图的说明）')
    for n in sorted(set(present) - declared, key=int):
        bad.append(f'{root}: figures 里有 {os.path.basename(present[n])}，'
                   f'正文没有任何"图{n}"引用 → T5（每幅图都要被附图说明与具体实施方式引用）')
    # T6 只看**实存文件**的编号是否连续：把正文声明并进分母，会让"正文写了 图2 但包里没有 图2"
    # 这种情形反过来把跳号补圆（union 连续、T6 不响），而跳号与缺图是两回事，各判各的。
    nums = sorted({int(k) for k in present})
    if nums and not unnamed:
        seen.add('T6')
        if nums != list(range(1, len(nums) + 1)):
            miss = sorted(set(range(1, max(nums) + 1)) - set(nums))
            bad.append(f'{root}: 图号不是从 1 起连续编号（缺 {miss}）→ T6'
                       f'（实施细则第二十一条：几幅附图应当按照"图1，图2，……"顺序编号排列）')
    elif unnamed:
        notes.append(f'{root}: {len(unnamed)} 个图文件名认不出图号（{named}）'
                     f' → T6 未判（连号要靠认得出的图号，猜号会把缺号判成不缺）')
    return bad, notes, seen


def abstract_figure_windows(text):
    """命中「摘要附图」的行 → [(行号, 参与判定的窗口文本)]。

    窗口只多取"本节正文"这一层：指认可能写在本行的括注里（模板那种「## 摘要附图（指定图 X）」），
    也可能另起一行。不往标题层级外扩——扩到下一节就把"摘要附图：图2"和下一节的
    "图3 为……"混成一句，误伤面从此由文档排版决定。

    已经被某个标题窗口吃掉的行不再单独开一处判定：正文里"……写明摘要附图图号"这种**谈到**
    这四个字的句子会命中同一子串，各算一处就把一处指认报成两处（计数与位点同时虚胖）。
    """
    out = []
    lines = text.splitlines()
    consumed = set()
    for i, ln in enumerate(lines):
        if ABSTRACT_FIG_SECTION not in ln or i in consumed:
            continue
        win = [ln]
        if MD_HEAD_LINE.match(ln):
            j = i + 1
            while j < len(lines) and not MD_HEAD_LINE.match(lines[j]):
                win.append(lines[j])
                consumed.add(j)
                j += 1
        out.append((i + 1, '\n'.join(win)))
    return out


def abstract_figure(root, docs):
    """T8：摘要附图那句法条的两半各判各的。

    §4.5.2 前半句「说明书有附图的，申请人应当指定其中一幅……作为摘要附图，并在请求书中写明图号」
    判**有没有指认**；后半句「指定的摘要附图不是说明书附图之一的，审查员可以通知申请人补正」
    判**指认对不对**。前半句在第 47 轮登记成"判不动"，卡点是交付包里没有请求书——那个前提
    载体已被第 48 轮（`8b93842`）作废：著录项底稿就是本仓的请求书落点，`## 摘要附图` 那一节也在。
    于是四档各得其所：**底稿在、有附图、读不到指认 ⇒ 违规**；那一处**写着占位 ⇒ 未判**（还没定
    不等于没指定）；那一处在底稿里**填完了却没号 ⇒ 违规**；指认出现在底稿**之外**的文书、或包里
    压根没有那件底稿 ⇒ 未判（指认没落点，不折成违规）；包里一张附图都没有 ⇒ 不适用（法条那句的
    主语是"说明书有附图的"）。

    返回值与 T4–T6 同形状 (违规, 未判说明, 实判判据集合)：**只要真出过判决**才把 T8 记进实判
    ——读到指认、或判出"该指定却没指定"都算；占位与不适用不算（把已判折成未报是第 36 轮那批坑）。
    """
    bad, notes, seen = [], [], set()
    desig, shell = [], []
    for path, text in docs:
        for lineno, win in abstract_figure_windows(text):
            nums = ABSTRACT_FIG_NUM.findall(win)
            if nums:
                desig += [(path, lineno, n) for n in nums]
            else:
                shell.append((path, lineno, win))
    present, unnamed = present_figures(root)
    named = '、'.join(os.path.basename(p) for p in unnamed[:3]) + (' 等' if len(unnamed) > 3 else '')
    if unnamed:
        # 认不出号的图也算"有图"，但拿猜出来的号去对指定，对上了也不说明——与 T4–T6 同口径。
        notes.append(f'{root}: 图文件名认不出图号（{named}）→ T8 未判（不折成合规）')
        return bad, notes, seen
    ph_sites = [(p, l) for p, l, w in shell if PLACEHOLDER_TOKEN.search(w)]
    blank_sites = [(p, l) for p, l, w in shell if not PLACEHOLDER_TOKEN.search(w)]
    # 指认的**落点**是那件著录项底稿（第 48 轮进骨架）：包里有它，"读不到指认"才是没指定；
    # 包里根本没有那件载体时，指认没地方读 ⇒ 走未判，不折成违规——与 R16/R19"取不到载体就未判"同一条。
    carrier = [p for p, _ in docs if _cir.REQUEST_DRAFT_NAME in os.path.basename(p)]
    if not desig and not shell:
        if present and carrier:
            bad.append(f'{root}: 包里有 {len(present)} 幅说明书附图，著录项底稿（{os.path.basename(carrier[0])}）'
                       f'里却读不到任何摘要附图指认 → T8'
                       '（指南 §4.5.2 逐字「说明书有附图的，申请人应当指定其中一幅……作为摘要附图，'
                       '并在请求书中写明图号」——载体在，指认就是没写）')
            seen.add('T8')
        elif present:
            notes.append(f'{root}: 有 {len(present)} 幅说明书附图，但包里没有那件著录项底稿'
                         f'（文件名含「{_cir.REQUEST_DRAFT_NAME}」的文书），指认没有落点'
                         f' → T8 未判（§4.5.2 要图号写在请求书里，不折成违规也不折成合规）')
        else:
            notes.append(f'{root}: 没有说明书附图，也没有摘要附图指定 → T8 不适用'
                         f'（指南 §4.5.2 那句的主语是"说明书有附图的"）')
        return bad, notes, seen
    if desig:
        seen.add('T8')
    for path, lineno, n in desig:
        if n not in present:
            got = '、'.join('图' + x for x in sorted(present, key=int)) if present else '一张图都没有'
            bad.append(f'{path}:{lineno}: 摘要附图指定了 图{n}，说明书附图里没有这张（{got}）→ T8'
                       f'（指南 §4.5.2：指定的摘要附图不是说明书附图之一的，应当补正）')
    # 空白那一处按落点分档：在底稿里＝填完了却没指认 ⇒ 违规；在别的文书里只是"谈到"那一节 ⇒ 未判。
    blank_carrier = [(p, l) for p, l in blank_sites
                     if _cir.REQUEST_DRAFT_NAME in os.path.basename(p)]
    blank_other = [(p, l) for p, l in blank_sites
                   if _cir.REQUEST_DRAFT_NAME not in os.path.basename(p)]
    if blank_carrier and present:
        for path, lineno in blank_carrier:
            bad.append(f'{path}:{lineno}: 「摘要附图」那一处填完了却没有图号，'
                       f'而包里有 {len(present)} 幅说明书附图 → T8'
                       '（§4.5.2 要申请人指定一幅并写明图号；这里既读不出号、也没有占位标记，'
                       '就是"写完了却没指认"，不许躲进未判）')
        seen.add('T8')
    elif blank_carrier:
        notes.append(f'{root}: {len(blank_carrier)} 处「摘要附图」没写图号，而包里也没有说明书附图'
                     f' → T8 不适用（法条那句的主语是"说明书有附图的"）')
    if blank_other:
        where = '、'.join(f'{p}:{l}' for p, l in blank_other[:3])
        notes.append(f'{root}: {len(blank_other)} 处「摘要附图」在底稿之外（{where}）'
                     f' → T8 未判（指认的落点是著录项底稿，别处的这一行只是谈到那一节）')
    if ph_sites:
        where = '、'.join(f'{p}:{l}' for p, l in ph_sites[:3])
        notes.append(f'{root}: {len(ph_sites)} 处「摘要附图」还是占位（{where}）'
                     f' → T8 未判（没定不等于没指定，不折成违规也不折成合规）')
    return bad, notes, seen


def label_table_map(docs):
    """从文书里收集「标记｜名称」对照：只认 N 门禁那一族表（表头同时有标记与名称列）。"""
    m, found = {}, False
    for path, text in docs:
        for header, rows in _t.table_blocks(text):
            jn, jm = _t.col(header, '标记'), _t.col(header, '名称')
            if jn is None or jm is None:
                continue
            found = True
            for cs in rows:
                num = (cs[jn] if jn < len(cs) else '').strip()
                nm = (cs[jm] if jm < len(cs) else '').strip()
                if num.isdigit() and nm:
                    m.setdefault(num, nm)
    return m, found


def check_package(root, docs=None):
    """返回 (违规, 未判说明, 实判判据集合, 需按 rc=2 收场的成因或 None)。"""
    bad, notes, seen = [], [], set()
    mans, orphan = find_manifests(root)
    # 孤儿判一次就够，且不能只在"一张清单都没有"时才判：一个包画了 12 张图、
    # 只有 1 张是手画的 PNG（没有清单），按旧写法 mans 非空就跳过了整个分支——
    # 那张图上写了什么，谁都没核过，读数却是"实判判据 3 条 / 违规 0"。
    fatal = None
    if orphan:
        fatal = ('图不是 patent_figure 出的，图上写了什么无从查证 → 本次未做完整判定（rc=2）。'
                 '重画请走 scripts/patent_figure.py，别手画 PNG 就当交付件')
        notes.append(f'{root}: figures 里有 {len(orphan)} 张 PNG 没有配套 manifest'
                     f'（{("、".join(orphan[:3]))}{" 等" if len(orphan) > 3 else ""}）'
                     f'——有清单的那些照常判，但整包对账不完整')
    # 文书要先读：T4–T6 拿"正文声明的图号"对"figures 里真实存在的图号"，
    # 一个包连 figures 目录都没有时，恰恰最需要这两条（缺整批附图）。
    if docs is None:
        docs = []
        for dp, _, fs in os.walk(root):
            if os.path.basename(dp) == 'figures':
                continue
            for f in sorted(fs):
                if f.lower().endswith(('.md', '.docx')):
                    docs.append((os.path.join(dp, f), read_any(os.path.join(dp, f))))
    r_bad, r_notes, r_seen = number_reconcile(root, docs)
    bad += r_bad
    notes += r_notes
    seen |= r_seen
    # T8 也放在这一段：它只需要文书与图文件，不需要 manifest，所以必须排在
    # 下面两个"没有清单就提前收尾"的 return 之前——排在后面就等于有手画图时它不判。
    t8_bad, t8_notes, t8_seen = abstract_figure(root, docs)
    bad += t8_bad
    notes += t8_notes
    seen |= t8_seen
    if not mans:
        if orphan:
            return bad, notes, seen, fatal
        notes.append(f'{root}: 没有 figures 目录，也没有任何图 ↔ 文书的对账对象 → T1–T3 未判')
        return bad, notes, seen, None

    pool = norm('\n'.join(t for _, t in docs))

    for mp in mans:
        man, err = load_manifest(mp)
        if err:
            bad.append(err)
            continue
        fig = man['figure']
        for num, part in sorted(man['marks'].items(), key=lambda kv: str(kv[0])):
            seen.add('T1')
            if norm(part) not in pool:
                bad.append(f'{mp}（{fig}）: 标记 {num} 指向的部件「{part}」在文书里逐字找不到 → T1'
                           f'（图上出现了文书没有的部件）')
        for txt in man['texts']:
            t = norm(txt)
            if not txt.strip():
                continue
            toks = [m.group(0).strip() for m in NUM_TOKEN.finditer(t) if any(c.isdigit() for c in m.group(0))]
            if not toks:
                seen.add('T1')
                if t not in pool:
                    bad.append(f'{mp}（{fig}）: 框内文字「{txt}」在文书里逐字找不到 → T1'
                               f'（图上出现了文书没有的部件/说明）')
                continue
            seen.add('T2')
            for tok in toks:
                if tok not in pool:
                    bad.append(f'{mp}（{fig}）: 框内文字「{txt}」里的量值「{tok}」'
                               f'在文书里逐字找不到 → T2（图中数值与文书不逐字一致）')

    table, table_found = label_table_map(docs)
    if table_found and table:
        seen.add('T3')
        fig_marks = set()
        for mp in mans:
            man, err = load_manifest(mp)
            if err:
                continue
            fig_marks |= set(man['marks'])
            for num, part in sorted(man['marks'].items(), key=lambda kv: str(kv[0])):
                if num not in table:
                    bad.append(f'{mp}（{man["figure"]}）: 图上标了 {num}={part}，'
                               f'但文书那张对照表里没有 {num} → T3')
                elif table[num] != part:
                    bad.append(f'{mp}（{man["figure"]}）: 图上 {num}={part}，'
                               f'对照表里 {num}={table[num]} → T3（同号异名，图与表各说各话）')
        # T7：第二十一条"附图中未出现的附图标记不得在说明书文字部分中提及"——反向那一头。
        # T3 只从图上往外走（图有的号表里必须有），反着来没人管：表里凭空多写一行 15=缓冲垫，
        # 而任何一张图都没画过 15，N2/N3 只会核"表内自洽"，T3 也不会回头看，整包照样绿。
        # 文书侧号集合刻意只取对照表的标记列，不取正文里"名称+数字"的自由数字：
        # NUM_RUN 那支抽取会把"拉脱力 90N"的 90 也当成标记号，误伤面不可控（N3 用它是因为那里有表名当锚）。
        if not orphan:
            seen.add('T7')
            for num in sorted(table, key=int):
                if num not in fig_marks:
                    bad.append(f'{root}: 对照表写了 {num}={table[num]}，'
                               f'但没有任何一张图真的标着 {num} → T7'
                               f'（说明书文字里提及了附图里没有的附图标记，实施细则第二十一条）')
        else:
            notes.append(f'{root}: 有 {len(orphan)} 张手画 PNG 没有留底，表里的号也许正画在它上面 '
                         f'→ T7 未判（"看不见"不许折成违规）')
    elif table_found:
        notes.append(f'{root}: 文书里有标记表但一行可用对应都没有 → T3 未判')
    else:
        notes.append(f'{root}: 文书里没有「标记｜名称」对照表 → T3 未判（先过 N 门禁那条）')
    if 'T2' not in seen:
        notes.append(f'{root}: 图上一个带数值的文字都没有 → T2 未判（不是没写，是没触发）')
    return bad, notes, seen, fatal


def main():
    import argparse
    ap = argparse.ArgumentParser(description='图 ↔ 文书对账 T1–T8')
    ap.add_argument('targets', nargs='+', help='交付包目录（含 figures/ 与 01/02 段文书）')
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
    fatal_all = None
    for root in roots:
        bad, notes, seen, fatal = check_package(root)
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if seen else 0
        total += len(bad)
        fatal_all = fatal_all or fatal
        print(f'{root}: 违规 {len(bad)}｜实判判据 {len(seen)} 条')
    print(f'合计违规 {total}（规则 T1–T8，判据见脚本 docstring）；实判 {judged} 个包')
    if total:
        # 真找到的违规不许被"对账不完整"降级成环境档：先报违规，再补一句不完整在哪
        if fatal_all:
            print(f'另有: {fatal_all}')
        sys.exit(1)
    if fatal_all:
        print(f'输入不完整: {fatal_all}')
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main()
