#!/usr/bin/env python3
"""专利文书铁律门禁：把 SKILL.md 铁律与 references/hard-rules.md 中**可机械判定**的部分实跑成
红/绿判据，逐条报出 file:line 与触发规则号。不可判定的部分（是否"作新颖性声明"的语义、
数值是否有出处）仍归独立审查轮，本脚本不冒充。

用法:
  python3 check_iron_rules.py <交底书或申请文件.md ...> [--search-report 检索报告.md]
  python3 check_iron_rules.py <交付包目录> --all

判据（违规均计入退出码）:
  R1 绝对化/水平声明禁用词（hard-rules §3）
  R2 占位符写法不合规定格式（hard-rules §1/§6, templates §7.3）
  R3 权利要求文本内嵌"待确认"类注释（hard-rules §4 末条）
  R4 摘要超字数——按含标点口径（hard-rules §7）
  R5 背景技术出现的专利公开号不在检索报告已核验集合内（铁律 2）
  R6 本案型号/商标出现在文书任何位置（铁律 4；须给 --brand-terms，否则报未核，
     不自动猜型号——IP67/M5/45#钢 这类标准与规格写法会被模式匹配误伤）
  R7 发明名称超 25 字（templates §0）
  R8 EVT/投产文书缺逐字投产总则（铁律 5）
退出码: 0 合规 / 1 存在违规 / 2 输入问题（路径不存在或无可检文件，未做任何判定）
"""
import argparse, os, re, sys

# ---------- 判据参数（改判据只改这一带） ----------

# 一律违规的水平/新颖性声明词
BANNED_ALWAYS = ['首创', '填补空白', '国际领先', '国际先进']
# "首次"只在声明语境判红：与这些词同窗出现才算（否则"首次加载时"这类正常描述会误伤）
FIRST_TIME_CTX = re.compile(
    r'(首次[^，。；\n]{0,12}(公开|报道|提出|实现|发明|采用|研制|研发|量产|交付|达到|实现于)'
    r'|(?:技术|方案|装置|系统|方法|产品)[^，。；\n]{0,8}首次)')
# 占位判据分三条适用域。把 §6 的三字段式样当全局唯一式样会误伤自家模板：
# 2026-09-25 实测照 templates §0 写的交底书被判 R2 违规，而【待填】【待回填】【占位】
# 【待团队补充：对象】等分别是 templates / companion-papers / grant-application 规定的写法。
PLACEHOLDER_TOKEN = re.compile(r'【[^】]*】')
PLACEHOLDER_KIND = re.compile(r'^【(?:待[^】]{0,60}|占位)】$')          # R2b：须为 待*/占位 标记
CONFIRM3_PREFIX = '【待设计方确认：'                                      # R2c：仅此式样核三字段
CONFIRM3_SHAPE = re.compile(r'^【待设计方确认：[^｜】]+｜[^｜】]+｜[^｜】]+】$')
# 只认这三个为非法裸占位：TBD/TBC/ASSUMPTION 是 hard-rules §1 规定的合规状态标注，
# "待确认问题单"是本项目自有节名——两者都不能判红，否则门禁与自家规则打架。
BARE_TODO = re.compile(r'\b(?:TODO|FIXME|XXX)\b')
# 权利要求区内的注释式占位（§4：占位说明须移至说明书）。
# 括号内允许有说明文字——实测「（待确认：减振件型号）」这类写法才是真实形态，
# 只匹配紧邻括号的（待确认）会漏判。
CLAIM_ANNOTATION = re.compile(
    r'[（(][^（）()]{0,40}(?:待确认|待补充|待定|TBD|TODO|FIXME)[^（）()]{0,40}[）)]')
# 专利公开号形状（CN/EP/US/WO/JP/KR + 编号 + 文献种类码）
PUB_NO = re.compile(r'\b(?:CN|EP|US|WO|JP|KR)\s?\d{6,14}\s?[A-Z]\d?\b')
# 摘要锚点（交底书 §7 与申请文件"说明书摘要"）
ABSTRACT_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:摘要建议稿|说明书摘要)')
CLAIMS_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:权利要求书|权利要求建议稿)')
BACKGROUND_HEAD = re.compile(r'^#{2,3}\s*(?:\d+(?:\.\d+)*\.?\s*)?(?:背景技术|2\.1|现有技术)')
NEXT_SECTION = re.compile(r'^#{1,3}\s')
ABSTRACT_LIMIT = 300
TITLE_FIELD = re.compile(r'^\s*-\s*发明名称[:：]\s*(\S.*?)\s*$')      # R7（templates §0）
TITLE_MAX = 25
# R8 适用域：04_EVT 只在**路径**上认（正文里列出包结构不等于这份文书在 EVT 目录下），
# 正文侧认节标题「投产判定」与「投产总则」两种真属于 EVT 文书的写法
EVT_DIR = re.compile(r'04_EVT')
EVT_SCOPE = re.compile(r'投产判定|投产总则')
# 逐字规范串：以 templates §5 / evt-and-regulatory / README §4 三处一致写法为准（句号在引号内）
PRODUCTION_CLAUSE = '任何设计内容在对应物理实测全部通过前不得进入投产阶段；分析验证结论不构成投产依据。'


