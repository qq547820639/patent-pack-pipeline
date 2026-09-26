#!/usr/bin/env python3
"""附图标记对照表门禁 N1–N4：把 hard-rules §5「附图说明节末必备 标记｜名称｜所在图号 对照表」
与「同一部件同号、不得出现文书没有的标记」做成能实跑的判据。

为什么不引现成实现（本轮真实检索过的项目，见 README §6 的调研记录）：
  · patentsmartindia/patent-reference-numeral-checker（HTML+JS，无 LICENSE，2021 后未更新）：
    思路可借——把「同号配多名」当作缺陷；但它的词边界写死为英文虚词表（"the "/" of " 等），
    中文正文一律失效，且无 LICENSE 意味着不得复制代码，只能借鉴做法。
  · Wujiamu/PatentCAD-Annotator（C#，MIT，活跃）：从 Word 抽标记说明是为了往 CAD 里放引线，
    不是形式审查；移植等于用 Python 重写，还带进 AutoCAD/Word 互操作依赖。
  · friedrichscheele/ReferenceNumerals：仓库为空（API 报 409，size 0），没有可读实现。
所以这里沿用本仓库的 mdtable 共用读取（Python 3.9 可裸跑是硬约束，markdown-it-py 要 ≥3.10），
只借第一项的"同号异名"对账方向，且把词表取自对照表本身而不是自造抽取器。

判据：
  N1 该文书确实有「附图说明」节时，必须有标记说明表且三列齐（标记/名称/所在图号）。
     缺列排在"空表未判"之前判——骨架底稿只有表头没有行，先看行数就永远不出声。
     判红只发给"该有这张表的人"：路径在 02_申请文件 或正文提过「标记说明」。
     交底书这类内部文书有附图说明节却没表 → 报未判并说成因，不硬判红。
  N2 表内逐行：标记须为纯阿拉伯数字（CNIPA 要求附图用阿拉伯数字标记），三格非空；
     同一标记号不得挂两个名称、同一名称不得挂两个标记号（表内自相矛盾）。
  N3 正文↔表对账：正文里「表内名称 + 数字」式引用，数字必须等于表里该名称的标记号。
     词表取自权威表，不猜未登记的名称；名称前紧邻更长前缀时（"弹性支架"里的"支架"）
     可能是另一件未登记的零件，计入"未核"注记而不是判红——宁可漏报不误伤。
  N4 表内「所在图号」必须是本文书真的声明过的图号；图号集合取自正文（表格行遮掉后再取），
     否则表自己写的"图7"会把 7 变成已声明，这条判据就成了自证。
     文书没声明任何图号时 N4 走未判。

适用域（三条轴，任一命中即域内）：路径含 02_申请文件；正文出现「附图说明/标记说明」；
或正文里真有一张被 is_label_table() 认出来的表（写了表却没提名字也算域内）。
域外一律未判。

退出码: 0 合规 / 1 存在违规 / 2 输入不可用，或域内一份文书都没有（未做任何判定）。
"""
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

def read_any(path):
    """md 直读；docx 交给 check_iron_rules 那份唯一实现（DTD/压缩炸弹拒绝 + 表格还原成
    markdown 管道行）。这里不另写第二份 docx 解析——两套读取迟早在一句话的两种写法上打架。
    读不动必须报成因并 rc=2：把 .docx 当 md 读会抛 UnicodeDecodeError，而 traceback 的
    退码 1 在门禁语境里等于宣布"发现违规"，那是最坏的假红。"""
    try:
        return _cir.read_text(path)
    except Exception as e:
        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')
        sys.exit(2)

FIG_DIR = re.compile(r'02_申请文件')
FIG_SCOPE = re.compile(r'附图说明|标记说明')
FIG_WORD = re.compile(r'标记说明')
FIG_TAG = re.compile(r'^#{1,6}\s.*附图说明')
# 数字后紧跟这些就当成量值而非标记号（"底座 12mm"、"2015 年"、"3 倍"）。
UNIT_TAIL = re.compile(r'\s*(?:mm|cm|kg|MPa|kN|N·m|℃|%|毫米|厘米|分米|米|千克|公斤|吨|牛|秒|转|倍|个|件|次|年|月|日|元)')
NUM_RUN = re.compile(r'([一-鿿A-Za-z]+)[ 　]{0,2}(\d+)')
# 名称前的合法边界字：所述/该/上述/的/连接/与… 这类冠词或标点。前一个字不在这里、
# 又确实还有前缀时，说明匹配到的名称只是更长名称的尾巴，不能拿来判。
BOUND_BEFORE = set('述的了，,、（()（ 　和与或为在至由经图示')
CJK = re.compile(r'[一-鿿]')

