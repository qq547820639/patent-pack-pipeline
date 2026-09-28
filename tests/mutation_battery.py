#!/usr/bin/env python3
"""常驻变异电池：证明 tests/test_scripts.py 里那些判据断言真的会咬人。

为什么住在仓库里：判据门禁本身有常驻冒烟测试，但"这些测试有没有牙"这件事
此前只存在于 /tmp 的一次性脚本里，清一次 /tmp 就没了（实际发生过两次）。

用法:
    python3 tests/mutation_battery.py                 # 全部 arm 一跑（清单见 --arm choices）
    python3 tests/mutation_battery.py --arm lab        # 只跑一支（cen|chan|claims|dc|doc|evt|fig|iron|lab|pack|reg|text|vsr）
    python3 tests/mutation_battery.py --keep-work     # 保留工作副本便于手工复查

约定（与判据类脚本一致）:
    0 = 所有变异都被"点名该条款的断言"抓红，且还原后套件 GREEN
    1 = 有变异未被抓红（SURVIVED）、红因归错条款（MISRED）、探针失效（PROBE-FAIL）
        或崩溃致红（CRASH-KILL，崩溃不算覆盖）
    2 = 环境不可用（如缺 matplotlib 导致 fig 档无法判定），未做判定 ≠ 判定通过

自带的卫生规矩（都是踩过的坑）:
  · 变异必须写成 plausible 的错误实现。把判据改成让它抛异常，套件也会"红"，
    但那不是覆盖——所以分类器先认 CRASH-KILL。认它就得说清崩在哪：suite_tb() 只认
    **帧里出现套件文件名的那一段 Traceback**（不是"最后一段"，也不是全文搜词——
    断言消息里拼进来的子进程 Traceback 会冒充崩溃现场），crash_notes() 把帧与异常行
    随读数一起打出来。
    另：一档共用一份 work copy，且 suite() 里带 PYTHONDONTWRITEBYTECODE=1——还原后
    同尺寸的 .pyc 会按 mtime 秒级失效，让下一臂跑到上一臂的代码（第 20 轮一条只在跑批里
    出现、单臂与整档复算都不复现的 CRASH-KILL 读不到归因，这条是当时的唯一可加固面）。
  · 每支 arm 结束必须打一行「汇总」；缺行按 arm 崩溃处理（批跑时把日志 grep
    成只剩关键词，曾把一支电池 import 期的 SyntaxError 整个吞掉）。
  · 各档臂数**不在本 docstring 里手抄**（含 iron 档）：抄一份就是一份会过期的假账，
    而现算的读数已经在场——`汇总[组]: 共 N` 与常驻 `test_battery_needle_census` 的体检行
    都由 `MUTS` 现数。docstring 里唯一的手抄清单是上面那行「只跑一支（…）」的**档名**，
    它由同一条常驻用例与 `MUTS` 键对账（抄漏一档＝那一档等于不存在）。
  · fig 档需要 matplotlib；没有就如实 SKIP 并把退出码判 2，不折成"通过"。
  · 两条规则互相遮蔽时不许硬凑 arm：lab 档的 `nm = max(cands, key=len)` 与边界字表
    是同一条防误伤的两层，注入前者永远先被后者挡下（短名之前的那段字属于更长名称，
    一般不在边界字表里）⇒ 读成 SURVIVED 是量具真相，不是覆盖缺口：摘掉这支、
    用例留作回归护栏（改名或加同名词时它仍有意义）。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PY = sys.executable

IRON = 'scripts/check_iron_rules.py'
CF = 'scripts/check_figures.py'
PF = 'scripts/patent_figure.py'
V = 'scripts/verify_search_report.py'
NP = 'scripts/new_product_package.py'
CE = 'scripts/check_evt.py'
CR = 'scripts/check_regulatory.py'
CD = 'scripts/check_design_completion.py'
CN = 'scripts/check_figure_labels.py'
CT = 'scripts/check_figure_text.py'
CQ = 'scripts/check_claims.py'
MT = 'scripts/mdtable.py'
RG = 'scripts/regen_docx.py'
RP = 'scripts/rebuild_package.py'
TB = 'tests/mutation_battery.py'        # cen 档有一条臂咬电池自己的 arm 清单，目标就是本文件
TS = 'tests/test_scripts.py'            # 量具自身也算一个目标：常驻里的提取器自测要有注入臂咬得住

# (说明, 目标脚本, 原样 needle, plausible 错误实现, 允许点名抓红的断言消息[可写成元组])
MUTS = {
    'claims': [
        # Q7／Q8（细则 22 条一款）：插图与"如图…所示"这两格各自要有一支只关自己的臂。
        ('Q7 插图判据关掉（权要里塞图也照过）', CQ,
         '        if CLAIM_IMAGE.search(ln):', '        if False:',
         # 两个合法原告：md 侧与 docx 侧（真嵌图档）各有一条"插图没被抓住"的断言，
         # docx 那条在测试文件里更靠前，先红的是它——expect 必须写成消费者集合。
         ('权要里的插图未被 Q7 抓到', 'Word 件里嵌入的插图未被 Q7 抓到')),
        ('Q8 引用语判据关掉（"如图…所示"指回别处也照过）', CQ,
         '        if CLAIM_FIG_REF.search(ln) or CLAIM_SPEC_REF.search(ln):', '        if False:',
         '权要里"如图…所示"未被 Q8 抓到'),
        # Q9／Q10／Q11（法源换成《专利审查指南》2023 §3.2.2 与 §3.3）：三支各配一支只关自己的臂。
        # Q10 的两半（「约＋数字」与「或类似物」）在源码里是 if/elif 两条独立触发路径，
        # 所以给两支臂——合成一条臂的话"只关掉一半"永远读不出是哪个触发条件掉了。
        ('Q9 模糊用语判据关掉（权要里写"例如／必要时"也照过）', CQ,
         '        for term in VAGUE_TERMS:', '        for term in ():',
         '权要里的模糊用语未被 Q9 抓到'),
        ('Q10「约＋数字」那一半关掉（数值边界被"约"糊过去也不报）', CQ,
         '        m = APPROX_SHAPE.search(joined)', '        m = None',
         '权要里"约＋数字"未被 Q10 抓到'),
        ('Q10「或类似物」那一半关掉（指南逐字点名的短语不再判）', CQ,
         '        elif APPROX_PHRASE in joined:', '        elif False:',
         '权要里「或类似物」未被 Q10 抓到'),
        ('Q11 句号位点判据关掉（一项里写满句号也照过）', CQ,
         '        for li, ln in ilines:', '        for li, ln in ():',
         # 三条原告都是"只有 Q11 关掉才会红"的档：两条 md 位点档、一条本轮新增的 Word 档
         # （docx 面在 test_check_claims 里排在 md 档之前，所以它先红——第 38 轮实测 MISRED 后补进名字表）。
         ('权要一行里结尾之前的句号未被 Q11 抓到', '多行权项里非结尾那行的句号未被 Q11 抓到',
          'Word 件的句号位点读数不符')),
        # 判严方向：指南那句是"只允许在结尾处使用句号"（划界），不是"每项必须以句号收尾"（义务）。
        # 把划界写成义务的注入必须由**反向控制**（权项结尾不带句号仍须全绿）抓住，
        # 而不是由合规档抓住——OK 那份每项都以句号收尾，判严了它照样全绿。
        ('Q11 判严方向（划界当成义务：结尾没有句号也判红）', CQ,
         '        last_line, last_txt = ilines[-1][0], ilines[-1][1].rstrip()',
         '        last_line, last_txt = ilines[-1][0], ilines[-1][1].rstrip()\n'
         "        if not last_txt.endswith('。'):\n"
         "            bad.append(f'{where(last_line)}: 权利要求 {n} 结尾没有句号 → Q11')\n",
         '权要结尾没有句号被 Q11 判红'),
        ('Q1 编号连续性判据关掉', CQ,
         '    if sorted(nums) != list(range(1, len(nums) + 1)):', '    if False:',
         '权项跳号未被 Q1 抓到'),
        ('Q2 独权位置判据关掉', CQ,
         '        late = sorted(x for x in ind if first_dep is not None and x > first_dep)',
         '        late = []', '独权排在从权之后未被 Q2 抓到'),
        ('Q3 在后的引用不报', CQ,
         '            elif r >= n:', '            elif False:', '从权向后引用未被 Q3 抓到'),
        ('Q4 多项引多项不报', CQ,
         '            if bases:', '            if False:', '多项从权引多项基础未被 Q4 抓到'),
        ('Q5 括号外标记不报', CQ,
         '                if [nm for nm in name2num if pre.endswith(nm) and name2num[nm] == num]:',
         '                if False:', '附图标记写在括号外未被 Q5 抓到'),
        ('没有权要节时把未判折成合规', CQ,
         '    if not hit:', '    if False:', '没有权利要求书节被折成合规或未上报'),
        # 引用语里的权项号不当标记：真正兜住这层误伤的是"前缀必须逐字以表内名称结尾"，
        # 由合规档（含两处"根据权利要求 1"）与 q5 档两头钉；源码里那句 DEP_REF 扣除只是第二层保险，
        # 单独给它配注入会在改名后的判据下永不开火，宁可不占 arm 也不留一支不复现的变异。
        ('读不动的 docx 不再兜异常（崩一次就是一张假违规单）', CQ,
         '    except Exception as e:', '    except ImportError as e:',
         '读不动的 docx 崩成异常或退码不是 2'),
        ('Q6 从属条数判据关掉', CQ,
         '    if not (lo <= ndep <= hi):', '    if False:', 'Q6 档位判错'),
        ('Q6 发明档放宽成 1–20（太薄的权要不再判红）', CQ,
         "TYPE_BANDS = {'发明': (7, 10), '实用新型': (4, 8)}",
         "TYPE_BANDS = {'发明': (1, 20), '实用新型': (4, 8)}", 'Q6 档位判错'),
        ('Q6 只落一档时不报「部分未判」（为什么没判红这件事就丢了）', CQ,
         '        if len(fits) != 2:', '        if False:',
         '只有一型容得下时没说出'),
        ('Q6 把认不出的 --type 当成没给（告诉它「外观设计」也不提示）', CQ,
         "            why = ('未给 --type' if not ptype else",
         "            why = ('未给 --type' if True else",
         '认不出的 --type 被当成'),
        ('Q6 认出类别却不查档位（两型一律走并集）', CQ,
         '    if key in TYPE_BANDS:', '    if False:', 'Q6 档位判错'),
        ('输入档不再只接目录（文件当目录喂进 Q）', CQ,
         '        if os.path.isdir(p):', '        if True:', '传文件未说成因并 fail-closed'),
        # ── 第 39 轮 Q12（指南第一部分第一章 §4.4：编号前不得冠"权利要求"或"权项"）两支 ──
        # 关掉那一支有两个合法原告：q12 那档（两种冠词各一条）与 q12allpre 那档
        # （通篇冠词、权项一行也解析不出，仍必须判满）——后者是本轮"节面三条排在无项早退之前"
        # 那个顺序改动的回归钉，套件遇红即停所以读不到它，列进 expect 只为换序后仍认得出。
        ('Q12 关掉（通篇写"权利要求1、"也照过）', CQ,
         '        if CLAIM_NUM_PREFIX.search(ln):', '        if False:',
         ('权项编号前冠"权利要求／权项"未被 Q12 抓到',
          '通篇冠"权利要求"的权要书里 Q12 没判满三条')),
        # 判严方向：指南只禁"编号前冠词"，不禁「N.」这个编号形状本身。原告必须是**合规控制**——
        # 第一红落在套件最前面那份合规档（OK 那八项权要，覆盖账"实判判据 12 条"）上，本轮新写的
        # q12clean（把冠词去掉、其余形状不动）是同一件事的第二张合规控制，列全以免换序后 MISRED。
        ('Q12 判严方向（把「N.」编号本身也判红：指南只禁编号前冠词）', CQ,
         r"CLAIM_NUM_PREFIX = re.compile(r'^\s*(?:权利要求|权项)\s*\d{1,3}\s*[.、．]')",
         r"CLAIM_NUM_PREFIX = re.compile(r'^\s*(?:权利要求|权项)?\s*\d{1,3}\s*[.、．]')",
         ('合规权要被判红，或十二条没各判到', '合规的「N.」顺序编号被 Q12 判红')),
    ],
    'iron': [
        ('R1 禁用词判据关闭', IRON, "        for w in BANNED_ALWAYS:", '        for w in []:',
         'R1「首创」未触发'),
        ('R2b 白名单收窄回旧式样（应被【待填写】误伤档抓住）', IRON,
         "PLACEHOLDER_KIND = re.compile(r'^【(?:待[^】]{0,60}|占位)】$')",
         "PLACEHOLDER_KIND = re.compile(r'^【(?:待团队补充|待签署)】$')",
         ('R2b 把【待确认】式样判红', '新生成的包未通过铁律门禁')),
        ('R2b 判据关闭', IRON, '            if not PLACEHOLDER_KIND.match(token):',
         '            if False:', 'R2b 未拦非 待*/占位 方括号标记'),
        ('R2b 反向（恒判红）', IRON, '            if not PLACEHOLDER_KIND.match(token):',
         '            if True:', ('R2b 把【待确认】式样判红', '新生成的包未通过铁律门禁')),
        ('R2c 三字段核不掉', IRON,
         '            elif token.startswith(CONFIRM3_PREFIX) and not CONFIRM3_SHAPE.match(token):',
         '            elif False:', 'R2c 未拦缺字段三字段占位'),
        ('R2c 恒判红（误伤合规三字段）', IRON,
         '            elif token.startswith(CONFIRM3_PREFIX) and not CONFIRM3_SHAPE.match(token):',
         '            elif token.startswith(CONFIRM3_PREFIX):', 'R2c 误判合规三字段占位'),
        ('R3 权文占位核不掉', IRON, '            m = CLAIM_ANNOTATION.search(ln)',
         '            m = None', 'R3 权文内占位注释未触发'),
        ('R4 摘要字数核不掉', IRON, '        if n > ABSTRACT_LIMIT:', '        if False:',
         'R4 超限未触发'),
        ('R5 越界公开号核不掉', IRON, '    if allowed_pub_nos is not None:',
         '    if False:', 'R5 越界公开号未触发'),
        ('R6 清单不生效', IRON, '    for term in (brand_terms or []):', '    for term in []:',
         'R6 未命中已声明的型号'),
        ('R6 缺清单时不再报未核', IRON, '    if brand_terms is None:', '    if False:',
         '缺 --brand-terms 时 R6 应报'),
        ('R7 字数核不掉', IRON, '            if n > TITLE_HARD_MAX:', '            if False:',
         'R7 未拦超长发明名称'),
        ('R7 阈值过严误伤合规名称', IRON, '            if n > TITLE_HARD_MAX:', '            if n > 3:',
         'R7 误判合规发明名称'),
        ('R8 逐字串不核', IRON, '        if PRODUCTION_CLAUSE not in text:', '        if False:',
         'R8 未拦缺逐字投产总则的'),
        ('R8 误伤 EVT 之外的文书', IRON,
         '    if EVT_DIR.search(path) or EVT_SCOPE.search(text):', '    if True:',
         ('合规稿件未全绿', '新生成的包未通过铁律门禁')),
        ('R8 适用域退化回"正文提到 04_EVT 就算 EVT 文书"', IRON,
         '    if EVT_DIR.search(path) or EVT_SCOPE.search(text):',
         '    if EVT_DIR.search(path) or EVT_DIR.search(text) or EVT_SCOPE.search(text):',
         '新生成的包未通过铁律门禁'),
        ('R9 逐字查新声明判据关掉', IRON,
         '        if NOVELTY_FLAT not in flat:', '        if False:',
         'R9 未拦缺逐字查新声明'),
        ('R9 作用域退化回全文（写在别的节也算兑现）', IRON,
         "        flat = re.sub(r'\\s+', '', '\\n'.join(bg_body))",
         "        flat = re.sub(r'\\s+', '', text)",
         '作用域丢了'),
        # R10 七条：整条不跑／适用域越界／两节引错法源／词表混进 R1 的词／词表混进撞车词／
        # 内联写法冒充节／pStyle 通道之外还有一条 md 通道。
        # 后两条各打一张"只关掉自己"的常驻前提断言（交集为空、撞车词必绿），
        # 这两格若没有注入臂，前提断言就是装饰。
        ('R10 整条不跑（摘要与简要说明的宣传语都不管）', IRON,
         '    for head, ref in R10_SCOPE:', '    for head, ref in ():',
         ('摘要里的商业宣传语未被 R10 抓住', 'docx 里的宣传语未被 R10 抓到')),
        ('R10 适用域越出两节（把权利要求段也管进来）', IRON,
         "R10_SCOPE = ((ABSTRACT_HEAD, '细则第二十六条：摘要中不得使用商业性宣传用语'),",
         "R10_SCOPE = ((ABSTRACT_HEAD, '细则第二十六条：摘要中不得使用商业性宣传用语'),\n"
         "             (CLAIMS_HEAD, '越界'),",
         'R10 越出摘要／简要说明两节去管全文了'),
        ('R10 简要说明侧引成摘要那条法源', IRON,
         "             (BRIEF_DESC_HEAD, '细则第三十一条：简要说明不得使用商业性宣传用语'))",
         "             (BRIEF_DESC_HEAD, '细则第二十六条：摘要中不得使用商业性宣传用语'))",
         ('简要说明里的宣传语未被 R10 抓住', 'docx 两节各引各的法源没分开')),
        ('R10 词表与 R1 重叠（同一件事被两条判据各报一遍）', IRON,
         "COMMERCIAL = ['性价比', '物美价廉', '价廉物美',",
         "COMMERCIAL = ['首创', '性价比', '物美价廉', '价廉物美',",
         'R10 词表与 R1 的 BANNED_ALWAYS 有重叠'),
        ('R10 词表混进技术撞车词（绝对式编码器被当宣传语）', IRON,
         "COMMERCIAL = ['性价比', '物美价廉', '价廉物美',",
         "COMMERCIAL = ['绝对', '性价比', '物美价廉', '价廉物美',",
         '技术语义撞车的词被 R10 判红了'),
        ('R10 的节锚点丢掉井号（正文里的「简要说明：」冒充一个节）', IRON,
         r"BRIEF_DESC_HEAD = re.compile(r'^#{2,3}\s*(?:\d+\.\s*)?(?:外观)?简要说明')",
         r"BRIEF_DESC_HEAD = re.compile(r'^\s*(?:\d+\.\s*)?(?:外观)?简要说明')",
         ('内联写法被当成一个节来判了',
          # 锚点放宽后一级标题 `# 简要说明` 也会先被 section_body 取走，
          # 于是"简要说明里的宣传语必红"那档同样翻绿——同一件变异的第二个合法原告。
          '简要说明里的宣传语未被 R10 抓住')),
        ('脚本总结行谎称 R1–R5', IRON, '（规则 R1–R13，判据见脚本 docstring）',
         '（规则 R1–R5，判据见脚本 docstring）', '门禁自报规则区间与实际判据'),
        ('R11 引用语判据关掉（说明书里"如权利要求…所述"照过）', IRON,
         '            m = CLAIMS_QUOTE_REF.search(ln)', '            m = None',
         '说明书里的引用语与宣传语未被 R11/R10 各点一条'),
        ('R10 说明书面关掉（第三张面没人看）', IRON,
         "            for w in COMMERCIAL:\n                if w in ln:\n"
         "                    findings.append(Finding('R10 说明书宣传用语', path, dstart + 1 + off,",
         "            for w in COMMERCIAL:\n                if False:\n"
         "                    findings.append(Finding('R10 说明书宣传用语', path, dstart + 1 + off,",
         '说明书里的引用语与宣传语未被 R11/R10 各点一条'),
        # 区域退化（单变量）：只把 R11 那一圈的行源从"说明书区域"换成"整份文书"，
        # R10 说明书面仍留在 dbody 上——第一版臂改的是 doc_region 那一行，两支面一起越域，
        # 结果先红的落在第 34 轮那条"R10 越出两节"控制上，电池读成 MISRED（红因归错条款）。
        # 第二版直接换成 enumerate(lines) 又 MISRED 一次：区域外那行的下标一起变，
        # 先红的是本轮那条绝对坐标档（它数的是 specdoc 那一行，索引一漂位点就错）。
        # 所以改成"区域行原样在前、区域外补在后面"：区域命中的下标一个不动，
        # 只有出域的那句新增开火——它咬的正是常驻那条出域档（第 38 轮之前那条按
        # `'→ R11' not in` 写、按构造永真，无论怎么退化都抓不到——见提交说明）。
        ('R11 说明书面区域退化成全文（别的节里的引用语也判）', IRON,
         '        for off, ln in enumerate(dbody):',
         '        for off, ln in enumerate(dbody + [l for l in lines if l not in dbody]):',
         # 第 40 轮区域改成多块并集之后，"区域之外补进来"补的是**所有块**之外的行，
         # 摘要与简要说明那两节从此也在里面，所以第一红挪到 R10 的越界档（常驻里它排在
         # 出域档之前）；「说明书」区域那一档是同一件变异的第二个消费者，两条都列进来。
         # 按本仓规矩 expect 是消费者集合，不调测试顺序来保读数。
         ('R10 越出摘要／简要说明两节去管全文了', '「说明书」区域之外被 R11/R10 越域判了')),
        # 这条打的是**量具**：常驻里那把现推 R 号的尺子若退回只认一位，R10 会被折成 R1，
        # "号有断档"从此看不见——与第 26 轮契约取号那次同源，只是这次咬的是测试自己。
        ('R 号提取器退回只认一位（R10 被折成 R1，断档永远看不见）', TS,
         r'''    return sorted({int(x) for x in re.findall(r"Finding\(\s*['\"]R(\d{1,2})", src)})''',
         r'''    return sorted({int(x) for x in re.findall(r"Finding\(\s*['\"]R(\d)", src)})''',
         ('R 号提取器把两位数判据号读错了', '门禁自报规则区间与实际判据')),
        # 文档侧取号不剥 URL 的 %XX 转义：`%E5%AE%A1` 会被 \b 读成判据号 E5，
        # 契约当场把 README 判成"文档虚指"（第 38 轮真踩过，读数是 文档虚指=['E5','E6']）。
        # 这一支臂打的是量具自己：剥转义那一步被拿掉时，常驻里的 URL 探针档必须红。
        ('文档侧取号不剥百分号转义（URL 里的 %E5 被当成判据号）', TS,
         "        return set(re.findall(DOC_RE, re.sub(PCT_ESC, '', t)))",
         '        return set(re.findall(DOC_RE, t))',
         '文档侧取号不认两位数或误收 0 号'),
        ('--all 只扫顶层（不递归）', IRON, '        for dp, _, fs in os.walk(root):',
         '        for dp, _, fs in [(root, [], [f for f in os.listdir(root)\n'
         '                              if os.path.isfile(os.path.join(root, f))])]:',
         ('--all 未递归到子目录里的两份文书', '--all 未抓到子目录内的违规',
          '新生成的包未通过铁律门禁')),
        ('docx 正文通道关掉（当成 utf-8 文本硬读）', IRON,
         "    if path.lower().endswith('.docx'):\n        return docx_text(path)",
         '    if False:\n        return docx_text(path)',
         ('Word-only 权要未被 Q 真判', '合规 docx 被铁律判红',
          'Word-only 申请文件被 P10 当成缺件')),
        ('docx 节标题还原失效（R3/R4 找不到节）', IRON,
         "            out.append('#' * int(m.group(1)) + ' ')", "            out.append('')",
         ('Word-only 权要未被 Q 真判', 'pStyle 还原没吃上力',
          'Word-only 申请文件被 P10 当成缺件')),
        ('docx 无节标题时不报未判（拿零违规冒充核过）', IRON,
         "        if p.lower().endswith('.docx') and not re.search(r'^#{1,6}\\s', text, re.M):",
         '        if False:', '无节标题的 docx 未报三态'),
        ('DOCTYPE/ENTITY 拒绝闸关掉（实体展开风险）', IRON, '        if marker in head:',
         '        if False:', '声明的 document.xml 未被拒绝'),
        ('zip 炸弹尺寸闸关掉', IRON, '        if info.file_size > MAX_XML_BYTES:',
         '        if False:', '上限被越过却没有拒绝'),
        ('--all 指到文件时不说成因', IRON, "f'--all 需要目录，实得不是目录: ",
         "f'，实得不是目录: ", '--all 指向非目录时未说明原因'),
        # ── 第 39 轮 R12／R13（指南第二部分第二章 §2.2.6 与 §2.4：同一张「标记｜名称」表，
        #    三面三种括号方向）六支臂 ────────────────────────────────────────────────────
        # 关掉判据的两支：原告是本轮那两条"必须开火"档（R12／R13 各一条，互不遮蔽）。
        ('R12 关掉（具体实施方式把标记写成加括号也照过）', IRON,
         '            if r12_start is not None:', '            if False:',
         'R12 具体实施方式加括号那一档开火数不对'),
        ('R13 关掉（摘要把标记裸写也照过）', IRON,
         '            if r13_start is not None:', '            if False:',
         'R13 摘要裸写标记那一档开火数不对'),
        # 号集放宽两支（R13 面与 R12 面各一支）：丢掉"必须是表里登记过的名称↔号对"这根锚，
        # 任何数字都当标记。原告必须是**表外自由数字的合规控制**（共 3 组／行程 5mm／2020 年／
        # 步骤（11）），不是那两条必红档——放宽后必红档照样红，读不出这把尺子已经越界。
        # R13 面放宽的第一红落在"两面合写的合规档"（它排在 R12／R13 各档之前），
        # 那一档同时装着两种括号方向，所以它也是下面"方向互换"那一支的原告。
        ('R13 号集放宽（丢掉表里登记这根锚，摘要里任何数字都当标记）', IRON,
         r"            bare = re.compile(re.escape(nm) + r'\s*' + re.escape(num) + r'(?![0-9])')",
         r"            bare = re.compile(r'(?<![0-9])[0-9]+')",
         '两面各按各的方向写的合规档没能全绿'),
        ('R12 号集放宽（丢掉锚，具体实施方式里任何括号数字都当标记）', IRON,
         r"            pbr = re.compile(re.escape(nm) + r'\s*[（(]\s*' + re.escape(num) + r'\s*[）)]')",
         r"            pbr = re.compile(r'[0-9]+\s*[）)]')",
         # 原告是那张"表外加括号数字（步骤 11）仍须全绿"的合规控制。常驻里 R12 那一对刻意把
         # 合规档排在必红档**之前**（与 R13 那对相反）：放宽后必红档只是条数变多，
         # 若它先红，读数就成了"开火数不对"而不是"这把尺子越界咬表外数字"。
         '具体实施方式里不加括号的标记、或"（11）"这类表外加括号数字被 R12 判红了'),
        ('R12 与 R13 方向互换（摘要该加括号却按不加判、具体实施方式反之）', IRON,
         r"            bare = re.compile(re.escape(nm) + r'\s*' + re.escape(num) + r'(?![0-9])')"
         + "\n"
         + r"            pbr = re.compile(re.escape(nm) + r'\s*[（(]\s*' + re.escape(num) + r'\s*[）)]')",
         r"            bare = re.compile(re.escape(nm) + r'\s*[（(]\s*' + re.escape(num) + r'\s*[）)]')"
         + "\n"
         + r"            pbr = re.compile(re.escape(nm) + r'\s*' + re.escape(num) + r'(?![0-9])')",
         '两面各按各的方向写的合规档没能全绿'),
        # 号集从包级退回单份文书：那张表常写在**另一份**文书的附图说明节里（本轮的真实形态），
        # 退回去摘要侧就永远看不见它、只剩"未判"。原告是"包级号集"那一档（分两份扫必须翻红）；
        # 同一对里的另一半"只扫摘要那份报未判"在注入下照旧成立，咬不住——所以这一支只有前一半。
        ('号集改成按单份文书读（不再包级）', IRON,
         '    marks = mark_map([t for _, t in docs])\n    for p, text in docs:\n',
         '    for p, text in docs:\n        marks = mark_map([text])\n',
         '对照表写在另一份文书时 R13 没判红'),
        # ── 第 40 轮 R11／R10 说明书区域（`spec_doc_blocks`：把"锚标题层级"改成
        #    "锚法条节名的多块并集"）五支臂 ──────────────────────────────────────────────
        # 常驻夹具 test_iron_spec_region_shapes 已按落点形状成对判（生产扁平／旧嵌套／出域节名
        # 静默／第二处同名节／区域为空三态／生产真工件），这里补"只关自己"的注入臂：
        # 每支只动 spec_doc_blocks 里的一处判点，其余三面（块头认什么、块到哪止、取几块、
        # 原点怎么算）各自单独占一支，免得一支退化把另一支的读数一起改掉。
        # 块头那一支的 expect 写成元组：第一红落在 test_check_iron_rules 的"出域档正向对偶"
        # （它排在按形状判的那档之前），扁平形状①档是同一件事的第二个消费者——两档都只由
        # "块头认节名"这半撑着，遇红即停的套件读不到第二档，所以它按消费者集合列进来。
        ('说明书区域退回"止于下一个 ≤2 级标题"的旧划法（扁平模板上只剩一行射程）', IRON,
         "        if not (SPEC_DOC_HEAD.match(raw) or title == '说明书' or title in SPEC_SECTIONS):",
         '        if not SPEC_DOC_HEAD.match(raw):',
         ('出域档的前提不成立：同样这批字节把节名换成「具体实施方式」后也没开火，',
          '生产扁平形状（五节全 `##`）里「## 具体实施方式」下那句未被 R11/R10 各点一条，')),
        # 块止条件那一支：丢掉 SPEC_REGION_STOP 名单后只剩"级数不高于自己才停"，
        # 于是 `# 说明书` 一级块把夹在里面的 `## 权利要求书` 一起吞进区域——
        # 那里用引用语正是法条要求的写法，吞进来就是把假阴性修成假阳性。
        # 原告只有"层级不救场"那一档：扁平形状里各节同为 `##`，Stop 名单本来就轮不到说话，
        # 只有 1 级标题做块头时它才是唯一防线（常驻那条③换名档在注入下照旧静默，咬不住）。
        ('区域吞进权利要求书（那里用引用语是法条要求的写法，吞进来＝造假红）', IRON,
         '            if jlevel and (jlevel <= level or jtitle in SPEC_REGION_STOP):',
         '            if jlevel and jlevel <= level:',
         '「# 说明书」底下那一节「## 权利要求书」被并进区域了（越界假红）'),
        # 五节名单那一支：SPEC_SECTIONS 是**共享常量**（定义住判据侧，rebuild_package 从 _cir 取），
        # 所以丢掉「附图说明」的第一红落在 P12 那一档（套件里它排在区域档之前），
        # 区域侧的"第二处同名节"是同一件变异的第二个消费者——expect 按消费者集合列全，
        # 不调测试顺序来保读数（本仓规矩）。
        ('五节名单退回四节（丢掉附图说明那一块，第二处同名节的判点就没了）', IRON,
         "SPEC_SECTIONS = ('技术领域', '背景技术', '发明内容', '附图说明', '具体实施方式')",
         "SPEC_SECTIONS = ('技术领域', '背景技术', '发明内容', '具体实施方式')",
         ('有图的包缺「附图说明」节没被 P12 点出',
          '第二处同名节（生产包里 `## 附图说明` 出现两次）里的违规句未被逐块报出，')),
        # 块数那一支：只取第一块＝后面的块整批看不见。两支原告各钉一块（扁平形状那块与
        # 第二处同名那块），单写任一支都会在另一支上读成 MISRED——它们是同一件变异的两个消费者。
        ('块扫描只取第一块（后面的块整批看不见）', IRON,
         '        spans.append((i, j - 1))',
         '        spans.append((i, j - 1))\n        break',
         ('生产扁平形状（五节全 `##`）里「## 具体实施方式」下那句未被 R11/R10 各点一条，',
          '第二处同名节（生产包里 `## 附图说明` 出现两次）里的违规句未被逐块报出，')),
        # 原点那一支：多块并集下每条 Finding 的行号由它自己所在那块算出（`dstart + 1 + off`）。
        # 共用第一个原点在"只有一块"时读不出来，所以原告必须是**开在两处**的扁平形状档——
        # 它按绝对坐标对账（位点由测试自己 enumerate 夹具算出），漂一行就红。
        ('多块并集下所有 Finding 共用第一个原点（位点漂到别处）', IRON,
         '        blocks.append((k, lines[k:e + 1]))',
         '        blocks.append((blocks[0][0] if blocks else k, lines[k:e + 1]))',
         '生产扁平形状（五节全 `##`）里「## 具体实施方式」下那句未被 R11/R10 各点一条，'),
        # ── 第 41 轮 Word 通道区域形状档（test_iron_spec_region_shapes_docx）配的这支臂 ──────
        # 落点为什么选在**名单本体**而不是扫描循环那一行：上面第 40 轮已有一支针
        # `if jlevel and (jlevel <= level or jtitle in SPEC_REGION_STOP):`（谓词接法），而常驻体检
        # `test_battery_needle_census` 要求每条 needle 在目标脚本里**恰好命中一次**——同一段代码
        # 让两支臂共用同一个 needle 串，`replace(old, new, 1)` 只会打到第一处，体检也当场报 dup。
        # 所以这一支把 `SPEC_REGION_STOP` 元组里「权利要求书」那一格摘掉，谓词那一行一字不动：
        # 两支臂各咬一层退化——那一支证明"名单没接进扫描循环"会被抓到，这一支证明"名单里少一格"
        # 也会被抓到，只留任一支的话另一层的退化都是静默的。
        # 原告写成**消费者集合**（本仓规矩：两臂原告重叠时列全，不调测试顺序去保读数）：摘掉名单
        # 里那一格之后，md 面"层级不救场"那档与本轮新加的 Word 面 H1 罩档是同一个成因，而套件遇红
        # 即停、TESTS 里 md 那档排在 Word 这档之前 ⇒ 电池读到的第一红是 md 那条消息；Word 那条是
        # 同一件变异的第二个消费者，它被单独咬到的证据见收尾报告的"手动注入＋只跑新档"三行读数
        # （电池自身看不见第二档——fail-fast 是套件的既有行为，不是本臂的缺陷）。
        ('区域 Stop 名单摘掉「权利要求书」那一格（说明书罩把权要吞进区域）', IRON,
         "SPEC_REGION_STOP = ('权利要求书', '权利要求建议稿', '说明书摘要', '摘要建议稿',\n"
         "                    '图中标记说明', '说明书附图', '附图', '简要说明', '简要说明建议稿')",
         "SPEC_REGION_STOP = ('权利要求建议稿', '说明书摘要', '摘要建议稿',\n"
         "                    '图中标记说明', '说明书附图', '附图', '简要说明', '简要说明建议稿')",
         ('「# 说明书」底下那一节「## 权利要求书」被并进区域了（越界假红）',
          'Word 件「# 说明书」罩底下那一节「## 权利要求书」被并进区域了（越界假红，'
          '那里用引用语是法条要求的写法）')),
    ],
    'fig': [
        ('C1 彩色判据关闭', CF, '    if colored > 0 and not allow_color:', '    if False:',
         'C1 彩色判据未触发或未标名'),
        ('C1 恒判红（误伤合规稀疏框图）', CF, '    if colored > 0 and not allow_color:', '    if True:',
         '稀疏合法框图被误判违规'),
        ('C2 空白判据关闭', CF, '    if ink == 0:', '    if False:',
         'C2 空白判据未触发或未标名'),
        ('C2 阈值反向（ink>0 即判空白）', CF, '    if ink == 0:', '    if ink > 0:',
         'C2 空白判据未触发或未标名'),
        ('回归：把 C2 改回旧的字节阈值 10240', CF, '    if ink == 0:',
         '    if os.path.getsize(path) < 10240:', '稀疏合法框图被误判违规'),
        ('C3 只打印不判红（历史事故原样复现）', CF,
         '        total_bad += len(check_docx_media(d))', '        _printed_only = check_docx_media(d)',
         'docx 丢图未计入退出码'),
        ('C3 只查目录里第一份 docx（历史缺陷）', CF,
         "    nfig = len([x for x in os.listdir(figdir) if x.lower().endswith('.png')])\n"
         "    for f in sorted(os.listdir(d)):\n        if not f.endswith('.docx'):",
         "    nfig = len([x for x in os.listdir(figdir) if x.lower().endswith('.png')])\n"
         "    for f in [x for x in sorted(os.listdir(d)) if x.endswith('.docx')][:1]:\n        if False:",
         '同目录第二份 docx 丢图未被逐个核对'),
        ('C3 丢图判据关闭', CF, '        else:\n            print(f"  FAIL {f}: media=',
         '        elif False:\n            print(f"  FAIL {f}: media=',
         'docx 丢图未计入退出码'),
        ('C3 在没有 figures 目录时仍然判红', CF,
         '    if not os.path.isdir(figdir):\n        return bad', '    if False:\n        return bad',
         '无 figures 目录被判违规'),
        ('C3 把 media 目录放宽到整个 word/（把 document.xml 也数进去）', CF,
         "media = [x for x in z.namelist() if x.startswith('word/media/')]",
         "media = [x for x in z.namelist() if x.startswith('word/')]",
         ('图数齐全时误判违规', '坏件移除后该目录仍未放行')),
        ('C3 把非 zip 的 .docx 静默跳过（只打印不计数）', CF,
         '            bad.append(p)\n            continue', '            continue',
         '打不开的 docx 未计入违规或未说清成因'),
        ('C4 只打印不计入退出码', CF,
         '            total_bad += len(check_docx_embedded(d, tmp, allow_color, stats))',
         '            _printed = check_docx_embedded(d, tmp)',
         'docx 内嵌彩色图未被 C4 抓到'),
        ('C4 内嵌图判据关闭', CF,
         '                    if reasons:\n                        why = \'; \'.join(reasons)',
         '                    if False:\n                        why = \'; \'.join(reasons)',
         'docx 内嵌彩色图未被 C4 抓到'),
        ('C4 恒判红（合规内嵌件也咬）', CF,
         '                    if reasons:\n                        why = \'; \'.join(reasons)',
         '                    if True:\n                        why = \'; \'.join(reasons)',
         ('合规内嵌图被 C4 误判', '坏件移除后该目录仍未放行')),
        ('有损格式被折成违规（JPEG 色度噪声）', CF,
         "                    if ext not in ('.png', '.tif', '.tiff', '.bmp', '.gif'):",
         '                    if False:',
         ('有损内嵌图未走"未核"三态', '有损格式被当成违规')),
        ('外观设计包的 C4 豁免失效', CF,
         "    if 'views' in d or '外观设计' in d:\n"
         "        print(f'  note {d}: 外观设计视图目录，C4 内嵌图像素规则不适用')",
         '    if False:\n'
         "        print(f'  note {d}: 外观设计视图目录，C4 内嵌图像素规则不适用')",
         '外观设计包未被 C4 跳过'),
        ('内嵌件解不开被折成"看不见"（不计数）', CF,
         "                        bad.append(f'{f}: {os.path.basename(n)} 内嵌图无法解码 -> {e}')",
         "                        pass",
         '解不开的内嵌件未判红或未说成因'),
        ('C5 判据关掉（写了请求保护色彩交黑白件也没人管）', CF,
         "        if decl and stats['images'] and stats['colored'] == 0:", '        if False:',
         '没被 C5 抓到'),
        ('声明了也不开豁免（合法彩色申请继续被 C1 误伤）', CF,
         '        allow_color = bool(decl)', '        allow_color = False',
         '仍被 C1 误伤，或豁免没说出依据在哪'),
        ('文书读不动时不计数（未核这件事就不跟着 C1 出去）', CF,
         '                unreadable += 1', '                unreadable = 0',
         '没跟着真开火的 C1 一起出去'),
        ('F5 线宽判据关掉', PF,
         '        if not (LINE_W_RANGE[0] <= width <= LINE_W_RANGE[1]):', '        if False:',
         '未被 F5 拦住'),
        ('F5 带宽收成一个点（合法 1.0/1.5pt 全被判红）', PF,
         'LINE_W_RANGE = (0.8, 1.5)', 'LINE_W_RANGE = (0.8, 0.8)',
         '被 F5 误伤'),
        ('离线档不再自述"这一档不判 F5"（违规 0 会被读成全核过）', PF,
         'F5 线宽无位图侧 witness、本档一律不判', 'F5 线宽本档不判（自述被删）',
         '未打印离线覆盖面自述'),
        ('F6 的填充面扫描整段摘掉', PF,
         '        for p in self.ax.patches:', '        for p in []:',
         'F6 未拦住'),
        ('F6 只写了扫描没接进 save()（灰底图照样落盘）', PF,
         '        self.violations += self.scan_vector()      # F6：画布对象上还看得见，存成 PNG 就没了',
         '        pass  # F6 钩子被摘',
         'F6 没接进 save()'),
        ('F6 白底豁免收掉（实心白填充与剖面 hatch 全被判红）', PF,
         '            if p.get_fill() and a > 0.999 and not (r > 0.95 and g > 0.95 and b > 0.95):',
         '            if p.get_fill() and a > 0.0:',
         'F6 把实心白填充判红了'),
        ('把 --help 豁免抹掉（用法出口退回"不认 flag"档）', CF,
         "    if any(a in ('-h', '--help') for a in args):", '    if False:',
         '出口未打印用法并退 0'),
        ('F1 dpi 下限不核', PF, '        if dpi < DPI_MIN:', '        if False:', 'F1 未拦住'),
        ('F1 图宽区间不核', PF,
         '        if not (WIDTH_CM_RANGE[0] <= fig_w_cm <= WIDTH_CM_RANGE[1]):', '        if False:',
         'F1 未拦住'),
        ('F1 恒判红（误伤合规出图）', PF,
         '        if not (WIDTH_CM_RANGE[0] <= fig_w_cm <= WIDTH_CM_RANGE[1]):', '        if True:',
         '合规几何参数被建图即判红'),
        ('F2 图题照收不误', PF, '        if caption:', '        if False:',
         'save(caption=) 未拒绝嵌图题'),
        ('F3 同图内同号异件不查', PF, '            if prev is not None and prev != part:',
         '            if False:', '同图内同号异件未被 F3 抓到'),
        ('F3 与已登记历史不一致不查', PF, '            if hist is not None and hist != part:',
         '            if False:', '与本案登记表同号异件未在出图当场抓到'),
        ('F3 与已登记历史恒判红', PF, '            if hist is not None and hist != part:',
         '            if hist is not None:', 'verify_saved 复检未全绿'),
        ('F3 跨图同号异件不查', PF, '            if num in seen and seen[num][1] != part:',
         '            if False:', '跨图同号异件未抓到'),
        ('F4 框内字数不核', PF, '        if len(text) > BOX_TEXT_MAX:', '        if False:',
         'F4 未拦超长框内文字'),
        ('F4 阈值过严误伤合规框', PF, '        if len(text) > BOX_TEXT_MAX:',
         '        if len(text) > 2:', '合规框内文字被 F4 误判'),
        ('自检未过的图不删（违规件会被打包带走）', PF, '            os.remove(path)',
         '            pass', '自检未过的图仍留在盘上'),
        ('--check 有 dpi 也永不核图宽', PF, '        if dpi and dpi >= DPI_MIN - 1:',
         '        if False:', 'PNG 带 dpi 元数据时 --check 未核图宽'),
        ('--check 把无 dpi 元数据按假定 dpi 反推成违规', PF,
         '        if dpi and dpi >= DPI_MIN - 1:\n            w_cm = w_px / dpi * 2.54',
         '        if True:\n            w_cm = w_px / (dpi or DPI_MIN) * 2.54',
         '无 dpi 元数据时 F1 未走三态'),
        ('--check 无 dpi 时把已判出的像素违规一起丢掉', PF,
         "            print(f'  note {p}: PNG 无 dpi 元数据，F1 几何未核（不折成违规也不折成合规）')",
         "            print(f'  note {p}: PNG 无 dpi 元数据，F1 几何未核（不折成违规也不折成合规）')\n"
         '            probs = []',
         'F1 三态把该图的像素判据一起免检了'),
        # C 门禁的输入档（第 20 轮端到端跑出来的：`<目录> --all` 以 FileNotFoundError
        # 崩进 C4 并退 1，而 1 专属"存在违规"；零参数则静默退 0）。三档各一条注入。
        ('未知 flag 又被当成目录喂进 os.listdir', CF,
         "        if d.startswith('-'):", '        if False:',
         '未知 flag 被当成目录喂进 C 门禁'),
        ('不存在的路径不再 fail-closed（崩一次发一张假违规单）', CF,
         '        if not os.path.isdir(d):', '        if False:',
         '路径不存在未说清成因并 fail-closed'),
        ('零参数被当成"已判过且合规"', CF, '    if not args:', '    if False:',
         '一个目录都没接却被当成已通过'),
    ],
    'vsr': [
        # V5/V6 只管句法形状，五支臂各钉一条：整串中文、块数区间、泛义词表、单字碎块、
        # 占位先认（反方向：把占位判成违规也是坏）、IPC/CPC 形状。
        ('V5 整串中文这一支关掉', V,
         '            if len(blocks) == 1 and CJK_RUN.search(blocks[0]):', '            if False:',
         '整串中文检索式未被 V5 抓到'),
        ('V5 块数区间放开成不设限', V,
         'BLOCK_MIN, BLOCK_MAX = 2, 8', 'BLOCK_MIN, BLOCK_MAX = 0, 999',
         ('块数越界未被 V5 抓到', '单个长块未被 V5 抓到')),
        ('V5 泛义词表清空', V,
         "VAGUE_WORDS = ('检索', '增强', '系统', '方法')", 'VAGUE_WORDS = ()',
         '泛义词块未被 V5 抓到'),
        ('V5 不再认单字碎块', V,
         '            frag = [b for b in blocks if ONE_CJK.match(b) or b in VAGUE_WORDS]',
         '            frag = [b for b in blocks if b in VAGUE_WORDS]',
         '单字碎块未被 V5 抓到'),
        ('V5 把占位当成写坏了的检索式（底稿期直接红）', V,
         "        if '【' in q and '】' in q:", '        if False:',
         ('占位检索式被折成违规或不吭声', '骨架底稿未通过 V1–V6')),
        ('V6 分类号形状不查', V,
         '    if wrong:', '    if False:', '坏分类号没被抓到、或把好的也一起报了'),
        ('V4 arXiv 预印本标注判据关掉', V,
         "            elif PREPRINT_WORD not in cell('kind'):", '            elif False:',
         '没被 V4 抓到'),
        ('V4 把"表里没有类型列"折成违规', V,
         '                v4_no_col = True',
         "                bad.append(f'{path}: 缺列也判红 → V4')",
         '被折成违规或折成合规'),
        ('V1 放过无可机检标识的条目', V, '        if kind is None:', '        if False:',
         '无标识条目未判 V1'),
        ('V1 把所有条目都判成无标识', V, '        if kind is None:', '        if True:',
         '合规检索报告被 V1/V2/V3 误判'),
        ('V2 专利关键日期不核', V, "        if kind == 'patent' and 'key_date' not in no_col",
         "        if False and 'key_date' not in no_col", '缺字段未逐条判 V2'),
        ('V2 核验出处不核', V, "        if 'source' not in no_col and not cell('source').strip():",
         '        if False:', '缺字段未逐条判 V2'),
        ('缺列抑制失效（一条缺陷放大成 N 条）', V,
         '    no_col = set(missing)     # 整列缺失时不再逐行刷"未填"，否则一条缺陷被放大成 N 条',
         '    no_col = set()', '整列缺失被放大成逐条违规'),
        ('行列数不符仍按位取列', V, '        if ncols and len(cells) != ncols:',
         '        if False and len(cells) != ncols:', '多出一格的行未被报出'),
        ('V3 源说查无此项却不判红', V, "        if st == 'absent':", '        if False:',
         '源说查无此项却未判 V3'),
        ('V3 把源不可达折算成违规', V,
         "            notes.append(f'{path}: {ident} 在线源不可达，存在性未核（不折成违规也不折成合规）')",
         "            bad.append(f'{path}: 在线源不可达 {ident} → V3')",
         '网络不可达被判成引用造假'),
        ('arXiv 只看状态码不数 entry', V,
         "        return 'ok' if b'<entry' in body else 'absent'", "        return 'ok'",
         'arXiv 空 feed 被当成存在'),
        ('在线核成计数把专利也算进去', V,
         "            notes.append(f'{path}: {ident} 存在性未核（无可用无密钥源，按 S1 逐条人工核对）')",
         "            notes.append(f'{path}: {ident} 存在性未核')\n            checked += 1",
         '在线核成应只数 DOI+arXiv 两条'),
        ('--require-online 不再 rc=2', V,
         '    if args.require_online and not args.offline and online_ok == 0:', '    if False:',
         '--require-online 在源全不可达时未 rc=2'),
        ('目录模式不再限定 *检索* 这个名字（README 之类也被挑进来了）', V,
         "             if '检索' in f and f.lower().endswith(('.md', '.docx'))]",
         "             if f.lower().endswith(('.md', '.docx'))]", '目录模式挑文件不对'),
        ('输入不存在被当成零违规放行', V,
         "            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')\n            sys.exit(2)",
         '            continue', '路径不存在未按要求说清成因'),
        ('骨架不再生成 EVT 底稿', NP,
         "    with open(os.path.join(evt, f'EVT_{name}.md'), 'w', encoding='utf8') as f:\n"
         '        f.write(EVT.format(name=name, clause=PRODUCTION_CLAUSE))', '    pass',
         '缺 EVT 报告底稿'),
        ('投产总则不 import 而是重抄一份（与判据漂移）', NP,
         'f.write(EVT.format(name=name, clause=PRODUCTION_CLAUSE))',
         "f.write(EVT.format(name=name, clause='任何设计内容在对应物理实测全部通过前不得进入投产阶段。'))",
         '新生成的包未通过铁律门禁'),
        ('EVT 底稿表头丢掉「判定」列（E1–E3 无从判起）', NP,
         '| # | 设计项 | 验证方法 | 分析结论 | 物理实测项 | 判定 |\n|---|---|---|---|---|---|',
         '| # | 设计项 | 验证方法 | 分析结论 |\n|---|---|---|---|',
         '骨架上的 EVT 底稿未通过 E1–E4'),
        ('零条目不再如实报"0 条"（rc=0 冒充已核过）', V,
         '        if n_ent == 0:', '        if False:', '或未如实报出"条目 0 条"'),
        ('骨架不再生成检索底稿', NP,
         "    with open(os.path.join(root, f'检索_{name}.md'), 'w', encoding='utf8') as f:\n"
         '        f.write(SEARCH.format(name=name))', '    pass', '缺检索报告底稿'),
        ('底稿文件名丢掉"检索"二字（目录模式将挑不到它）', NP,
         "f'检索_{name}.md'", "f'report_{name}.md'", '缺检索报告底稿'),
        ('骨架表头列名与 templates §10 漂移', NP,
         '| # | 类型 | 标识符 | 标题 | 关键日期 | 核验出处 | 核验日期 |',
         '| # | 类型 | 编号 | 标题 | 日期 |', '骨架底稿未通过 V1'),
        ('V 的 docx 读取退回按 md 直读（Word 报告 ⇒ 退码 1 冒充"发现违规"）', V,
         '        text = read_any(p)',
         "        text = open(p, encoding='utf8').read()",
         'Word 检索报告未被 V 真判（表格没吃到）'),
        ('目录成对时不再挑可编辑源（md+docx 两份都算，条目翻倍）', V,
         '            got, skipped = pick_reports(p)',
         "            got, skipped = ([os.path.join(p, f) for f in sorted(os.listdir(p))"
         " if '检索' in f and f.lower().endswith(('.md', '.docx'))], [])",
         ('成对时没挑 md（或两份都算进去了）', '成对挑选没说出被丢的那份，或条目数被翻倍')),
        ('被丢掉的那份不说出来（静默丢件与不丢读数相同）', V,
         '            for f in skipped:', '            for f in []:',
         '成对挑选没说出被丢的那份，或条目数被翻倍'),
        ('目录模式退回只收 md（Word-only 交付包对 V 完全隐形）', V,
         "f.lower().endswith(('.md', '.docx'))]",
         "f.lower().endswith('.md')]", '目录模式未收 .docx 检索报告'),
    ],
    'pack': [
        # P1–P4 里 P4（UTF-8 标志位）没有注入：合法打包路径下 Python zipfile 总会置位，
        # 造不出"未置位"的 zip；它由 test_rebuild_package 的直接断言钉（flag_bits & 0x800）。
        ('P1 字节数比对关掉（截断看不见）', RP,
         '            if infos[rel].file_size != sz:', '            if False:',
         '截断（字节数不符）没被抓到'),
        ('P2 内容哈希比对关掉', RP,
         '            if a != b:', '            if False:',
         '同长度换字（SHA-256 不符）没被抓到'),
        ('P3 读不出条目的兜异常收窄（崩一次就不是一回事了）', RP,
         '            except zipfile.BadZipFile as e:', '            except ImportError as e:',
         'P3 没抓到、逃逸成异常、或重复上报'),
        ('P3 已被 testzip 点名的条目再报一遍', RP,
         '                if rel != crc_bad:', '                if True:',
         'P3 没抓到、逃逸成异常、或重复上报'),
        ('名单差集不报（只比内容，名字丢了不知道）', RP,
         '        for x in sorted(set(want_rel) ^ set(got)):', '        for x in []:',
         '名单差集或交集内容比对没报全'),
        ('输入档不再只接包目录', RP,
         '    if not os.path.isdir(target):', '    if False:',
         '传文件没说明成因'),
        ('P5 缺段判据关掉（少一整段也照样打包交付）', RP,
         '        if not os.path.isdir(os.path.join(pkg, d)):', '        if False:',
         '缺一段没被点名成一条 P5'),
        ('P6 包根 README 存在性不报（缺 README 也不吭声）', RP,
         "        bad.append('P6 包根没有 README.md（§8 六件套之一）')", '        pass',
         '包根缺 README.md 没被抓到'),
        ('P7 退化成"目录里有东西就行"（0 字节文件骗过它）', RP,
         '        if not any(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(app) for f in fs):',
         '        if not os.listdir(app):',
         '只有一个 0 字节文件也被当成'),
        # P8／P9：读「专利清单」的类型列与全包图数。四条各钉一头，
        # 「认不出就当发明」与「看不见就当没图」是这类判据最自然的两种坏法。
        ('P8 认不出类别时当成发明（类别不明确从此不报）', RP,
         "                key = _ck.type_of(cell)",
         "                key = _ck.type_of(cell) or '发明'",
         ('类别写成「产品」没被 P8 抓到', '空类型没被 P8 抓到')),
        ('P8 先认类别再认占位（【待填写：发明/实用新型】被读成已定发明）', RP,
         "                if '【' in cell and '】' in cell:", '                if False:',
         '占位被当成已声明类别，或没说清这是未判'),
        ('P9 实用新型零图不报', RP,
         "                elif n_img == 0:\n                    bad.append('P9 专利清单列了实用新型",
         "                elif False:\n                    bad.append('P9 专利清单列了实用新型",
         '实用新型零图未被 P9 抓到（或牵连误报了 P8）'),
        ('docx 读不动时 P9 猜成"没图"（看不见折成违规）', RP,
         '                    return None', '                    return 0',
         'docx 读不动时 P9 猜成"没图"、或干脆不吭声'),
        ('P10 缺件判据关掉（少一整件也照样打包）', RP,
         '        for s in miss:', '        for s in ():',
         ('缺权利要求书没被 P10 抓到', '摘要/附图被当成说明书，或缺件报少了')),
        ('P10 退回"包含"认节（摘要与附图冒充说明书）', RP,
         '    miss = [s for s in APPLY_SECTIONS if s not in aseen]',
         '    miss = [s for s in APPLY_SECTIONS if not any(s in h for h in aseen)]',
         '摘要/附图被当成说明书，或缺件报少了'),
        # P12 四条：整条不跑／适用域跟着 P10 走歪／"同一份说明书"这条被放宽成并集／
        # 附图说明的条件项被当成无条件项。第三条最要紧——它正是 P12 与 P10/P11 的分工：
        # 并集判"包里有吗"，逐份判"这一份齐不齐"，两者混用会把拼盘读成合规。
        ('P12 五节这条整列不跑', RP,
         '    if need_trio and adocs is not None:', '    if False:',
         '缺两节没被 P12 逐节点出来（或牵连误报了别的）'),
        ('P12 的适用域跟着外观那一支走（该判的不判）', RP,
         "    need_trio = (not declared) or bool({'发明', '实用新型'} & set(declared))",
         "    need_trio = bool(declared)",
         ('外观设计包被按发明口径要三件或五节', '缺两节没被 P12 逐节点出来',
          # 类型未定（清单只有表头）时被折成豁免，先红的仍是 P10 那档合规范本
          '三件齐的申请文件被 P10 误伤')),
        ('P12 放宽成并集（五节拆成五份文件也算齐）', RP,
         "        specs = [(f, sset) for f, sset in adocs[0] if '说明书' in sset]",
         "        specs = [('整个 02 目录',"
         "{n for _f, ss in adocs[0] for n in ss})]"
         " if any('说明书' in ss for _f, ss in adocs[0]) else []",
         '五节被拆成五份文件仍被读成"说明书五节齐"'),
        ('P12 把「附图说明」当无条件项（无图发明也被要）', RP,
         "                    want_fig = bool(n_fig) or '实用新型' in declared",
         "                    want_fig = True",
         '没有附图的发明包被 P12 要求"附图说明"这一节'),
        ('读不动的文书不再计成未核（P10 的绿就没了依据）', RP,
         "        if aunread:\n            notes.append(f'P10 未核：",
         "        if False:\n            notes.append(f'P10 未核：",
         '读不动的 docx 被折成缺件、或未核这件事没说出来'),
        # P10 的适用面两个相反方向各一条：把发明口径套到只列外观设计的包上（假红），
        # 和把"类型还没定"折成豁免（假绿）。同 needle、不同变体——这一对的形状就是
        # 记忆里"冗余双防线必须各配一条只关掉自己的对照"，只是这次两根轴在同一行上。
        ('P10 对只列外观设计的包也按发明口径要三件', RP,
         "    need_trio = (not declared) or bool({'发明', '实用新型'} & set(declared))",
         '    need_trio = True',
         '只列外观设计、依法只交简要说明与图的包被按发明口径要了三件'),
        ('P10 把"类型还没定"折成豁免', RP,
         "    need_trio = (not declared) or bool({'发明', '实用新型'} & set(declared))",
         "    need_trio = bool({'发明', '实用新型'} & set(declared))",
         ('类型还没定时 P10 被折成"这一支不受要求"（未判当豁免）',
          # 同一件变异的第二个合法原告：合规范本（清单只有表头 ⇒ 类型未定）会先被
          # "P10 不适用"那句 note 撞红，因为老断言禁的是"任何 P10 note"。
          '三件齐的申请文件被 P10 误伤')),
        # P11 五条：整条不跑／适用域越界（未列外观设计也管）／节名退回"包含"认（建议稿冒充）／
        # 没图这一半漏判／同一件事实被 P9 与 P11 各报一遍。
        # 第 4、5 条分别打的是 P11 里"漏判"与"双报"两个相反方向——它们由同一件事实
        # （n_img==0 且两型同列）决定，缺任一臂另一臂就是装饰。
        ('P11 外观设计那一支整条不跑', RP,
         "            if '外观设计' in declared:", "            if False:",
         ('外观设计缺简要说明没被 P11 单独点出来', '同一件"全包零图"被判成两个原告')),
        ('P11 适用域越界（清单没列外观设计也去要简要说明）', RP,
         "            if '外观设计' in declared:", "            if True:",
         ('只列发明的包被 P11 管上了（适用域越界）', '三件齐的申请文件被 P10 误伤',
          '外观齐件', '缺简要说明的外观设计包',
          # 再两个合法原告：越界后所有 P8/P9 那批只列发明／实用新型的夹具
          # 都会被 P11 要一份简要说明，先红的可能是清单族那档而非我新写的那档。
          '合规清单被 P8/P9 误伤')),
        ('P11 节名退回"包含"认（「简要说明建议稿」冒充已交）', RP,
         '                    if DESIGN_SECTION not in aseen:',
         '                    if not any(DESIGN_SECTION in h for h in aseen):',
         '「简要说明建议稿」被当成已经交了简要说明'),
        ('P11 的"没图"漏判（外观设计的图片这一格没人核）', RP,
         "                    elif n_img == 0:\n                        if '实用新型' in declared:",
         "                    elif False:\n                        if '实用新型' in declared:",
         ('零图的外观设计包没被 P11 恰好抓住一条', '同一件"全包零图"被判成两个原告')),
        ('P11 与 P9 各报一遍同一件"全包零图"', RP,
         "                        if '实用新型' in declared:",
         "                        if False:",
         '同一件"全包零图"被判成两个原告'),
    ],
    'doc': [
        ('陈旧判据彻底关闭（永不判陈旧）', RG,
         '        if os.path.getmtime(md) > dm + 1:', '        if False:',
         'md 比 docx 新却未判陈旧'),
        ('容差被放大到一年（正常流程里常年假绿）', RG,
         '        if os.path.getmtime(md) > dm + 1:',
         '        if os.path.getmtime(md) > dm + 31536000:',
         'md 比 docx 新却未判陈旧'),
        ('孪生 mtime 读不到时不再兜住（崩给调用方看，退码 1 冒充发现违规）', RG,
         '        except OSError:', '        except ImportError:',
         '孪生 docx 读不到 mtime 时未 fail-closed'),
        ('陈旧只打印不计入退出码', RG,
         '        sys.exit(1 if stale else 0)', '        sys.exit(0)',
         'md 比 docx 新却未判陈旧'),
        ('配对规则放宽到有 md 就算（无孪生也报陈旧）', RG,
         '                if os.path.exists(d):', '                if True:',
         '无孪生 docx 的 md 被算进配对'),
        ('--check 指到文件时不说成因', RG,
         "f'--check 需要目录，实得不是目录: ", "f'，实得不是目录: ",
         '--check 指到文件未说明成因'),
        ('无成对文件被折成未判定（rc=2）', RG,
         '        if not n:', '        if n < 0:', '无成对文件时读数不对'),
    ],
    'evt': [
        ('E1 空判定被整行跳过（含糊措辞当已判）', CE,
         "                if not present:\n"
         "                    bad.append(f'{where} 判定列未落三态（须 ✅/⚠️/❌ 恰一个），'\n"
         "                               f'实得「{cells[jv][:20]}」→ E1')",
         '                if not present:\n                    continue',
         'E1 空判定（含糊措辞）未判红'),
        ('E1 两符号并存不再判红', CE, '                elif len(present) > 1:',
         '                elif False:', 'E1 双符号并存未判红'),
        ('E2 ⚠️ 的缺口要求核不掉', CE,
         "                elif present[0].startswith(WARN) and not all(w in v for w in GAP_WORDS):",
         '                elif False:', 'E2 ⚠️ 缺关闭判据未判红'),
        ('E2 ❌ 的改法要求核不掉', CE,
         "                elif present[0].startswith(FAIL) and not any(w in v for w in FIX_WORDS):",
         '                elif False:', ('E2 ❌ 缺改法未判红', 'E2 ⚠️ 缺关闭判据未判红')),
        ('E3 疑似实测值不判红', CE,
         '                if (UNIT_NUM.search(cell) or VERB_NUM.search(cell))'
         ' and not PENDING.search(cell):',
         '                if False:', '编造的实测值未被 E3 抓到'),
        ('E3 恒判红（把合规的待实测行也咬了）', CE,
         '                if (UNIT_NUM.search(cell) or VERB_NUM.search(cell))'
         ' and not PENDING.search(cell):',
         '                if UNIT_NUM.search(cell) or VERB_NUM.search(cell):',
         '合规 EVT 报告被 E1–E4 误判'),
        ('量值定义放宽回"任意数字"（标准号与条款号全成假阳性）', CE,
         '                if (UNIT_NUM.search(cell) or VERB_NUM.search(cell))'
         ' and not PENDING.search(cell):',
         "                if re.search(NUM, cell) and not PENDING.search(cell):",
         '标准号/IPC 号被当成实测值'),
        ('E4 阈值被放到 90%', CE, '        if dev > 0.10 and not DEV_ANNO.search(raw):',
         '        if dev > 0.9 and not DEV_ANNO.search(raw):', '偏差 25% 未标注未被 E4 抓到'),
        ('E4 恒判红（标了原因也咬）', CE, '        if dev > 0.10 and not DEV_ANNO.search(raw):',
         '        if True:', '已标注偏差原因仍被 E4 判红'),
        ('E4 把"缺一侧"的未判注记改成违规（三态失效）', CE,
         '            if md or mr:\n                notes.append(',
         '            if md or mr:\n                bad.append(',
         ('缺复算值被折成 E4 违规（应走未判）', '已标注偏差原因仍被 E4 判红')),
        ('交付物缺判定表被白白放行（散文 EVT 报告）', CE,
         '        if by_path:', '        if False:', '交付物缺判定表却未判红'),
        ('规则文档缺表被误判红（该走未判）', CE,
         '        if by_path:', '        if True:',
         '规则类文档缺表被误判红'),
        ('域外文书被当成已判合规（三态失效）', CE, '    if not (by_path or by_text):',
         '    if False:', ('域外文书未走三态', '域外文书未走三态或未说明成因')),
        ('域内文书为零时不再 rc=2', CE, '    if judged == 0:', '    if False:',
         ('域内文书为零时被当成"已通过"',
          '删掉 EVT 底稿后未走"未判定"三态')),
        ('输入不存在被当成零违规放行', CE,
         "            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')\n            sys.exit(2)",
         '            continue', '路径不存在未按要求说清成因'),
    ],
    # G 组：法规/裁决门禁。每条判据至少配一支"关掉它"和一支"让它恒红"的变异，
    # 外加三态（残行/空表/域外/rc=2）与共用读取器 mdtable 各自的反向对照。
    'reg': [
        ('G1 未落三态不判红（含糊措辞当已判）', CR, '    if not hits:', '    if False:',
         'G1 未恰好开火一条'),
        ('G1 恒判红（合规的"适用"也咬）', CR, '    if not hits:', '    if True:',
         '合规法规文书被判红'),
        ('G1 两态并存不再判红', CR, '    elif len(hits) > 1:', '    elif False:',
         'G1 未恰好开火一条'),
        ('状态词放宽回子串（"基本适用""符合性"当成已判）', CR,
         "        if (not prev or prev in BEFORE) and (not nxt or nxt in AFTER or nxt in '（('):",
         '        if True:',
         ('合规法规文书被判红', 'G1 未恰好开火一条', '合法结论被判红（子串边界失效）')),
        ('G1 有判定无依据不核', CR,
         "                if J['basis'] is not None and not cell(cells, J['basis']).strip():",
         '                if False:', 'G1 未恰好开火一条'),
        ('G1 缺「依据」列整表不报（读者以为已判）', CR,
         "        if 'G1' in tags and J['basis'] is None:", '        if False:',
         ('缺列被放大成逐条或没报', '法规底稿表头少一列却未判红')),
        ('G2 逐条映射结论不核三态', CR, "        if 'G2' in tags:", "        if False and tags:",
         ('G2 两条未各自开火，或被 G1 抢判', '五条判据未全部真判')),
        ('G3 缺口的关闭路径不核', CR,
         "                if not cell(cells, J['fix']).strip() and not cell(cells, J['test']).strip():",
         '                if False:', 'G3 未开火或放大'),
        ('G3 恒判红（给了修订建议也咬）', CR,
         "                if not cell(cells, J['fix']).strip() and not cell(cells, J['test']).strip():",
         '                if True:', ('合规法规文书被判红', '只给修订建议的缺口被判红')),
        ('G3 缺列抑制失效（整表一条被逐行放大）', CR,
         "        if 'G3' in tags and J['fix'] is None and J['test'] is None:", '        if False:',
         '缺口清单缺列被放大成逐条或没报'),
        ('G4 四要素减成两要素', CR,
         "                                ('约束', J['constraint']), ('生效范围', J['scope'])):",
         "                                ('约束', J['constraint'])):",
         'G4 两半未各自开火'),
        ('G4 裁决依据不要求 EVT 证据', CR,
         '                if basis.strip() and not (EVT_EVIDENCE.search(basis) or DEFER.search(basis)):',
         '                if False:', 'G4 两半未各自开火'),
        ('G4 证据集合把"会议纪要"也算证据', CR,
         "EVT_EVIDENCE = re.compile(r'复算|仿真|FMEA|公差分析|实测|EVT')",
         "EVT_EVIDENCE = re.compile(r'复算|仿真|FMEA|公差分析|实测|EVT|会议')",
         'G4 两半未各自开火'),
        ('G4 缺列抑制失效', CR, '        if g4_missing:', '        if False:',
         ('裁决缺列被放大成逐条或没报', 'G4 两半未各自开火')),
        ('G5 费用数字不带口径也放行', CR,
         '                    if NUM.search(v) and not ESTIMATE.search(v):',
         '                    if False:', 'G5 未把费用/周期两列都核到'),
        ('G5 恒判红（没给数字也咬）', CR,
         '                    if NUM.search(v) and not ESTIMATE.search(v):',
         '                    if True:', ('合规法规文书被判红', '没给数字的行被 G5 误伤')),
        ('G5 只核第一根费用列（周期整列放过）', CR,
         "        'cost': _t.cols(header, *COST_COLS),",
         "        'cost': _t.cols(header, *COST_COLS)[:1],",
         'G5 未把费用/周期两列都核到'),
        ('残行仍按位取列（静默读错列）', CR,
         '            (good if len(cells) == len(header) else ragged).append(k + 1)',
         '            (good if True else ragged).append(k + 1)',
         ('残行仍被按位取列判红', '合规法规文书被判红')),
        ('空表不报成因（未判被折成"看起来判过了"）', CR, '            if tags:',
         '            if False and tags:', ('空表被折成合规或判红', '骨架上的法规底稿未通过 G1–G5')),
        ('05 目录零表格的散文裁决书不再判红', CR,
         '    if not tables and REG_DIR.search(path):', '    if False and tables:',
         '05 目录内零表格的散文裁决书未判红'),
        ('适用域只看路径不看正文（散文躲过判据）', CR,
         '    return bool(REG_DIR.search(path) or REG_SCOPE.search(text))',
         '    return bool(REG_DIR.search(path))', '正文按表名认域未生效'),
        ('域外文书被当成已判合规（三态失效）', CR, '    if not in_scope(path, text):',
         '    if False:', '域外文书未走三态'),
        ('域内文书为零时不再 rc=2', CR, '    if judged == 0:', '    if False:',
         ('域内文书为零时被当成"已通过"', '删掉法规底稿后未走"未判定"三态')),
        ('输入不存在被当成零违规放行', CR,
         "            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')\n            sys.exit(2)",
         '            continue', '路径不存在未说清成因并 fail-closed'),
        ('共用读取器把分隔行当数据行（三处判据一起漂）', MT,
         "    return bool(cells) and set(''.join(cells)) <= set('-: ')",
         '    return False',
         ('合规法规文书被判红', '合规包未 rc=0', '骨架底稿未通过 V1–V6',
          '骨架上的法规底稿未通过 G1–G5')),
        ('共用读取器的列名匹配收窄成精确相等', MT,
         '        if any(k in h for k in keys):', '        if h in keys:',
         ('五条判据未全部真判', '同义列名未认，G1 空转', '编造的实测值未被 E3 抓到',
          '法规底稿表头少一列却未判红')),
    ],
    # dc 档：设计补全门禁。四类表的分类器、逐格必填与"必须"列集合、触发式的 K5、
    # 三条适用域轴、以及"底稿表头由判据生成"这条同源关系各配反向对照。
    'dc': [
        ('K1 未落两类不判红（半截裁定当已判）', CD, '                if not hit:',
         '                if False:', 'K1 未恰好开火一条'),
        ('K1 恒判红（合规的"设计补全"也咬）', CD, '                if not hit:',
         '                if True:', '合规设计补全文书被判红'),
        ('K1 两类并列不再判红', CD, '                elif len(hit) > 1:',
         '                elif False:', 'K1 未恰好开火一条'),
        ('K1 整类被跳过（登记表不参与判定）', CD, '        if tag is None:',
         "        if tag == 'K1':", ('K1 未恰好开火一条', '五条判据未全部真判')),
        ('逐格必填判据关闭（空格也放行）', CD,
         '                if not cell(cs, cols[name]).strip():', '                if False:',
         ('状态空着未报 K1', '决策卡约束条件空着未报', '冲突记录无建议处置未报 K3',
          '接口极限值空着未报 K4')),
        ("必填集合从 must 扩到整表列（把合法空格判红）", CD,
         "            for name in SPECS[tag]['must']:", "            for name in SPECS[tag]['cols']:",
         '合规设计补全文书被判红'),
        ('K2 候选数不核（单候选也能过）', CD,
         '                if len(CAND_SEP.findall(v)) + 1 < 2:', '                if False:',
         '单候选选型未被 K2 抓到'),
        ('K2 候选恒判红（多候选也咬）', CD,
         '                if len(CAND_SEP.findall(v)) + 1 < 2:', '                if True:',
         '合规设计补全文书被判红'),
        ('候选分隔符只认斜杠（顿号不算）', CD,
         "CAND_SEP = re.compile(r'[、;；/|｜]|<br')",
         "CAND_SEP = re.compile(r'/')", '合规设计补全文书被判红'),
        ('表类识别放宽成任一命中（只有一根识别列也算这张表）', CD,
         "        if all(_t.col(header, key) is not None for key in spec['by']):",
         "        if any(_t.col(header, key) is not None for key in spec['by']):",
         ('合规设计补全文书被判红', '只凭一根识别列就被当成登记表')),
        ('表类识别整体失效', CD,
         "    for tag, spec in SPECS.items():", "    for tag, spec in []:",
         ('五条判据未全部真判', '骨架上的设计补全底稿未通过 K1–K5')),
        ('缺列不报（结构错了也没人喊）', CD, '        if missing:', '        if False:',
         ('K1 缺列被放大成逐行或没报', '底稿表头被改坏后 K2 未判红')),
        ('缺列判定排在空表之后（骨架掉列永远不出声）', CD, '        if missing:',
         '        if missing and rows:',
         ('底稿表头被改坏后 K2 未判红', 'K1 缺列被放大成逐行或没报')),
        ('空表分支吞掉整张表（连行列一起不看）', CD, '        if not rows:', '        if True:',
         '五条判据未全部真判'),
        ('K5 不核守护记录（代理指标裸奔）', CD, '            if not GUARD.search(body):',
         '            if False:', '代理指标无守护记录未被 K5 抓到'),
        ('K5 恒判红（有守护记录也咬）', CD, '            if not GUARD.search(body):',
         '            if True:', '合规设计补全文书被判红'),
        ('K5 触发不记账（实判读数虚低）', CD, "            seen.add('K5')", '            pass',
         '五条判据未全部真判'),
        ('适用域第三条轴失效（写了表没提名字就躲过）', CD,
         '    return any(table_kind(h) for h, _ in _t.table_blocks(text))', '    return False',
         '按表类认域这条轴没生效'),
        ('适用域第二条轴漏掉「接口定义」（只认其余表名）', CD,
         "DC_SCOPE = re.compile(r'决策卡|补全登记表|缺失机构补全|冲突记录|接口定义')",
         "DC_SCOPE = re.compile(r'决策卡|补全登记表|缺失机构补全|冲突记录')",
         '正文出现节名却没被认成域内文书'),
        ('域内文书为零时不再 rc=2', CD, '    if judged == 0:', '    if False:',
         '域内文书为零时被当成"已通过"'),
        ('目录里一份 .md 都没有却被当成已判空', CD, '    if not paths:', '    if False:',
         '目录里没有 .md 时未说清"一份都没扫到"这条成因'),
        ('输入不存在被当成零违规放行', CD,
         "            print(f'输入不可用，未做任何判定: {p}（既不是文件也不是目录）')\n            sys.exit(2)",
         '            continue', '路径不存在未说清成因并 fail-closed'),
        ('骨架不再生成设计补全底稿（K 门禁没有载体）', NP,
         "    with open(os.path.join(dc_dir, f'补全_{name}.md'), 'w', encoding='utf8') as f:\n"
         '        f.write(design_doc(name))', '    pass', '缺设计补全底稿'),
        ('底稿表头改成手抄一份（脱离判据 SPECS）', NP,
         r"        parts.append(f'## {title}\n{_dc.header_row(tag)}\n{_dc.separator_row(tag)}\n')",
         r"        parts.append(f'## {title}\n| 决策项 | 可选方案 | 选定方案 | 依据 | 风险与回退 |"
         r"\n|---|---|---|---|---|\n')",
         ('底稿表头与判据 SPECS 不同源', '骨架上的设计补全底稿未通过 K1–K5')),
        # 共用件与 G 档反向对照
        # mdtable.sections 是共享件：切节失效会连带把「按节取表」的消费者一起打倒——
        # P8／P9 那条"清单没列专利"的断言就是其中之一（它靠 sections 找到「专利清单」节）。
        # 允许清单按先例写成元组（chan 档一支臂点两名同理）：列进来的是"这次变异真的会把哪条打断"，
        # 不是把任何红都算过。
        ('切节失效：K5 的粒度从"节"退成"整篇"（跨节遮挡）', MT,
         '        if heading_line(ln):', '        if False:',
         ('K5 被另一节的守护记录遮挡', '清单没列专利时被折成合规或误判红')),
        ('G 缺「依据」列的判定挪到空表之后（骨架掉列静默）', CR,
         "        if 'G1' in tags and J['basis'] is None:",
         "        if J['basis'] is None and rows:",
         ('法规底稿表头少一列却未判红', '缺列被放大成逐条或没报')),
    ],
    # docx 通道从本轮起有两把门禁共用（N 与 Q 都读同一份抽取），
    # 抽取坏掉时先红的是套件里排在前面的那支断言——下面四支 expect 因此各带两个消费者。
    # cen＝"清单现算"这一类：判据核的是"文档抄的那份名单 == 树里现算的那份"。
    # 两支脚本侧臂各钉一头（现算侧认拼写、对账侧认差集），第三支钉电池自己的 arm 清单，
    # 第四支是语料侧（README）臂——它同时证明"变异目标不必是 .py"这条放开是真的。
    'cen': [
        ('消费者换了拼写，现算就不认了（清单对账于是恒真）', CE,
         "_t = _load('mdtable')", '_t = _load("mdtable")',
         'mdtable 共用清单不对账'),
        ('现算把量具自己也算成消费者', 'tests/test_scripts.py',
         "        return {n for n, s in srcs.items() if n != 'mdtable.py'",
         "        return {n for n, s in srcs.items() if True",
         '消费者现算漏了某种拼写或把量具自己算了进去'),
        ('电池自己的 arm 清单漏抄一支（那支等于不存在）', TB,
         '只跑一支（' + 'cen|chan|claims|', '只跑一支（' + 'chan|claims|',
         '电池 docstring 的 arm 清单与 MUTS 键不对齐'),
        ('README 少列一个消费者（文档侧差集必须咬得动）', 'README.md',
         '`check_figure_labels.py`、`check_figure_text.py`', '`check_figure_labels.py`',
         'mdtable 共用清单不对账'),
    ],
    'chan': [
        ('docx 表格还原分支整支关掉（表散成裸行→N 误判"有节无表"）', IRON,
         "        if p.tag.endswith('}tbl'):", '        if False:',
         ('Word-only 权要未被 Q 真判', '合规 docx 未被 N 真判（表格没还原成可按下标取列的行）')),
        ('段落分支不跳过表格内部段落（单元格既进管道行又散成裸行）', IRON,
         '        if id(p) in inside:', '        if False:',
         # expect 是**消费者集合**：这支臂动的是 `docx_text` 的表格/段落互斥，两处读数都会翻——
         # 专属原告是 `test_docx_table_channel` 那句，但套件里排在它**前面**的
         # `test_check_claims`（Word-only 权要的覆盖账 12 条那一档）先红，
         # 遇红即停的套件永远读不到第二个。r67（10d5426）与 r70（a48ddf4）两次 HEAD 全量复算
         # 同一读数 ⇒ 同组兄弟臂（上面那支的 expect 早就是元组）第 22 轮那批"扩成消费者集合"的
         # 修复漏了这一支，不是新出现的前移。不调测试顺序来保读数。
         ('表格单元格被重复吐成裸行（表格分支与段落分支没互斥）',
          'Word-only 权要未被 Q 真判（只认 md 的话这里假绿或成串假红）')),
        ('单行表不补 |---|（mdtable 要求两行才算一张表→表隐身）', IRON,
         '                if len(rows) == 1:', '                if False:',
         '单行 docx 表隐身成"无表"（分隔符没补上）'),
        ('表格行忘了换行（整张表连成一行）', IRON,
         r"                out.append('\n'.join(rows) + '\n')", '                out.extend(rows)',
         ('Word-only 权要未被 Q 真判', '合规 docx 未被 N 真判（表格没还原成可按下标取列的行）')),
        ('DTD/ENTITY 前置拒绝形同虚设', IRON,
         "    for marker in (b'<!DOCTYPE', b'<!ENTITY'):", '    for marker in ():',
         ('含 DOCTYPE/ENTITY 声明的 document.xml 未被拒绝',
          '含 DTD 声明的 docx 未按要求拒绝并说成因')),
        ('N 的 docx 读取退回按 md 直读（zip 字节 → 退码 1 冒充"发现违规"）', CN,
         '        return _cir.read_text(path)',
         '        return open(path, encoding="utf8").read()',
         '合规 docx 未被 N 真判（表格没还原成可按下标取列的行）'),
        ('N 的 --all 退回只收 md', CN,
         "f.lower().endswith(('.md', '.docx'))", "f.lower().endswith('.md')",
         '--all 未把 .docx 收进待检清单'),
        ('G 的 --all 退回只收 md', CR,
         "f.lower().endswith(('.md', '.docx'))", "f.lower().endswith('.md')",
         'G 门禁未能在 docx 裁决书上真判'),
        ('E 的 --all 退回只收 md', CE,
         "f.lower().endswith(('.md', '.docx'))", "f.lower().endswith('.md')",
         'EVT 门禁未能在 docx 上真判（表格没吃到或 --all 收集漏了 .docx）'),
        ('K 的 --all 退回只收 md', CD,
         "f.lower().endswith(('.md', '.docx'))", "f.lower().endswith('.md')",
         '补全门禁未能在 docx 上真判（表格没吃到或 --all 收集漏了 .docx）'),
    ],
    'text': [
        ('T1 部件名核对关掉（图上有文书没有的部件看不见）', CT,
         '            if norm(part) not in pool:', '            if False:',
         '图上标号与对照表名称不一致未按预期开火'),
        ('T1 框内文字核对关掉', CT, '                if t not in pool:', '                if False:',
         '图上有文书没有的部件未按预期开火'),
        ('T2 量值核对关掉（图中数值与文书不一致看不见）', CT,
         '                if tok not in pool:', '                if False:',
         '图中数值差一个数字未按预期开火'),
        ('归一化放宽成"去掉所有空白"（部件名塞空格就蒙混）', CT,
         "    return SPACE_AROUND_SIGN.sub(r'\\1', txt)", "    return re.sub(r'\\s+', '', txt)",
         '部件名中间塞空格就蒙混过关（归一过头）'),
        ('归一化彻底不做（符号后一个空格就判红）', CT,
         "    return SPACE_AROUND_SIGN.sub(r'\\1', txt)", '    return txt',
         '符号后空白被当成不一致（该归一的不归一）'),
        ('有 PNG 无清单不再 fail-closed（把「看不见」折成「核过了」）', CT,
         '        if orphan:', '        if False:',
         ('有 PNG 无 manifest 被当成"核过了"或"发现违规"', '部分图没有清单被当成核过了')),
        # 上面那支 `if False` 先把"全孤儿"那档打红；"混合档"要靠下面这条只关掉
        # 混合路径的注入才量得到（第 20 轮端到端实测：旧写法把看孤儿关在 `if not mans`
        # 里，12 张图混 1 张手画 PNG 读成"实判 3 条/违规 0"）。一档一处第一红。
        ('看孤儿只在一张清单都没有时才判（混合档漏掉）', CT,
         '    fatal = None\n    if orphan:', '    fatal = None\n    if orphan and not mans:',
         '部分图没有清单被当成核过了'),
        ('清单配对改回 splitext（双后缀切错，合规包被读成缺清单）', CT,
         '        have = {f[:-len(suffix)] for f in fs if f.endswith(suffix)}',
         '        have = {os.path.splitext(f)[0] for f in fs if f.endswith(suffix)}',
         ('双后缀被 splitext 切错', '图与文书逐字一致却被判红')),
        ('T 档读不动的 docx 不再兜异常（崩一次就是一张假违规单）', CT,
         "    except Exception as e:\n        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')",
         "    except ImportError as e:\n        print(f'输入不可用，未做任何判定: {path}（{type(e).__name__}: {e}）')",
         '读不动的 docx 未走 rc=2'),
        ('对账不完整时把真判出的违规降级成环境档', CT,
         '    if total:', '    if total and not fatal_all:',
         ('部分图没有清单被当成核过了', '判出的违规被')),
        # T4–T6（第 21 轮从实施细则第四十六/二十一条捡回来的图号对账）各自一条注入
        ('T4 缺图判据关掉（声明了图2而包里没有也不报）', CT,
         '    for n in sorted(declared - set(present), key=int):',
         '    for n in sorted([]):', '声明了 图2'),
        ('T5 没人引用的图不报', CT,
         '    for n in sorted(set(present) - declared, key=int):',
         '    for n in sorted([]):',
         # 先红的是 mixed 那档（它同时断 '→ T5'），d5 专用的那条在它后面——两支都是 T5 的消费者，
         # 读数只报第一支会误判成"红因不对"，所以两支都认。
         ('部分图没有清单被当成核过了', '多一张没人引用的图未被 T5 抓到')),
        ('T6 跳号判据关掉', CT,
         '        if nums != list(range(1, len(nums) + 1)):', '        if False:',
         '图号跳号未被 T6 抓到'),
        ('T7 表有图无的号不报（说明书提了图上没有的标记）', CT,
         '            for num in sorted(table, key=int):', '            for num in sorted([]):',
         '未被 T7 抓到'),
        ('T7 在有手画图时也硬判（把看不见折成违规）', CT,
         '        if not orphan:', '        if True:',
         # 先红的是 mixed 那档（它断 'T7 未判'，位置在 t7_orphan 之前），t7_orphan 是第二支消费者。
         ('部分图没有清单被当成核过了', '看不见≠违规')),
        ('T6 把正文声明并进分母（缺图反过来把跳号补圆）', CT,
         '    nums = sorted({int(k) for k in present})',
         '    nums = sorted({int(k) for k in present} | {int(k) for k in declared})',
         '图号跳号未被 T6 抓到'),
        ('认不出图号时硬塞一个号（把未判折成违规）', CT,
         '                unnamed.append(os.path.join(dp, f))',
         "                have.setdefault('9', os.path.join(dp, f))",
         '文件名认不出图号时被折成合规或违规'),
        ('没有图的包被硬判', CT,
         "        notes.append(f'{root}: 没有 figures 目录，也没有任何图 ↔ 文书的对账对象 → T1–T3 未判')",
         "        bad.append(f'{root}: 没有图 → T1 违规')",
         ('没有图的包被硬判', '新生成的包在图↔文书对账上未走')),
        ('T3 判到却不记（七条判据少一条也报全判到）', CT,
         "        seen.add('T3')", '        pass', '合规案没把七条判据都判到'),
        ('清单不再去重（同一句话留两份底）', PF,
         "                'texts': list(dict.fromkeys(texts))}",
         "                'texts': list(texts)}",
         '框内文字要按绘制顺序去重留出底'),
    ],

    'lab': [
        ('N1 有附图说明节却无表这条判红整个关掉', CN,
         "        if has_fig_section and (FIG_DIR.search(path) or FIG_WORD.search(text)):",
         "        if False:", ('02 目录下无对照表的说明书未判红', '有附图说明节却无对照表未判红')),
        ('N1 判红扩到交底书（该当未判的一侧被误伤）', CN,
         "        if has_fig_section and (FIG_DIR.search(path) or FIG_WORD.search(text)):",
         "        if has_fig_section:", '交底书被硬判红，或未如实说未判'),
        ('识别列改成三列全中（掉列的表就认不出了）', CN,
         "    return (_t.col(header, '名称') is not None or _t.col(header, '所在图号') is not None)",
         "    return _t.col(header, '名称') is not None and _t.col(header, '所在图号') is not None",
         ('掉识别列时成因说错（应报缺名称列，而不是无表）',
          '底稿表头被改坏后 N1 未判红')),
        ('识别列不看「标记」列（任何带名称的表都被当对照表）', CN,
         "    if _t.col(header, '标记') is None:", '    if False:',
         ('整包 --all 未把 02 目录内文书计入实核数',
          '骨架上的说明书底稿未通过 N1–N4，或空表没走未判三态')),
        ('适用域第三条轴关掉（写了表却没提名字的文书读成域外）', CN,
         "    return any(is_label_table(h) for h, _ in _t.table_blocks(text))",
         "    return False", '第三条适用域轴（表被认出即域内）未生效'),
        ('prose_only 不遮表格行（N4 用表自证图号）', CN,
         r"    return '\n'.join(ln for ln in text.splitlines() if not ln.strip().startswith('|'))",
         "    return text", '表内自写图号被当成已声明（N4 成了自证）'),
        ('N2 阿拉伯数字校验关闭', CN,
         r"            if m and not re.fullmatch(r'\d+', m):", '            if False:',
         '汉字标记未判红'),
        ('N2 阿拉伯数字校验反向（恒判红）', CN,
         r"            if m and not re.fullmatch(r'\d+', m):", '            if True:',
         ('合规说明书底稿被误判红', '合规 docx 未被 N 真判（表格没还原成可按下标取列的行）')),
        ('N2 逐格必填关闭', CN, '                if not cell(cs, J[name]).strip():',
         '                if False:', '空格子未判红'),
        ('N2 同号两名关闭', CN, '                if m in num2name and num2name[m] != nm:',
         '                if False:', '同一标记挂两个名称未判红'),
        ('N2 同名两号关闭', CN, '                if nm in name2num and name2num[nm] != m:',
         '                if False:', '同一名称挂两个标记未判红'),
        ('N3 正文↔表对账关闭', CN, '            if num != name2num[nm]:', '            if False:',
         ('正文标记与表错配未判红', 'docx 里的标号错配未判红')),
        ('N3 未登记前缀不再豁免（误伤"合金支架"）', CN,
         '            if before and before[-1] not in BOUND_BEFORE:', '            if False:',
         '更长前缀被折成违规或缺少未核说明'),
        ('N3 边界字表形同虚设（合规正文也记成未核）', CN,
         '            if before and before[-1] not in BOUND_BEFORE:', '            if True:',
         ('正文标记与表错配未判红', '一致正文被记成未核', 'docx 里的标号错配未判红')),
        ('N3 单位豁免关闭（"底座厚度 12mm"被当标记错配）', CN,
         '            if UNIT_TAIL.match(prose[m.end():m.end() + 6]):', '            if False:',
         '带单位的量值被当成正文标记错配'),
        ('N4 所在图号核验关闭', CN, '                    if fno not in idx:',
         '                    if False:', '未声明图号未判红'),
        ('N4 正文无图号时的未判注记丢掉', CN,
         "        notes.append(f'{path}: 正文没有「图N」式图号声明 → N4 未判（表里的所在图号无从比对）')",
         '        pass', '正文无图号声明时未走未判'),
        ('空表折成判红（骨架期底稿过不了自己的闸）', CN,
         "            notes.append(f'{where_t} 只有表头没有数据行 → 本表 N2 未判')",
         "            bad.append(f'{where_t} 空表 → N2')",
         ('空表骨架读数不对', '骨架上的说明书底稿未通过 N1–N4，或空表没走未判三态')),
        ('seen 不记 N3（合规案空转，四判据少一条也报全判到）', CN,
         "        seen.add('N3')", '        pass', ('合规案未把四条判据都判到', '合规 docx 未被 N 真判（表格没还原成可按下标取列的行）')),
        ('域内文书为零不再 rc=2', CN, '    if judged == 0:', '    if False:',
         ('域内文书为零时被当成"已通过"', '删掉说明书底稿后未走"未判定"三态')),
        ('底稿对照表头改成手抄（列名与判据漂移）', NP,
         r"        body = hint if hint else f'{_nl.header_row()}\n{_nl.separator_row()}'",
         r"        body = hint if hint else '| 标记 | 名称 | 图号 |' + chr(10) + '|---|---|---|'",
         ('说明书底稿表头与判据 COLS 不同源',
          '骨架上的说明书底稿未通过 N1–N4，或空表没走未判三态')),
        ('说明书底稿不再生成（N 门禁在骨架期没有载体）', NP,
         "    with open(os.path.join(fd_dir, f'说明书_{name}.md'), 'w', encoding='utf8') as f:",
         '    if False:',
         # 第 41 轮（r70/a48ddf4 全量复算）扩成消费者集合：骨架不再落说明书底稿时先红的是
         # 第 39 轮新加的"骨架包上 R12/R13 走未判三态"那一档（它排在 N 门禁的档之前）。
         # r67（10d5426）时 lab 组 22/22 全清、r70 变 21/22 ⇒ 这条错置是**第 39 轮造出来的**，
         # 与上面 `chan` 那支的第 22 轮旧账不同源；两处的修法同一条：expect 记全消费者，
         # 不去调测试顺序保读数。
         ('缺说明书底稿（N1–N4 没有载体）',
          '骨架包上 R12/R13 没走"未判"三态（空表被折成合规，或被折成违规）')),
    ],}

def make_work():
    work = tempfile.mkdtemp(prefix='mutbat_')
    for sub in ('scripts', 'tests', 'references'):
        shutil.copytree(os.path.join(ROOT, sub), os.path.join(work, sub))
    for f in ('README.md', 'SKILL.md'):
        src = os.path.join(ROOT, f)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(work, f))
    return work


def suite(work, mutating=None):
    """跑常驻套件。默认把网络放进死代理：V 的 live 档自己 SKIP，其余各档不依赖网络。

    mutating 传「组/标签」：套件里有一档专管电池锚点体检（每条 needle 须恰好命中一次），
    而变异本身就是把那条 needle 从文件里换掉——不告诉它"现在动的是谁"，
    体检就会把当前变异报成失配，把 13 条 fig 变异读成 MISRED（第 16 轮实测）。
    baseline 那趟不传 ⇒ 体检全量跑，陈旧锚点仍然在落锤前就被拦住。"""
    env = dict(os.environ, https_proxy='http://127.0.0.1:9/', http_proxy='http://127.0.0.1:9/',
               HTTPS_PROXY='http://127.0.0.1:9/', HTTP_PROXY='http://127.0.0.1:9/',
               PYTHONDONTWRITEBYTECODE='1',
               PP_MUTATING=mutating or '')
    r = subprocess.run([PY, 'tests/test_scripts.py'], cwd=work, capture_output=True,
                       text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def fatal_exception(out):
    """返回"让套件退出的那一次异常"的类型名；输出里没有属于套件的 Traceback 则返回 None。

    两个方向都实测踩过（第 20 轮，2026-09-26）：
      · 旧判法 `'Traceback' in out and 'AssertionError' not in out` 只会说"崩了"，
        说不出崩在哪个测试，一次只在跑批里出现的读数既不能复算也不能归因；
        而崩溃消息里只要抄进一段带 AssertionError 字样的子进程输出，它就把崩溃读成抓红。
      · 改成"取最后一段 Traceback"又反向错一次：assert_ 会把子进程输出整段拼进断言消息，
        门禁一崩，输出末尾是**子进程**的 Traceback ⇒ doc/vsr 两条正常抓红被读成 CRASH-KILL。
    现在的判据是"帧里出现套件文件名的那一段"（见 suite_tb），两种误读各留一条常驻控制。
    """
    head, _ = suite_tb(out)
    if not head:
        return None
    m = re.match(r'([A-Za-z_][\w.]*\.)?([A-Za-z_][\w]*(?:Error|Exception|Exit|Interrupt))\b', head)
    return m.group(2) if m else (head.split(':')[0][:40] or 'Traceback')


def suite_tb(out, runner='test_scripts.py'):
    """取"套件自己死掉的那一段 Traceback"（异常行 + 帧）；找不到返回 (None, None)。

    判据是"帧里出现 runner 文件名"，不是"取最后一段"。本仓的 assert_ 会把子进程输出整段
    拼进断言消息，被测门禁一崩，输出的**末尾**就是那份子进程 Traceback（帧全在 scripts/ 下），
    取最后一段会把一次正常抓红读成崩溃——第 20 轮 doc 与 vsr 两条变异就是这么被误判的，
    而同一对变异在旧"全文搜词"判法下读的是抓红：两趟读数互相矛盾，才把这把新尺子的缺陷暴露出来。
    """
    for blk in reversed(out.split('Traceback (most recent call last):')[1:]):
        lines, frames, i = blk.splitlines(), [], 0
        while i < len(lines):
            ln = lines[i]
            if not ln.strip() or ln[:1] in (' ', chr(9)):
                frames.append(ln.strip())
                i += 1
                continue
            break
        head = lines[i].strip() if i < len(lines) else ''
        if any(runner in f for f in frames):
            return head, frames
    return None, None


def crash_notes(out, n=6):
    """崩溃那一段的帧与异常行——没有它，CRASH-KILL 只是一句"不算覆盖"。"""
    head, frames = suite_tb(out)
    if not head:
        return []
    return [f.strip() for f in frames if f.strip()][-n:] + [head]

def run_arm(name, work, verbose=False):
    killed = misred = surv = broken = crash = 0
    for label, rel, old, new, expect in MUTS[name]:
        path = os.path.join(work, rel)
        if not os.path.isfile(path):
            print(f'  [PROBE-FAIL] {label} —— 目标脚本不存在 {rel}')
            broken += 1
            continue
        orig = open(path, encoding='utf8').read()
        if old not in orig:
            print(f'  [PROBE-FAIL] {label} —— needle 未命中（脚本已改，请同步电池）')
            broken += 1
            continue
        open(path, 'w', encoding='utf8').write(orig.replace(old, new, 1))
        # 变异本身必须仍是"可运行的另一种实现"：改出语法错的文件不是覆盖证据，
        # 而是电池自己的缺陷（本轮就有一条 needle 只截到半截 f-string，留下孤立续行）
        # 只有 .py 目标能编译检查；语料侧（README 这类）改的是文字，编译无从谈起，
        # 但不让改就把「文档↔脚本」这类判据永远排除在电池之外——那是人为限制不是判据限制。
        chk = (subprocess.run([PY, '-m', 'py_compile', rel], cwd=work,
                               capture_output=True, text=True)
               if rel.endswith('.py')
               else subprocess.run([PY, '-c', 'pass'], capture_output=True, text=True))
        # py_compile 只管**语法**。本轮实测到一条变异把常量插成"引用同文件里更晚定义的常量"：
        # 语法合法、py_compile 全过，但导入即 NameError ⇒ 整套件第一档（真渲染图那档）先炸，
        # 读数被记成 "C1 彩色判据未触发" 的 MISRED。那不是"另一种实现"，是"这个模块不存在"，
        # 属于电池自己的缺陷，必须单列而不是当成覆盖或归因失败。
        # 只 exec scripts/：tests/test_scripts.py 一 exec 就是跑整套件（那是被测内容不是检查）。
        if chk.returncode == 0 and rel.startswith('scripts/'):
            chk = subprocess.run(
                [PY, '-c', 'import importlib.util as u, sys; '
                 's = u.spec_from_file_location("mb_probe", sys.argv[1]); '
                 'm = u.module_from_spec(s); s.loader.exec_module(m)', rel],
                cwd=work, capture_output=True, text=True)
            note = '导入'
        else:
            note = '编译'
        if chk.returncode != 0:
            print(f'  [BAD-MUTATION] {label} —— 变异后文件不能{note}：{chk.stderr.strip()[-90:]}')
            broken += 1
            open(path, 'w', encoding='utf8').write(orig)
            continue
        rc, out = suite(work, f'{name}/{label}')
        open(path, 'w', encoding='utf8').write(orig)
        wants = expect if isinstance(expect, tuple) else [expect]
        exc = fatal_exception(out)
        if rc == 0:
            print(f'  [SURVIVED ]  {label}')
            surv += 1
        elif exc not in (None, 'AssertionError'):
            print(f'  [CRASH-KILL] {label} —— 崩溃致红（{exc}），不算覆盖')
            for ln in crash_notes(out):
                print('      | ' + ln[:140])
            crash += 1
        elif any(w in out for w in wants):
            got = next(w for w in wants if w in out)
            print(f'  [KILLED ]    {label}  (点名断言 "{got}")')
            killed += 1
        else:
            first = [l.strip()[:78] for l in out.splitlines() if l.startswith('AssertionError')]
            print(f'  [MISRED ]    {label}  预期 {wants}，实际先红 {first}')
            misred += 1
    total = len(MUTS[name])
    bad = surv + misred + broken + crash
    print(f'汇总[{name}]: 共 {total} · 抓红 {killed} · 红因不对 {misred} · 未检出 {surv} · '
          f'探针失效/坏变异 {broken} · 崩溃致红 {crash}')
    return bad, total, killed


def main():
    ap = argparse.ArgumentParser(description='常驻变异电池：证明判据断言真的会咬人')
    ap.add_argument('--arm', default='all', choices=['all'] + sorted(MUTS))
    ap.add_argument('--keep-work', action='store_true', help='保留工作副本便于复查')
    args = ap.parse_args()

    try:
        import matplotlib    # noqa: F401
        have_mpl = True
    except ImportError:
        have_mpl = False

    arms = sorted(MUTS) if args.arm == 'all' else [args.arm]
    if not have_mpl and 'fig' in arms:
        print('fig 档需要 matplotlib（出图期 F1–F6 与真像素核对）→ 本次未判定，不是通过。'
              '装上后重跑，或 --arm iron/vsr 先跑其余两支。')
        arms = [a for a in arms if a != 'fig']
        if not arms:
            sys.exit(2)

    work = make_work()
    print(f'工作副本 {work}')
    rc0, out0 = suite(work)
    if rc0 != 0:
        print('baseline 未 GREEN，先修套件再谈变异覆盖：\n' + out0[-1200:])
        shutil.rmtree(work, ignore_errors=True)
        sys.exit(1)
    print('=== baseline === GREEN')

    bad_total = 0
    for name in arms:
        if not have_mpl and name == 'fig':
            continue
        b, n, k = run_arm(name, work)
        # 每档必须"要么全数要么报错"：killed+b+… 与总档数对不上即为本电池自身失效
        if k + b != n:
            print(f'汇总[{name}] 自相矛盾：抓红 {k} + 异常 {b} != 总 {n} —— 电池自身失效')
            b += 1
        bad_total += b
    rc_end, out_end = suite(work)
    print(f'还原后套件 {"GREEN" if rc_end == 0 else "RED!!（还原失败）"}')
    if not args.keep_work:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f'工作副本留在 {work}')
    sys.exit(1 if (bad_total or rc_end) else 0)


if __name__ == '__main__':
    main()