class Finding:
    __slots__ = ('rule', 'path', 'line', 'msg', 'quote')

    def __init__(self, rule, path, line, msg, quote=''):
        self.rule, self.path, self.line, self.msg, self.quote = rule, path, line, msg, quote

    def __str__(self):
        loc = f'{self.path}:{self.line}' if self.line else self.path
        q = f' -> {self.quote}' if self.quote else ''
        return f'  FAIL {self.rule} {loc}: {self.msg}{q}'


def section_body(lines, head_re):
    """返回 (起始行号 1-based, 该节正文行列表)；找不到返回 (None, [])。"""
    for i, ln in enumerate(lines):
        if head_re.match(ln.strip()):
            body = []
            for j in range(i + 1, len(lines)):
                if NEXT_SECTION.match(lines[j]):
                    break
                body.append(lines[j])
            return i + 1, body
    return None, []


def check_text(path, text, allowed_pub_nos=None, brand_terms=None):
    """对单份文书文本跑全部判据，返回 (findings, notes)。notes 为不计入违规的说明行。"""
    findings, notes = [], []
    lines = text.splitlines()

    for i, raw in enumerate(lines, 1):
        for w in BANNED_ALWAYS:
            if w in raw:
                findings.append(Finding('R1 绝对化措辞', path, i, f'禁用词「{w}」', raw.strip()[:60]))
        if '首次' in raw and FIRST_TIME_CTX.search(raw):
            findings.append(Finding('R1 绝对化措辞', path, i, '「首次」用于新颖性声明', raw.strip()[:60]))

        for m in PLACEHOLDER_TOKEN.finditer(raw):
            token = m.group(0)
            if not PLACEHOLDER_KIND.match(token):
                findings.append(Finding(
                    'R2b 占位符格式', path, i,
                    '方括号占位须以「待」开头或用【占位】，否则不是本仓库规定的占位式样', token))
            elif token.startswith(CONFIRM3_PREFIX) and not CONFIRM3_SHAPE.match(token):
                findings.append(Finding(
                    'R2c 三字段占位', path, i,
                    '【待设计方确认：…】须为 对象｜阻塞项｜关闭判据 三字段', token))
        if BARE_TODO.search(raw):
            findings.append(Finding('R2a 占位符格式', path, i,
                                    '裸 TODO/FIXME/XXX 字样（TBD/TBC 属 §1 允许的状态标注，不判）',
                                    raw.strip()[:60]))

    cstart, cbody = section_body(lines, CLAIMS_HEAD)
    if cstart is not None:
        for off, ln in enumerate(cbody):
            m = CLAIM_ANNOTATION.search(ln)
            if m:
                findings.append(Finding('R3 权文内占位注释', path, cstart + 1 + off,
                                        '占位说明应移至说明书', m.group(0)))

    astart, abody = section_body(lines, ABSTRACT_HEAD)
    if astart is not None:
        n = len(re.sub(r'\s', '', ''.join(abody)))
        if n > ABSTRACT_LIMIT:
            findings.append(Finding('R4 摘要字数', path, astart,
                                    f'摘要含标点 {n} 字 > {ABSTRACT_LIMIT}'))

    if allowed_pub_nos is not None:
        start, body = section_body(lines, BACKGROUND_HEAD)
        if start is None:
            notes.append('背景技术节未找到，未核公开号归属')
        else:
            seen, missing = set(), []
            for off, ln in enumerate(body):
                for m in PUB_NO.finditer(ln):
                    no = re.sub(r'\s', '', m.group(0)).upper()
                    seen.add(no)
                    if no not in allowed_pub_nos:
                        missing.append((off + start + 1, no))
            for ln_no, no in missing:
                findings.append(Finding('R5 公开号越界', path, ln_no,
                                        '该公开号不在检索报告已核验清单内'))
            notes.append(f'背景技术公开号 {len(seen)} 个已核，越界 {len(missing)} 个')
    else:
        nums = set(re.sub(r'\s', '', x).upper() for x in PUB_NO.findall(text))
        if nums:
            notes.append(f'文书含 {len(nums)} 个公开号，未给 --search-report，R5 未核（不折算合规也不折算违规）')
    # R6 商标/型号禁令（铁律 4）：须由调用方给出本案的型号/商标清单，
    # 不自动猜——实测 IP67、M5、45#钢 这类标准/规格写法会被模式匹配误伤。
    for term in (brand_terms or []):
        if not term:
            continue
        pat = re.compile(re.escape(term), re.I)
        for i, raw in enumerate(lines, 1):
            if pat.search(raw):
                findings.append(Finding('R6 商标型号', path, i,
                                        f'出现本案型号/商标「{term}」，应改通用名', raw.strip()[:60]))
    if brand_terms is None:
        pub = set(re.sub(r'\s', '', x).upper() for x in PUB_NO.findall(text))
        cand = [t for t in re.findall(r'\b[A-Za-z]{2,}[-_ ]?\d{2,}\b', text)
                if t.upper() not in pub]
        notes.append(f'未给 --brand-terms，R6 未核'
                     + (f'（另有 {len(set(cand))} 处型号形态待人工判）' if cand else ''))

    # R7 发明名称字数（templates §0：≤25 字）
    for i, raw in enumerate(lines, 1):
        m = TITLE_FIELD.match(raw)
        if m:
            val = m.group(1)
            n = len(re.sub(r'\s', '', val))
            if n > TITLE_MAX:
                findings.append(Finding('R7 发明名称字数', path, i,
                                        f'发明名称 {n} 字 > {TITLE_MAX}'))
            break
    else:
        notes.append('未找到「发明名称：」字段，R7 未核')

    # R8 EVT 投产总则逐字（铁律 5 / EVT 诚实边界）
    if EVT_DIR.search(path) or EVT_SCOPE.search(text):
        if PRODUCTION_CLAUSE not in text:
            findings.append(Finding(
                'R8 投产总则', path, 1,
                'EVT/投产文书缺逐字投产总则：' + PRODUCTION_CLAUSE[:24] + '…'))
    return findings, notes


