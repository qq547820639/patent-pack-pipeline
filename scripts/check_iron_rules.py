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
# 规定的占位写法（templates §7.3 与 hard-rules §6）
VALID_PLACEHOLDER = re.compile(
    r'^【(?:待团队补充|待签署|待设计方确认：[^｜】]+｜[^｜】]+｜[^｜】]+)】$')
# 以"待"开头却不符合上述格式 ⇒ 意图是占位但写法不合规定
INTENDED_PLACEHOLDER = re.compile(r'【待[^】]*】')
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


def check_text(path, text, allowed_pub_nos=None):
    """对单份文书文本跑全部判据，返回 (findings, notes)。notes 为不计入违规的说明行。"""
    findings, notes = [], []
    lines = text.splitlines()

    for i, raw in enumerate(lines, 1):
        for w in BANNED_ALWAYS:
            if w in raw:
                findings.append(Finding('R1 绝对化措辞', path, i, f'禁用词「{w}」', raw.strip()[:60]))
        if '首次' in raw and FIRST_TIME_CTX.search(raw):
            findings.append(Finding('R1 绝对化措辞', path, i, '「首次」用于新颖性声明', raw.strip()[:60]))

        for m in INTENDED_PLACEHOLDER.finditer(raw):
            token = m.group(0)
            if not VALID_PLACEHOLDER.match(token):
                findings.append(Finding(
                    'R2 占位符格式', path, i,
                    '占位须为【待团队补充】/【待签署】/【待设计方确认：对象｜阻塞项｜关闭判据】', token))
        if BARE_TODO.search(raw):
            findings.append(Finding('R2 占位符格式', path, i, '裸 TODO/TBD/待确认 类字样', raw.strip()[:60]))

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
    return findings, notes


def gather_files(args):
    if args.all:
        root = args.targets[0]
        out = []
        for dp, _, fs in os.walk(root):
            for f in sorted(fs):
                if f.lower().endswith('.md'):
                    out.append(os.path.join(dp, f))
        return out
    return args.targets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('targets', nargs='+', help='待检 .md 文件，或配合 --all 传交付包目录')
    ap.add_argument('--all', action='store_true', help='递归检查目录下所有 .md')
    ap.add_argument('--search-report', help='检索报告 .md：提供 R5 的已核验公开号集合')
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
        print(f'未找到待检文件（--all 目录下无 .md？）: {args.targets[0]}（未做任何判定）')
        sys.exit(2)

    allowed = None
    if args.search_report:
        if not os.path.isfile(args.search_report):
            print(f'检索报告不存在: {args.search_report}')
            sys.exit(2)
        allowed = set(re.sub(r'\s', '', x).upper()
                      for x in PUB_NO.findall(open(args.search_report, encoding='utf8').read()))
        print(f'检索报告已核验公开号 {len(allowed)} 个')

    total = 0
    for p in paths:
        text = open(p, encoding='utf8').read()
        findings, notes = check_text(p, text, allowed)
        for note in notes:
            print(f'  note {p}: {note}')
        for f in findings:
            print(str(f))
        total += len(findings)
        print(f'{p}: 违规 {len(findings)}')
    print(f'合计违规 {total}（规则 R1–R5，判据见脚本 docstring）')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