COLS = ('标记', '名称', '所在图号')
NAME_TAG = '附图标记说明表'
# 骨架底稿的小节骨架（new_product_package 从这里生成，列名不在那份脚本里重抄）
DOC_SECTIONS = (('附图说明', '（逐幅写：图 N 为……；N 从 1 起顺序编号，一幅一行）'),
                ('图中标记说明', None))


def header_row():
    return '| ' + ' | '.join(COLS) + ' |'


def separator_row():
    return '|' + '---|' * len(COLS)


def cell(cs, j):
    return cs[j] if j is not None and j < len(cs) else ''


def is_label_table(header):
    """识别规则：有「标记」列，且「名称」「所在图号」至少一个在场。
    为什么不要求三列全中：底稿掉了哪一列，判据就该说"缺这一列"；若把掉列的表认成
    "不是这张表"，报出来的就是"没有对照表"——症状相同、成因不同，读者会去补一张新表
    而不是改回列名。也不接受只有「标记」一列的表：那种表在这里无从对账，交给 N1 的
    "有附图说明节却无表"那条说话。"""
    if _t.col(header, '标记') is None:
        return False
    return (_t.col(header, '名称') is not None or _t.col(header, '所在图号') is not None)


def in_scope(path, text):
    if FIG_DIR.search(path) or FIG_SCOPE.search(text):
        return True
    return any(is_label_table(h) for h, _ in _t.table_blocks(text))


def figure_numbers(prose):
    """文书声明过的图号集合（图1/图 1/图 12）。"""
    return {m.group(1) for m in re.finditer(r'图[ 　]?(\d+)(?!\d)', prose)}


def prose_only(text):
    """遮掉表格行后的正文：N3/N4 都要拿"作者说的话"去对"表里填的格"，
    若把表格行也算进正文，N4 会拿表自己的 所在图号 当声明来源（自证），
    N3 会把表内名称+标记当成正文错配。"""
    return '\n'.join(ln for ln in text.splitlines() if not ln.strip().startswith('|'))