MAX_XML_BYTES = 32 * 1024 * 1024   # 单份 document.xml 的解压上限，常驻测试把它调小来验这道闸


def docx_text(path):
    """抽取 .docx 正文（只用 stdlib）。交付物是 docx，铁律不能只检 md——
    "md 改干净了、docx 还留着禁用词"正是本仓库记录在案的事故形状。

    段落标题按 w:pStyle 还原成 markdown 井号，让 R3/R4/R7 这类按节判的判据
    在 pandoc 产物上同样可用；非 pandoc 风格命名（标题样式对不上）时相应节
    找不到，会走各自的"未核"三态而不是判绿。

    表格按 w:tbl 还原成 markdown 管道行（表头后补一行 |---|）：Word 里的表格
    单元格本身也是 w:p，逐段吐出来的话整张表就散成一串裸行——按列读的判据
    （E/G/K/N 都靠 mdtable 认列）一律认不出这张表，症状是"交付件里有表却报无表"。
    只补一行分隔符还有第二个理由：mdtable 要求连续两行才算一张表，
    只有表头的 docx 表若不补分隔符就整张隐身，骨架期的"未判"会退化成"没有表"。"""
    import xml.etree.ElementTree as ET
    import zipfile
    # docx 可能是外部交付件，ET 的默认解析器不防实体展开（十亿 laugh）与 zip 炸弹。
    # 这里用两条前置拒绝代替引第三方库：document.xml 合法内容里不该有 DTD/ENTITY 声明，
    # 也不该有几十 MB 的解压尺寸。拒绝时说清成因并走 rc=2，不静默判绿。
    with zipfile.ZipFile(path) as z:
        info = z.getinfo('word/document.xml')
        if info.file_size > MAX_XML_BYTES:
            raise ValueError(f'document.xml 解压尺寸 {info.file_size} > {MAX_XML_BYTES}，疑为压缩炸弹')
        blob = z.read('word/document.xml')
    head = blob[:65536]
    for marker in (b'<!DOCTYPE', b'<!ENTITY'):
        if marker in head:
            raise ValueError(f'document.xml 含 {marker.decode()} 声明，拒绝解析（防实体展开）')
    root = ET.fromstring(blob)
    # 表格内部的段落由表格分支统一按格取文，段落分支要跳过它们，
    # 否则同一格文字既进 "| a | b |" 又进裸行，读起来像"表在、表内容也散在外面"。
    inside = set()
    for tbl in [e for e in root.iter() if e.tag.endswith('}tbl')]:
        for el in tbl.iter():
            inside.add(id(el))

    def txt(el):
        return ''.join((t.text or '') for t in el.iter() if t.tag.endswith('}t'))

    out = []
    for p in root.iter():
        if p.tag.endswith('}tbl'):
            rows = []
            for tr in p:
                if not tr.tag.endswith('}tr'):
                    continue
                cells = [txt(tc) for tc in tr if tc.tag.endswith('}tc')]
                rows.append('| ' + ' | '.join(cells) + ' |')
                if len(rows) == 1:
                    rows.append('|' + '---|' * len(cells))
            # 每行必须以换行收尾：mdtable 按行取列，四行连成一行的话整张表读不出来
            if rows:
                out.append('\n'.join(rows) + '\n')
            continue
        if id(p) in inside:
            continue
        if not p.tag.endswith('}p'):
            continue
        style = ''
        for el in p.iter():
            if el.tag.endswith('}pStyle'):
                style = el.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val', '')
        m = re.search(r'(?:Heading|标题|title)[\s_-]*(\d)', style, re.I)
        if style.lower().startswith('title'):
            out.append('# ')
        elif m:
            out.append('#' * int(m.group(1)) + ' ')
        out.append(txt(p))
        out.append('\n')
    return ''.join(out)


