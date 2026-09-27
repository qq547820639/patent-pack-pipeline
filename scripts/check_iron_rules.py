#!/usr/bin/env python3
"""专利文书铁律门禁：把 SKILL.md 铁律与 references/hard-rules.md 中**可机械判定**的部分实跑成
红/绿判据，逐条报出 file:line 与触发规则号。不可判定的部分（那句查新声明**是否属实**、
数值是否有出处）仍归独立审查轮，本脚本不冒充——R9 判的是那句话在不在，不是它说得对不对。

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
  R9 背景技术节缺逐字查新声明句（hard-rules §2 第三条，templates §1 要求置于本节末尾；
     判"在本节内"而不是"在全文某处"——那句话是给本节兜底的，写在别的节不算兑现）
  R10 「说明书摘要／摘要建议稿」与「简要说明」两节内出现商业性宣传用语
     （《专利法实施细则》第二十六条"摘要中不得使用商业性宣传用语"、
      第三十一条"简要说明不得使用商业性宣传用语，也不得说明产品的性能"，两句逐字读自
      国务院令第 769 号修订后全文，留底与逐字抽取读数见 .codebuddy/attest/r58_law_quotes.log）。
     适用域**只在这两节**：法源两句各管一件文书，扩到全文会把技术比较措辞判红而细则没这么说。
     两节都不在这份文书里 ⇒ 不适用，不出提示行：交底书没有简要说明、说明书没有摘要都是正常形态，
     这与"docx 读不出节标题所以核不动"（下面那条 note 三态）是两件事。
  R11 说明书文书区域里出现"如权利要求……所述的……"一类引用语
     （《专利法实施细则》第二十条三款，逐字读自 769 号令修订后全文）。区域是「说明书」
     标题（≤2 级，负向排除 说明书摘要/附图）起至下一个 ≤2 级标题止——要跨过它的
     ### 小节，section_body 会把区域截在第一个小节。没有说明书区域 ⇒ 不适用（不出提示行）。
  R10 的第三张面：同一区域里的商业性宣传语（同条"也不得使用商业性宣传用语"），
     词表与摘要/简要说明两张面共用 COMMERCIAL，不抄第二份。
  R12 具体实施方式那一面把登记过的附图标记放进了括号——《专利审查指南》（2023）第二部分第二章
     §2.2.6 要求标记紧跟在相应技术名称后面、**不加括号**（本机留底逐文本 txt:5506-5510，PDF p156／2-20）。
     号集只认包内那张「标记｜名称」对照表里真存在的名称↔号对，表外的自由数字（"共 3 组""5mm"
     "2020 年定型"）不当标记——否则这把尺子只造假红。
  R13 摘要那一面的附图标记没放进括号——同部分 §2.4「摘要文字部分出现的附图标记应当加括号」
     （txt:5594，PDF p159／2-23）。与 R12 共用同一张对照表做号集，**两面的方向正好相反**，
     再和权利要求书那一面（标记必须在括号内，归 check_claims 的 Q5）凑成三面三样。
     包内没有那张表 ⇒ R12/R13 一起报未判，既不折成违规也不折成合规。
退出码: 0 合规 / 1 存在违规 / 2 输入问题（路径不存在或无可检文件，未做任何判定）
"""
import argparse, os, re, sys
import importlib.util as _ilu

