#!/usr/bin/env python3
"""常驻变异电池：证明 tests/test_scripts.py 里那些判据断言真的会咬人。

为什么住在仓库里：判据门禁本身有常驻冒烟测试，但"这些测试有没有牙"这件事
此前只存在于 /tmp 的一次性脚本里，清一次 /tmp 就没了（实际发生过两次）。

用法:
    python3 tests/mutation_battery.py                 # 全部 arm 一跑（清单见 --arm choices）
    python3 tests/mutation_battery.py --arm lab        # 只跑一支（doc|dc|evt|fig|iron|lab|reg|vsr）
    python3 tests/mutation_battery.py --keep-work     # 保留工作副本便于手工复查

约定（与判据类脚本一致）:
    0 = 所有变异都被"点名该条款的断言"抓红，且还原后套件 GREEN
    1 = 有变异未被抓红（SURVIVED）、红因归错条款（MISRED）、探针失效（PROBE-FAIL）
        或崩溃致红（CRASH-KILL，崩溃不算覆盖）
    2 = 环境不可用（如缺 matplotlib 导致 fig 档无法判定），未做判定 ≠ 判定通过

自带的卫生规矩（都是踩过的坑）:
  · 变异必须写成 plausible 的错误实现。把判据改成让它抛异常，套件也会"红"，
    但那不是覆盖——所以分类器先认 CRASH-KILL。
  · 每支 arm 结束必须打一行「汇总」；缺行按 arm 崩溃处理（批跑时把日志 grep
    成只剩关键词，曾把一支电池 import 期的 SyntaxError 整个吞掉）。
  · fig 档需要 matplotlib；没有就如实 SKIP 并把退出码判 2，不折成"通过"。
  · 两条规则互相遮蔽时不许硬凑 arm：lab 档的 `nm = max(cands, key=len)` 与边界字表
    是同一条防误伤的两层，注入前者永远先被后者挡下（短名之前的那段字属于更长名称，
    一般不在边界字表里）⇒ 读成 SURVIVED 是量具真相，不是覆盖缺口：摘掉这支、
    用例留作回归护栏（改名或加同名词时它仍有意义）。
"""
import argparse
import os
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
MT = 'scripts/mdtable.py'
RG = 'scripts/regen_docx.py'

