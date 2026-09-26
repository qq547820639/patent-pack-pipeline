#!/usr/bin/env python3
"""图↔文书对账 T1–T3：把 hard-rules §5 最后两条纯承诺变成能实跑的判据——
「图中数值与文书逐字一致」「不得出现交底书没有的部件/参数」。

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

三态：没有 figures 目录 ⇒ 未判（有的交付形态本就没有图）；
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
    if not mans:
        if orphan:
            return [], notes, seen, fatal
        notes.append(f'{root}: 没有 figures 目录，也没有任何图 ↔ 文书的对账对象 → T1–T3 未判')
        return bad, notes, seen, None

    if docs is None:
        docs = []
        for dp, _, fs in os.walk(root):
            if os.path.basename(dp) == 'figures':
                continue
            for f in sorted(fs):
                if f.lower().endswith(('.md', '.docx')):
                    docs.append((os.path.join(dp, f), read_any(os.path.join(dp, f))))
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
    ap = argparse.ArgumentParser(description='图 ↔ 文书对账 T1–T3')
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
    print(f'合计违规 {total}（规则 T1–T3，判据见脚本 docstring）；实判 {judged} 个包')
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