_DIR = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    """本仓共用件的载入方式与各门禁一致（mdtable 只依赖 stdlib，Python 3.9 裸跑是硬约束）。"""
    spec = _ilu.spec_from_file_location(name, os.path.join(_DIR, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_t = _load('mdtable')

# ---------- 判据参数（改判据只改这一带） ----------

# 一律违规的水平/新颖性声明词
BANNED_ALWAYS = ['首创', '填补空白', '国际领先', '国际先进']
# R10 的词表：只放**纯商业宣传词**，一个都不与 BANNED_ALWAYS 重复。
# 理由不是"怕抄漏"，是怕同一件事报两遍（P3 同一条纪律）：上面那四个词全文任何位置都已被
# R1 判红，摘要节里再挂一条 R10 只是把屏幕淹掉。交集为空由常驻断言守着，不靠人记。
# 词表本身是**房内口径**：细则只写了"不得使用商业性宣传用语"六个字，没有列举。
# 《专利审查指南》（2023，局令第 78 号）原文本机已逐字读到（2026-09-27 第 38 轮，613 页 PDF 抽取件
# 留底 .codebuddy/attest/zhinan2023_ahippc.txt，复算命令见 README §6），但**指南自己也没有列举词表**——
# 它只重复"不得使用商业性宣传用语"并另给了一句可判的形状（第一部分第一章 §7.7 说明书／§7.8 权利要求书
# 各有一句"不得使用商业性宣传用语以及贬低或者诽谤他人…的词句"）。
# 所以下面每一个词仍然是"我判它是宣传语"，不是"法条列了它"。
# 被**排除**的词都有技术语义撞车，2026-09-27 全仓普查（Explore 子代理只读数、我复算）：
#   第一（序数：第一项/第一方面）、绝对（绝对数值／绝对式编码器）、最优（代理最优／最优实施例）、
#   顶级（顶级域名）、高端（高端交换机）、完美（完美匹配）、终身（终身学习）、免费（免费开源库）、
#   最佳（最佳实施方式）、首选（裸形；只留"用户首选"这种复合形）、领先（裸形，只留四复合词）。
COMMERCIAL = ['性价比', '物美价廉', '价廉物美', '销量第一', '销量领先', '热销', '爆款',
              '王牌', '驰名', '著名商标', '用户首选', '一站式', '口碑', '好评如潮',
              '业界标杆', '行业领先', '国内领先', '世界领先', '国际一流', '世界一流',
              '颠覆性', '革命性', '独一无二', '无可比拟', '极致', '尊享', '尊贵']
# "首次"只在声明语境判红：与这些词同窗出现才算（否则"首次加载时"这类正常描述会误伤）
FIRST_TIME_CTX = re.compile(
    r'(首次[^，。；\n]{0,12}(公开|报道|提出|实现|发明|采用|研制|研发|量产|交付|达到|实现于)'
    r'|(?:技术|方案|装置|系统|方法|产品)[^，。；\n]{0,8}首次)')
# 占位判据分三条适用域。把 §6 的三字段式样当全局唯一式样会误伤自家模板：
# 2026-09-25 某次观察（当场未留命令；这个形状今天由 test_scripts 的 R2b 三态档钉住）：
# 照 templates §0 写的交底书被判 R2 违规，而【待填】【待回填】【占位】
# 【待团队补充：对象】等分别是 templates / companion-papers / grant-application 规定的写法。
PLACEHOLDER_TOKEN = re.compile(r'【[^】]*】')
PLACEHOLDER_KIND = re.compile(r'^【(?:待[^】]{0,60}|占位)】$')          # R2b：须为 待*/占位 标记
CONFIRM3_PREFIX = '【待设计方确认：'                                      # R2c：仅此式样核三字段
CONFIRM3_SHAPE = re.compile(r'^【待设计方确认：[^｜】]+｜[^｜】]+｜[^｜】]+】$')
# 只认这三个为非法裸占位：TBD/TBC/ASSUMPTION 是 hard-rules §1 规定的合规状态标注，
# "待确认问题单"是本项目自有节名——两者都不能判红，否则门禁与自家规则打架。
BARE_TODO = re.compile(r'\b(?:TODO|FIXME|XXX)\b')
# 权利要求区内的注释式占位（§4：占位说明须移至说明书）。
# 括号内允许有说明文字——「（待确认：减振件型号）」这类写法才是真实形态（某次观察、未留命令，
# 由 test_scripts 的 R2c 三字段档复算），
# 只匹配紧邻括号的（待确认）会漏判。
CLAIM_ANNOTATION = re.compile(
    r'[（(][^（）()]{0,40}(?:待确认|待补充|待定|TBD|TODO|FIXME)[^（）()]{0,40}[）)]')
# 专利公开号形状（CN/EP/US/WO/JP/KR + 编号 + 文献种类码）
PUB_NO = re.compile(r'\b(?:CN|EP|US|WO|JP|KR)\s?\d{6,14}\s?[A-Z]\d?\b')
# 摘要锚点（交底书 §7 与申请文件"说明书摘要"）
ABSTRACT_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:摘要建议稿|说明书摘要)')
# 外观设计那一件（细则第三十一条、专利法第二十七条都叫它"简要说明"）。
# 只认标题行，不认正文里的"简要说明：申请人请求保护色彩。"式内联写法——
# 那句是 C5 的触发词面，两张面分开判，否则这把尺子会顺着 C5 的夹具开火。
BRIEF_DESC_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:外观)?简要说明')
CLAIMS_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:权利要求书|权利要求建议稿)')
BACKGROUND_HEAD = re.compile(r'^#{2,3}\s*(?:\d+(?:\.\d+)*\.?\s*)?(?:背景技术|2\.1|现有技术)')
NEXT_SECTION = re.compile(r'^#{1,3}\s')