# (说明, 目标脚本, 原样 needle, plausible 错误实现, 允许点名抓红的断言消息[可写成元组])
MUTS = {
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
        ('R7 字数核不掉', IRON, '            if n > TITLE_MAX:', '            if False:',
         'R7 未拦超长发明名称'),
        ('R7 阈值过严误伤合规名称', IRON, '            if n > TITLE_MAX:', '            if n > 3:',
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
        ('脚本总结行谎称 R1–R5', IRON, '（规则 R1–R8，判据见脚本 docstring）',
         '（规则 R1–R5，判据见脚本 docstring）', '门禁自报规则区间与实际判据'),
        ('--all 只扫顶层（不递归）', IRON, '        for dp, _, fs in os.walk(root):',
         '        for dp, _, fs in [(root, [], [f for f in os.listdir(root)\n'
         '                              if os.path.isfile(os.path.join(root, f))])]:',
         ('--all 未递归到子目录里的两份文书', '--all 未抓到子目录内的违规',
          '新生成的包未通过铁律门禁')),
        ('docx 正文通道关掉（当成 utf-8 文本硬读）', IRON,
         "    if path.lower().endswith('.docx'):\n        return docx_text(path)",
         '    if False:\n        return docx_text(path)', '合规 docx 被铁律判红'),
        ('docx 节标题还原失效（R3/R4 找不到节）', IRON,
         "            out.append('#' * int(m.group(1)) + ' ')", "            out.append('')",
         'pStyle 还原没吃上力'),
        ('docx 无节标题时不报未判（拿零违规冒充核过）', IRON,
         "        if p.lower().endswith('.docx') and not re.search(r'^#{1,6}\\s', text, re.M):",
         '        if False:', '无节标题的 docx 未报三态'),
        ('DOCTYPE/ENTITY 拒绝闸关掉（实体展开风险）', IRON, '        if marker in head:',
         '        if False:', '声明的 document.xml 未被拒绝'),
        ('zip 炸弹尺寸闸关掉', IRON, '        if info.file_size > MAX_XML_BYTES:',
         '        if False:', '上限被越过却没有拒绝'),
        ('--all 指到文件时不说成因', IRON, "f'--all 需要目录，实得不是目录: ",
         "f'，实得不是目录: ", '--all 指向非目录时未说明原因'),
    ],
    'fig': [
        ('C1 彩色判据关闭', CF, '    if colored > 0:', '    if False:',
         'C1 彩色判据未触发或未标名'),
        ('C1 恒判红（误伤合规稀疏框图）', CF, '    if colored > 0:', '    if True:',
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
         '            total_bad += len(check_docx_embedded(d, tmp))',
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
    ],
    'vsr': [
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
        ('目录模式不再限定 *检索*.md', V,
         "                      if f.endswith('.md') and '检索' in f]",
         "                      if f.endswith('.md')]", '目录模式挑文件不对'),
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
    ],
    'doc': [
        ('陈旧判据彻底关闭（永不判陈旧）', RG,
         '            if os.path.getmtime(md) > os.path.getmtime(d) + 1]',
         '            if False]', 'md 比 docx 新却未判陈旧'),
        ('容差被放大到一年（正常流程里常年假绿）', RG,
         '            if os.path.getmtime(md) > os.path.getmtime(d) + 1]',
         '            if os.path.getmtime(md) > os.path.getmtime(d) + 31536000]',
         'md 比 docx 新却未判陈旧'),
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
         ('域内文书为零时被当成"已通过"', '骨架上的 E 门禁未走"未判定"三态',
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
         ('合规法规文书被判红', '合规包未 rc=0', '骨架底稿未通过 V1–V3',
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
        ('切节失效：K5 的粒度从"节"退成"整篇"（跨节遮挡）', MT,
         '        if heading_line(ln):', '        if False:',
         'K5 被另一节的守护记录遮挡'),
        ('G 缺「依据」列的判定挪到空表之后（骨架掉列静默）', CR,
         "        if 'G1' in tags and J['basis'] is None:",
         "        if J['basis'] is None and rows:",
         ('法规底稿表头少一列却未判红', '缺列被放大成逐条或没报')),
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
         '合规说明书底稿被误判红'),
        ('N2 逐格必填关闭', CN, '                if not cell(cs, J[name]).strip():',
         '                if False:', '空格子未判红'),
        ('N2 同号两名关闭', CN, '                if m in num2name and num2name[m] != nm:',
         '                if False:', '同一标记挂两个名称未判红'),
        ('N2 同名两号关闭', CN, '                if nm in name2num and name2num[nm] != m:',
         '                if False:', '同一名称挂两个标记未判红'),
        ('N3 正文↔表对账关闭', CN, '            if num != name2num[nm]:', '            if False:',
         '正文标记与表错配未判红'),
        ('N3 未登记前缀不再豁免（误伤"合金支架"）', CN,
         '            if before and before[-1] not in BOUND_BEFORE:', '            if False:',
         '更长前缀被折成违规或缺少未核说明'),
        ('N3 边界字表形同虚设（合规正文也记成未核）', CN,
         '            if before and before[-1] not in BOUND_BEFORE:', '            if True:',
         ('正文标记与表错配未判红', '一致正文被记成未核')),
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
         "        seen.add('N3')", '        pass', '合规案未把四条判据都判到'),
        ('域内文书为零不再 rc=2', CN, '    if judged == 0:', '    if False:',
         ('域内文书为零时被当成"已通过"', '删掉说明书底稿后未走"未判定"三态')),
        ('底稿对照表头改成手抄（列名与判据漂移）', NP,
         r"        body = hint if hint else f'{_nl.header_row()}\n{_nl.separator_row()}'",
         r"        body = hint if hint else '| 标记 | 名称 | 图号 |' + chr(10) + '|---|---|---|'",
         ('说明书底稿表头与判据 COLS 不同源',
          '骨架上的说明书底稿未通过 N1–N4，或空表没走未判三态')),
        ('说明书底稿不再生成（N 门禁在骨架期没有载体）', NP,
         "    with open(os.path.join(fd_dir, f'说明书_{name}.md'), 'w', encoding='utf8') as f:",
         '    if False:', '缺说明书底稿（N1–N4 没有载体）'),
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
               PP_MUTATING=mutating or '')
    r = subprocess.run([PY, 'tests/test_scripts.py'], cwd=work, capture_output=True,
                       text=True, env=env)
    return r.returncode, r.stdout + r.stderr


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
        chk = subprocess.run([PY, '-m', 'py_compile', rel], cwd=work,
                             capture_output=True, text=True)
        if chk.returncode != 0:
            print(f'  [BAD-MUTATION] {label} —— 变异后文件不能编译：{chk.stderr.strip()[-90:]}')
            broken += 1
            open(path, 'w', encoding='utf8').write(orig)
            continue
        rc, out = suite(work, f'{name}/{label}')
        open(path, 'w', encoding='utf8').write(orig)
        wants = expect if isinstance(expect, tuple) else [expect]
        if rc == 0:
            print(f'  [SURVIVED ]  {label}')
            surv += 1
        elif 'Traceback' in out and 'AssertionError' not in out:
            print(f'  [CRASH-KILL] {label} —— 崩溃致红，不算覆盖')
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
        print('fig 档需要 matplotlib（出图期 F1–F4 与真像素核对）→ 本次未判定，不是通过。'
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
