#!/usr/bin/env python3
"""EVT 报告诚实性门禁：把 evt-and-regulatory §1/§3 里可机械判定的那部分变成会咬人的判据。

适用域：交付包 04_EVT验证/ 下的报告，或正文含「投产判定/投产总则」的文书（路径与正文
分轴，判据对象定义与 R8 同源，见 check_iron_rules.EVT_DIR / EVT_SCOPE）。域外文书一律
报"未判"，不折成合规。

判据（E1–E4；投产总则逐字由 R8 管，这里不重复一条）：
  E1 判定必须落在三态内：判定格只能出现 ✅ / ⚠️ / ❌ 之一，且恰好一个。
     空判定、"基本通过"这类无符号措辞、或同时给两个符号都判红——三态是
     "准许试制 / 列缺口 / 给改法"的入口，含糊等于没判。
  E2 非 ✅ 必须带下一步：⚠️ 须出现"缺口"与"关闭判据"，❌ 须出现"改法"。
     只写不通过而不给改法，等于把决策成本推回给读者。
  E3 物理实测列不得有实测值：物理实测项只允许"测试规程+预测值+合格判据+待物理实测"。
     出现量值却没有"待物理实测/Not Run/预测值"字样 → 判红（对应"严禁编造实测数据"）。
     标准号/法规号/IPC 号里的数字先摘掉再找量值，否则 GB/T 35270 本身就是假阳性。
  E4 复算偏差>10% 必须标注：同一行同时给出设计值与复算值时算相对偏差，超 10% 而未写
     "偏差/原因"即判红；缺一侧、或设计值为 0 使相对偏差无定义时按"未判"三态处理。

退出码: 0 合规 / 1 存在违规 / 2 输入不可用，或目录内根本没有 EVT 域内文书
        （未做任何判定，不当作"已通过"）。
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
_cir = _load('check_iron_rules')
EVT_DIR, EVT_SCOPE = _cir.EVT_DIR, _cir.EVT_SCOPE

VERDICTS = ('✅', '⚠️', '❌')
WARN, FAIL = '⚠', '❌'
VS16 = '️'
NUM = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
PENDING = re.compile(r'待物理实测|Not Run|未实测|预测值|预估值')
# E3 只认"量值"：数字带单位，或"测得/实测/结果"紧跟数字。
# 这样标准号（GB/T 31701-2015）、条款号（第 4.3 条）、IPC/ECLA 码（A42B3/00）天然不在其列，
# 不必再维护一张"引用号长什么样"的豁免表——那种表永远缺一种写法。
UNIT = r'(?:mm|cm|kg|mg|g|kN|N·m|N|MPa|kPa|℃|°|Hz|dB|ms|min|%|次|只|件|组|人|例)'
UNIT_NUM = re.compile(rf'{NUM}\s*{UNIT}\b')
VERB_NUM = re.compile(rf'(?:测得|实测值|实测|结果)\s*[:：=]?\s*{NUM}')
DESIGN_VAL = re.compile(rf'(?:设计值|名义值)\s*[:：=]?\s*({NUM})')
RECALC_VAL = re.compile(rf'(?:复算值|复算|独立复算|重算)\s*[:：=]?\s*({NUM})')
DEV_ANNO = re.compile(r'偏差|原因')
GAP_WORDS = ('缺口', '关闭判据')
FIX_WORDS = ('改法',)


def in_scope(path, text):
    return bool(EVT_DIR.search(path) or EVT_SCOPE.search(text))


def tables(text):
    """产出 (表头, [数据行])——只认含「判定」或「实测」列的表；分行/取列由 mdtable 唯一实现。"""
    for header, rows in _t.table_blocks(text):
        if _t.col(header, '判定') is not None or _t.col(header, '实测') is not None:
            yield header, rows


def check_text(path, text):
    """返回 (违规列表, 未判列表)。"""
    bad, notes = [], []
    by_path = bool(EVT_DIR.search(path))
    by_text = bool(EVT_SCOPE.search(text))
    if not (by_path or by_text):
        return [], [f'{path}: 非 EVT 文书（路径不含 04_EVT，正文无「投产判定/投产总则」），'
                    f'E1–E4 未判']

    found = list(tables(text))
    has_verdict = any(_t.col(h, '判定') is not None for h, _ in found)
    if not has_verdict:
        # 模板 §5 第 1 项就是"验证总表（…判定 ✅⚠️❌）"。交付物缺这张表要判红，
        # 否则"用散文写的 EVT 报告"会在 E1–E3 上白白通过——没载体不等于已核过。
        # 规则文档只是正文提到"投产判定"，不是交付物，报未判而不是判红。
        if by_path:
            bad.append(f'{path}: 未找到含「判定」列的验证总表 → E1–E3 无从判起'
                       f'（templates §5 第 1 项要求每项设计一行给出判定）')
        else:
            notes.append(f'{path}: 正文提到投产判定但不在 04_EVT 目录内，且无判定列表格'
                         f'→ E1–E3 未判（仅 E4 逐行核）')
    for tno, (header, rows) in enumerate(found, 1):
        jv = _t.col(header, '判定')
        jp = _t.col(header, '实测')
        for rno, cells in enumerate(rows, 1):
            where = f'{path}: 表{tno} 第{rno}行'
            if jv is not None and jv < len(cells):
                v = cells[jv].replace(VS16, '')
                present = [x for x in VERDICTS if x.replace(VS16, '') in v]
                if not present:
                    bad.append(f'{where} 判定列未落三态（须 ✅/⚠️/❌ 恰一个），'
                               f'实得「{cells[jv][:20]}」→ E1')
                elif len(present) > 1:
                    bad.append(f'{where} 判定列同时出现 {present} → E1')
                elif present[0].startswith(WARN) and not all(w in v for w in GAP_WORDS):
                    bad.append(f'{where} ⚠️ 未同时列缺口与关闭判据 → E2')
                elif present[0].startswith(FAIL) and not any(w in v for w in FIX_WORDS):
                    bad.append(f'{where} ❌ 未给改法 → E2')
            if jp is not None and jp < len(cells):
                cell = cells[jp]
                if (UNIT_NUM.search(cell) or VERB_NUM.search(cell)) and not PENDING.search(cell):
                    bad.append(f'{where} 物理实测列出现疑似实测值「{cell[:24]}」'
                               f'却无"待物理实测/Not Run/预测值"标注 → E3')

    for ln_no, raw in enumerate(text.splitlines(), 1):
        md, mr = DESIGN_VAL.search(raw), RECALC_VAL.search(raw)
        if not (md and mr):
            if md or mr:
                notes.append(f'{path}:{ln_no} 只给出{"设计值" if md else "复算值"}一侧，'
                             f'相对偏差无从算 → E4 未判')
            continue
        a, b = float(md.group(1)), float(mr.group(1))
        if a == 0:
            notes.append(f'{path}:{ln_no} 设计值为 0，相对偏差无定义 → E4 未判')
            continue
        dev = abs(b - a) / abs(a)
        if dev > 0.10 and not DEV_ANNO.search(raw):
            bad.append(f'{path}:{ln_no} 复算偏差 {dev * 100:.1f}% > 10% 且未标注偏差原因 → E4')
    return bad, notes


def main():
    import argparse
    ap = argparse.ArgumentParser(description='EVT 报告诚实性门禁 E1–E4')
    ap.add_argument('targets', nargs='+', help='EVT 报告 .md，或配合 --all 传交付包/04_EVT 目录')
    ap.add_argument('--all', action='store_true',
                    help='递归目录下所有 .md（域外文件自动走"未判"）')
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
        bad, notes = check_text(p, text)
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        judged += 1 if in_scope(p, text) else 0
        total += len(bad)
        print(f'{p}: 违规 {len(bad)}')
    print(f'合计违规 {total}（规则 E1–E4，判据见脚本 docstring）；实核 EVT 文书 {judged} 份')
    if judged == 0:
        print('没有一份落在 EVT 适用域内 → 本次未做任何判定（rc=2），不当作"已通过"')
        sys.exit(2)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