# R10 的适用域：两节各引各的法源（同一张词表，打在摘要上引 26 条、打在简要说明上引 31 条，
# 报成同一句的话读者分不出这条红是哪件文书欠的）。写成常量而不是内联在循环里，
# 是为了让"只关掉其中一节"这件事在变异测试里打得中（判据参数集中在这一带，本文件的惯例）。
R10_SCOPE = ((ABSTRACT_HEAD, '细则第二十六条：摘要中不得使用商业性宣传用语'),
             (BRIEF_DESC_HEAD, '细则第三十一条：简要说明不得使用商业性宣传用语'))
# 说明书文书区域：细则第二十条三款的两条禁令（禁"如权利要求……所述的……"一类的引用语、
# 禁商业性宣传语）都作用在**整份说明书**上，要跨过它的 ### 小节——section_body 在任何下个
# 标题处就断，会把五节里四节漏掉。区域=「说明书」标题（≤2 级；负向排除 说明书摘要/附图）
# 起至下一个 ≤2 级标题止。
SPEC_DOC_HEAD = re.compile(r'^#{1,2}\s*(?:\d+[.、]?\s*)?说明书(?!摘要|附图)')
CLAIMS_QUOTE_REF = re.compile(r'如权利要求[^，。；\n]{0,24}所述')
# R12／R13：同一张「标记｜名称」对照表，三面各有自己的写法（第 39 轮，法源已亲验的指南）：
#   权利要求书 —— 标记**必须**放括号里（细则第二十二条，check_claims 的 Q5 那一头）；
#   具体实施方式 —— 标记**不得**加括号，且要紧跟技术名称（指南第二部分第二章 §2.2.6，
#     PDF p156／印刷页 2-20：「…并放在相应的技术名称的后面，不加括号。例如…可以写成
#     "电阻3通过三极管4的集电极与电容5相连接"，不得写成"3通过4与5连接"」）；
#   摘要 —— 出现的标记**应当**加括号（同部分 §2.4，PDF p159／2-23：
#     「此外，摘要文字部分出现的附图标记应当加括号」）。
# 两面的号集都只认那张表里登记过的「名称↔号」对：表外的自由数字（"拉脱力 90N""2020 年"）
# 一律不当标记——与 Q5 同一条防线，否则这两把尺子只会造假红。
SPEC_IMPL_HEAD = re.compile(r'^#{2,4}\s*(?:\d+(?:\.\d+)*[.、]?\s*)?具体实施方式')


def mark_map(texts):
    """包内所有文书里的「名称→标记号」对照表（与 check_claims.mark_set、N3 同一形状）。

    号集取"表里真存在的号"：同名多号时保留第一个（N2 本就禁止同号异名/同名异号，
    出现多号是那张表自己的缺陷，不归这两条判据重复报）。"""
    name2num = {}
    for text in texts:
        for header, rows in _t.table_blocks(text):
            jm, jn = _t.col(header, '标记'), _t.col(header, '名称')
            if jm is None or jn is None:
                continue
            for cs in rows:
                v = (cs[jm] if jm < len(cs) else '').strip()
                nm = (cs[jn] if jn < len(cs) else '').strip()
                if v.isdigit() and nm:
                    name2num.setdefault(nm, v)
    return name2num

