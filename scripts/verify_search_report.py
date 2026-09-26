#!/usr/bin/env python3
"""检索报告核验门禁：把"已核验"从一句自称变成可机检 + 可在线复算的字段。

判据（V1–V3，文档出处见 references/templates.md §C 与 hard-rules §1）：
  V1 每条已核验条目必须带可机检标识：专利公开号 / DOI / arXiv id 三选一，
     且标识符形状本身合法（公开号沿用 check_iron_rules.PUB_NO，一处定义）。
  V2 每条条目必须填齐：标识符｜关键日期｜核验出处｜核验日期。
     铁律 1 要求"含授权日/优先权日核对"，没填就等于把核对责任推给读者。
  V3 在线存在性：DOI 走 Crossref、arXiv id 走 arXiv 官方 API。
     源明确说"查无此项"→ 违规；源不可达/超时/DNS 失败 → 一律"未核"三态，
     绝不把网络故障折算成"引用造假"，也不折算成"引用已核验"。

为什么专利号不在线核：本轮实测 google patents 的两个端点在本机 75s 无响应、
patentsview DNS 解析不到、EPO OPS 需 OAuth key、Espacenet 403、patentscope 只有
JSF 表单。宁可不判，也不拿一个没跑通的源假装"已核验"。

读 md 与 docx 两个通道（docx 走 check_iron_rules 那份唯一抽取器，表格还原成管道行后按列读）；
目录模式同时收 .md 与 .docx，同名成对时挑 .md 并把丢了的谁说出来。

退出码: 0 全部通过（含"未核"不影响通过的情形） / 1 存在违规 /
        2 输入不可用，或在线核对一条都没做成且调用方要求必核（--require-online）。
"""
import importlib.util as _ilu
import os
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request

S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_t = _load('mdtable')
# 复用铁律门禁里的公开号形状，避免两处各写一份正则而漂移
_cir = _load('check_iron_rules')
PUB_NO = _cir.PUB_NO

def read_any(path):
    """md 直读；docx 走 check_iron_rules 那份唯一实现（含 DTD/压缩炸弹拒绝与表格还原）。
    铁律门禁那边早就用同一条路读检索报告（--search-report 传 docx 今天就吃得下），
    V 却还 open() 硬读——同一份权威清单两套读法。把 .docx 当 md 读会抛
    UnicodeDecodeError，而 traceback 的退码 1 在本仓契约里意思是"发现违规"。"""
    try:
        return _cir.read_text(path)
    except Exception as e:
        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')
        sys.exit(2)


def pick_reports(d):
    """目录模式：收文件名含"检索"的 .md 与 .docx。

    同名成对时只挑 md——md 是可编辑源、docx 是它的导出件，两份都收会把同一批条目
    报两遍，而"违规 4 条"与"同一份报告违规 2 条"在退出码上完全同形。
    丢件必须说出来：静默丢与静默不丢，读数一模一样。"""
    found = [f for f in sorted(os.listdir(d))
             if '检索' in f and f.lower().endswith(('.md', '.docx'))]
    stems_md = {os.path.splitext(f)[0] for f in found if f.lower().endswith('.md')}
    out, skipped = [], []
    for f in found:
        if f.lower().endswith('.docx') and os.path.splitext(f)[0] in stems_md:
            skipped.append(f)
            continue
        out.append(os.path.join(d, f))
    return out, skipped

DOI_RE = re.compile(r'\b(10\.\d{4,9}/[^\s|，。；)】]+)', re.I)
ARXIV_RE = re.compile(r'\barxiv[:：]\s*(\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)', re.I)
DATE_RE = re.compile(r'\b\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?\b')
CROSSREF_URL = 'https://api.crossref.org/works/{doi}'
ARXIV_URL = 'https://export.arxiv.org/api/query?id_list={id}&max_results=1'
UA = 'patent-pack-pipeline/1.0 (citation existence check; +https://github.com/qq547820639/patent-pack-pipeline)'
TIMEOUT = 15
# 表头别名：模板里用的列名与脚本认的列名之间只留这一处映射
COLS = {'identifier': ('标识符', '公开号', '编号', 'ID'),
        'key_date': ('关键日期', '公开日', '授权日', '发表日'),
        'source': ('核验出处', '出处'),
        'verified_on': ('核验日期', '核对日期')}


