#!/usr/bin/env python3
"""法规与裁决文书门禁：把 evt-and-regulatory §4/§5 里可机械判定的部分做成会咬人的判据。

适用域（与 R8/E 同一套"路径 or 正文节标题"分轴思路）：交付包 05_法规与裁决/ 目录内的文书，
或正文出现「适用性判定 / 逐条映射 / 合规缺口 / 裁决总表」这类表名的文书。域外一律报未判。

判据（G1–G5）：
  G1 适用性判定表：判定列必须落在 适用 / 不适用 / 部分适用 三态之一（恰一个），且依据列非空。
     三态是规程写死的口径；写成"基本适用""待确认"等于没判。
  G2 逐条映射表：结论列必须落在 符合 / 不符合 / 无法判定 三态之一（恰一个）。
     "无法判定"是合法结论，空着或写"详见正文"不是。
  G3 合规缺口清单：每行必须给出 修订建议 或 实测规程 至少一个，否则缺口没有关闭路径。
  G4 裁决总表四要素：结论 / 依据 / 约束 / 生效范围 四列都要非空；且依据必须引 EVT 侧证据
     （复算 / 仿真 / FMEA / 公差分析 / 实测），或按规程明写"维持冻结值，转 EVT 实测裁决"。
  G5 送检清单的费用与周期须带"公开…估算"口径——数字不带口径就像承诺过的报价。

表头整列缺失只报一条（缺列），不逐行放大成 N 条；缺列属结构问题，**空表也照报**
（骨架底稿只有表头，若"没行就不看列"，表头掉一列永远不会出声）。行列数与表头不符时不按位取值，
报格式错（按位读会把"依据"当成"约束"，静默读错列比报一条格式错更糟）。
只有表头没有数据行的表、以及文书里根本没有的表，一律报"未判"而不是判红——缺席的表
可能是这份文书本就不含（裁决书没有送检清单很正常）。唯一例外：05_法规与裁决/ 目录内
的交付文书一张表都没有，那是载体缺席，判红。

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

REG_DIR = re.compile(r'05_法规与裁决')
REG_SCOPE = re.compile(r'适用性判定|逐条映射|合规缺口|裁决总表|送检包清单')

EVT_EVIDENCE = re.compile(r'复算|仿真|FMEA|公差分析|实测|EVT')
DEFER = re.compile(r'维持冻结值.*转.*实测裁决|转\s*EVT\s*实测裁决')
COST_COLS = ('费用', '周期', '报价', '时间')
# G5 只认"公开信息估算"这类明写：一个数字不带口径就像报过的价。
ESTIMATE = re.compile(r'公开[^|]{0,10}估算|估算[^|]{0,10}公开')
NUM = re.compile(r'\d')


def in_scope(path, text):
    return bool(REG_DIR.search(path) or REG_SCOPE.search(text))


# 状态词要按"整词"命中：不适用/部分适用 都含 适用，符合/不符合 互为子串，
# 光看子串会把"基本适用""符合性"这种含糊措辞当成已判。故要求命中位置的前后
# 是边界（行首、空白、顿号、括号、斜杠、句读）或串首串尾。
BEFORE = set(' \t、，,;；:：/|（(【[。<〈『「')
AFTER = set('、，,;；:：/|）)】>]。〉』」 \t')


def has_state(text, name):
    start = 0
    while True:
        k = (text or '').find(name, start)
        if k < 0:
            return False
        prev = text[k - 1] if k > 0 else ''
        end = k + len(name)
        nxt = text[end] if end < len(text) else ''
        if (not prev or prev in BEFORE) and (not nxt or nxt in AFTER or nxt in '（('):
            return True
        start = k + 1
    return False


def which_states(text, names):
    return [n for n in names if has_state(text, n)]


APPLIC_NAMES = ('适用', '不适用', '部分适用')
MAP_NAMES = ('符合', '不符合', '无法判定')


def _tri(value, names, label, where, tag, bad):
    """三态判据：判定格必须恰好落进 names 之一。一个都没命中＝没判；
    命中两个＝自相打架（"适用 不适用"这种并列在法规文书里等于把结论推给读者）。"""
    hits = which_states(value, names)
    if not hits:
        bad.append(f'{where} {label}列未落三态（须 {"/".join(names)} 恰一个），'
                   f'实得「{(value or "")[:20]}」→ {tag}')
    elif len(hits) > 1:
        bad.append(f'{where} {label}列同时出现 {hits} → {tag}')


def cell(cs, j):
    """按列号取格；列号缺失或该行格子不够时返回空串（不够的情况已在 ragged 里报掉）。"""
    return cs[j] if j is not None and j < len(cs) else ''


def _columns(header):
    """一张表的列位。列名口径与 templates 的法规/裁决文书格式节同源；同义词按较宽的
    收——漏认一列会让整条判据静默不判，那比误判更难发现。"""
    return {
        'std': _t.col(header, '标准', '法规'),
        'ap': _t.col(header, '判定', '适用性'),
        'basis': _t.col(header, '依据', '出处'),
        'clause': _t.col(header, '条款'),
        'concl': _t.col(header, '结论'),
        'gap': _t.col(header, '缺口'),
        'fix': _t.col(header, '修订建议', '整改'),
        'test': _t.col(header, '实测规程', '送检', '实测项'),
        'conf': _t.col(header, '冲突', '裁决项'),
        'constraint': _t.col(header, '约束'),
        'scope': _t.col(header, '生效范围'),
        'cost': _t.cols(header, *COST_COLS),
    }


def header_tags(J):
    """表头命中哪些判据——只看列在不在，不看行。命不中的判据走未判，不判红。"""
    hit = []
    if J['ap'] is not None and J['std'] is not None:
        hit.append('G1')
    if J['concl'] is not None and (J['clause'] is not None or J['std'] is not None):
        hit.append('G2')
    if J['gap'] is not None:
        hit.append('G3')
    if J['conf'] is not None and J['concl'] is not None:
        hit.append('G4')
    if J['cost']:
        hit.append('G5')
    return hit


def check_text(path, text):
    """返回 (违规列表, 未判说明列表, 实际判到的判据集合)。"""
    bad, notes, seen = [], [], set()
    if not in_scope(path, text):
        return [], [f'{path}: 非法规/裁决文书（路径不含 05_法规与裁决，正文无相关表名），'
                    f'G1–G5 未判'], seen

    tables = list(_t.table_blocks(text))
    empty = set()     # 有表头没行的表：已经按表报过未判，不再按判据重复一条
    if not tables and REG_DIR.search(path):
        # 规程 §4/§5 要求裁决登记与适用性判定都以表为载体。05 目录下的交付文书一张表
        # 都没有，等于载体缺席——报红而不是五连"未判"，否则散文写的裁决书会白过。
        # 只是正文提到这些表名的规则文档（不在 05 目录）不走这条，按未判处理。
        bad.append(f'{path}: 05_法规与裁决 目录下的文书没有任何表格 → G1–G5 无从判起'
                   f'（evt-and-regulatory §4/§5 要求适用性判定表与裁决总表）')
        return bad, notes, seen
    for tno, (header, rows) in enumerate(tables, 1):
        where_t = f'{path}: 表{tno}'
        J = _columns(header)
        tags = header_tags(J)
        good, ragged = [], []
        for k, cells in enumerate(rows):
            (good if len(cells) == len(header) else ragged).append(k + 1)
        if ragged:
            notes.append(f'{where_t} 第{"、".join(map(str, ragged))}行列数与表头 '
                         f'{len(header)} 列不符，不按位取列 → 这些行未判')
        # 结构性缺列先判，且排在"空表未判"之前：骨架底稿只有表头没有行，若先看行数，
        # "表头掉了一列"就永远不出声——那正是骨架与判据漂移的形状。
        g4_missing = ([n for n, j in (('依据', J['basis']), ('约束', J['constraint']),
                                      ('生效范围', J['scope'])) if j is None]
                      if 'G4' in tags else [])
        if 'G1' in tags and J['basis'] is None:
            bad.append(f'{where_t} 适用性判定表缺「依据」列 → G1（整表报一条，不逐行放大）')
        if 'G3' in tags and J['fix'] is None and J['test'] is None:
            bad.append(f'{where_t} 缺口清单既无「修订建议」也无「实测规程」列 → G3')
        if g4_missing:
            bad.append(f'{where_t} 裁决表缺列 {g4_missing} → G4'
                       f'（结论+依据+约束+生效范围是四要素）')
        if not rows:
            # 有表头没行＝架子搭了、一条没判。判红会和"这份文书本来不含该类表"混成
            # 同一种读数，所以报未判并点名命中了哪些判据，交人核。
            # 表头连一条判据都不命中的表（专利清单之类）不报，否则每份文书都会被
            # 一堆与法规无关的表刷满未判说明。
            if tags:
                notes.append(f'{where_t} 只有表头没有数据行 → 本表 {"、".join(tags)} 未判')
                empty.update(tags)
            continue
        seen.update(tags)
        good_rows = [(k, rows[k - 1]) for k in good]

        if 'G1' in tags:
            for rno, cells in good_rows:
                where = f'{where_t} 第{rno}行'
                _tri(cell(cells, J['ap']), APPLIC_NAMES, '判定', where, 'G1', bad)
                if J['basis'] is not None and not cell(cells, J['basis']).strip():
                    bad.append(f'{where} 有判定却无依据 → G1')
        if 'G2' in tags:
            for rno, cells in good_rows:
                _tri(cell(cells, J['concl']), MAP_NAMES, '结论',
                     f'{where_t} 第{rno}行', 'G2', bad)
        if 'G3' in tags and (J['fix'] is not None or J['test'] is not None):
            for rno, cells in good_rows:
                if not cell(cells, J['fix']).strip() and not cell(cells, J['test']).strip():
                    bad.append(f'{where_t} 第{rno}行 缺口既无修订建议也无实测规程 → G3')
        if 'G4' in tags and not g4_missing:
            for rno, cells in good_rows:
                where = f'{where_t} 第{rno}行'
                for name, j in (('结论', J['concl']), ('依据', J['basis']),
                                ('约束', J['constraint']), ('生效范围', J['scope'])):
                    if not cell(cells, j).strip():
                        bad.append(f'{where} 裁决缺「{name}」 → G4')
                basis = cell(cells, J['basis'])
                if basis.strip() and not (EVT_EVIDENCE.search(basis) or DEFER.search(basis)):
                    bad.append(f'{where} 裁决依据既未引 EVT 侧证据也未写"转实测裁决"：'
                               f'{basis[:24]} → G4')
        if 'G5' in tags:
            for rno, cells in good_rows:
                for j in J['cost']:
                    v = cell(cells, j)
                    if NUM.search(v) and not ESTIMATE.search(v):
                        bad.append(f'{where_t} 第{rno}行 费用/周期给了数字却未标"公开信息估算"：'
                                   f'{v[:24]} → G5')

    for tag, name in (('G1', '适用性判定表'), ('G2', '逐条映射表'), ('G3', '合规缺口清单'),
                      ('G4', '裁决总表'), ('G5', '送检费用清单')):
        if tag not in seen and tag not in empty:
            notes.append(f'{path}: 未出现有数据行的{name} → {tag} 未判'
                         f'（该类表缺席不判红，交由人核）')
    return bad, notes, seen


def main():
    import argparse
    ap = argparse.ArgumentParser(description='法规与裁决文书门禁 G1–G5')
    ap.add_argument('targets', nargs='+', help='法规/裁决文书 .md，或配合 --all 传交付包目录')
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
        res = check_text(p, text)
        bad, notes, judged_tags = res[0], res[1], res[2]
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if in_scope(p, text) else 0
        total += len(bad)
        print(f'{p}: 违规 {len(bad)}｜实判判据 {len(judged_tags)} 条')
    print(f'合计违规 {total}（规则 G1–G5，判据见脚本 docstring）；实核法规文书 {judged} 份')
    if judged == 0:
        print('没有一份落在法规/裁决适用域内 → 本次未做任何判定（rc=2），不当作"已通过"')
        sys.exit(2)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
