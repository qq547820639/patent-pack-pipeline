#!/usr/bin/env python3
"""03_设计补全 文书门禁：把 design-completion §1/§2 与 templates §4/§6 里可机械判定的部分做成判据。

适用域（三条轴，任一命中即域内）：路径含 03_设计补全/；正文出现「决策卡 / 补全登记表 /
冲突记录 / 接口定义」等表名；或正文里真有一张被 table_kind() 认出来的表。
第三条轴让"写了这张表却没提这个名字"的文书也进域——判据对象由分类器说了算，
不在这里再维护一份关键词表（两份名单迟早漂移）。域外一律报未判。

判据（K1–K5）：
  K1 缺失机构补全登记表：类型裁定必须命中 设计补全 / 保留占位-第三方确认 之一，
     且裁定依据与状态两格非空。"补全""待定"这类不落在两类里的写法等于没裁定，
     而两类并列（"设计补全 保留占位"）是自相打架——同一格既是补全又是第三方确认，
     读者不知道该谁动手。这里按子串计数就够：两类名字互不包含（不同于 G1 的
     "适用 ⊂ 不适用 / 部分适用"），所以不需要整词边界；单独写"保留占位"（缺后半段）
     按 0 命中判红，因为规程要求写明是"第三方确认"这一类。
  K2 设计决策卡：六列齐全、逐格非空；且「可选方案」须列出 ≥2 个候选
     （design-completion §2"方案空间显式列举后选型"）——只有一个候选的"选型"没有选过。
     候选数按分隔符（、；/｜<br>）现算，数法偏保守：单格里出现" M2/M3 "会被数成两个，
     偏向漏报而非误伤。
  K3 冲突记录七字段（编号/事项/冻结值/设计值/冲突理由/建议处置/状态）：缺列整表报一条，
     逐行须有冲突理由、建议处置与状态。允许与冻结参数冲突，但必须显式登记——
     没有建议处置的冲突记录等于把矛盾留在表里。
  K4 接口定义七必备字段（名称/方向/类型/额定值/极限值/失效模式/验证方法）：
     缺列报一条，逐格非空。极限值与验证方法常被人留空，而这两个恰好是能否验收的落点。
  K5 古德哈特审查（触发式）：某节以代理指标为目标（对称性指数/准确率/覆盖率/召回率/
     代理指标/评分函数/目标函数）时，该节须出现守护项或退化解审查的记录
     （守护项/退化解/Goodhart/古德哈特/下限/约束/不做代理）。没触发就报未判，不判红。

与 G 门禁同一套卫生规矩：整列缺失只报一条不逐行放大；行列数与表头不符的行不按位取列、
只进未判注记；只有表头没有行的表与文书里本就没有的表都报未判——03 段的设计文档
可以合理地一张表都没有（§4 的结构是九节散文+计算过程），所以这里不设"零表即判红"。

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

DC_DIR = re.compile(r'03_设计补全')
DC_SCOPE = re.compile(r'决策卡|补全登记表|缺失机构补全|冲突记录|接口定义')

KINDS = ('设计补全', '保留占位-第三方确认')
CAND_SEP = re.compile(r'[、;；/|｜]|<br')
PROXY = re.compile(r'对称性指数|准确率|覆盖率|召回率|代理指标|评分函数|目标函数')
GUARD = re.compile(r'守护项|退化解|Goodhart|古德哈特|下限|单调性|分布约束|不做代理|不作代理')

# 每类表的 (识别列 by, 全部必填列 cols, 逐行须非空的 must)。
# 识别列决定"这是哪张表"；cols 决定"缺哪一列要报"；must 决定"哪一格空着算违规"。
# must 刻意窄于 cols：登记表里 占位落点/补全优先级 这类列，列必须在（否则整表读不出），
# 但某行还没轮到填它不算撒谎；而 类型裁定/状态 空着就是"没判"。
# 列名同时是骨架底稿的表头来源（new_product_package 从这里生成），所以这里就是唯一口径。
SPECS = {
    'K1': {'by': ('类型裁定', '缺失项'),
           'cols': ('编号', '包/专利件', '缺失项', '占位落点', '类型裁定', '裁定依据',
                    '补全优先级', '建议补全内容摘要', '状态'),
           'must': ('缺失项', '类型裁定', '裁定依据', '状态')},
    'K2': {'by': ('可选方案', '选定方案'),
           'cols': ('决策项', '可选方案', '选定方案', '依据', '约束条件', '风险与回退'),
           'must': ('决策项', '可选方案', '选定方案', '依据', '约束条件', '风险与回退')},
    'K3': {'by': ('冻结值', '设计值'),
           'cols': ('编号', '事项', '冻结值', '设计值', '冲突理由', '建议处置', '状态'),
           'must': ('事项', '冲突理由', '建议处置', '状态')},
    'K4': {'by': ('额定值', '失效模式'),
           'cols': ('名称', '方向', '类型', '额定值', '极限值', '失效模式', '验证方法'),
           'must': ('名称', '方向', '类型', '额定值', '极限值', '失效模式', '验证方法')},
}
KINDS_TAG = ('K1', 'K2', 'K3', 'K4')
KIND_NAMES = {'K1': '缺失机构补全登记表', 'K2': '设计决策卡', 'K3': '冲突记录表',
              'K4': '接口定义表'}
# 骨架底稿的小节骨架：(小节标题后缀, 表类)。交付包 03 段按这张表落四张空表。
DOC_SECTIONS = (('1. 缺失项登记表', 'K1'), ('2. 设计决策卡', 'K2'),
                ('3. 冲突记录', 'K3'), ('4. 接口定义', 'K4'))


def header_row(tag):
    """某类表的规范表头行——骨架底稿与判据共用这一处，避免"模板改了、底稿没改"。"""
    return '| ' + ' | '.join(SPECS[tag]['cols']) + ' |'


def separator_row(tag):
    return '|' + '---|' * len(SPECS[tag]['cols'])



def cell(cs, j):
    return cs[j] if j is not None and j < len(cs) else ''


def table_kind(header):
    """这张表是哪一类。识别列要求全部命中，避免"顺带有个状态列"就被认成登记表。"""
    for tag, spec in SPECS.items():
        if all(_t.col(header, key) is not None for key in spec['by']):
            return tag
    return None


def in_scope(path, text):
    if DC_DIR.search(path) or DC_SCOPE.search(text):
        return True
    return any(table_kind(h) for h, _ in _t.table_blocks(text))


def check_text(path, text):
    """返回 (违规列表, 未判说明列表, 实际判到的判据集合)。"""
    bad, notes, seen = [], [], set()
    if not in_scope(path, text):
        return [], [f'{path}: 非设计补全文书（路径不含 03_设计补全，正文无这四类表名，'
                    f'也没有被认出的表），K1–K5 未判'], seen

    for tno, (header, rows) in enumerate(_t.table_blocks(text), 1):
        tag = table_kind(header)
        where_t = f'{path}: 表{tno}'
        if tag is None:
            continue
        cols = {k: _t.col(header, k) for k in SPECS[tag]['cols']}
        missing = [k for k, j in cols.items() if j is None]
        if missing:
            # 缺列先判、且排在"空表未判"之前：骨架底稿只有表头没有行，
            # 若先看行数，"表头掉了一列"就永远不出声——那正是骨架与判据漂移的形状。
            bad.append(f'{where_t} {KIND_NAMES[tag]}缺列 {missing} → {tag}'
                       f'（整表报一条，不逐行放大）')
            continue
        good, ragged = [], []
        for k, cs in enumerate(rows):
            (good if len(cs) == len(header) else ragged).append(k + 1)
        if ragged:
            notes.append(f'{where_t} 第{"、".join(map(str, ragged))}行列数与表头 '
                         f'{len(header)} 列不符，不按位取列 → 这些行未判')
        if not rows:
            notes.append(f'{where_t} 只有表头没有数据行 → 本表 {tag} 未判')
            continue
        seen.add(tag)
        for rno, cs in [(k, rows[k - 1]) for k in good]:
            where = f'{where_t} 第{rno}行'
            for name in SPECS[tag]['must']:
                if not cell(cs, cols[name]).strip():
                    bad.append(f'{where} 「{name}」空着 → {tag}')
            if tag == 'K1':
                v = cell(cs, cols['类型裁定']).strip()
                hit = [k for k in KINDS if k in v]
                if not hit:
                    bad.append(f'{where} 类型裁定「{v[:24]}」未落在 '
                               f'{" / ".join(KINDS)} 两类之一 → K1')
                elif len(hit) > 1:
                    bad.append(f'{where} 类型裁定同时出现 {hit} → K1')
            if tag == 'K2':
                v = cell(cs, cols['可选方案'])
                if len(CAND_SEP.findall(v)) + 1 < 2:
                    bad.append(f'{where} 可选方案只有一个候选「{v[:24]}」，'
                               f'没有方案空间就无所谓选型 → K2')
    proxy_seen = False
    for title, body in _t.sections(text):
        if PROXY.search(body):
            proxy_seen = True
            seen.add('K5')
            if not GUARD.search(body):
                bad.append(f'{path}: 节「{title[:24]}」以代理指标为目标，'
                           f'却没有守护项/退化解审查记录 → K5（design-completion §1）')
    if not proxy_seen:
        notes.append(f'{path}: 未出现代理指标类优化目标 → K5 未判（不是没审，是没触发）')
    for tag in KINDS_TAG:
        if tag not in seen:
            notes.append(f'{path}: 未出现有数据行的{KIND_NAMES[tag]} → {tag} 未判'
                         f'（该类表缺席不判红，交由人核）')
    return bad, notes, seen


def main():
    import argparse
    ap = argparse.ArgumentParser(description='03_设计补全文书门禁 K1–K5')
    ap.add_argument('targets', nargs='+', help='设计补全文书 .md，或配合 --all 传交付包目录')
    ap.add_argument('--all', action='store_true',
                    help='递归目录下所有 .md 与 .docx（域外自动走未判）')
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
    print(f'合计违规 {total}（规则 K1–K5，判据见脚本 docstring）；实核设计补全文书 {judged} 份')
    if judged == 0:
        print('没有一份落在设计补全适用域内 → 本次未做任何判定（rc=2），不当作"已通过"')
        sys.exit(2)
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