def fetch_json(url):
    """返回 (状态, 数据)。状态: 'ok' / 'absent' / 'unreachable'。"""
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return 'ok', r.read()
    except urllib.error.HTTPError as e:
        # Crossref 对未注册 DOI 明确回 404，这就是"查无此项"
        return ('absent' if e.code == 404 else 'unreachable'), None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        return 'unreachable', None


def verify_online(kind, ident):
    """V3 在线存在性。返回 'ok' / 'absent' / 'unreachable'。"""
    if kind == 'doi':
        st, _ = fetch_json(CROSSREF_URL.format(doi=urllib.parse.quote(ident, safe='')))
        return st
    if kind == 'arxiv':
        st, body = fetch_json(ARXIV_URL.format(id=urllib.parse.quote(ident)))
        if st != 'ok' or body is None:
            return st
        # arXiv 对不存在的 id 也回 200，只是 entry 数为 0——必须数条目而不是看状态码
        return 'ok' if b'<entry' in body else 'absent'
    return 'unreachable'      # 专利公开号：无可用无密钥源


def classify(ident):
    """返回 (类型, 规范化标识符) 或 (None, None)。"""
    m = ARXIV_RE.search(ident)
    if m:
        return 'arxiv', m.group(1)
    m = DOI_RE.search(ident)
    if m:
        return 'doi', m.group(1).rstrip('.,;）)】')
    m = PUB_NO.search(ident)
    if m:
        return 'patent', re.sub(r'\s', '', m.group(0)).upper()
    return None, None


def parse_report(text):
    """取「已核验条目」小节里的表格。
    返回 (缺列列表, 行列表, 表头列数)；小节整体缺席时缺列列表返回 ['<无小节>']，
    让调用方给出与"表缺列"不同的成因——两者修法不一样。"""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if _t.heading_line(ln) and '已核验' in ln:
            start = i
            break
    if start is None:
        return ['<无小节>'], [], 0
    header, rows = None, []
    for ln in lines[start + 1:]:
        if _t.heading_line(ln):
            break
        s = ln.strip()
        if not s.startswith('|'):
            continue
        cells = _t.split_row(s)
        if _t.is_separator(cells):
            continue
        if header is None:
            header = cells
            continue
        rows.append(cells)
    if header is None:
        return ['<无表>'], [], 0
    missing, idx = [], {}
    for key, aliases in COLS.items():
        for col, name in enumerate(header):
            if any(a in name for a in aliases):
                idx[key] = col
                break
        else:
            missing.append(key)
    return missing, [(r, idx) for r in rows], len(header)


