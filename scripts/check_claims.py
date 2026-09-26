#!/usr/bin/env python3
"""权利要求结构门禁 Q1–Q5：把 hard-rules §4 里"形状可机判"的那几条从人记变成实跑。

法源逐字对过《专利法实施细则》（2023 修订，国务院令第 769 号）正文：
  第二十二条「权利要求书有几项权利要求的，应当用阿拉伯数字顺序编号」
            「该标记应当放在相应的技术特征后并置于括号内」
  第二十三条「权利要求书应当有独立权利要求」
  第二十四条「……应当只有一个独立权利要求，并写在……从属权利要求之前」
  第二十五条「从属权利要求只能引用在前的权利要求」
            「……只能以择一方式引用在前的权利要求，并不得作为另一项多项从属权利要求的基础」
条号与原文由本人重开官方页面核对（不是转述）；§4 里"独权须落在区别特征上""设计目标值撤出权要"
这类要读懂技术方案才能判的，仍然归 reviewer，本门禁不冒充。

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

三态：交付包里没有可识别的"权利要求书"节 ⇒ Q1–Q5 全部未判（有的交付形态把权要交给代理机构写）；
      有节但一行权项都解析不出 ⇒ Q1–Q4 未判并说清读到了什么；
      没有标记对照表 ⇒ Q5 未判（括号形状没有可对照的号集）。
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


def read_any(path):
    try:
        return _cir.read_text(path)
    except Exception as e:
        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')
        sys.exit(2)


def claims_body(text):
    """返回权利要求书节的 (起始行号, 该节正文行)；找不到节返回 (None, [])。"""
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
    return start, body


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


def check_text(path, text, name2num, marks_found):
    """返回 (违规, 未判/提示, 实判判据集合)。"""
    bad, notes, seen = [], [], set()
    cstart, body = claims_body(text)
    if cstart is None:
        return [], [f'{path}: 没有「权利要求书」节 → Q1–Q5 未判'
                    f'（权要由代理机构撰写时本就没有这一节）'], seen
    items = split_items(body)
    if not items:
        return [], [f'{path}: 有权利要求书节但一行权项都没解析出（不以「N.」起头？）'
                    f' → Q1–Q4 未判'], seen
    where = lambda off: f'{path}:{cstart + 1 + off}'

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


def check_package(root):
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
            b, n, s = check_text(path, text, name2num, marks_found)
            bad += b
            notes += n
            seen |= s
    if not hit:
        notes.append(f'{root}: 包内没有任何文书带「权利要求书」节 → Q1–Q5 未判')
    return bad, notes, seen


def main():
    ap = argparse.ArgumentParser(description='权利要求结构门禁 Q1–Q5（只接目录）')
    ap.add_argument('targets', nargs='+', help='交付包目录')
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
        bad, notes, seen = check_package(root)
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if seen else 0
        total += len(bad)
        print(f'{root}: 违规 {len(bad)}｜实判判据 {len(seen)} 条')
    print(f'合计违规 {total}（规则 Q1–Q5，判据见脚本 docstring）；实判 {judged} 个包')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
