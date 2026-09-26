#!/usr/bin/env python3
"""图↔文书对账 T1–T6：把 hard-rules §5 最后两条纯承诺变成能实跑的判据——
「图中数值与文书逐字一致」「不得出现交底书没有的部件/参数」——
外加《专利法实施细则》点名却全仓无人核的图号三对账（T4 缺图 / T5 图未被引用 / T6 跳号）。

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

三态：没有 figures 目录 ⇒ 未判（有的交付形态本就没有图）；      图文件名认不出图号（主视图.png 之类）⇒ T4–T6 未判，不去猜号——猜错会把缺号判成不缺；
      figures 里有 PNG 却没有 manifest ⇒ rc=2 说"图不是本库出的，无从对账"——
      这不是违规，但绝不是"核过了"。这一条与"有没有别的图带着清单"无关：
      12 张图里混 1 张手画 PNG，那张图上写着什么同样没人核过，包级对账就不完整。

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
        for mp in mans:
            man, err = load_manifest(mp)
            if err:
                continue
            for num, part in sorted(man['marks'].items(), key=lambda kv: str(kv[0])):
                if num not in table:
                    bad.append(f'{mp}（{man["figure"]}）: 图上标了 {num}={part}，'
                               f'但文书那张对照表里没有 {num} → T3')
                elif table[num] != part:
                    bad.append(f'{mp}（{man["figure"]}）: 图上 {num}={part}，'
                               f'对照表里 {num}={table[num]} → T3（同号异名，图与表各说各话）')
    elif table_found:
        notes.append(f'{root}: 文书里有标记表但一行可用对应都没有 → T3 未判')
    else:
        notes.append(f'{root}: 文书里没有「标记｜名称」对照表 → T3 未判（先过 N 门禁那条）')
    if 'T2' not in seen:
        notes.append(f'{root}: 图上一个带数值的文字都没有 → T2 未判（不是没写，是没触发）')
    return bad, notes, seen, fatal


def main():
    import argparse
    ap = argparse.ArgumentParser(description='图 ↔ 文书对账 T1–T6')
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
    print(f'合计违规 {total}（规则 T1–T6，判据见脚本 docstring）；实判 {judged} 个包')
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