def check_report(path, text, online=True):
    """返回 (违规列表, 未核列表, 在线已核条目数, 表内条目总数)。"""
    bad, notes, checked = [], [], 0
    missing, parsed, ncols = parse_report(text)
    if missing == ['<无小节>']:
        bad.append(f'{path}: 未找到「已核验条目」小节 → V1/V2 无从判起（铁律 1 的引用白名单没有载体）')
        return bad, notes, checked, 0
    if missing == ['<无表>']:
        bad.append(f'{path}: 「已核验条目」小节下没有表格 → V1/V2 无从判起')
        return bad, notes, checked, 0
    if missing:
        bad.append(f'{path}: 「已核验条目」表缺列 {missing}（列名见 templates §C）→ V1/V2')
    no_col = set(missing)     # 整列缺失时不再逐行刷"未填"，否则一条缺陷被放大成 N 条
    for cells, idx in parsed:
        def cell(key):
            i = idx.get(key)
            return cells[i] if i is not None and i < len(cells) else ''
        if ncols and len(cells) != ncols:
            # 行列数与表头对不上时按位取值会静默读错列（把"出处"当成"核验日期"），
            # 那比报一条格式错更糟——报出来说明并跳过这一行的字段核对。
            bad.append(f'{path}: 该行 {len(cells)} 列与表头 {ncols} 列不符，未按位取列 → V1')
            continue
        ident_raw = cell('identifier')
        if not ident_raw:
            continue                      # 空标识行不重复刷违规，交给下面的未核说明
        kind, ident = classify(ident_raw)
        if kind is None:
            bad.append(f'{path}: 条目「{ident_raw[:40]}」无可机检标识（公开号/DOI/arXiv id 皆不匹配）→ V1')
            continue
        if kind == 'patent' and 'key_date' not in no_col and not DATE_RE.search(cell('key_date')):
            bad.append(f'{path}: {ident} 未填关键日期（铁律 1 要求公开日/授权日核对）→ V2')
        if 'source' not in no_col and not cell('source').strip():
            bad.append(f'{path}: {ident} 未填核验出处 → V2')
        if 'verified_on' not in no_col and not DATE_RE.search(cell('verified_on')):
            bad.append(f'{path}: {ident} 未填核验日期 → V2')
        if not online:
            notes.append(f'{path}: {ident} 在线存在性未核（--offline）')
            continue
        if kind == 'patent':
            notes.append(f'{path}: {ident} 存在性未核（无可用无密钥源，按 S1 逐条人工核对）')
            continue
        st = verify_online(kind, ident)
        if st == 'absent':
            bad.append(f'{path}: {kind.upper()} {ident} 在源侧查无此项 → V3（自称已核验的条目不存在）')
        elif st == 'unreachable':
            notes.append(f'{path}: {ident} 在线源不可达，存在性未核（不折成违规也不折成合规）')
        else:
            checked += 1
    return bad, notes, checked, len(parsed)


def main():
    import argparse
    ap = argparse.ArgumentParser(description='检索报告核验门禁 V1–V3')
    ap.add_argument('report', nargs='+', help='检索报告 .md 或 .docx（可多份，也可直接传包目录）')
    ap.add_argument('--offline', action='store_true',
                    help='跳过在线核对（V1/V2 照判，V3 一律报未核）')
    ap.add_argument('--require-online', action='store_true',
                    help='一条在线核对都没做成时按 rc=2 退出（供 CI 用，默认关）')
    args = ap.parse_args()

    paths = []
    for p in args.report:
        if os.path.isdir(p):
            got, skipped = pick_reports(p)
            paths += got
            for f in skipped:
                print(f'  note {os.path.join(p, f)}: 与同名 .md 成对 → 按可编辑源挑 .md，'
                      f'这份未参与判定（要单独核它就直接传路径）')
        elif os.path.isfile(p):
            paths.append(p)
        else:
            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')
            sys.exit(2)
    if not paths:
        print('输入不可用，未做任何判定: 未找到任何检索报告（.md 或 .docx）')
        sys.exit(2)

    total, online_ok, entries = 0, 0, 0
    for p in paths:
        text = read_any(p)
        bad, notes, checked, n_ent = check_report(p, text, online=not args.offline)
        if n_ent == 0:
            # 零条目在包骨架底稿期合法，但"一条都没核"与"核完且全部合规"在退出码上
            # 同形——必须把这个数摆出来，别让 rc=0 冒充"已经核过了"
            print(f'  note {p}: 已核验条目 0 条（骨架底稿合法；交付前须填实并逐条核）')
        for n in notes:
            print(f'  note {n}')
        for b in bad:
            print(f'  {b}')
        total += len(bad)
        online_ok += checked
        entries += n_ent
        print(f'{p}: 违规 {len(bad)}')
    print(f'合计违规 {total}（规则 V1–V3，判据见脚本 docstring）；'
          f'条目 {entries} 条，在线核成 {online_ok} 条')
    if args.require_online and not args.offline and online_ok == 0:
        print('--require-online 且在线核对 0 条成 → 本次判定不成立（rc=2）')
        sys.exit(2)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