# 300 字这一格的**法源不是细则第二十六条**：本机逐字读到的 769 号令修订后全文里根本没有"300"
# 这个数（留底 .codebuddy/attest/gz769.htm，页面全文 `'300' in text` 读数 False；
# 抽取过程见 .codebuddy/attest/r58_law_quotes.log），该条只剩"写明…概要"与
# "不得使用商业性宣传用语"两句判得动。今天仍然管用的 300 字出自
# 《专利审查指南》（2023）——2026-09-27 第 38 轮起**指南原文已亲验**（613 页 PDF 抽取件留底
# .codebuddy/attest/zhinan2023_ahippc.txt，复算命令见 README §6），逐字两处：
#   第二部分第二章 §2.4（PDF p159／印刷页 2-23）「细则26.2（4）摘要文字部分（包括标点符号）
#     不得超过300个字，并且不得使用商业性宣传用语。此外，摘要文字部分出现的附图标记应当加括号。」
#   第一部分第二章 §7.5（4）（PDF p71）实用新型侧同文一句。
# 注意一处归属：指南把这句标在"细则 26.2"名下，而修订后的细则 26 条没有字数——
# **那是指南自己的标注，不是细则的现行文本**，抄进文档时不得反过来把它写成"细则规定"。
# 旧法（2010 版细则）那一款写过什么本机未读到，"修订时删掉了"这一说没有一手依据，不作陈述。
ABSTRACT_LIMIT = 300
TITLE_FIELD = re.compile(r'^\s*-\s*发明名称[:：]\s*(\S.*?)\s*$')      # R7（templates §0）
TITLE_MAX = 25
# R8 适用域：04_EVT 只在**路径**上认（正文里列出包结构不等于这份文书在 EVT 目录下），
# 正文侧认节标题「投产判定」与「投产总则」两种真属于 EVT 文书的写法
EVT_DIR = re.compile(r'04_EVT')
EVT_SCOPE = re.compile(r'投产判定|投产总则')
# 逐字规范串：以 templates §5 / evt-and-regulatory / README §4 三处一致写法为准（句号在引号内）
PRODUCTION_CLAUSE = '任何设计内容在对应物理实测全部通过前不得进入投产阶段；分析验证结论不构成投产依据。'
# R9 的逐字串（hard-rules §2 第三条）。比较前只剥空白：作者软换行/pandoc 折行不是改措辞，
# 但汉字、标点、数字一个都不许差——与 check_figure_text T2 的归一口径同一档。
NOVELTY_CLAUSE = '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。'
NOVELTY_FLAT = re.sub(r'\s+', '', NOVELTY_CLAUSE)


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


def doc_region(lines, head_re):
    """层级区域：从 head_re 命中的标题起，到下一个**级数不高于它**的标题止。
    section_body 在任何下个标题就断——说明书那一份里五节全是 ### 小节，
    用它会把区域截在「### 技术领域」，四条禁令等于没判。找不到返回 (None, [])。"""
    for i, ln in enumerate(lines):
        if head_re.match(ln.strip()):
            level = len(ln) - len(ln.lstrip('#'))
            body = []
            for j in range(i + 1, len(lines)):
                mj = re.match(r'^(#{1,6})\s', lines[j])
                if mj and len(mj.group(1)) <= level:
                    break
                body.append(lines[j])
            return i + 1, body
    return None, []