def read_text(path):
    """按扩展名分派读文本。docx 打不开/无 document.xml 时抛异常，由调用方转 rc=2。"""
    if path.lower().endswith('.docx'):
        return docx_text(path)
    return open(path, encoding='utf8').read()


def gather_files(args):
    if args.all:
        root = args.targets[0]
        out = []
        for dp, _, fs in os.walk(root):
            for f in sorted(fs):
                if f.lower().endswith(('.md', '.docx')):
                    out.append(os.path.join(dp, f))
        return out
    return args.targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('targets', nargs='+', help='待检 .md 或 .docx 文件，或配合 --all 传交付包目录')
    ap.add_argument('--all', action='store_true', help='递归检查目录下所有 .md 与 .docx')
    ap.add_argument('--search-report', help='检索报告 .md：提供 R5 的已核验公开号集合')
    ap.add_argument('--brand-terms', help='逗号分隔的本案型号/商标清单（R6）；不给则 R6 报未核')
    args = ap.parse_args()

    if args.all and not os.path.isdir(args.targets[0]):
        print(f'--all 需要目录，实得不是目录: {args.targets[0]}（未做任何判定）')
        sys.exit(2)
    paths = gather_files(args)
    bad = [p for p in paths if not os.path.isfile(p)]
    if bad:
        print('输入不可用，未做任何判定: ' + ', '.join(bad))
        sys.exit(2)
    if not paths:
        print(f'未找到待检文件（--all 目录下无 .md/.docx？）: {args.targets[0]}（未做任何判定）')
        sys.exit(2)

    allowed = None
    if args.search_report:
        if not os.path.isfile(args.search_report):
            print(f'检索报告不存在: {args.search_report}')
            sys.exit(2)
        allowed = set(re.sub(r'\s', '', x).upper()
                      for x in PUB_NO.findall(read_text(args.search_report)))
        print(f'检索报告已核验公开号 {len(allowed)} 个')

    brands = None
    if args.brand_terms is not None:
        brands = [t.strip() for t in args.brand_terms.split(',') if t.strip()]
        print(f'型号/商标清单 {len(brands)} 项: {", ".join(brands)}')

    total = 0
    for p in paths:
        try:
            text = read_text(p)
        except Exception as e:
            # 抽不出正文就谈不上判定：说清成因并 rc=2，不折成"这份文书没有违规"
            print(f'输入不可用，未做任何判定: {p}（{type(e).__name__}: {e}）')
            sys.exit(2)
        if p.lower().endswith('.docx') and not re.search(r'^#{1,6}\s', text, re.M):
            # 节标题靠 w:pStyle 还原；样式名对不上（非 pandoc 产物）时 R3/R4 根本找不到节，
            # 这时"违规 0"不等于核过，必须说明未核。
            print(f'  note {p}: 未识别到节标题样式 → R3/R4（按节判的判据）未核')
        findings, notes = check_text(p, text, allowed, brands)
        for note in notes:
            print(f'  note {p}: {note}')
        for f in findings:
            print(str(f))
        total += len(findings)
        print(f'{p}: 违规 {len(findings)}')
    print(f'合计违规 {total}（规则 R1–R8，判据见脚本 docstring）')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