def check_text(path, text):
    """返回 (违规列表, 未判/未核说明列表, 实际判到的判据集合)。"""
    bad, notes, seen = [], [], set()
    if not in_scope(path, text):
        return [], [f'{path}: 非附图文书（路径不含 02_申请文件，正文无「附图说明/标记说明」，'
                    f'也没有认出标记说明表），N1–N4 未判'], seen

    tables = list(_t.table_blocks(text))
    label = [(tno, h, r) for tno, (h, r) in enumerate(tables, 1) if is_label_table(h)]
    has_fig_section = any(FIG_TAG.match(ln) for ln in text.splitlines())

    if not label:
        if has_fig_section and (FIG_DIR.search(path) or FIG_WORD.search(text)):
            bad.append(f'{path}: 有「附图说明」节却没有图中标记说明对照表 → N1'
                       f'（hard-rules §5 要求三列对照表必备）')
        elif has_fig_section:
            notes.append(f'{path}: 有附图说明节但既不在 02_申请文件 也没提「标记说明」→ N1 未判'
                         f'（对照表是说明书的形式要求，交底书这类内部文书不硬判）')
        else:
            notes.append(f'{path}: 既无附图说明节也无标记说明表 → N1–N4 未判'
                         f'（本份文书不含该类表，不判红）')
        return bad, notes, seen

    prose = prose_only(text)
    idx = figure_numbers(prose)
    if not idx:
        notes.append(f'{path}: 正文没有「图N」式图号声明 → N4 未判（表里的所在图号无从比对）')

    # 两张表都可能给词表供料，所以映射在表循环之外累积：写在循环里时，
    # 一旦某张表因缺列/零行提前 continue，N3 阶段就会读到没绑定的名字。
    num2name, name2num = {}, {}
    for tno, header, rows in label:
        where_t = f'{path}: 表{tno}'
        seen.add('N1')
        J = {k: _t.col(header, k) for k in COLS}
        missing = [k for k, j in J.items() if j is None]
        if missing:
            bad.append(f'{where_t} {NAME_TAG}缺列 {missing} → N1（整表报一条，不逐行放大）')
            continue
        good, ragged = [], []
        for k, cs in enumerate(rows):
            (good if len(cs) == len(header) else ragged).append(k + 1)
        if ragged:
            notes.append(f'{where_t} 第{"、".join(map(str, ragged))}行列数与表头 '
                         f'{len(header)} 列不符，不按位取列 → 这些行未判')
        if not rows:
            notes.append(f'{where_t} 只有表头没有数据行 → 本表 N2 未判')
            continue
        seen.add('N2')
        for rno, cs in [(k, rows[k - 1]) for k in good]:
            where = f'{where_t} 第{rno}行'
            for name in COLS:
                if not cell(cs, J[name]).strip():
                    bad.append(f'{where} 「{name}」空着 → N2')
            m = cell(cs, J['标记']).strip()
            if m and not re.fullmatch(r'\d+', m):
                bad.append(f'{where} 标记「{m[:16]}」不是阿拉伯数字 → N2'
                           f'（附图用阿拉伯数字标记）')
                continue
            nm = cell(cs, J['名称']).strip()
            if m.isdigit() and nm:
                if m in num2name and num2name[m] != nm:
                    bad.append(f'{where} 标记 {m} 在表内既指「{num2name[m]}」又指「{nm}」→ N2')
                else:
                    num2name.setdefault(m, nm)
                if nm in name2num and name2num[nm] != m:
                    bad.append(f'{where} 名称「{nm}」在表内既挂 {name2num[nm]} 又挂 {m} → N2')
                else:
                    name2num.setdefault(nm, m)
            fg = cell(cs, J['所在图号']).strip()
            if fg and idx:
                seen.add('N4')
                for fno in re.findall(r'\d+', fg):
                    if fno not in idx:
                        bad.append(f'{where} 所在图号 图{fno} 不在本文声明的图号集合 '
                                   f'{sorted(int(x) for x in idx)[:12]} 内 → N4')

    # N3：正文（遮掉表格行）里的「表内名称+数字」必须与表一致
    if name2num:
        seen.add('N3')
        amb = 0
        for m in NUM_RUN.finditer(prose):
            pre, num = m.group(1), m.group(2)
            if UNIT_TAIL.match(prose[m.end():m.end() + 6]):
                continue
            cands = [nm for nm in name2num if pre.endswith(nm)]
            if not cands:
                continue
            nm = max(cands, key=len)
            before = pre[:len(pre) - len(nm)]
            if before and before[-1] not in BOUND_BEFORE:
                amb += 1
                continue
            if num != name2num[nm]:
                bad.append(f'{path}: 正文写「{pre} {num}」，而表内「{nm}」的标记是 '
                           f'{name2num[nm]} → N3（同号异名/异号同名）')
        if amb:
            notes.append(f'{path}: {amb} 处名称前还有未登记的前缀，无法确定是不是同一零件 → '
                         f'N3 未核（不判红也不折成合规）')
    else:
        notes.append(f'{path}: 表内没有可用的「标记→名称」对应 → N3 未判')
    return bad, notes, seen


def main():
    import argparse
    ap = argparse.ArgumentParser(description='附图标记对照表门禁 N1–N4')
    ap.add_argument('targets', nargs='+', help='说明书/附图文书 .md，或配合 --all 传交付包目录')
    ap.add_argument('--all', action='store_true', help='递归目录下所有 .md 与 .docx（域外自动走未判）')
    args = ap.parse_args()

    paths = []
    for p in args.targets:
        if args.all and os.path.isdir(p):
            for dp, _, fs in os.walk(p):
                paths += [os.path.join(dp, f) for f in sorted(fs) if f.lower().endswith(('.md', '.docx'))]
        elif os.path.isfile(p):
            paths.append(p)
        elif args.all:
            print(f'--all 需要目录，实得不是目录: {p}（未做任何判定）')
            sys.exit(2)
        else:
            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')
            sys.exit(2)
    if not paths:
        print('输入不可用，未做任何判定: 未找到任何 .md')
        sys.exit(2)

    total = judged = 0
    for p in paths:
        text = read_any(p)
        bad, notes, tags = check_text(p, text)
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if in_scope(p, text) else 0
        total += len(bad)
        print(f'{p}: 违规 {len(bad)}｜实判判据 {len(tags)} 条')
    print(f'合计违规 {total}（规则 N1–N4，判据见脚本 docstring）；实核附图标记文书 {judged} 份')
    if judged == 0:
        print('没有一份落在附图标记适用域内 → 本次未做任何判定（rc=2），不当作"已通过"')
        sys.exit(2)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