def check_text(path, text, allowed_pub_nos=None, brand_terms=None, marks=None):
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

    # R10：两节各判各的，法源写在消息里——同一张词表打在摘要上引 26 条、打在简要说明上引 31 条，
    # 报成同一句话的话，读者就分不出这条红是哪一件文书欠的（判据消息要带本档专属成因词）。
    # 交底书的「摘要建议稿」与申请文件的「说明书摘要」共用 ABSTRACT_HEAD：前者就是后者的前身，
    # 在提交前拦比交出去再补正便宜。
    for head, ref in R10_SCOPE:
        hstart, hbody = section_body(lines, head)
        if hstart is None:
            continue
        for off, ln in enumerate(hbody):
            for w in COMMERCIAL:
                if w in ln:
                    findings.append(Finding('R10 摘要/简要说明宣传用语', path,
                                            hstart + 1 + off,
                                            f'商业性宣传用语「{w}」——{ref}', ln.strip()[:60]))

    # R11＋R10 的说明书面：细则第二十条三款"……并不得使用'如权利要求……所述的……'
    # 一类的引用语，也不得使用商业性宣传用语"。区域是**整份说明书**（跨 ### 小节），
    # 词表复用 R10 的 COMMERCIAL（一张词表三张面，不抄第二份）；引用语是独立正则。
    # 没有「说明书」区域 ⇒ 不适用（不出提示行），与 R10 两节的口径一致。
    dstart, dbody = doc_region(lines, SPEC_DOC_HEAD)
    if dstart is not None:
        for off, ln in enumerate(dbody):
            m = CLAIMS_QUOTE_REF.search(ln)
            if m:
                findings.append(Finding('R11 说明书引用语', path, dstart + 1 + off,
                                        f'说明书里用"{m.group(0)}"指回权利要求'
                                        '——细则第二十条三款：不得使用该类引用语', ln.strip()[:60]))
            for w in COMMERCIAL:
                if w in ln:
                    findings.append(Finding('R10 说明书宣传用语', path, dstart + 1 + off,
                                            f'商业性宣传用语「{w}」——细则第二十条三款：'
                                            '说明书里不得使用商业性宣传用语', ln.strip()[:60]))

    # R12／R13：同一张「标记｜名称」对照表，三面三种写法（第四面是 check_claims 的 Q5）：
    #   摘要——标记应当加括号（指南第二部分第二章 §2.4，PDF p159／印刷页 2-23 逐字）；
    #   具体实施方式——标记紧跟技术名称、**不加**括号（同部分 §2.2.6，PDF p156／2-20 逐字）。
    # 号集只认表里登记的「名称↔号」对，表外的自由数字（"拉脱力 90N""2020 年"）一律不当标记——
    # 与 Q5 同一条防线，否则这两把尺子只会造假红。包内没有那张表 ⇒ 两条未判（不折成合规）；
    # 区域不在本份文书 ⇒ 该条不适用，不出提示行（与 R11 同口径）。
    r13_start, r13_body = section_body(lines, ABSTRACT_HEAD)
    r12_start, r12_body = doc_region(lines, SPEC_IMPL_HEAD)
    if not marks:
        if r13_start is not None or r12_start is not None:
            notes.append('文里有摘要／具体实施方式区域，但包内没有「标记｜名称」对照表 '
                         '→ R12/R13 未判（看不见不等于合规）')
    else:
        for nm, num in sorted(marks.items()):
            bare = re.compile(re.escape(nm) + r'\s*' + re.escape(num) + r'(?![0-9])')
            pbr = re.compile(re.escape(nm) + r'\s*[（(]\s*' + re.escape(num) + r'\s*[）)]')
            if r13_start is not None:
                for off, ln in enumerate(r13_body):
                    m = bare.search(ln)
                    if m:
                        findings.append(Finding(
                            'R13 摘要标记未加括号', path, r13_start + 1 + off,
                            f'摘要里「{m.group(0).strip()}」的标记 {num} 没放进括号'
                            '——指南 §2.4：摘要文字部分出现的附图标记应当加括号',
                            ln.strip()[:60]))
            if r12_start is not None:
                for off, ln in enumerate(r12_body):
                    m = pbr.search(ln)
                    if m:
                        findings.append(Finding(
                            'R12 具体实施方式标记加括号', path, r12_start + 1 + off,
                            f'具体实施方式里「{m.group(0).strip()}」给标记 {num} 加了括号'
                            '——指南 §2.2.6：应放在相应技术名称后面、不加括号'
                            '（不加括号是这一面的要求，与权利要求书的 Q5 相反）',
                            ln.strip()[:60]))

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
    # 不自动猜——IP67、M5、45#钢 这类标准/规格写法会被模式匹配误伤
# （语料就在常驻用例里：tests/test_scripts.py 的 "紧固件按 M5 螺纹、防护等级 IP67、材料 45#钢" 那一档）。
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

    # R9 背景技术节的逐字查新声明（hard-rules §2 / templates §1「末尾统一查新声明句」）。
    # 只判本节：这句话是给"背景技术只引了初步检索"这件事兜底的，全文别处出现不算兑现；
    # 反过来，本节都没有（骨架底稿就只有附图说明＋标记说明两节）时报未判，不折成违规。
    bg_start, bg_body = section_body(lines, BACKGROUND_HEAD)
    if bg_start is None:
        notes.append('背景技术节未找到，R9 未判（不折成违规也不折成合规）')
    else:
        flat = re.sub(r'\s+', '', '\n'.join(bg_body))
        if NOVELTY_FLAT not in flat:
            findings.append(Finding(
                'R9 查新声明', path, bg_start,
                '背景技术节缺逐字查新声明：' + NOVELTY_CLAUSE[:20] + '…'))
        else:
            nonblank = [l.strip() for l in bg_body if l.strip()]
            if nonblank and NOVELTY_FLAT not in re.sub(r'\s+', '', nonblank[-1]):
                notes.append('R9 声明句在本节内但不在末尾（templates §1 要求置于末尾）——只提示不判红')
    return findings, notes


MAX_XML_BYTES = 32 * 1024 * 1024   # 单份 document.xml 的解压上限，常驻测试把它调小来验这道闸


def docx_text(path):
    """抽取 .docx 正文（只用 stdlib）。交付物是 docx，铁律不能只检 md——
    "md 改干净了、docx 还留着禁用词"正是本仓库记录在案的事故形状。

    段落标题按 w:pStyle 还原成 markdown 井号，让 R3/R4/R10 这类按节判的判据
    在 pandoc 产物上同样可用；非 pandoc 风格命名（标题样式对不上）时相应节
    找不到，会走各自的"未核"三态而不是判绿。（R7 不在这张名单里：它认的是
    `- 发明名称：` 那一行，与节标题还原无关。）

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
        # 嵌入的图形对象（插图/OLE/旧式 VML）在纯文本抽取里是**看不见的**，
        # 而 Q7 判的是"权利要求书里不得有插图"——不看这一行，Word 件上 Q7 永远是绿的瞎子。
        # 折算成一行 md 图片语法：Q7 的正则两通道吃同一份，别处没有判据扫这个形状。
        # 表格里的图不在此列（表格分支按格取文，见上）——登记为已知盲区，不是"已核无图"。
        if any(el.tag.endswith(('}drawing', '}object', '}pict')) for el in p.iter()):
            out.append('![](docx-embedded-object)\n')
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
    docs = []
    for p in paths:
        try:
            docs.append((p, read_text(p)))
        except Exception as e:
            # 抽不出正文就谈不上判定：说清成因并 rc=2，不折成"这份文书没有违规"
            print(f'输入不可用，未做任何判定: {p}（{type(e).__name__}: {e}）')
            sys.exit(2)
    # R12/R13 的号集是**包级**事实：那张「标记｜名称」表常写在另一份文书的附图说明节里，
    # 按单份文书各读各的，摘要侧就永远看不见表、永远报未判。
    marks = mark_map([t for _, t in docs])
    for p, text in docs:
        if p.lower().endswith('.docx') and not re.search(r'^#{1,6}\s', text, re.M):
            # 节标题靠 w:pStyle 还原；样式名对不上（非 pandoc 产物）时 R3/R4 根本找不到节，
            # 这时"违规 0"不等于核过，必须说明未核。
            print(f'  note {p}: 未识别到节标题样式 → R3/R4/R10/R12/R13（按节判的判据）未核')
        findings, notes = check_text(p, text, allowed, brands, marks)
        for note in notes:
            print(f'  note {p}: {note}')
        for f in findings:
            print(str(f))
        total += len(findings)
        print(f'{p}: 违规 {len(findings)}')
    print(f'合计违规 {total}（规则 R1–R13，判据见脚本 docstring）')
    sys.exit(1 if total else 0)


if __name__ == '__main__':
    main()
