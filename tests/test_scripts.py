#!/usr/bin/env python3
"""patent-pack-pipeline 脚本冒烟测试（吸收 K-Dense CI 纪律：带 scripts/ 的技能必须带 tests/）。
运行: python3 tests/test_scripts.py（仓库根目录执行）
同时兼作环境自检：打印各依赖是否就绪、缺失影响哪个环节。
"""
import importlib.util
import os, re, shutil, sys, tempfile, time, subprocess, zipfile, stat
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
PY = sys.executable
SKIPPED = []   # 整档未跑的测试记这里，收尾行不得把它们算成 PASS
# 测试个数不手写：手写分母会漏掉新加的测试（新增一档忘了改数，收尾行就把 N+1 档报成 N 档）。
# 分母由下面 __main__ 里的 TESTS 清单现算，并核对清单与模块里定义的 test_* 函数一一对应。

# 直接复用被测脚本自己的判据，避免测试里手抄一份会漂移的判定
_spec = importlib.util.spec_from_file_location('regen_docx', os.path.join(S, 'regen_docx.py'))
_regen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_regen)


def run(cmd, cwd=None, env=None):
    e = {**os.environ, **env} if env else None
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, env=e)


def show(r):
    return f'rc={r.returncode}\n--stdout--\n{r.stdout}\n--stderr--\n{r.stderr}'


def assert_(cond, msg, r=None):
    if not cond:
        raise AssertionError(msg + ('\n' + show(r) if r is not None else ''))


# ---------- 环境自检 ----------

# (探测名, 导入名或 None, 缺失时受影响的环节)
DEPS = [
    ('pandoc', None, 'md→docx 转换 scripts/regen_docx.py（Word 交付物）'),
    ('numpy', 'numpy', '附图彩色像素扫描 scripts/check_figures.py'),
    ('Pillow', 'PIL', '附图读取 scripts/check_figures.py'),
    ('python-docx', 'docx', 'docx 转换后复核 scripts/regen_docx.py'),
    ('matplotlib', 'matplotlib', '专利附图出图 scripts/patent_figure.py（F1–F6 与出图自检，SKILL 纪律 2）'),
    ('pypandoc(可选)', 'pypandoc', 'pandoc 不在 PATH 时的兜底定位路径'),
]


def _cell(text, width):
    """定宽排版，兼容 CJK 双宽字符与超长路径（路径居中截断，保住右侧状态列）。"""
    text = str(text)

    def w(s):
        return sum(2 if ord(c) > 0x2E7F else 1 for c in s)

    if w(text) > width:
        keep = width - 3
        head = keep // 2
        tail = keep - head
        text = text[:head] + '…' + text[-tail:]
    return text + ' ' * max(0, width - w(text))


def probe_env():
    print('=== 环境自检 ===')
    print(f'  {_cell("python", 14)}{_cell(sys.version.split()[0], 40)}OK')
    missing = []
    for label, mod, impact in DEPS:
        if mod is None:
            path = _regen.resolve_pandoc()
            ok, detail = bool(path), path or ''
        else:
            try:
                m = importlib.util.find_spec(mod)
                ok = m is not None
                spec = importlib.import_module(mod) if ok else None
                detail = getattr(spec, '__version__', '') if spec else ''
            except Exception:
                ok, detail = False, ''
        print(f'  {_cell(label, 14)}{_cell(detail, 40)}' + ('OK' if ok else 'MISSING → ' + impact))
        if not ok:
            missing.append((label, impact))
    if missing:
        print(f'  → {len(missing)} 项缺失，相关环节需先安装或走回退路径（见 README §7）。')
    print()
    return missing


# ---------- 各脚本冒烟 ----------

def _line_figure(path, w=1260, h=900, elements=1, tint=None, dpi=None):
    """生产口径白底黑线附图：16cm@200dpi≈1260px 宽。tint 给定时叠加彩色像素。
    elements=1 刻意取"稀疏但合法"的框图——它压缩后仅约 5.4KB，用来钉住字节阈值回归。
    dpi 给定时写入 pHYs 元数据（模拟 matplotlib/第三方导出件），不给则 PNG 无 dpi 元数据。"""
    im = Image.new('RGB', (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for i in range(elements):
        y = 20 + i * (h - 40) // max(elements, 1)
        d.line([(30, y), (w - 30, y)], fill=(0, 0, 0), width=3)
        d.rectangle([60 + i * 5, y + 3, 90 + i * 5, y + 14], outline=(0, 0, 0), width=2)
    if tint:
        a = np.array(im); a[100, 100] = tint
        im = Image.fromarray(a)
    im.save(path, **({'dpi': (dpi, dpi)} if dpi else {}))
    return path


def test_check_figures():
    # C1 彩色像素：必须拦（必红）+ 不染色时必须不报 C1（必绿）
    # C2 空白图：必须拦（必红）+ 加一笔黑线后必须放行（必绿）
    # 回归夹具：稀疏合法框图字节数 <10KB，曾因文件字节阈值被误判违规
    with tempfile.TemporaryDirectory() as d:
        fd = os.path.join(d, 'figures'); os.makedirs(fd)
        _line_figure(f'{fd}/图1_稀疏合法框图.png')
        _line_figure(f'{fd}/图2_彩.png', tint=(255, 0, 0))
        Image.new('RGB', (400, 300), (255, 255, 255)).save(f'{fd}/图3_全白空白.png')
        r = run([PY, f'{S}/check_figures.py', d])
        assert_(r.returncode == 1, f'三夹具中至少两张违规，rc 应为 1：{show(r)}', r)
        assert_('图2_彩' in r.stdout and 'C1' in r.stdout, 'C1 彩色判据未触发或未标名', r)
        assert_('图3_全白空白' in r.stdout and 'C2' in r.stdout, 'C2 空白判据未触发或未标名', r)
        assert_('图1_稀疏合法框图' not in r.stdout, '稀疏合法框图被误判违规', r)

        # 逐条撤红：只留稀疏框图 → 必须全绿（证明上面两条红是条件红，不是无条件红）
        os.remove(f'{fd}/图2_彩.png'); os.remove(f'{fd}/图3_全白空白.png')
        r2 = run([PY, f'{S}/check_figures.py', d])
        assert_(r2.returncode == 0 and '违规 0' in r2.stdout, '合规夹具未全绿', r2)
        sz = os.path.getsize(f'{fd}/图1_稀疏合法框图.png')
        assert_(sz < 10240, f'回归夹具字节数 {sz} 已 ≥10240，钉不住旧字节阈值缺陷，请重造夹具')
        print(f'PASS check_figures（C1/C2 各自成对必红必绿；{sz}B 稀疏框图不误判）')




def test_check_figures_embedded():
    """C4：交付物是 docx，图就活在 docx 里——只查 figures/ 会被"在 Word 里换图"绕过。"""
    try:
        from docx import Document
    except ImportError:
        SKIPPED.append('check_figures_embedded')
        print('SKIP check_figures_embedded（本机无 python-docx，造不出带内嵌图的 docx）')
        return
    # 违规素材必须放在被扫目录之外：上一版把彩色图写进 d 里，
    # 于是"docx 内嵌彩色"这一判其实是隔壁那条 C1 在开火——C4 被架空了。
    with tempfile.TemporaryDirectory() as out, tempfile.TemporaryDirectory() as d:
        fd = os.path.join(d, 'figures'); os.makedirs(fd)
        _line_figure(f'{fd}/图1.png', elements=1)
        _line_figure(f'{fd}/图2.png', elements=2)
        colored = os.path.join(out, '彩色.png')
        _line_figure(colored, tint=(255, 0, 0))

        def build(path, imgs):
            doc = Document(); doc.add_heading('说明书附图', level=1)
            for i in imgs:
                doc.add_picture(i)
            doc.save(path)

        # 必红：figures/ 干净、图数也对得上，唯一违规是 docx 里嵌了一张彩色件
        build(os.path.join(d, '申请文件.docx'), [colored, f'{fd}/图2.png'])
        r = run([PY, f'{S}/check_figures.py', d])
        assert_(r.returncode == 1 and 'C4' in r.stdout and 'image1.png' in r.stdout,
                f'docx 内嵌彩色图未被 C4 抓到: {show(r)}', r)
        # 必绿：换成合规件必须放行（同一夹具只差内嵌图内容）
        build(os.path.join(d, '申请文件.docx'), [f'{fd}/图1.png', f'{fd}/图2.png'])
        r2 = run([PY, f'{S}/check_figures.py', d])
        assert_(r2.returncode == 0 and '违规 0' in r2.stdout,
                f'合规内嵌图被 C4 误判: {show(r2)}', r2)

        # 三态：JPEG 是有损格式，黑白线稿存 JPEG 也会出色度噪声 → 只能报未核
        jpg = os.path.join(out, '扫描.jpg')
        Image.open(f'{fd}/图1.png').convert('RGB').save(jpg, quality=80)
        build(os.path.join(d, '申请文件2.docx'), [jpg, f'{fd}/图2.png'])
        r3 = run([PY, f'{S}/check_figures.py', d])
        assert_('C4 未核' in r3.stdout, f'有损内嵌图未走"未核"三态: {show(r3)}', r3)
        assert_(r3.returncode == 0,
                f'有损格式被当成违规（判据过严）: {show(r3)}', r3)
        os.remove(os.path.join(d, '申请文件2.docx'))

        # 必红：内嵌件根本解不开，是交付件坏了，不能折成"看不见所以不判"
        junk = os.path.join(d, '申请文件3.docx')
        # 替换已有内嵌件而不是新增一张：新增会让 media 数也变，rc=1 就由 C3 白送，
        # "解码失败要不要计入" 这条判据就被架空了。
        with zipfile.ZipFile(os.path.join(d, '申请文件.docx')) as src:
            items = [(i, src.read(i)) for i in src.namelist()]
        with zipfile.ZipFile(junk, 'w') as z:
            for name, blob in items:
                z.writestr(name, b'GARBAGE-NOT-A-PNG'
                           if name.startswith('word/media/') else blob)
        r4 = run([PY, f'{S}/check_figures.py', d])
        assert_(r4.returncode == 1 and '无法解码' in r4.stdout,
                f'解不开的内嵌件未判红或未说成因: {show(r4)}', r4)
        os.remove(junk)

    # 外观设计包允许彩色渲染图，C4 必须整档跳过而不是挨个判红
    with tempfile.TemporaryDirectory() as dv:
        fdv = os.path.join(dv, 'figures'); os.makedirs(fdv)
        _line_figure(os.path.join(fdv, '视图1.png'), tint=(255, 0, 0))
        doc = Document(); doc.add_heading('外观简要说明', level=1)
        doc.add_picture(os.path.join(fdv, '视图1.png'))
        doc.save(os.path.join(dv, '外观申请.docx'))
        os.rename(dv, dv + '_外观设计')
        dv = dv + '_外观设计'
        r5 = run([PY, f'{S}/check_figures.py', dv])
        assert_('C4 内嵌图像素规则不适用' in r5.stdout and 'FAIL' not in r5.stdout,
                f'外观设计包未被 C4 跳过: {show(r5)}', r5)
    print('PASS check_figures C4（docx 内嵌图必查 + 有损三态 + 解码失败必红 + 外观设计跳过）')


def test_new_product_package():
    with tempfile.TemporaryDirectory() as d:
        r = run([PY, f'{S}/new_product_package.py', 'TESTX', d])
        assert_(r.returncode == 0, '骨架生成失败', r)
        for sub in ['01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决']:
            assert_(os.path.isdir(os.path.join(d, 'TESTX_专利交付包', sub)), f'缺目录 {sub}：{r.stdout}')
        assert_(os.path.exists(os.path.join(d, 'TESTX_专利交付包', 'README.md')), '缺 README.md')
        # 底稿在场，且文件名带"检索"——verify_search_report 的目录模式靠它挑文件
        stub = os.path.join(d, 'TESTX_专利交付包', '检索_TESTX.md')
        assert_(os.path.isfile(stub), f'缺检索报告底稿（骨架期 V 门禁没有载体）: {r.stdout}', r)
        # 骨架必须开箱即绿：底稿的列名与小节名要和 templates §10 完全一致，
        # 否则 V 门禁要么挑不到文件，要么一上来就报"缺列"
        rv = run([PY, f'{S}/verify_search_report.py', stub, '--offline'])
        assert_(rv.returncode == 0 and '违规 0' in rv.stdout
                and '已核验条目 0 条' in rv.stdout and '缺列' not in rv.stdout,
                '骨架底稿未通过 V1–V6，或未如实报出"条目 0 条"', rv)
        ri = run([PY, f'{S}/check_iron_rules.py', d, '--all'])
        assert_(ri.returncode == 0, '新生成的包未通过铁律门禁（底稿措辞与 R 判据打架）', ri)
        # 第 39 轮那两条标记括号判据在骨架上的正确读数：说明书底稿**有**「说明书摘要」与
        # 「具体实施方式」两个区域，而那张「标记｜名称」表只有表头没有行 ⇒ 号集为空 ⇒
        # 必须说"未判"，既不判红也不冒充核过（生产侧的三态，与 R12/R13 夹具档同一口径）。
        assert_('R12/R13 未判（看不见不等于合规）' in ri.stdout,
                '骨架包上 R12/R13 没走"未判"三态（空表被折成合规，或被折成违规）', ri)
        # 生产侧也要过 Q 族：骨架那份说明书底稿没有真权项，正确读数是一句"未判"，
        # 既不该判红（新判据与生产底稿打架会在这里点名），也不许被折成"核过了"。
        rq = run([PY, f'{S}/check_claims.py', d])
        # 缺席断言不能写 `'→ Q' not in stdout`：三态注记自己就写着 `→ Q…未判`
        # （骨架这份是 `→ Q1–Q6、Q9–Q11、Q13 未判（有节却无项，那几条判不起）`），
        # 这样写会被门禁的复述挡住（永假）。只数非 note 的违规行。
        # 注记文案第 39 轮改过一次：节面三条 Q7／Q8／Q12 现在排在"无项早退"之前，
        # 骨架那份「权利要求书」节只有一行【待填写…】⇒ 走的是"有节却无项"那一档，
        # 不再是"没有权利要求书节 → Q1–Q13 未判"。断言按门禁此刻的真读数写。
        qfired = [ln for ln in rq.stdout.splitlines()
                  if '→ Q' in ln and not ln.lstrip().startswith('note ')]
        assert_(rq.returncode == 0
                and '有权利要求书节但一行权项都没解析出' in rq.stdout
                and '→ Q1–Q6、Q9–Q11、Q13 未判（有节却无项，那几条判不起）' in rq.stdout
                and not qfired,
                f'新生成的包在权利要求形状门禁上的读数不对: {show(rq)}', rq)
        # EVT 底稿在场，且骨架就能被 E1–E4 真判一次（有判定列的表，空行合法）
        evt = os.path.join(d, 'TESTX_专利交付包', '04_EVT验证', 'EVT_TESTX.md')
        assert_(os.path.isfile(evt), f'缺 EVT 报告底稿（E1–E4 没有载体）: {r.stdout}', r)
        re_ = run([PY, f'{S}/check_evt.py', d, '--all'])
        assert_(re_.returncode == 0 and '实核 EVT 文书 1 份' in re_.stdout
                and '无从判起' not in re_.stdout,
                '骨架上的 EVT 底稿未通过 E1–E4，或没被当成域内文书真判', re_)
        # 三态另测：把唯一的 EVT 域内文书删掉，必须 rc=2 说"未做任何判定"而不是判绿
        os.remove(evt)
        re2 = run([PY, f'{S}/check_evt.py', d, '--all'])
        assert_(re2.returncode == 2 and '没有一份落在 EVT 适用域内' in re2.stdout,
                '删掉 EVT 底稿后未走"未判定"三态', re2)
        # 法规底稿在场：五张表都只有表头 → 骨架开箱过 G1–G5（未判注记，不判红）
        reg = os.path.join(d, 'TESTX_专利交付包', '05_法规与裁决', '法规_TESTX.md')
        assert_(os.path.isfile(reg), f'缺法规/裁决底稿（G1–G5 没有载体）: {r.stdout}', r)
        rg = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(rg.returncode == 0 and '实核法规文书 1 份' in rg.stdout
                and '只有表头没有数据行' in rg.stdout,
                '骨架上的法规底稿未通过 G1–G5，或空表没走未判三态', rg)
        reg_text = open(reg, encoding='utf8').read()
        # 真开一火：空表也要能看见"表头掉了一列"，否则骨架与判据漂移永远不出声
        with open(reg, 'w', encoding='utf8') as f:
            f.write(reg_text.replace('| 标准/法规 | 判定 | 依据 |', '| 标准/法规 | 判定 |'))
        rg4 = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(rg4.returncode == 1 and '缺「依据」列' in rg4.stdout,
                '法规底稿表头少一列却未判红（空表被当成无需看列）', rg4)
        # 载体缺席必红：05 目录里换成一张表都没有的散文裁决书
        with open(reg, 'w', encoding='utf8') as f:
            f.write('# 裁决说明\n\n经评审认为适用，无表。\n')
        rg2 = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(rg2.returncode == 1 and '没有任何表格' in rg2.stdout,
                '05 目录内零表格的散文裁决书未判红', rg2)
        os.remove(reg)
        rg3 = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(rg3.returncode == 2 and '没有一份落在法规/裁决适用域内' in rg3.stdout,
                '删掉法规底稿后未走"未判定"三态', rg3)
        # 设计补全底稿：表头由 K 门禁的 SPECS 生成，四张空表开箱走未判
        import importlib.util as _il
        _sp = _il.spec_from_file_location('cdc', f'{S}/check_design_completion.py')
        cdc = _il.module_from_spec(_sp)
        _sp.loader.exec_module(cdc)
        dc_path = os.path.join(d, 'TESTX_专利交付包', '03_设计补全', '补全_TESTX.md')
        assert_(os.path.isfile(dc_path), f'缺设计补全底稿（K1–K4 没有载体）: {r.stdout}', r)
        dc_text = open(dc_path, encoding='utf8').read()
        lost = [f'{tag}:{c}' for tag, spec in cdc.SPECS.items() for c in spec['cols']
                if c not in dc_text]
        assert_(lost == [], f'底稿表头与判据 SPECS 不同源，缺列 {lost}', None)
        rk = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(rk.returncode == 0 and '实核设计补全文书 1 份' in rk.stdout
                and '只有表头没有数据行' in rk.stdout,
                '骨架上的设计补全底稿未通过 K1–K5，或空表没走未判三态', rk)
        # 真开一火：把决策卡的「约束条件」列抹掉，K2 必须当场缺列判红
        with open(dc_path, 'w', encoding='utf8') as f:
            f.write(dc_text.replace('| 依据 | 约束条件 | 风险与回退 |', '| 依据 | 风险与回退 |'))
        rk2 = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(rk2.returncode == 1 and "['约束条件']" in rk2.stdout and '→ K2' in rk2.stdout,
                '底稿表头被改坏后 K2 未判红（说明骨架底稿没真被这张门禁吃进去）', rk2)
        # 说明书底稿：附图说明节 + 三列对照表，表头取自判据侧 COLS（N1–N4 的载体）
        _sp2 = _il.spec_from_file_location('cfl', f'{S}/check_figure_labels.py')
        cfl = _il.module_from_spec(_sp2)
        _sp2.loader.exec_module(cfl)
        sp_path = os.path.join(d, 'TESTX_专利交付包', '02_申请文件', '说明书_TESTX.md')
        assert_(os.path.isfile(sp_path), f'缺说明书底稿（N1–N4 没有载体）: {r.stdout}', r)
        sp_text = open(sp_path, encoding='utf8').read()
        lost_n = [c for c in cfl.COLS if c not in sp_text]
        assert_(lost_n == [], f'说明书底稿表头与判据 COLS 不同源，缺列 {lost_n}', None)
        rn = run([PY, f'{S}/check_figure_labels.py', d, '--all'])
        assert_(rn.returncode == 0 and '实核附图标记文书 1 份' in rn.stdout
                and '只有表头没有数据行' in rn.stdout,
                '骨架上的说明书底稿未通过 N1–N4，或空表没走未判三态', rn)
        # 真开一火：把「所在图号」列抹掉，N1 必须当场缺列判红（空表也看得见结构漂移）
        with open(sp_path, 'w', encoding='utf8') as f:
            f.write(sp_text.replace('| 标记 | 名称 | 所在图号 |', '| 标记 | 名称 |'))
        rn2 = run([PY, f'{S}/check_figure_labels.py', d, '--all'])
        assert_(rn2.returncode == 1 and "['所在图号']" in rn2.stdout and '→ N1' in rn2.stdout,
                '底稿表头被改坏后 N1 未判红（骨架底稿没真被这张门禁吃进去）', rn2)
        # 载体整张缺席：留个有附图说明节的说明书却没有对照表 → N1 必红
        with open(sp_path, 'w', encoding='utf8') as f:
            f.write(sp_text.split('## 图中标记说明')[0])
        rn3 = run([PY, f'{S}/check_figure_labels.py', d, '--all'])
        assert_(rn3.returncode == 1 and '却没有图中标记说明对照表' in rn3.stdout,
                '有附图说明节却无对照表未判红', rn3)
        # 图↔文书对账在骨架期必须"看得见但没有对象"：没有 figures 目录只报未判，
        # 既不判红也不装作核过（这条集成断言专抓适用域误伤，人工跑一遍很容易漏）
        rt = run([PY, f'{S}/check_figure_text.py', os.path.join(d, 'TESTX_专利交付包')])
        assert_(rt.returncode == 0 and 'T1–T3 未判' in rt.stdout,
                '新生成的包在图↔文书对账上未走"未判"三态（判据把骨架误伤或误判成核过）', rt)
        os.remove(sp_path)
        rn4 = run([PY, f'{S}/check_figure_labels.py', d, '--all'])
        assert_(rn4.returncode == 2 and '没有一份落在附图标记适用域内' in rn4.stdout,
                '删掉说明书底稿后未走"未判定"三态', rn4)
    print('PASS new_product_package（五段目录+README+检索/EVT/法规/补全/说明书五份底稿，开箱即过 R/V/E/G/K/N 六门禁）')


def test_rebuild_package():
    with tempfile.TemporaryDirectory() as d:
        pkg = os.path.join(d, 'T包_交付包')
        # 夹具**自己抄一份**五段名，不从判据常量取：取了常量，改常量时夹具跟着一起改，
        # "P5 会不会真拦住缺段"这条就永远不红（与 IRON_OK_BG 硬编码逐字句同理）。
        for seg in ('01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决'):
            os.makedirs(os.path.join(pkg, seg))
        open(os.path.join(pkg, 'README.md'), 'w', encoding='utf8').write(
            '# T包 专利交付包\n\n## 专利清单\n\n| 序号 | 专利名称 | 类型 |\n|---|---|---|\n')
        # 三件齐（P10）＋五节（P12）＋附图说明（N1）：第六份"合规范本"被新判据照红的那一处，
        # 红得对——02_申请文件 法定就是摘要／权要／说明书三件，夹具只写一件等于替判据造假绿；
        # 同一份说明书又要按二十条一款带齐五节，这次补的是那五节（本包无图，附图说明是条件项）。
        open(os.path.join(pkg, '02_申请文件', '说明书_T包.md'), 'w', encoding='utf8').write(
            '# T包 申请文件（说明书骨架）\n\n## 说明书摘要\n\n躯干框架。\n'
            '## 权利要求书\n\n1. 一种躯干框架。\n\n## 说明书\n\n正文。\n'
            '## 技术领域\n\n可穿戴设备。\n## 背景技术\n\n在先技术。\n'
            '## 发明内容\n\n方案要点。\n## 具体实施方式\n\n实施例一。\n'
            '\n## 附图说明\n\n图 1 为躯干框架结构示意图。\n')
        src = os.path.join(pkg, '01_交底书', '交底书.md')
        BODY = '中文内容测试' * 8
        open(src, 'w', encoding='utf8').write(BODY)
        r = run([PY, f'{S}/rebuild_package.py', pkg])
        assert_(r.returncode == 0 and 'SHA-256+CRC+UTF-8 标志位全过' in r.stdout,
                '打包或 P1–P10 校验异常', r)
        with zipfile.ZipFile(pkg + '.zip') as z:
            i = [x for x in z.infolist() if '交底书.md' in x.filename][0]
            assert_(i.flag_bits & 0x800, 'UTF-8 标志位未置', r)
            assert_(z.read(i.filename).decode('utf8') == BODY, 'zip 内容损坏', r)

        # main() 每次重打包，所以"名单对得上而内容不对"这种成品只能直接喂给 verify()
        _sp = importlib.util.spec_from_file_location('rp_bt', f'{S}/rebuild_package.py')
        rp = importlib.util.module_from_spec(_sp); _sp.loader.exec_module(rp)
        REL = '01_交底书/交底书.md'

        def craft(tag, name, data):
            z = os.path.join(d, tag + '.zip')
            with zipfile.ZipFile(z, 'w', zipfile.ZIP_STORED) as zf:
                zf.writestr('T包_交付包/' + name, data)
            return z

        assert_(rp.verify(pkg, os.path.join(d, 'T包_交付包.zip')) == [],
                f'合规包被 P1–P4 判红（这把尺子自己造假红）: {rp.verify(pkg, os.path.join(d, "T包_交付包.zip"))}', None)
        v = rp.verify(pkg, craft('p1', REL, BODY[:len(BODY) // 2]))
        assert_(any(x.startswith('P1') for x in v), f'截断（字节数不符）没被抓到: {v}', None)
        v = rp.verify(pkg, craft('p2', REL, BODY.replace('测试', '测式')))
        assert_(any(x.startswith('P2') for x in v), f'同长度换字（SHA-256 不符）没被抓到: {v}', None)
        # 名单差集也要报——且不能因为报了差集就跳过交集内容比对
        d5 = os.path.join(d, 'P包_两文件'); os.makedirs(os.path.join(d5, '01_交底书'))
        open(os.path.join(d5, '01_交底书', '交底书.md'), 'w', encoding='utf8').write(BODY)
        open(os.path.join(d5, '01_交底书', '检索报告.md'), 'w', encoding='utf8').write('一份没进包的文件')
        p5 = os.path.join(d, 'p5.zip')
        with zipfile.ZipFile(p5, 'w', zipfile.ZIP_STORED) as zf:
            zf.writestr('P包_两文件/' + REL, BODY[:4])
            zf.writestr('P包_两文件/01_交底书/多出来的.md', 'x')
        v = rp.verify(d5, p5)
        assert_(any('目录有、zip 里没' in x for x in v) and any('zip 有、目录里没有' in x for x in v)
                and any(x.startswith('P1') for x in v),
                f'名单差集或交集内容比对没报全: {v}', None)
        # P3：翻一个内容字节让 CRC 炸；判据必须把它报成 P3 而不是带 traceback 退 1，
        # 且 testzip 点过名的条目不再报第二遍（同一件事报两次会淹掉别的原告）。
        p3 = craft('p3', REL, BODY)
        raw = bytearray(open(p3, 'rb').read())
        k = raw.index('中'.encode('utf8')); raw[k] += 1
        cp = os.path.join(d, 'p3c.zip'); open(cp, 'wb').write(bytes(raw))
        try:
            v3 = rp.verify(pkg, cp)
        except Exception as e:
            v3 = [f'逃逸异常 {type(e).__name__}']
        assert_(any(x.startswith('P3') for x in v3)
                and len([x for x in v3 if x.startswith('P3')]) == 1,
                f'P3 没抓到、逃逸成异常、或重复上报: {v3}', None)
        bad = os.path.join(d, '坏包.zip'); open(bad, 'wb').write(b'not a zip')
        try:
            rp.verify(pkg, bad); code = None
        except SystemExit as e:
            code = e.code
        assert_(code == 2, f'打不开的 zip 没按 rc=2 收（实得 {code}）', None)

        r = run([PY, f'{S}/rebuild_package.py'])
        assert_(r.returncode == 2 and '用法' in r.stdout, f'零参数没按 rc=2 收: {show(r)}', r)
        r = run([PY, f'{S}/rebuild_package.py', src])
        assert_(r.returncode == 2 and '只接包目录' in r.stdout, f'传文件没说明成因: {show(r)}', r)

        # P5–P7 包形状：三条各自成对。上面那份合规夹具守"三绿"（verify==[] 已经含它），
        # 这里各造一份只坏一项的包，坏哪一条必须点名哪一条——顺手把整包判红等于没有判据。
        def mkshape(tag, drop=None, readme='清单', empty_app=False):
            p = os.path.join(d, tag)
            for seg in ('01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决'):
                if seg != drop:
                    os.makedirs(os.path.join(p, seg))
            if readme is not None:
                open(os.path.join(p, 'README.md'), 'w', encoding='utf8').write(
                    '# 交付包\n\n## 专利' + readme + '\n\n| 序号 | 名称 | 类型 |\n')
            # 三件齐（P10）：骨架期那份只有"正文"两个字的说明书，P10 一上去就红了——
            # 这是设计好的反馈：02_申请文件 的法定件本来就是摘要／权要／说明书三件，
            # 夹具若只写一件，"缺一件会不会真拦住"那条断言就永远不红。
            # 五节名在这里**硬写**而不是 import 判据常量：抄了常量，改名时夹具跟着改，
            # "少一节会不会真拦住"那条断言就永远不红（R9/P10 同一先例）。
            open(os.path.join(p, '02_申请文件', '说明书.md'), 'w', encoding='utf8').write(
                '# 申请文件\n## 说明书摘要\n摘要正文\n## 权利要求书\n1. 一种装置。\n'
                '## 说明书\n正文\n## 技术领域\n可穿戴设备。\n## 背景技术\n在先技术。\n'
                '## 发明内容\n方案要点。\n## 附图说明\n见随包图样。\n'
                '## 具体实施方式\n实施例一。\n' if not empty_app else '')
            return p

        v = rp.shape_violations(mkshape('形状包_合规'))
        assert_(v == [], f'合规包形状被 P5–P7 判红（假红）: {v}', None)
        v = rp.shape_violations(mkshape('形状包_缺段', drop='04_EVT验证'))
        assert_([x for x in v if x.startswith('P5')] and
                len([x for x in v if x.startswith('P5')]) == 1 and '04_EVT验证' in v[0] and
                not any(x.startswith('P7') for x in v),
                f'缺一段没被点名成一条 P5（或牵连误报了别的）: {v}', None)
        v = rp.shape_violations(mkshape('形状包_无清单', readme='须知道'))
        assert_(any(x.startswith('P6') for x in v) and not any(x.startswith('P5') for x in v),
                f'README 缺「专利清单」没被抓成 P6，或被误报成 P5: {v}', None)
        v = rp.shape_violations(mkshape('形状包_无README', readme=None))
        assert_(any(x.startswith('P6') and '包根没有 README.md' in x for x in v),
                f'包根缺 README.md 没被抓到: {v}', None)
        v = rp.shape_violations(mkshape('形状包_空申请', empty_app=True))
        assert_(any(x.startswith('P7') for x in v) and not any(x.startswith('P5') for x in v),
                f'02_申请文件 只有一个 0 字节文件也被当成"有交付物"（P7 漏报或被误报成缺段）: {v}', None)
        pdir = mkshape('形状包_真空申请')
        for f in os.listdir(os.path.join(pdir, '02_申请文件')):
            os.remove(os.path.join(pdir, '02_申请文件', f))
        v = rp.shape_violations(pdir)
        assert_(any(x.startswith('P7') for x in v), f'02_申请文件 真是空目录时 P7 没抓到: {v}', None)
        # P8／P9：类型列要落在三类里（第四十四条（六）），实用新型必须有附图（同条（一））。
        # 表由夹具自己写，不从判据里取表头——取了常量，改名时夹具跟着改，
        # "填错类型会不会真拦住"那条断言就永远不红。
        def mktbl(tag, cells, png=0, media=0, broken_docx=False):
            p = mkshape(tag)
            lines = ['# 交付包', '', '## 专利清单',
                     '| 编号 | 类型 | 名称 | 附图/视图 | 定位 |',
                     '|---|---|---|---|---|']
            for i, c in enumerate(cells or [], 1):
                lines.append(f'| {i} | {c} | 锁扣 | 图1 | 结构 |')
            open(os.path.join(p, 'README.md'), 'w', encoding='utf8').write('\n'.join(lines) + '\n')
            fig = os.path.join(p, '02_申请文件', 'figures')
            os.makedirs(fig, exist_ok=True)
            for i in range(png):
                open(os.path.join(fig, f'图{i + 1}.png'), 'wb').write(b'\x89PNG' + b'0' * 30)
            if media or broken_docx:
                dz = os.path.join(p, '02_申请文件', '申请文件.docx')
                if broken_docx:
                    open(dz, 'wb').write(b'not a zip')
                else:
                    import zipfile as _zf
                    with _zf.ZipFile(dz, 'w') as z:
                        z.writestr('word/document.xml', '<w:document/>')
                        for i in range(media):
                            z.writestr(f'word/media/image{i + 1}.png', 'x' * 20)
            return p

        def shape(tag, cells, **kw):
            return rp.shape_state(mktbl(tag, cells, **kw))

        b, n = shape('P89_清单无行', None)
        assert_(b == [] and any('一张专利都没列' in x for x in n),
                f'清单没列专利时被折成合规或误判红: {b} / {n}', None)
        b, n = shape('P89_发明有图', ['发明'], png=1)
        assert_(b == [] and n == [], f'合规清单被 P8/P9 误伤: {b} / {n}', None)
        b, n = shape('P89_实用新型无图', ['实用新型'])
        assert_(any(x.startswith('P9') and '全包找不到一张图' in x for x in b)
                and not any(x.startswith('P8') for x in b),
                f'实用新型零图未被 P9 抓到（或牵连误报了 P8）: {b} / {n}', None)
        b, _ = shape('P89_实用新型有png', ['实用新型'], png=1)
        assert_(b == [], f'有 png 的实用新型仍被 P9 判红: {b}', None)
        b, _ = shape('P89_实用新型docx内嵌', ['实用新型'], media=1)
        assert_(b == [], f'图只在 docx 的 word/media 里就被当成没图（C4 同一条理由）: {b}', None)
        b, _ = shape('P89_类型写产品', ['产品'], png=1)
        assert_(any(x.startswith('P8') and '不是 发明／实用新型／外观设计' in x for x in b),
                f'类别写成「产品」没被 P8 抓到: {b}', None)
        b, _ = shape('P89_类型空', [''], png=1)
        assert_(any(x.startswith('P8') and '没写类型' in x for x in b),
                f'空类型没被 P8 抓到: {b}', None)
        # 底稿的占位「【待填写：发明/实用新型】」里真含着"发明"两个字：
        # 先认类别后认占位会把"还没定"读成"定了发明"，那种包两头都不红。
        b, n = shape('P89_类型占位', ['【待填写：发明/实用新型】'], png=1)
        assert_(b == [] and any('还是占位' in x and '未判' in x for x in n),
                f'占位被当成已声明类别，或没说清这是未判: {b} / {n}', None)
        b, n = shape('P89_实用新型docx读不动', ['实用新型'], broken_docx=True)
        assert_(b == [] and any(x.startswith('P9 未判') for x in n),
                f'docx 读不动时 P9 猜成"没图"、或干脆不吭声: {b} / {n}', None)

        # P10：02_申请文件 三件齐（专利法 26 条一；不予受理那一半另引细则 44 条（一））
        def mkapp(tag, body=None, docx=False, broken=False):
            p = mkshape(tag)
            app = os.path.join(p, '02_申请文件')
            for f in os.listdir(app):
                os.remove(os.path.join(app, f))
            if body is not None:
                nm = '申请文件.docx' if docx else '申请文件.md'
                if docx:
                    from docx import Document
                    doc = Document()
                    for ln in body.splitlines():
                        if ln.startswith('## '):
                            doc.add_heading(ln[3:], level=2)
                        elif ln.strip():
                            doc.add_paragraph(ln)
                    doc.save(os.path.join(app, nm))
                else:
                    open(os.path.join(app, nm), 'w', encoding='utf8').write(body)
            if broken:
                open(os.path.join(app, '坏件.docx'), 'wb').write(b'not a zip')
            return p

        # 五节一起带上（P12）：FULL3 是 P10/P11 各档的"合规范本"，不带五节就会被 P12 照红，
        # 而那些档测的是缺件/遮蔽，不是五节齐——正本清源是补夹具，不是放宽判据。
        FULL3 = ('# 申请文件\n## 说明书摘要\nx\n## 权利要求书\n1. 一种装置。\n'
                 '## 说明书\ny\n## 技术领域\nz1\n## 背景技术\nz2\n## 发明内容\nz3\n'
                 '## 附图说明\nz4\n## 具体实施方式\nz5\n## 说明书附图\n图1\n')
        b, n = rp.shape_state(mkapp('P10_三件齐', FULL3))
        assert_(b == [] and not any('P10' in x for x in n),
                f'三件齐的申请文件被 P10 误伤: {b} / {n}', None)
        b, _ = rp.shape_state(mkapp('P10_缺权要', FULL3.replace('## 权利要求书\n1. 一种装置。\n', '')))
        assert_(any('P10' in x and '权利要求书' in x for x in b),
                f'缺权利要求书没被 P10 抓到: {b}', None)
        # 子串遮蔽：模板 §2 里「说明书摘要」「说明书附图」与「说明书」并列存在，
        # 按"包含"认的话，一份只写了摘要与附图的包会被读成"说明书齐了"。
        b, _ = rp.shape_state(mkapp('P10_摘要不算说明书',
                                    '# 申请文件\n## 说明书摘要\nx\n## 说明书附图\n图1\n'))
        assert_(sum('P10' in x for x in b) == 2
                and any('「说明书」' in x for x in b) and any('「权利要求书」' in x for x in b),
                f'摘要/附图被当成说明书，或缺件报少了: {b}', None)
        b, _ = rp.shape_state(mkapp('P10_带编号括注',
                                    '# 申请文件\n### 1. 说明书（正文另存）\n'
                                    '### 2. 权利要求书（取自交底书 §6）\n### 3. 说明书摘要（≤300 字）\n'
                                    '### 4. 技术领域（可穿戴设备）\n### 5. 背景技术（引证在先技术）\n'
                                    '### 6. 发明内容\n### 7. 附图说明\n### 8. 具体实施方式\n'))
        assert_(b == [], f'节名带编号与尾注时 P10 误伤: {b}', None)
        try:
            from docx import Document
            b, _ = rp.shape_state(mkapp('P10_只有Word件', FULL3, docx=True))
            assert_(b == [], f'Word-only 申请文件被 P10 当成缺件: {b}', None)
        except ImportError:
            print('  SKIP P10 的 docx 通道（无 python-docx）')
        b, n = rp.shape_state(mkapp('P10_坏docx', FULL3, broken=True))
        assert_(b == [] and any('P10 未核' in x for x in n),
                f'读不动的 docx 被折成缺件、或未核这件事没说出来: {b} / {n}', None)
        # 目录在而里面一份文书都没有：P7 报空壳，P10 也照报三件缺（两码事，各报各的）
        b, n = rp.shape_state(mkapp('P10_空壳02', None))
        assert_(any(x.startswith('P7') for x in b) and sum(x.startswith('P10') for x in b) == 3
                and not any('P10 未判' in x for x in n),
                f'空壳 02 目录的两种坏没分开报: {b} / {n}', None)

        # P11：外观设计那一支的法定件（细则 44 条（一）**后段**＋专利法 27 条一）。
        # 第三十轮把 44 条（一）引成"……"时正好切掉了"或者外观设计专利申请缺少请求书、
        # 图片或者照片、简要说明的"这半句，于是 P9/P10 都落了地而这一支还空着。
        BRIEF = '# 简要说明\n## 简要说明\n本外观设计产品的名称：手柄。用途：握持。\n'

        def mkbrief(tag, cells, brief=None, **kw):   # 缺件靠默认，交件必须显式给 brief=BRIEF
            p = mktbl(tag, cells, **kw)
            if brief is not None:
                open(os.path.join(p, '02_申请文件', '简要说明.md'), 'w', encoding='utf8').write(brief)
            return p

        b, n = rp.shape_state(mkbrief('P11_外观齐件', ['外观设计'], png=1, brief=BRIEF))
        # 断言只看"P11 自己开没开口"，不能写 'P11' in note：
        # P10 那句"归 P11 判"的说明里就含 P11 三个字，字面判会把说明读成开火。
        assert_(b == [] and not any(x.startswith('P11') for x in n),
                f'交了简要说明又有图的外观设计包被 P11 误伤: {b} / {n}', None)
        SPEC5 = ('技术领域', '背景技术', '发明内容', '附图说明', '具体实施方式')
        SPEC4 = ('技术领域', '背景技术', '发明内容', '具体实施方式')

        def mkonly(tag, cells, names, img=True):
            p = mktbl(tag, cells)                       # 先造表，再清 02 段重建内容
            app = os.path.join(p, '02_申请文件')
            for f in os.listdir(app):
                fp = os.path.join(app, f)
                shutil.rmtree(fp) if os.path.isdir(fp) else os.remove(fp)
            for nm in names:
                open(os.path.join(app, nm + '.md'), 'w', encoding='utf8').write(
                    '# %s\n## %s\n正文若干。\n' % (nm, nm))
            if img:      # 图的有无是 P12 的条件项输入，必须可由夹具控制
                open(os.path.join(app, '主视图.png'), 'wb').write(b'\x89PNG' + b'0' * 30)
            return p

        def mkspec(tag, cells, names, png=1, split=False):
            """P12 的夹具：先把 P10 那三件立齐（否则测的是 P10 不是 P12），
            再把 names 里的五节按 split 写进一份或几份文书。"""
            p = mkonly(tag, cells, ['说明书摘要', '权利要求书', '说明书'], img=bool(png))
            app = os.path.join(p, '02_申请文件')
            for nm in names:
                fn = ('说明书_%s.md' % nm) if split else '说明书.md'
                with open(os.path.join(app, fn), 'a', encoding='utf8') as f:
                    f.write('## %s\n%s：正文若干。\n' % (nm, nm))
            if png:
                open(os.path.join(app, '图1.png'), 'wb').write(b'\x89PNG' + b'0' * 30)
            return p

        # 缺简要说明：单这一件坏，就该只点这一个名（图已经给了）
        b, _ = rp.shape_state(mkbrief('P11_缺简要说明', ['外观设计'], png=1, brief=None))
        assert_([x for x in b if x.startswith('P11')] and
                all('简要说明' in x for x in b if x.startswith('P11')),
                f'外观设计缺简要说明没被 P11 单独点出来: {b}', None)
        # 建议稿式节名不与"简要说明"全等 ⇒ 仍算缺（与 P10 的"摘要不算说明书"同一条认法）
        b, _ = rp.shape_state(mkbrief('P11_建议稿不算', ['外观设计'], png=1,
                                      brief='# 简要说明建议稿\n## 简要说明建议稿\n名称：手柄。\n'))
        assert_(any(x.startswith('P11') and '简要说明' in x for x in b),
                f'「简要说明建议稿」被当成已经交了简要说明: {b}', None)
        # 没图：外观设计的"图片或者照片"是 44 条（一）后段明文那一格
        b, _ = rp.shape_state(mkbrief('P11_外观没图', ['外观设计'], png=0, brief=BRIEF))
        assert_(sum(x.startswith('P11') for x in b) == 1 and
                any('图片或照片' in x for x in b if x.startswith('P11')) and
                not any(x.startswith('P9') for x in b),
                f'零图的外观设计包没被 P11 恰好抓住一条（或反过来牵连了 P9）: {b}', None)
        # docx 内嵌件算图：与 P9 同一条通道，两通道任一有图即不判红
        b, _ = rp.shape_state(mkbrief('P11_图在docx里', ['外观设计'], media=1, brief=BRIEF))
        assert_(not any(x.startswith('P11') and '图片' in x for x in b),
                f'图藏在 docx word/media/ 里被 P11 当成没交图: {b}', None)
        # 两型同列且零图：全包几张图是**一件事实**，判红只出一次（P9），P11 补一条 note
        b, n = rp.shape_state(mkbrief('P11_两型都缺图', ['实用新型', '外观设计'], png=0,
                                         brief=BRIEF))
        assert_(sum(('图片' in x or '一张图' in x) for x in b) == 1 and
                any(x.startswith('P9') for x in b) and
                any('P11 的"没图"' in x for x in n),
                f'同一件"全包零图"被判成两个原告，或那件 note 没说清: {b} / {n}', None)
        # 清单没列外观设计 ⇒ 不适用（与"没列实用新型"对偶，连没图也不报）
        b, n = rp.shape_state(mkspec('P11_未列外观', ['发明'], list(SPEC5)))
        assert_(b == [] and not any(x.startswith('P11') for x in b + n),
                f'只列发明的包被 P11 管上了（适用域越界）: {b} / {n}', None)
        # 类型格还是占位 ⇒ 未判，不折成"没交"也不折成合规
        b, n = rp.shape_state(mkbrief('P11_类型占位', ['【待填写：发明/外观设计】'], png=0))
        assert_(b == [] and any('占位' in x for x in n),
                f'类别未定时 P11 猜了一边: {b} / {n}', None)
        # 02_申请文件 整段不在 ⇒ P5 报缺段，P11 走未判（同一件坏不占两个原告）
        gone = mkbrief('P11_无02段', ['外观设计'], png=1, brief=BRIEF)
        shutil.rmtree(os.path.join(gone, '02_申请文件'))
        b, n = rp.shape_state(gone)
        assert_(any(x.startswith('P5') for x in b) and
                not any(x.startswith('P11') for x in b) and
                any('P11 未判' in x for x in n),
                f'缺整段被判成"缺简要说明"（重复）或未说清未判: {b} / {n}', None)
        # 包里有读不动的 docx ⇒ 图这一半未判（不猜"没图"），简要说明这一半照判缺
        b, n = rp.shape_state(mkbrief('P11_坏docx', ['外观设计'], broken_docx=True))
        assert_(any(x.startswith('P11') and '简要说明' in x for x in b) and
                any('P11 未判' in x and 'docx' in x for x in n),
                f'读不动的 docx 下，P11 该"半判半未判"而不是一边倒: {b} / {n}', None)

        # P10 的适用面：三件是**发明／实用新型那一支**的要件（44 条（一）同一项里给
        # 外观设计另写了后一段）。三种包形各钉一头：
        #   只列外观设计 → 不许按发明口径要件（那是假红）
        #   混合两型   → 发明那一支照样要三件，不能被"外观不交"带过去
        #   类型占位   → 未判不许折成豁免
        b, n = rp.shape_state(mkonly('P10_外观只交简要说明', ['外观设计'], ['简要说明']))
        assert_(not any(x.startswith('P10') for x in b) and
                any('P10 不适用' in x for x in n),
                f'只列外观设计、依法只交简要说明与图的包被按发明口径要了三件: {b} / {n}', None)
        b, n = rp.shape_state(mkonly('P10_混合缺权要', ['发明', '外观设计'],
                                     ['简要说明', '说明书摘要', '说明书']))
        assert_(sum(x.startswith('P10') for x in b) == 1 and
                any('权利要求书' in x for x in b),
                f'混合包里发明那一支的三件要件丢了: {b} / {n}', None)
        b, n = rp.shape_state(mkonly('P10_类型占位仍要三件', ['【待填写：发明/实用新型】'],
                                     ['简要说明']))
        assert_(sum(x.startswith('P10') for x in b) == 3 and
                not any('P10 不适用' in x for x in n),
                f'类型还没定时 P10 被折成"这一支不受要求"（未判当豁免）: {b} / {n}', None)

        # P12：细则第二十条一款的说明书五节（技术领域／背景技术／发明内容／附图说明／具体实施方式），
        # 二款还要求"按照前款规定的方式和顺序撰写…并在每一部分前面写明标题"⇒ 认的是**节标题**，
        # 不是正文里提到这几个词。两条口径缺一不可，否则判据会松成"出现过就行"：
        #   ① 必须**同一份**说明书里齐（拼盘式满足不算）；
        #   ② 附图说明只在"这份说明书所属的包有图"或实用新型时才要（20 条（四）写的是"说明书有附图的"）。
        b, n = rp.shape_state(mkspec('P12_五节齐', ['发明'], list(SPEC5)))
        assert_(b == [] and not any(x.startswith('P12') for x in n),
                f'五节齐的发明说明书被 P12 误伤: {b} / {n}', None)
        b, _ = rp.shape_state(mkspec('P12_缺两节', ['发明'], ['技术领域', '附图说明', '具体实施方式']))
        assert_(sum(x.startswith('P12') for x in b) == 2 and
                all('背景技术' in x or '发明内容' in x for x in b if x.startswith('P12')),
                f'缺两节没被 P12 逐节点出来（或牵连误报了别的）: {b}', None)
        # 拼盘：五节各写在各文件里 ⇒ 并集会读成齐，P12 必须看穿
        b, _ = rp.shape_state(mkspec('P12_拼盘不算', ['发明'], list(SPEC5), split=True))
        assert_(any(x.startswith('P12') for x in b),
                f'五节被拆成五份文件仍被读成"说明书五节齐": {b}', None)
        # 发明＋全包零图 ⇒ 附图说明不硬要（20 条（四）的条件句）
        b, _ = rp.shape_state(mkspec('P12_无图发明免附图说明', ['发明'], list(SPEC4), png=0))
        assert_(b == [], f'没有附图的发明包被 P12 要求"附图说明"这一节: {b}', None)
        # 实用新型 ⇒ 图是 44 条（一）的硬要求，附图说明这一节也就跟着要（有图的那档已测在上面）
        b, _ = rp.shape_state(mkspec('P12_实用新型有图缺附表', ['实用新型'], list(SPEC4), png=1))
        assert_(any(x.startswith('P12') and '附图说明' in x for x in b),
                f'有图的包缺「附图说明」节没被 P12 点出: {b}', None)
        # 类型未定（占位）⇒ 与 P10 同口径照判；只列外观设计 ⇒ 不适用（那一支根本没有说明书）
        b, n = rp.shape_state(mkbrief('P12_只列外观', ['外观设计'], png=1, brief=BRIEF))
        assert_(b == [] and any('P12 不适用' in x for x in n) and
                any('P10 不适用' in x for x in n),
                f'外观设计包被按发明口径要三件或五节（或不适用这件事没说出口）: {b} / {n}', None)
        b, n = rp.shape_state(mkonly('P12_无说明书那份', ['发明'],
                                     ['说明书摘要', '权利要求书']))
        assert_(any(x.startswith('P10') for x in b) and
                any('P12 未判' in x for x in n),
                f'连「说明书」节都没有时，P12 该说未判而不是再判一遍缺件: {b} / {n}', None)

        # 模板 §2 是给人抄的那份形状：它若与 P10/P12 对不上，判据就是在判红自己的范本
        # （V5 第一版犯的正是这个错，红在自家 templates §10 上）。所以把那段 markdown
        # **原样**取出来当文书喂进去——不另抄一份"我以为模板长什么样"的字符串。
        tpl = open(os.path.join(ROOT, 'references', 'templates.md'), encoding='utf8').read()
        seg = tpl.split('## 2. CNIPA 申请文件草稿模板', 1)
        assert_(len(seg) == 2, '模板 §2 的标题变了，这条"范本必须开箱过门禁"的断言就空转了', None)
        body = seg[1].split('```', 2)[1]
        assert_('### 附图说明' in body and '## 说明书（' in body,
                '模板 §2 里五节不是各自立标题（P12 会判红自己的范本）', None)
        tp = mkonly('P12_模板§2形状', ['发明'], [])
        open(os.path.join(tp, '02_申请文件', '申请文件.md'), 'w', encoding='utf8').write(body)
        b, n = rp.shape_state(tp)
        assert_(b == [], f'照 templates §2 写出来的申请文件被 P10/P12 判红: {b} / {n}', None)
        # 反向：把模板里那五个小标题去掉（回到旧写法"五节挤在一个括注里"），P12 必须逐节点出五条
        stripped = body.replace('### 技术领域\n### 背景技术\n### 发明内容\n### 附图说明\n'
                                '### 具体实施方式\n', '')
        assert_(stripped != body, '模板 §2 里那五行标题变了，这个反向对照没改动任何东西', None)
        open(os.path.join(tp, '02_申请文件', '申请文件.md'), 'w', encoding='utf8').write(stripped)
        b, _ = rp.shape_state(tp)
        assert_(sum(x.startswith('P12') for x in b) == 5,
                f'五节被收回括注后 P12 没有逐节点出五条: {b}', None)

        # 形状判据必须走得到真入口：main() 打完包后要能报出来（否则 shape 只在单元里活着）
        rpk = mkshape('形状包_走main', drop='05_法规与裁决')
        r = run([PY, f'{S}/rebuild_package.py', rpk])
        assert_(r.returncode == 1 and 'P5' in r.stdout and '05_法规与裁决' in r.stdout,
                f'缺段包从 main() 出去时没被判红点名: {show(r)}', r)
        r = run([PY, f'{S}/rebuild_package.py', mktbl('P89_走main红', ['实用新型'])])
        assert_(r.returncode == 1 and 'P9' in r.stdout,
                f'零图的实用新型从 main() 出去时没被点名: {show(r)}', r)
        r = run([PY, f'{S}/rebuild_package.py', mktbl('P89_走main未判', ['【待填写】'])])
        assert_(r.returncode == 0 and 'note' in r.stdout and '占位' in r.stdout,
                f'未判没随 main() 打印：退 0 就等于宣称核过了: {show(r)}', r)
        r = run([PY, f'{S}/rebuild_package.py',
                 mkapp('P10_走main红', FULL3.replace('## 权利要求书\n1. 一种装置。\n', ''))])
        assert_(r.returncode == 1 and 'P10' in r.stdout and '权利要求书' in r.stdout,
                f'缺件的申请文件从 main() 出去时没被点名: {show(r)}', r)
        r = run([PY, f'{S}/rebuild_package.py',
                 mkbrief('P11_走main红', ['外观设计'], png=1)])
        assert_(r.returncode == 1 and 'P11' in r.stdout and '简要说明' in r.stdout,
                f'缺简要说明的外观设计包从 main() 出去时没被点名: {show(r)}', r)
        # 自报区间的上界必须由源码现推（与 check_iron_rules 那把 R 号尺子同一条纪律）。
        # 本轮实测到四处 "P1–P11" 是一个中断补丁没落盘留下的旧值——判据加了 P12 而自述还说 11，
        # 契约只看文档侧的区间，看不见脚本自己这两行。
        rpsrc = open(f'{S}/rebuild_package.py', encoding='utf8').read()
        pk = sorted({int(x) for x in re.findall(r"(?:bad|notes)\.append\((?:f|)['\"]P([1-9]\d?)(?!\d)", rpsrc)} |
                    {int(x) for x in re.findall(r'^\s{2}P([1-9]\d?)\s', rpsrc, re.M)})
        assert_(pk and pk[0] == 1, f'P 号现推结果不像话（应从 P1 起）：{pk}', None)
        # 提取器自带的反证：两位数必须看得见，否则会退化成"永远说 P1–P9"而无人察觉
        _psrc = ('  P9 九号\n  P12 十二号\nbad.append(\'P10 报文\')\n'
                 'bad.append(f"P11 报文")\nnotes.append(\'P8／P9 未判\')\nP0 不是判据号\n')
        _pp = sorted({int(x) for x in re.findall(
            r"(?:bad|notes)\.append\((?:f|)['\"]P([1-9]\d?)(?!\d)", _psrc)} | {int(x) for x in re.findall(
            r'^\s{2}P([1-9]\d?)\s', _psrc, re.M)})
        assert_(_pp == [8, 9, 10, 11, 12], f'P 号提取器对两位数漏判或误收 0 号：{_pp}', None)
        for claim in (f'MISMATCH（P1–P{pk[-1]}）', f'（P1–P{pk[-1]} 任一）'):
            assert_(claim in rpsrc,
                    f'打包门禁自报的区间与实际判据 P1–P{pk[-1]} 不一致：缺 {claim}', None)
        assert_(re.search(r'包形状 P5–P9 判', open(os.path.join(ROOT, 'references', 'hard-rules.md'),
                                                   encoding='utf8').read()) is None,
                'hard-rules §8 还说 P5–P9 判包形状（区间落后于判据）', None)

    print('PASS rebuild_package（P1 截断 / P2 换字 / P3 CRC 单报 / 名单差集 / 合规包零误报 / '
          'P5–P7 各成对且从 main() 走得到 / P8–P9 九档含占位与内嵌图 / '
          'P10 三件齐含遮蔽与未核＋只列外观设计不套发明口径（三向各一档） / '
          'P11 外观设计两件含建议稿遮蔽与两型同列不重复报 / '
          'P12 说明书五节齐含拼盘不认、附图说明条件项与模板§2 正反两档 / rc=2 三档）')


def _make_pandoc_shim(bin_dir, corrupt=False):
    """造一个名为 pandoc 的桩：默认用 python-docx 直出 docx，并把收到的 locale 写进 sidecar；
    corrupt=True 时转换"成功"(rc=0)但产出非 docx 字节，用来验证脚本内部的 python-docx 复核。
    用于在没有真 pandoc 的机器上仍然验证「解析→子进程→locale 透传→复核→计数」全链路。"""
    shim = os.path.join(bin_dir, 'pandoc')
    body = ('''import os, sys
args = sys.argv[1:]
src = args[0]
out = args[args.index('-o') + 1]
''' + ('''open(out, 'wb').write(b'NOT-A-DOCX' * 40)
open(out + '.locale', 'w').write(os.environ.get('LC_ALL', '') + '|' + os.environ.get('LANG', ''))
''' if corrupt else '''from docx import Document
doc = Document()
for line in open(src, encoding='utf8').read().splitlines():
    if line.strip():
        doc.add_paragraph(line.lstrip('#').strip())
doc.save(out)
open(out + '.locale', 'w').write(os.environ.get('LC_ALL', '') + '|' + os.environ.get('LANG', ''))
'''))
    open(shim, 'w', encoding='utf8').write(f'#!{PY}\n' + body)
    os.chmod(shim, os.stat(shim).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return shim


def _md_fixture(d, name='测试'):
    md = os.path.join(d, f'{name}.md')
    open(md, 'w', encoding='utf8').write('# 标题\n\n中文段落测试。\n')
    open(os.path.join(d, f'{name}.docx'), 'w').close()  # 占位使 regen 拾取
    return md, name


def test_regen_docx():
    # 必红对照：pandoc 确实不可用时，必须 fail-closed 给出可行动诊断，而不是抛 traceback。
    # 用 PYTHONPATH 上的 pypandoc 桩（get_pandoc_path 抛 OSError，与真实缺 pandoc 行为一致）
    # 保证这一档在任何机器上都成立。
    with tempfile.TemporaryDirectory() as d:
        stub = os.path.join(d, 'stub'); os.makedirs(stub)
        open(os.path.join(stub, 'pypandoc.py'), 'w', encoding='utf8').write(
            'def get_pandoc_path():\n    raise OSError("pandoc not found")\n')
        empty = os.path.join(d, 'nopath'); os.makedirs(empty)
        _md_fixture(d)
        r = run([PY, f'{S}/regen_docx.py', d],
                env={'PATH': empty, 'PYTHONPATH': stub})
        assert_(r.returncode == 2, f'缺 pandoc 未走 fail-closed（应 rc=2，实得 {r.returncode}）', r)
        assert_('pandoc' in r.stdout and 'brew install pandoc' in r.stdout,
                '缺 pandoc 时未打印可行动安装提示', r)
        assert_('Traceback' not in r.stdout + r.stderr, '缺 pandoc 时抛裸 traceback', r)

    # 必红对照二：python-docx 缺失也是环境问题，必须走 rc=2，
    # 不能被记成逐文件 failed:（否则调用方会去改 md 而不是装依赖）。
    with tempfile.TemporaryDirectory() as d:
        stub = os.path.join(d, 'stub'); os.makedirs(stub)
        open(os.path.join(stub, 'docx.py'), 'w', encoding='utf8').write(
            'raise ImportError("simulated: python-docx not installed")\n')
        bindir = os.path.join(d, 'bin'); os.makedirs(bindir)
        _make_pandoc_shim(bindir)
        _md_fixture(d)
        r = run([PY, f'{S}/regen_docx.py', d], env={'PATH': bindir, 'PYTHONPATH': stub})
        assert_(r.returncode == 2, f'缺 python-docx 未走 fail-closed（应 rc=2，实得 {r.returncode}）', r)
        assert_('pip install python-docx' in r.stdout, '缺 python-docx 时未打印安装指引', r)
        assert_('failed: 1' not in r.stdout, '缺依赖被误计为文件级失败', r)

    # 必绿对照：pandoc 可用时必须真转换、rc=0、产物可开、UTF-8 locale 已透传。
    with tempfile.TemporaryDirectory() as d:
        bindir = os.path.join(d, 'bin'); os.makedirs(bindir)
        _make_pandoc_shim(bindir)
        _, name = _md_fixture(d)
        r = run([PY, f'{S}/regen_docx.py', d], env={'PATH': bindir})
        assert_(r.returncode == 0 and 'failed: 0' in r.stdout, 'pandoc 可用时转换链路不通', r)
        from docx import Document
        doc = Document(os.path.join(d, f'{name}.docx'))
        assert_(any('中文段落测试' in p.text for p in doc.paragraphs), 'docx 内容缺失', r)
        got = open(os.path.join(d, f'{name}.docx.locale')).read().strip()
        assert_(got == 'C.utf8|C.utf8', f'UTF-8 locale 未透传给 pandoc（实得 {got!r}）', r)

    # pypandoc 兜底档：pandoc 不在 PATH，但 pypandoc.get_pandoc_path() 能给出路径时必须可用。
    # README §7 声称 pip install pypandoc-binary 无需改 PATH 即可工作，这里把它做成常驻判据。
    with tempfile.TemporaryDirectory() as d:
        bindir = os.path.join(d, 'bin'); os.makedirs(bindir)
        shim = _make_pandoc_shim(bindir)
        stub = os.path.join(d, 'stub'); os.makedirs(stub)
        open(os.path.join(stub, 'pypandoc.py'), 'w', encoding='utf8').write(
            f'def get_pandoc_path():\n    return {shim!r}\n')
        nopath = os.path.join(d, 'nopath'); os.makedirs(nopath)
        _, name = _md_fixture(d)
        r = run([PY, f'{S}/regen_docx.py', d], env={'PATH': nopath, 'PYTHONPATH': stub})
        assert_(r.returncode == 0 and 'failed: 0' in r.stdout,
                'pandoc 不在 PATH 但 pypandoc 可解析时未走兜底路径', r)

    # 复核档：pandoc 转换"成功"但产物不是合法 docx → 脚本内部的 python-docx 复核必须抓到
    with tempfile.TemporaryDirectory() as d:
        bindir = os.path.join(d, 'bin'); os.makedirs(bindir)
        _make_pandoc_shim(bindir, corrupt=True)
        _md_fixture(d)
        r = run([PY, f'{S}/regen_docx.py', d], env={'PATH': bindir})
        assert_(r.returncode == 1 and 'failed: 1' in r.stdout and 'python-docx' in r.stdout,
                '损坏 docx 未被内部复核准出为失败（rc/计数/原因任一不符）', r)

    # 真 pandoc 端到端（本机有则跑，无则如实报跳过——不把"没跑"说成"跑过"）
    real = _regen.resolve_pandoc()
    if real:
        with tempfile.TemporaryDirectory() as d:
            _, name = _md_fixture(d)
            r = run([PY, f'{S}/regen_docx.py', d])
            assert_(r.returncode == 0 and 'failed: 0' in r.stdout, f'真 pandoc 端到端失败：{real}', r)
        print(f'PASS regen_docx（缺 pandoc 必红 fail-closed + 桩全链路 + 损坏 docx 复核 + 真 pandoc 端到端 @{real}）')
    else:
        print('PASS regen_docx（缺 pandoc 必红 fail-closed + 桩全链路 + 损坏 docx 复核）')
        print('     SKIP 真 pandoc 端到端：本机无 pandoc，装上后这一档自动启用；不把"没跑"说成"跑过"')


def test_check_figures_media_count():
    """C3：docx 嵌入图数 = figures 图数。这条曾只打印 MISMATCH 不影响退出码（实测 rc=0 放行）。"""
    try:
        from docx import Document
    except ImportError:
        print('SKIP check_figures C3 图数比对（本机无 python-docx，无法构造带图 docx）')
        return
    with tempfile.TemporaryDirectory() as d:
        fd = os.path.join(d, 'figures'); os.makedirs(fd)
        # 各图内容必须互不相同：python-docx 按图片字节哈希去重 media part，
        # 两张逐字节相同的图只会落 1 个 word/media/ 条目，那样 C3 比对就成了测夹具本身。
        for i in (1, 2):
            _line_figure(f'{fd}/图{i}.png', elements=i)

        def build(path, n_img):
            doc = Document()
            doc.add_paragraph('申请文件草稿')
            for i in range(1, n_img + 1):
                doc.add_picture(f'{fd}/图{i}.png')
            doc.save(path)

        # 必红：2 张附图只嵌 1 张 → 必须 rc=1 且报出 C3
        build(os.path.join(d, '缺图.docx'), 1)
        r = run([PY, f'{S}/check_figures.py', d])
        assert_(r.returncode == 1 and 'C3' in r.stdout,
                'docx 丢图未计入退出码（只打印不判红即放行）', r)

        # 必红：同一目录放两份申请文件草稿，图数不足的是第二份
        # （02_申请文件/ 常同时有发明/实用新型两份——只查第一份必须被抓到）
        os.remove(os.path.join(d, '缺图.docx'))
        build(os.path.join(d, 'a_齐全.docx'), 2)
        build(os.path.join(d, 'b_缺图.docx'), 1)
        r4 = run([PY, f'{S}/check_figures.py', d])
        assert_(r4.returncode == 1 and 'b_缺图' in r4.stdout and 'C3' in r4.stdout,
                '同目录第二份 docx 丢图未被逐个核对', r4)

        # 必红：打不开的 .docx 要计入违规——只打印"无法按 zip 打开"却不计数，
        # 等于给损坏交付件开绿灯。必须另起一个"其余全合规"的目录：
        # 上一版把坏件丢进还有 b_缺图 的目录，rc=1 由别的条款贡献，删掉计数的变异照样全绿。
        with tempfile.TemporaryDirectory() as d3:
            fd3 = os.path.join(d3, 'figures'); os.makedirs(fd3)
            for i in (1, 2):
                _line_figure(os.path.join(fd3, f'图{i}.png'), elements=i)
            dd3 = Document(); dd3.add_heading('说明书附图', level=1)
            for i in (1, 2):
                dd3.add_picture(os.path.join(fd3, f'图{i}.png'))
            dd3.save(os.path.join(d3, '齐全.docx'))
            open(os.path.join(d3, '坏件.docx'), 'wb').write(b'not a zip at all')
            r5 = run([PY, f'{S}/check_figures.py', d3])
            assert_(r5.returncode == 1 and '坏件.docx' in r5.stdout
                    and '无法按 zip' in r5.stdout,
                    '打不开的 docx 未计入违规或未说清成因', r5)
            os.remove(os.path.join(d3, '坏件.docx'))
            r6 = run([PY, f'{S}/check_figures.py', d3])
            assert_(r6.returncode == 0, '坏件移除后该目录仍未放行（前提不成立）', r6)

        # 必绿：全合规样本必须整条门禁放行（C1/C2/C3 同时满足）
        os.remove(os.path.join(d, 'b_缺图.docx'))
        build(os.path.join(d, '齐全.docx'), 2)
        r2 = run([PY, f'{S}/check_figures.py', d])
        assert_(r2.returncode == 0 and '-> OK' in r2.stdout, '图数齐全时误判违规', r2)

        # 边界：无 figures 目录时不参与比对，不得凭空判红
        with tempfile.TemporaryDirectory() as d2:
            build(os.path.join(d2, '无图目录.docx'), 0)
            r3 = run([PY, f'{S}/check_figures.py', d2])
            assert_(r3.returncode == 0, '无 figures 目录被判违规', r3)
    print('PASS check_figures C3（丢图必红 / 齐全必绿 / 无 figures 不误伤）')


IRON_TMPL = """# 专利技术交底书

## 2. 背景技术
{bg}

## 6. 权利要求建议稿
1. 一种腰部助力装置，包括躯干框架与髋关节驱动单元。
{claims}

## 7. 摘要建议稿
{abstract}

## 8. 检索关键词与 IPC 分类建议
A61F5/00
"""
IRON_OK_BG = ('现有技术 CN110404188A 公开了一种髋关节助力结构，与本案的区别在于载荷传递路径。\n'
              # R9 的合规侧：逐字句在这里**硬编码**而不是从判据常量取——取了常量，
              # 有人改判据串时合规夹具会跟着一起改，那条"改措辞即红"的断言就永远不红（R8 同例）。
              '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。')
IRON_OK_ABSTRACT = '本发明公开一种腰部助力外骨骼装置，涉及可穿戴设备技术领域，包括躯干框架与髋关节驱动单元。'


def _iron(bg=IRON_OK_BG, claims='', abstract=IRON_OK_ABSTRACT):
    return IRON_TMPL.format(bg=bg, claims=claims, abstract=abstract)


def test_check_iron_rules_docx():
    """交付物是 .docx：铁律必须也能读 docx 正文，并对读不出的情形说不。"""
    try:
        import docx  # noqa: F401  python-docx
    except ImportError:
        SKIPPED.append('check_iron_rules_docx')
        print('SKIP check_iron_rules_docx（本机无 python-docx，造不出 docx 夹具）')
        return
    import zipfile
    from docx import Document
    _sp = importlib.util.spec_from_file_location('cir_docx',
                                 os.path.join(S, 'check_iron_rules.py'))
    _cir_mod = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_cir_mod)

    with tempfile.TemporaryDirectory() as d:
        clean = os.path.join(d, '实用新型.docx')
        doc = Document()
        doc.add_heading('说明书摘要', level=2)
        doc.add_paragraph('本实用新型公开了一种脚手架减振节点，包括上夹板、下夹板与阻尼件。')
        doc.add_heading('具体实施方式', level=2)
        doc.add_paragraph('阻尼件采用橡胶层，硬度为邵氏 60A。')
        doc.save(clean)
        r = run([PY, f'{S}/check_iron_rules.py', clean])
        assert_(r.returncode == 0, f'合规 docx 被铁律判红: {show(r)}', r)

        bad = os.path.join(d, '带违规.docx')
        doc = Document()
        doc.add_heading('说明书摘要', level=2)
        doc.add_paragraph('本方案为业界首创。')
        doc.add_paragraph('阻尼件硬度 TODO 待定。')
        doc.save(bad)
        r = run([PY, f'{S}/check_iron_rules.py', bad])
        assert_(r.returncode == 1 and 'FAIL R1' in r.stdout,
                f'docx 内的禁用词未被 R1 抓到（说明根本没读进正文）: {show(r)}', r)
        assert_('FAIL R2a' in r.stdout, f'docx 内的裸 TODO 未被 R2a 抓到: {show(r)}', r)

        # 节标题还原必须是"有用的"：超 300 字摘要写进 docx，R4 要能按节判红。
        # 若 pStyle 映射失效，R4 只会因为找不到节而静默通过。
        over = os.path.join(d, '超长摘要.docx')
        doc = Document()
        doc.add_heading('说明书摘要', level=2)
        doc.add_paragraph('本实用新型公开了一种节点。' * 24)
        doc.save(over)
        r = run([PY, f'{S}/check_iron_rules.py', over])
        assert_(r.returncode == 1 and 'FAIL R4' in r.stdout,
                f'docx 的超 300 字摘要未被 R4 抓到（pStyle 还原没吃上力）: {show(r)}', r)

        # R9 的第二消费者：交付物是 Word 件，逐字查新声明这条判据不能只在 md 上开火。
        # 缺句必红、补上必绿——两头都测，否则"docx 里读不到节"也会让红那一档假绿。
        bgdoc = os.path.join(d, '缺声明.docx')
        doc = Document()
        doc.add_heading('背景技术', level=2)
        doc.add_paragraph('现有技术 CN110404188A 公开了一种减振节点。')
        doc.save(bgdoc)
        r = run([PY, f'{S}/check_iron_rules.py', bgdoc])
        assert_(r.returncode == 1 and 'FAIL R9' in r.stdout,
                f'docx 背景技术节缺逐字声明未被 R9 抓到: {show(r)}', r)
        doc.add_paragraph('以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。')
        doc.save(bgdoc)
        r = run([PY, f'{S}/check_iron_rules.py', bgdoc])
        assert_(r.returncode == 0 and 'FAIL R9' not in r.stdout and 'R9 未判' not in r.stdout,
                f'docx 补上逐字声明后 R9 未判绿（"没读到节"与"核过了"必须分得开）: {show(r)}', r)

        # R10 的第二消费者：交付物是 Word 件时，摘要里的宣传语同样要抓到。
        # 外观设计的「简要说明」也走同一通道——它是那一支唯一以"节"形态存在的法定件。
        promo = os.path.join(d, '宣传摘要.docx')
        doc = Document()
        doc.add_heading('说明书摘要', level=2)
        doc.add_paragraph('本发明公开一种装置，性价比极高。')
        doc.add_heading('简要说明', level=2)
        doc.add_paragraph('本外观设计产品的名称：手柄。销量第一。')
        doc.save(promo)
        r = run([PY, f'{S}/check_iron_rules.py', promo])
        assert_(r.returncode == 1 and 'FAIL R10' in r.stdout,
                f'docx 里的宣传语未被 R10 抓到（说明 pStyle 还原没喂到这一条）: {show(r)}', r)
        assert_('细则第二十六条' in r.stdout and '细则第三十一条' in r.stdout,
                f'docx 两节各引各的法源没分开: {show(r)}', r)

        # 三态：没有标题样式的 docx 找不到节 → 必须说"未核"，不能拿"违规 0"冒充核过
        naked = os.path.join(d, '无节标题.docx')
        doc = Document()
        doc.add_paragraph('本实用新型公开了一种节点，摘要字数无从判断。' * 20)
        doc.save(naked)
        r = run([PY, f'{S}/check_iron_rules.py', naked])
        assert_(r.returncode == 0 and '未识别到节标题样式' in r.stdout,
                f'无节标题的 docx 未报三态: {show(r)}', r)
        # 那句注记点名的判据清单也是自述：第 39 轮加了 R12/R13（都按节判），第 42 轮加了 R14、
        # 并把共用 `spec_doc_blocks` 的 R11 一起补进来（节标题还原不出来时**区域也是空的**，
        # 那两条同样从"判过"退成"没判"）。抄旧的清单就是把"看不见"说成"只影响那几条"。
        # ⚠ 这一格钉的是**现状**（现抄自门禁此刻的真读数），不是应然：今天没有任何机器-side 的尺子
        # 逼"新增的按节／按区域判的判据"把自己写进那句 note——已登记待办（把这份名单改成从源码现推：
        # 调用 `doc_region`／`spec_doc_blocks`／`section_body` 的那几条必须都在名单里）。
        assert_('→ R3/R4/R10/R11/R12/R13/R14（按节判的判据）未核' in r.stdout,
                f'docx 未核注记点名的判据清单不对: {show(r)}', r)

        # 损坏 docx 与带 DTD 的 document.xml 都必须 rc=2 说清成因，不折成"零违规"
        broken = os.path.join(d, '坏件.docx')
        with zipfile.ZipFile(broken, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>')
        r = run([PY, f'{S}/check_iron_rules.py', broken])
        assert_(r.returncode == 2 and '未做任何判定' in r.stdout,
                f'缺 document.xml 的 docx 未 fail-closed: {show(r)}', r)
        evil = os.path.join(d, '带DTD.docx')
        with zipfile.ZipFile(evil, 'w') as z:
            z.writestr('word/document.xml',
                       '<?xml version="1.0"?><!DOCTYPE w:document '
                       '[<!ENTITY a "首创">]>'
                       '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                       'wordprocessingml/2006/main"><w:p><w:r><w:t>&a;</w:t></w:r></w:p>'
                       '</w:document>')
        r = run([PY, f'{S}/check_iron_rules.py', evil])
        assert_(r.returncode == 2 and '拒绝解析' in r.stdout,
                f'含 DOCTYPE/ENTITY 声明的 document.xml 未被拒绝: {show(r)}', r)

        # --all 现在连 docx 一起收：整包复检不能只看 md。
        # 另起一个干净目录——上面那两个"故意坏"的 docx 会让门禁正确地 fail-closed，
        # 混在一起测就分不清是没收 docx 还是被坏件挡住了。
        # zip 炸弹闸：把上限临时收紧到 8 字节，正常小文件也必须被拒——
        # 不这么测的话，那道闸在这套夹具里从来没被真正走到过。
        saved = _cir_mod.MAX_XML_BYTES
        try:
            _cir_mod.MAX_XML_BYTES = 8
            try:
                _cir_mod.docx_text(clean)
                raise AssertionError('上限被越过却没有拒绝（闸失效）')
            except ValueError as e:
                assert_('压缩炸弹' in str(e), f'拒绝原因不对: {e}', None)
        finally:
            _cir_mod.MAX_XML_BYTES = saved

        with tempfile.TemporaryDirectory() as d2:
            shutil.copy(clean, os.path.join(d2, '实用新型.docx'))
            shutil.copy(bad, os.path.join(d2, '带违规.docx'))
            r = run([PY, f'{S}/check_iron_rules.py', d2, '--all'])
            assert_(r.returncode == 1 and '实用新型.docx' in r.stdout and '带违规.docx' in r.stdout,
                    f'--all 未递归收 docx: {show(r)}', r)
    print('PASS check_iron_rules_docx（docx 正文可读 + 节还原有牙 + 三种未判/拒绝路径）')



def test_docx_table_channel():
    """表格类门禁的 docx 通道：交付物是 Word 件，按列读的判据必须能在 .docx 上真判。

    这一档存在的直接理由：docx 抽取原先只按 w:p 逐段吐文本，Word 表格的单元格本身
    也是 w:p，于是整张对照表散成一串裸行——N1「有附图说明节却无表」会对每一份
    真交付件误判红；而把 .docx 当 md 直读更糟，UnicodeDecodeError 的退码 1
    在门禁语境里等于宣布"发现违规"。"""
    try:
        import docx  # noqa: F401  python-docx
    except ImportError:
        SKIPPED.append('docx_table_channel')
        print('SKIP docx_table_channel（本机无 python-docx，造不出带表格的 docx 夹具）')
        return
    from docx import Document

    def make(path, prose='所述底座 12 与支架 13 连接。', table=True, header_only=False,
             heading=True, cells=None):
        doc = Document()
        if heading:
            doc.add_heading('附图说明', level=2)
            doc.add_paragraph('图 1 为整体示意图；图 2 为底座剖视图。')
        doc.add_heading('具体实施方式', level=2)
        doc.add_paragraph(prose)
        doc.add_heading('图中标记说明', level=2)
        if table:
            rows = cells or [['标记', '名称', '所在图号'], ['12', '底座', '1、2'],
                             ['13', '支架', '1']]
            if header_only:
                rows = rows[:1]
            t = doc.add_table(rows=len(rows), cols=len(rows[0]))
            for i, row in enumerate(rows):
                for j, v in enumerate(row):
                    t.cell(i, j).text = v
        else:
            doc.add_paragraph('（这里本该有一张三列对照表）')
        doc.save(path)

    with tempfile.TemporaryDirectory() as d:
        ok = os.path.join(d, '说明书_包', '02_申请文件', '说明书.docx')
        os.makedirs(os.path.dirname(ok))
        make(ok)
        r = run([PY, f'{S}/check_figure_labels.py', ok])
        assert_(r.returncode == 0 and '实判判据 4 条' in r.stdout and '实核附图标记文书 1 份' in r.stdout,
                f'合规 docx 未被 N 真判（表格没还原成可按下标取列的行）: {show(r)}', r)

        # 单元格文字只许出现一次：既进管道行又散成裸行的话，正文对账会把自己和自己打架
        _sp = importlib.util.spec_from_file_location('cir_chan', f'{S}/check_iron_rules.py')
        _cir = importlib.util.module_from_spec(_sp)
        _sp.loader.exec_module(_cir)
        body = _cir.docx_text(ok)
        assert_('\n底座\n' not in body,
                f'表格单元格被重复吐成裸行（表格分支与段落分支没互斥）:\n{body}', None)
        assert_(body.count('| 12 | 底座 |') == 1, f'管道行重复或丢失:\n{body}', None)

        bad = os.path.join(d, 'bad.docx')
        make(bad, prose='所述底座 13 与支架连接。')
        r = run([PY, f'{S}/check_figure_labels.py', bad])
        assert_(r.returncode == 1 and '→ N3' in r.stdout,
                f'docx 里的标号错配未判红: {show(r)}', r)

        # 跨通道同判据：同样的内容写成 md 与写成 docx，结论必须一模一样
        md = os.path.join(d, 'same.md')
        open(md, 'w', encoding='utf8').write(
            '# 说明书\n## 附图说明\n图 1 为整体示意图；图 2 为底座剖视图。\n'
            '## 具体实施方式\n所述底座 13 与支架连接。\n'
            '## 图中标记说明\n| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
            '| 12 | 底座 | 1、2 |\n| 13 | 支架 | 1 |\n')
        rm = run([PY, f'{S}/check_figure_labels.py', md])
        assert_(rm.returncode == r.returncode == 1,
                f'同一内容两通道退码不一致（md={rm.returncode} docx={r.returncode}）', rm)
        got_md = [x for x in rm.stdout.splitlines() if '→ N3' in x]
        got_dx = [x for x in r.stdout.splitlines() if '→ N3' in x]
        assert_(len(got_md) == len(got_dx) == 1
                and got_md[0].split(':')[1].split('：', 1)[-1] == got_dx[0].split(':')[1].split('：', 1)[-1],
                f'两通道读到的不是同一条指控: md={got_md} docx={got_dx}', None)

        no_tbl = os.path.join(d, '无表.docx')
        make(no_tbl, table=False)
        r = run([PY, f'{S}/check_figure_labels.py', no_tbl])
        assert_(r.returncode == 1 and '却没有图中标记说明对照表' in r.stdout,
                f'docx 有附图说明节却无表未判红: {show(r)}', r)

        # 只有表头的 docx 表：必须仍然"看得见这张表"并走未判，而不是退化成"没有表"
        bare = os.path.join(d, '只有表头.docx')
        make(bare, header_only=True)
        r = run([PY, f'{S}/check_figure_labels.py', bare])
        assert_(r.returncode == 0 and '只有表头没有数据行' in r.stdout,
                f'单行 docx 表隐身成"无表"（分隔符没补上）: {show(r)}', r)

        # 整包 --all 也要收 docx：交付件通常 md+docx 成对，只扫 md 等于没扫交付物
        pkg = os.path.join(d, '说明书_包')
        r = run([PY, f'{S}/check_figure_labels.py', pkg, '--all'])
        assert_(r.returncode == 0 and '实核附图标记文书 1 份' in r.stdout,
                f'--all 未把 .docx 收进待检清单: {show(r)}', r)
        # 成对交付物里只有一侧脏：干净那侧不许洗绿，且红因必须按路径点名脏的那个文件
        dirty = os.path.join(pkg, '02_申请文件', '说明书_旧版.docx')
        make(dirty, prose='所述底座 13 与支架连接。')
        twin = os.path.join(pkg, '02_申请文件', '说明书.md')
        open(twin, 'w', encoding='utf8').write(
            '# 说明书\n## 附图说明\n图 1 为整体示意图。\n## 图中标记说明\n'
            '| 标记 | 名称 | 所在图号 |\n|---|---|---|\n| 12 | 底座 | 1 |\n')
        r = run([PY, f'{S}/check_figure_labels.py', pkg, '--all'])
        hits = [x for x in r.stdout.splitlines() if '→ N3' in x]
        assert_(r.returncode == 1 and len(hits) == 1 and '旧版.docx' in hits[0]
                and '实核附图标记文书 3 份' in r.stdout,
                f'成对交付物里 docx 侧的违规被 md 侧掩盖，或红因归错了文件: {show(r)}', r)

        # fail-closed 三档：外部落件（DTD/ENTITY）、坏 zip、超大解压 —— 全部 rc=2 说成因，
        # 绝不让 traceback 的退码 1 冒充"发现违规"
        evil = os.path.join(d, '恶意.docx')
        import shutil
        import zipfile
        shutil.copy(ok, evil)
        with zipfile.ZipFile(ok) as src, zipfile.ZipFile(evil, 'w') as dst:
            for n in src.namelist():
                b = src.read(n)
                if n == 'word/document.xml':
                    b = b.replace(b'<w:document', b'<!DOCTYPE w:document [<!ENTITY x "y">]>\n<w:document', 1)
                dst.writestr(n, b)
        r = run([PY, f'{S}/check_figure_labels.py', evil])
        assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'DOCTYPE' in r.stdout,
                f'含 DTD 声明的 docx 未按要求拒绝并说成因: {show(r)}', r)

        broken = os.path.join(d, '坏件.docx')
        open(broken, 'wb').write(b'not a zip at all')
        r = run([PY, f'{S}/check_figure_labels.py', broken])
        assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'Traceback' not in r.stderr,
                f'非 zip 的 .docx 抛出裸异常或退码不是 2: {show(r)} / {r.stderr[-200:]}', r)

        # 同样四把门里再验一把按表判的（G）：证明接线不是 N 独享
        greg = os.path.join(d, '法规_包', '05_法规与裁决', '裁决.docx')
        os.makedirs(os.path.dirname(greg))
        g = Document()
        g.add_heading('裁决总表', level=2)
        t = g.add_table(rows=2, cols=5)
        for i, row in enumerate([['冲突项', '结论', '依据', '约束', '生效范围'],
                                 ['表带厚度', '维持 2.4mm', 'EVT 复算 2.31mm', '投产后不得回退', '全部 SKU']]):
            for j, v in enumerate(row):
                t.cell(i, j).text = v
        g.save(greg)
        r = run([PY, f'{S}/check_regulatory.py', os.path.join(d, '法规_包'), '--all'])
        assert_(r.returncode == 0 and '实核法规文书 1 份' in r.stdout,
                f'G 门禁未能在 docx 裁决书上真判: {show(r)}', r)
        t2 = Document()
        t2.add_heading('裁决总表', level=2)
        t2b = t2.add_table(rows=2, cols=4)
        for i, row in enumerate([['冲突项', '结论', '依据', '约束'],
                                 ['表带厚度', '维持 2.4mm', 'EVT 复算 2.31mm', '投产后不得回退']]):
            for j, v in enumerate(row):
                t2b.cell(i, j).text = v
        t2.save(greg)
        r = run([PY, f'{S}/check_regulatory.py', os.path.join(d, '法规_包'), '--all'])
        assert_(r.returncode == 1 and '缺列' in r.stdout and '生效范围' in r.stdout,
                f'docx 裁决表掉一列却未判红: {show(r)}', r)

        # 四把按表判的门禁都要真吃到 docx：接线是同一处改动，但只测两把就当四把都通
        # 是不成立的推断——每一把的 --all 收集与读函数各自才说了算。
        # E 与 K 各写一条独立断言（不写成循环）：断言消息必须是字面量。
        # 常驻的 expect 存在性体检只能对着源文本核，f-string 里插 gate 会把
        # "哪把门禁没吃到 docx"这件事只剩在运行时，电池那条 expect 就成了查无实据的断言。
        efp = os.path.join(d, 'EVT_包', '04_EVT验证', '登记.docx')
        os.makedirs(os.path.dirname(efp), exist_ok=True)
        doc = Document()
        doc.add_heading('验证总表', level=2)
        rows = [['#', '设计项', '验证方法', '分析结论', '物理实测项', '判定'],
                ['1', '阻尼节点', '解析计算', '满足', '待物理实测', '✅']]
        te = doc.add_table(rows=len(rows), cols=len(rows[0]))
        for ra, row in enumerate(rows):
            for cb, v in enumerate(row):
                te.cell(ra, cb).text = v
        doc.save(efp)
        r = run([PY, f'{S}/check_evt.py', os.path.dirname(os.path.dirname(efp)), '--all'])
        assert_(r.returncode == 0 and '实核 EVT 文书 1 份' in r.stdout,
                'EVT 门禁未能在 docx 上真判（表格没吃到或 --all 收集漏了 .docx）', r)

        kfp = os.path.join(d, '补全_包', '03_设计补全', '登记.docx')
        os.makedirs(os.path.dirname(kfp), exist_ok=True)
        doc = Document()
        doc.add_heading('设计决策卡', level=2)
        rows = [['决策项', '可选方案', '选定方案', '依据', '约束条件', '风险与回退'],
                ['节点材料', '硅胶、TPE', '硅胶', '邵氏 60A 设计计算值', '成本上限', '回退 TPE']]
        tk = doc.add_table(rows=len(rows), cols=len(rows[0]))
        for ra2, row in enumerate(rows):
            for cb2, v in enumerate(row):
                tk.cell(ra2, cb2).text = v
        doc.save(kfp)
        r = run([PY, f'{S}/check_design_completion.py',
                 os.path.dirname(os.path.dirname(kfp)), '--all'])
        assert_(r.returncode == 0 and '实核设计补全文书 1 份' in r.stdout,
                '补全门禁未能在 docx 上真判（表格没吃到或 --all 收集漏了 .docx）', r)

    print('PASS docx_table_channel（表格还原 + 跨通道同判据 + 成对不互相洗绿 + 三档 fail-closed）')


def test_regen_docx_stale():
    """--check 陈旧检测：改过 md 忘了重转 must 红，且不需要 pandoc 就能问这一句。"""
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, '交底书.md')
        dx = os.path.join(d, '交底书.docx')
        open(md, 'w', encoding='utf8').write('# 交底书\n正文\n')
        open(dx, 'w', encoding='utf8').write('占位：陈旧检测只看 mtime，不需要真 docx')

        def check(root=None, env=None):
            cmd = [PY, f'{S}/regen_docx.py', root or d, '--check']
            return subprocess.run(cmd, capture_output=True, text=True,
                                  env=env or dict(os.environ))

        now = time.time()
        os.utime(dx, (now - 100, now - 100))          # docx 落后 100 秒
        os.utime(md, (now, now))
        r = check()
        assert_(r.returncode == 1 and '须重转' in r.stdout and '待重转 1 份' in r.stdout,
                f'md 比 docx 新却未判陈旧: {show(r)}', r)
        # 反向对照：刚重转完（docx 更新）必须放行，否则这条判据会在正常流程里常年假红
        os.utime(dx, (now + 10, now + 10))
        r2 = check()
        assert_(r2.returncode == 0 and '待重转 0 份' in r2.stdout,
                f'重转后仍被判陈旧: {show(r2)}', r2)
        # 只缺孪生 docx 的 md 不算陈旧（交付包里并非每份 md 都出 Word）
        only_md = os.path.join(d, 'README.md')
        open(only_md, 'w', encoding='utf8').write('# 包说明\n')
        r3 = check(d)
        assert_(r3.returncode == 0 and '成对文书 1 份' in r3.stdout,
                f'无孪生 docx 的 md 被算进配对: {show(r3)}', r3)
        # 不需要 pandoc：把 PATH 清空也必须答得上来（只读检查不该被转换依赖挡住）
        r4 = check(d, env={'PATH': '/nonexistent-dir', 'HOME': os.environ.get('HOME', '/')})
        assert_(r4.returncode == 0 and '成对文书 1 份' in r4.stdout,
                f'缺 pandoc 时 --check 未工作: {show(r4)}', r4)
        # 输入不对必须说成因并 rc=2
        r5 = check(md)
        assert_(r5.returncode == 2 and '--check 需要目录' in r5.stdout,
                f'--check 指到文件未说明成因: {show(r5)}', r5)
        # 完全没有成对文件 → 说"无从判陈旧"，但不是未判红也不是 rc=2
        with tempfile.TemporaryDirectory() as e:
            open(os.path.join(e, 'a.md'), 'w', encoding='utf8').write('# a\n')
            r6 = check(e)
            assert_(r6.returncode == 0 and '无从判陈旧' in r6.stdout,
                    f'无成对文件时读数不对: {show(r6)}', r6)
    # 双胞胎在列完目录之后、stat 之前消失（打包脚本与重转并发是真实场景）：
    # 读不到 mtime 必须按"待重转"收，不许把 FileNotFoundError 抛给调用方——
    # 那会让 --check 以退码 1 崩掉，而本仓的 1 专属"存在违规"，等于发一张假违规单。
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, 'a.md')
        dx = os.path.join(d, 'a.docx')
        open(md, 'w', encoding='utf8').write('# a\n')
        open(dx, 'wb').write(b'PK\x03\x04')
        t0 = time.time()
        os.utime(md, (t0 - 30, t0 - 30))
        os.utime(dx, (t0, t0))
        real = os.path.getmtime

        def blind(p):
            if str(p) == dx:
                raise FileNotFoundError(f'No such file or directory: {p}')
            return real(p)

        _regen.os.path.getmtime = blind
        try:
            stale, n = _regen.find_stale(d)
        except Exception as e:
            stale, n = None, f'{type(e).__name__}'
        finally:
            _regen.os.path.getmtime = real
        assert_(n == 1 and stale == [(md, dx)],
                f'孪生 docx 读不到 mtime 时未 fail-closed 成"待重转"（实得 {stale}/{n}）', None)
        # 对照组：不注入时同一对必须判"不陈旧"，否则上面那档是恒红
        stale2, n2 = _regen.find_stale(d)
        assert_(n2 == 1 and stale2 == [],
                f'对照组不成立（未注入却已判陈旧）: {stale2}', None)
    print('PASS regen_docx --check（陈旧必红/新转必绿/无孪生不算/不需 pandoc/rc=2/孪生读不到按待重转）')


def rule_span(src):
    """从门禁源码现取它定义的判据号（R1、R2a…→[1,2,…]）。
    `\\d{1,2}` 不可省成 `\\d`：那会把 R10 折成 1，于是"号有断档"这条断言从此看不见两位数区，
    自报区间也会被读成 R1–R9 而放行——与第 26 轮契约取号那次同源（当时是 [1-9] 漏了两位数）。
    `\\s*` 也不可省：R8 的 Finding( 与实参之间有换行，紧凑写法会把它整个漏掉。
    两份调用点（iron 档内、契约档内）共用这一把，不在两处各写一遍正则。"""
    return sorted({int(x) for x in re.findall(r"Finding\(\s*['\"]R(\d{1,2})", src)})


def test_check_iron_rules():
    """铁律门禁 R1–R13（区间由 rule_span 从脚本源码现推，见函数尾那行自述）：
    每条判据各自成对（注入即红 / 合规必绿），外加三态与输入不可用档。"""
    def gate(d, report=True, extra=None):
        cmd = [PY, f'{S}/check_iron_rules.py', os.path.join(d, '交底书.md')]
        if report:
            cmd += ['--search-report', os.path.join(d, '检索报告.md')]
        if extra:
            cmd += extra
        return run(cmd)

    def write(d, **kw):
        open(os.path.join(d, '交底书.md'), 'w', encoding='utf8').write(_iron(**kw))

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, '检索报告.md'), 'w', encoding='utf8').write(
            '# 检索报告\n已核验条目：CN110404188A。\n')

        # 基线：完全合规的稿件必须整条门禁放行（两条以上互斥判据同时红=永久红灯）
        write(d)
        r = gate(d)
        assert_(r.returncode == 0 and '违规 0' in r.stdout, '合规稿件未全绿', r)

        # R1 绝对化措辞
        write(d, bg=IRON_OK_BG + '\n本方案为业界首创。')
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R1' in r.stdout, 'R1「首创」未触发', r)
        write(d, bg=IRON_OK_BG + '\n控制模块在首次加载配置表时读取版本号。')
        r = gate(d)
        assert_(r.returncode == 0, 'R1 把正常语境里的「首次」误判违规', r)

        # R2 三条各配成对：非法写法必红、自家文档规定的式样一律不得误伤
        write(d, bg=IRON_OK_BG + '\n减振件硬度【待确认】。')
        r = gate(d)
        assert_(r.returncode == 0, 'R2b 把【待确认】式样判红（合法 待* 占位）', r)
        write(d, bg=IRON_OK_BG + '\n减振件硬度【TBD】。')
        r = gate(d)
        assert_(r.returncode == 1 and 'R2b' in r.stdout, 'R2b 未拦非 待*/占位 方括号标记', r)
        write(d, bg=IRON_OK_BG + '\n见下【待设计方确认：只有对象一项】。')
        r = gate(d)
        assert_(r.returncode == 1 and 'R2c' in r.stdout, 'R2c 未拦缺字段三字段占位', r)
        write(d, bg=IRON_OK_BG + '\n见下【待设计方确认：硬度值｜来料批次｜实测通过】。')
        r = gate(d)
        assert_(r.returncode == 0, 'R2c 误判合规三字段占位', r)
        write(d, bg=IRON_OK_BG + '\n此处 TODO 待补。')
        r = gate(d)
        assert_(r.returncode == 1 and 'R2a' in r.stdout, 'R2a 未拦裸 TODO', r)
        write(d, bg=IRON_OK_BG + '\n整机质量 4.2kg（设计目标 v3，TBD）。')
        r = gate(d)
        assert_(r.returncode == 0, 'R2 把 hard-rules §1 允许的 TBD 状态标注判红', r)
        # 自家 templates §0 规定的【待填写】不得误伤（曾实测误判，是门禁与模板打架）
        write(d, bg=IRON_OK_BG + '\n申请人（建议）：【待填写】；发明人：【占位】。')
        r = gate(d)
        assert_(r.returncode == 0, 'R2 误判 templates/companion-papers 规定的占位式样', r)

        # R3 权文内占位注释（真实形态是括号里带说明文字）
        write(d, claims='2. 根据权利要求 1 所述装置，其特征是设减振件（待确认：型号）。')
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R3' in r.stdout, 'R3 权文内占位注释未触发', r)
        write(d, claims='2. 根据权利要求 1 所述装置，其特征是设减振件。')
        r = gate(d)
        assert_(r.returncode == 0, 'R3 误判合规从权', r)

        # R4 摘要字数（含标点口径）——两个读数出自同一次计算
        over = '本发明公开一种腰部助力装置，' * 24
        n_over = len(re.sub(r'\s', '', over))
        assert_(n_over > 300, f'必红夹具仅 {n_over} 字，未过 300 限值，夹具失效')
        write(d, abstract=over)
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R4' in r.stdout and str(n_over) in r.stdout, 'R4 超限未触发', r)
        n_ok = len(re.sub(r'\s', '', IRON_OK_ABSTRACT))
        assert_(n_ok <= 300, f'合规夹具 {n_ok} 字已超限')
        write(d, abstract=IRON_OK_ABSTRACT)
        r = gate(d)
        assert_(r.returncode == 0, f'R4 把 {n_ok} 字合规摘要判红', r)

        # R5 公开号须属于检索报告（集合差）
        write(d, bg=IRON_OK_BG + ' 另见 CN999999999X。')
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R5' in r.stdout, 'R5 越界公开号未触发', r)
        write(d, bg=IRON_OK_BG + ' 另见 CN999999999X。')
        r = gate(d, report=False)
        assert_(r.returncode == 0 and 'R5 未核' in r.stdout,
                '缺检索报告时 R5 应报"未核"三态，不得折成违规也不得折成合规', r)

        # R6 商标/型号：给了清单才核，命中必红；不给报"未核"而不是凭空判红
        write(d, bg=IRON_OK_BG + ' 参见 XJ-200 型产品。')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '交底书.md'),
                 '--brand-terms', 'XJ-200'])
        assert_(r.returncode == 1 and 'FAIL R6' in r.stdout, 'R6 未命中已声明的型号', r)
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '交底书.md')])
        assert_(r.returncode == 0 and 'R6 未核' in r.stdout,
                '缺 --brand-terms 时 R6 应报"未核"，不得凭空判红或判合规', r)
        # 反向：标准/规格写法不得被当型号（不给清单时也只报未核，不自动判红）
        write(d, bg=IRON_OK_BG + ' 紧固件按 M5 螺纹、防护等级 IP67、材料 45#钢。')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '交底书.md')])
        assert_(r.returncode == 0 and 'R6 未核' in r.stdout, '标准规格写法被自动判红', r)

        # R7 发明名称字数：过 60 硬上限必红、≤25 必绿、字段缺失报未核。
        # 25<n≤60 那一档（法条允许、本仓只出提示）由常驻 test_r7_title_tiers 逐档钉，不在这里重复。
        named = '# 专利技术交底书\n\n## 0. 著录项目\n   - 发明名称：{t}\n'
        long_name = '一种' + '腰部助力外骨骼控制装置' * 6
        assert_(len(long_name) > 60, f'必红夹具仅 {len(long_name)} 字，未过硬上限')
        open(os.path.join(d, '命名.md'), 'w', encoding='utf8').write(named.format(t=long_name))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '命名.md')])
        assert_(r.returncode == 1 and 'FAIL R7' in r.stdout, 'R7 未拦超长发明名称', r)
        open(os.path.join(d, '命名.md'), 'w', encoding='utf8').write(
            named.format(t='一种腰部助力外骨骼装置'))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '命名.md')])
        assert_(r.returncode == 0, 'R7 误判合规发明名称', r)
        r = gate(d)
        assert_('R7 未核' in r.stdout, '无发明名称字段时 R7 未报未核', r)

        # R8 EVT 文书逐字投产总则（铁律 5）
        evt_dir = os.path.join(d, '04_EVT验证'); os.makedirs(evt_dir, exist_ok=True)
        evt = os.path.join(evt_dir, 'EVT报告.md')
        open(evt, 'w', encoding='utf8').write('# EVT 报告\n\n## 投产判定\n分析结论：满足判据。\n')
        r = run([PY, f'{S}/check_iron_rules.py', evt])
        assert_(r.returncode == 1 and 'FAIL R8' in r.stdout, 'R8 未拦缺逐字投产总则的 EVT 报告', r)
        open(evt, 'w', encoding='utf8').write(
            '# EVT 报告\n\n## 投产判定\n'
            '任何设计内容在对应物理实测全部通过前不得进入投产阶段；分析验证结论不构成投产依据。\n')
        r = run([PY, f'{S}/check_iron_rules.py', evt])
        assert_(r.returncode == 0, 'R8 误判已逐字写入投产总则的报告', r)
        r = gate(d)
        assert_('FAIL R8' not in r.stdout, '非 EVT 文书被 R8 误伤', r)

        # R9 背景技术节的逐字查新声明（hard-rules §2 第三条，第 22 轮普查认定它是
        # §1–§2 里唯一还剩下的"逐字承诺但无执行点"项，做法照 R8 的逐字串先例）。
        # 五档缺一不可：缺句必红／写在别处必红（作用域）／软换行必绿（归一）／
        # 没有本节必未判（骨架底稿那一档）／合规必绿由 IRON_OK_BG 那份夹具守。
        NOVELTY = '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。'
        write(d, bg='现有技术 CN110404188A 公开了一种髋关节助力结构，与本案的区别在于载荷传递路径。')
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R9' in r.stdout, 'R9 未拦缺逐字查新声明的稿件', r)
        # 只出现在别的节（这里塞进权利要求段）不算兑现——判据作用域必须是本节
        write(d)
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '交底书.md'),
                 '--search-report', os.path.join(d, '检索报告.md')])
        assert_(r.returncode == 0 and 'R9 未判' not in r.stdout,
                f'合规底稿被 R9 误伤，或该档其实是"未判"冒充的绿: {show(r)}', r)
        open(os.path.join(d, '别处.md'), 'w', encoding='utf8').write(
            _iron(bg='现有技术 CN110404188A 公开了一种髋关节助力结构。', claims=NOVELTY + '\n1. 一种装置，包括躯干框架。'))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '别处.md')])
        assert_(r.returncode == 1 and 'FAIL R9' in r.stdout,
                '声明句只出现在权利要求段也被当成"背景技术已声明"（作用域丢了）', r)
        # 软换行不是改措辞：把句子拆成两行仍须判绿
        open(os.path.join(d, '折行.md'), 'w', encoding='utf8').write(
            _iron(bg='现有技术 CN110404188A 公开了一种髋关节助力结构。\n'
                     '以上为背景技术的初步检索结果，正式申请前建议由专利代理\n机构进行专业查新检索。'))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '折行.md')])
        assert_(r.returncode == 0, f'被软换行折断的合规声明被 R9 误判: {show(r)}', r)
        # 一个标点之差必须仍然红：归一只许剥空白，标点与汉字是措辞的一部分
        open(os.path.join(d, '改标点.md'), 'w', encoding='utf8').write(
            _iron(bg='现有技术 CN110404188A 公开了一种髋关节助力结构。\n'
                     '以上为背景技术的初步检索结果、正式申请前建议由专利代理机构进行专业查新检索。'))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '改标点.md')])
        assert_(r.returncode == 1 and 'FAIL R9' in r.stdout, '逗号改成顿号后 R9 放行（逐字判据丢了）', r)
        # 没有背景技术节 ⇒ 未判，不折成违规也不折成合规（new_product_package 的说明书骨架就是这一档）
        open(os.path.join(d, '无本节.md'), 'w', encoding='utf8').write(
            '# 说明书\n\n## 附图说明\n\n图 1 为躯干框架结构示意图。\n')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '无本节.md')])
        assert_(r.returncode == 0 and 'R9 未判' in r.stdout,
                '缺背景技术节时 R9 未报未判（未判不得折成合规）', r)

        # R10：摘要／简要说明两节内的商业性宣传用语（细则 26 条、31 条各管一件文书）。
        # 六档：节内必红／合规摘要必绿／同一句写在别处不报（作用域）／技术撞车词不报（误伤面）／
        # 简要说明侧各引自己的法源／两张词表交集必须为空（否则同一件事被 R1 与 R10 各报一遍）。
        _isp = importlib.util.spec_from_file_location('cir_r10', f'{S}/check_iron_rules.py')
        _cir10 = importlib.util.module_from_spec(_isp)
        _isp.loader.exec_module(_cir10)
        overlap = set(_cir10.COMMERCIAL) & set(_cir10.BANNED_ALWAYS)
        assert_(not overlap,
                f'R10 词表与 R1 的 BANNED_ALWAYS 有重叠 {sorted(overlap)}：那四个词全文都报，'
                f'摘要节里再报一遍是同一件事占两个原告', r)
        assert_(len(_cir10.COMMERCIAL) >= 10,
                f'R10 词表只剩 {len(_cir10.COMMERCIAL)} 个词，这条判据基本等于没做', r)

        write(d, abstract='本发明公开一种腰部助力装置，性价比高，属业界标杆。')
        r = gate(d)
        assert_(r.returncode == 1 and 'FAIL R10' in r.stdout and '细则第二十六条' in r.stdout,
                f'摘要里的商业宣传语未被 R10 抓住（或没引对法源）: {show(r)}', r)
        write(d)
        r = gate(d)
        assert_(r.returncode == 0 and 'FAIL R10' not in r.stdout,
                f'合规摘要被 R10 误伤: {show(r)}', r)
        # 作用域：同一句写在权利要求段里不报（31/26 两句各管一件文书，不是全文禁词）
        open(os.path.join(d, '宣传在他节.md'), 'w', encoding='utf8').write(
            _iron(claims='1. 一种装置，性价比极高，属业界标杆。\n'))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '宣传在他节.md')])
        assert_(r.returncode == 0 and 'FAIL R10' not in r.stdout,
                f'R10 越出摘要／简要说明两节去管全文了: {show(r)}', r)
        # 撞车面：这些词在技术文本里是术语不是宣传语，全部排除在词表外（2026-09-27 全仓普查）
        open(os.path.join(d, '撞车词.md'), 'w', encoding='utf8').write(
            '# 说明书\n\n## 说明书摘要\n本发明第一方面提供一种装置，采用绝对式编码器，'
            '为顶级精度的最优实施例，终身学习框架免费开源，达到完美匹配。\n')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '撞车词.md')])
        assert_(r.returncode == 0 and 'FAIL R10' not in r.stdout,
                f'技术语义撞车的词被 R10 判红了: {show(r)}', r)
        # 简要说明侧：外观设计的这一件与摘要不同文书，法源必须引 31 条而不是 26 条
        open(os.path.join(d, '简要宣传.md'), 'w', encoding='utf8').write(
            '# 简要说明\n\n## 简要说明\n本外观设计产品的名称：手柄。销量第一，用户首选。\n')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '简要宣传.md')])
        assert_(r.returncode == 1 and 'FAIL R10' in r.stdout and '细则第三十一条' in r.stdout,
                f'简要说明里的宣传语未被 R10 抓住（或引成了摘要那条法源）: {show(r)}', r)
        # 「简要说明：…」写在正文里不算节（那是 C5 的触发词面，两张面分开判）。
        # 夹具刻意把标签单独成行、宣传语落在**下一行**：锚点若丢了井号，
        # 这一行会被当成节标题，下一行就成了"节内正文"，这把尺子会顺着 C5 的词面开火。
        # 标题用「文书」而不是「说明书」：R11/R10 的说明书面认 `# 说明书` 区域，
        # 标题写成说明书的话这句宣传语按 20 条三款就该红——那是另一档的事，不归这里测。
        open(os.path.join(d, '内联不算节.md'), 'w', encoding='utf8').write(
            '# 文书\n简要说明：\n本产品销量第一。\n')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '内联不算节.md')])
        assert_(r.returncode == 0 and 'FAIL R10' not in r.stdout,
                f'正文里的「简要说明：」内联写法被当成一个节来判了: {show(r)}', r)

        # R11＋R10 说明书面（细则 20 条三款，整份说明书区域）：双禁档各点各的、
        # 区域按《专利法实施细则》第二十条一款那五节的**节名**认，不锚标题层级
        # （扁平的 `##` 模板与嵌套的 `###` 小节都要开火，落点形状的成对档见下面的
        #  test_iron_spec_region_shapes）、引用语写在别的节不算、合规说明书零误报。
        # 缺席断言一律按本族**真输出形状**写：iron 族的违规行是 `FAIL <判据名> 路径:行: …`，
        # 违规行里没有 "→"。原先这两条写的是 `'→ R11' not in …`——按构造永真，
        # 等于第 37 轮那两条反向控制没验过。
        # （第 38 轮这条注释还写着"全份输出 grep -c → == 0"，第 39 轮起不成立：
        #  R12/R13 那句"未判"注记与 docx 那句"未核"注记都带 "→"。所以缺席断言只数违规行，
        #  见下面 R12／R13 那一档的 iron_hits()。）
        write(d, abstract=IRON_OK_ABSTRACT)
        SPEC_BAD = ('# 申请文件\n## 说明书\n### 技术领域\n可穿戴设备。\n### 具体实施方式\n'
                    '如权利要求1所述的装置，性价比极高。\n')
        open(os.path.join(d, 'specdoc.md'), 'w', encoding='utf8').write(SPEC_BAD)
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, 'specdoc.md')])
        assert_(r.returncode == 1 and 'R11 说明书引用语' in r.stdout
                and 'R10 说明书宣传用语' in r.stdout and '细则第二十条三款' in r.stdout,
                f'说明书里的引用语与宣传语未被 R11/R10 各点一条: {show(r)}', r)
        # 绝对坐标档：真行号由测试自己 enumerate 夹具文件算出，不抄门禁的读数——
        # 门禁报的行号与它差一行，这一档就红（Q 族同形状的一条在 test_check_claims 里）。
        real_spec = [i for i, ln in enumerate(SPEC_BAD.splitlines(), 1) if '如权利要求1所述' in ln]
        assert_(len(real_spec) == 1, f'夹具里"{real_spec}"处才算得出真行号，档位空转', None)
        hits = [ln for ln in r.stdout.splitlines() if 'R11 说明书引用语' in ln]
        assert_(len(hits) == 1 and f'specdoc.md:{real_spec[0]}:' in hits[0],
                f'R11 报的位点不是触发行（真行号 {real_spec[0]}）: {show(r)}', r)
        open(os.path.join(d, 'specok.md'), 'w', encoding='utf8').write(
            '# 申请文件\n## 说明书\n### 技术领域\n可穿戴设备。\n### 具体实施方式\n'
            '装置包括框架与弹臂。\n')
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, 'specok.md')])
        assert_(r.returncode == 0 and 'R11 说明书引用语' not in r.stdout
                and 'R10 说明书宣传用语' not in r.stdout,
                f'合规说明书被 R11/R10 误伤: {show(r)}', r)
        # 出域档必须配一份"同一批字节、只把节名换成区域内那一节"的正向档：
        # 没有它，"没开火"可能只是因为这份文书压根没进判据的域（读不到区域时它什么都不报）。
        # 出域那个名字用「权利要求书」而不是随便哪一节——"如权利要求1所述的…"在那一节是法条
        # **要求**的写法，区域把它吞进来就是把假阴性修成假阳性（第 39 轮区域按节名认之后，
        # 「### 技术领域」已在域内，这一档的对偶只能换成权利要求书／摘要／标记说明那一类节名）。
        SPEC_OUT = ('# 申请文件\n## 权利要求书\n如权利要求1所述的装置，性价比极高。\n'
                    '## 说明书\n装置包括框架。\n')
        open(os.path.join(d, 'specscope.md'), 'w', encoding='utf8').write(SPEC_OUT)
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, 'specscope.md')])
        assert_(r.returncode == 0 and 'R11 说明书引用语' not in r.stdout
                and 'R10 说明书宣传用语' not in r.stdout,
                f'「说明书」区域之外被 R11/R10 越域判了: {show(r)}', r)
        open(os.path.join(d, 'specscope_hit.md'), 'w', encoding='utf8').write(
            SPEC_OUT.replace('## 权利要求书', '## 具体实施方式', 1))
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, 'specscope_hit.md')])
        assert_(r.returncode == 1 and 'R11 说明书引用语' in r.stdout,
                f'出域档的前提不成立：同样这批字节把节名换成「具体实施方式」后也没开火，'
                f'那条"出域不判"是空转: {show(r)}', r)

        # ── R12／R13（《专利审查指南》2023 第二部分第二章 §2.2.6 与 §2.4，第 39 轮）──────────
        # 同一张「标记｜名称」对照表管三面三种括号方向：权利要求书**必须**把标记放进括号
        # （那一面归 check_claims 的 Q5）、具体实施方式**不得**加括号（R12）、
        # 摘要**应当**加括号（R13）。三面各配必红／必绿两档，外加"号集来自哪张表"这一档。
        # 缺席断言按 iron 族的**真输出形状**写。本轮真跑一次得到的原样一行（路径截长）：
        #   FAIL R13 摘要标记未加括号 /tmp/…/摘要标记裸写.md:3: 摘要里「支架3」的标记 3 没放进括号——…
        # 违规行里没有 "→"；上面第 38 轮那条注释"全份输出 grep -c → == 0"从本轮起**不成立**
        # （新加的"未判"注记自己就写着 `→ R12/R13 未判`），所以这里按违规行前缀数，
        # 并逐条钉"违规行自己不含 →"，不再拿整份输出说事。
        MARKS_TBL = ('## 图中标记说明\n| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
                     '| 2 | 锁扣本体 | 1 |\n| 3 | 支架 | 1 |\n| 4 | 弹性件 | 2 |\n')
        # 表外自由数字：3 是组数、5 是行程、2020 是年份、11 是步骤号。号集只认表里登记过的
        # 「名称↔号」对，把表外数字当标记就是把这两把尺子做成假红制造机（与 Q5 同一条防线）。
        NUM_DECOY = '共 3 组，行程 5mm，2020 年定型。'

        def wdoc(name, content):
            p = os.path.join(d, name + '.md')
            open(p, 'w', encoding='utf8').write(content)
            return p

        def iron_of(p):
            return run([PY, f'{S}/check_iron_rules.py', p])

        def iron_hits(out, rule):
            """本族违规行 = 以两个空格 + FAIL + 判据号开头的那些行（note 行不算）。"""
            return [ln for ln in out.splitlines() if ln.startswith(f'  FAIL {rule}')]

        def real_line(text, needle):
            """needle 在夹具里的**真 1-based 行号**，由测试自己数——不抄门禁的读数。"""
            got = [i for i, ln in enumerate(text.splitlines(), 1) if needle in ln]
            assert_(len(got) == 1, f'夹具不自洽：「{needle}」命中 {got} 行，这一档会空转', None)
            return got[0]

        # 合规合面档：摘要加括号、具体实施方式不加括号，两面各按各的方向写在同一份文书里。
        # 这一档必须全绿，它本身就是"两面的括号方向相反"的证据——哪一面把方向抄反，
        # 这里当场多出一条红（变异电池「R12 与 R13 方向互换」那一臂咬的就是它）。
        IRON_MARKS_OK = ('# 申请文件\n## 说明书摘要\n'
                         '本发明公开一种锁扣装置，包括支架（3）。' + NUM_DECOY + '\n'
                         '## 具体实施方式\n'
                         '支架3通过弹性件与锁扣本体2连接。' + NUM_DECOY + '\n' + MARKS_TBL)
        p = wdoc('两面合规', IRON_MARKS_OK)
        r = iron_of(p)
        assert_(r.returncode == 0 and not iron_hits(r.stdout, 'R12')
                and not iron_hits(r.stdout, 'R13'),
                f'两面各按各的方向写的合规档没能全绿（两面的括号方向相反，抄反哪一面都在这里红）: '
                f'{show(r)}', r)
        assert_('R12/R13 未判' not in r.stdout,
                f'包里明明有对照表却报"未判"，号集根本没读到那张表: {show(r)}', r)

        # R13 两面：摘要里裸写标记必红；写成括号式＋表外自由数字必绿
        R13_BAD = ('# 申请文件\n## 说明书摘要\n'
                   '本发明公开一种锁扣装置，包括支架3。' + NUM_DECOY + '\n' + MARKS_TBL)
        p = wdoc('摘要标记裸写', R13_BAD)
        r = iron_of(p)
        hits = iron_hits(r.stdout, 'R13')
        n13 = real_line(R13_BAD, '包括支架3。')
        assert_(r.returncode == 1 and len(hits) == 1,
                f'R13 摘要裸写标记那一档开火数不对（应为恰好一条）: {show(r)}', r)
        assert_(hits[0].startswith('  FAIL R13 摘要标记未加括号 ')
                and f'摘要标记裸写.md:{n13}:' in hits[0] and '→' not in hits[0],
                f'R13 的输出形状或位点不对（真行号 {n13}，形状该是 '
                f'"FAIL R13 摘要标记未加括号 路径:行: 成因"）: {show(r)}', r)
        assert_('指南 §2.4' in hits[0], f'R13 没把法源写到那一行上: {show(r)}', r)
        R13_OK = R13_BAD.replace('包括支架3。', '包括支架（3）。')
        p = wdoc('摘要标记加括号', R13_OK)
        r = iron_of(p)
        assert_(r.returncode == 0 and not iron_hits(r.stdout, 'R13'),
                f'摘要里已加括号的标记、或"共 3 组／5mm／2020 年"这类表外数字被 R13 判红了: '
                f'{show(r)}', r)

        # R12 两面：紧跟技术名称不加括号（＋表外数字）必绿；写成加括号必红。
        # 这一对刻意把**合规档排在必红档之前**（与上面 R13 那对的顺序相反），理由是：
        # 套件遇红即停，而"号集放宽"那支变异（丢掉"必须是表里登记过的名称↔号对"这根锚，
        # 任何括号数字都当标记）让必红档照样红、只是条数变多——若把必红档排在前面，
        # 那一臂的第一红就落在"开火数不对"上，读不出这把尺子已经越界咬到表外数字了。
        # 表外加括号的数字（步骤 11）也算假红：号集不认它，它就不是附图标记。
        R12_OK = ('# 申请文件\n## 具体实施方式\n'
                  '支架3通过弹性件与锁扣本体2连接。' + NUM_DECOY + '\n'
                  '上述步骤（11）中，锁扣本体先行到位。\n' + MARKS_TBL)
        p = wdoc('实施方式标记裸写', R12_OK)
        r = iron_of(p)
        assert_(r.returncode == 0 and not iron_hits(r.stdout, 'R12'),
                f'具体实施方式里不加括号的标记、或"（11）"这类表外加括号数字被 R12 判红了: '
                f'{show(r)}', r)
        R12_BAD = ('# 申请文件\n## 具体实施方式\n'
                   '支架（3）通过弹性件与锁扣本体2连接。' + NUM_DECOY + '\n' + MARKS_TBL)
        p = wdoc('实施方式标记加括号', R12_BAD)
        r = iron_of(p)
        hits = iron_hits(r.stdout, 'R12')
        n12 = real_line(R12_BAD, '支架（3）通过弹性件')
        assert_(r.returncode == 1 and len(hits) == 1,
                f'R12 具体实施方式加括号那一档开火数不对（应为恰好一条）: {show(r)}', r)
        assert_(hits[0].startswith('  FAIL R12 具体实施方式标记加括号 ')
                and f'实施方式标记加括号.md:{n12}:' in hits[0] and '→' not in hits[0],
                f'R12 的输出形状或位点不对（真行号 {n12}，形状该是 '
                f'"FAIL R12 具体实施方式标记加括号 路径:行: 成因"）: {show(r)}', r)
        assert_('指南 §2.2.6' in hits[0], f'R12 没把法源写到那一行上: {show(r)}', r)

        # 号集门：包内没有那张「标记｜名称」表 ⇒ 两条都未判（看不见不等于合规）；
        # 同一批违例文本配上表 ⇒ 立刻翻红。这一对才是"翻判决的是那张表、不是文字"的证据，
        # 只测前一半的话，"未判"可能只是判据压根没接线。
        BOTH_BAD = ('# 申请文件\n## 说明书摘要\n本发明公开一种锁扣装置，包括支架3。\n'
                    '## 具体实施方式\n支架（3）通过弹性件与锁扣本体2连接。\n')
        p = wdoc('无表违例', BOTH_BAD)
        r = iron_of(p)
        assert_(r.returncode == 0
                and 'R12/R13 未判（看不见不等于合规）' in r.stdout
                and not iron_hits(r.stdout, 'R12') and not iron_hits(r.stdout, 'R13'),
                f'包内没有对照表时 R12/R13 没走"未判"三态（红或静默都不对）: {show(r)}', r)
        BOTH_BAD_TBL = BOTH_BAD + MARKS_TBL
        p = wdoc('有表违例', BOTH_BAD_TBL)
        r = iron_of(p)
        h13, h12 = iron_hits(r.stdout, 'R13'), iron_hits(r.stdout, 'R12')
        assert_(r.returncode == 1 and len(h13) == 1 and len(h12) == 1,
                f'同一批违例文本配上对照表后 R12/R13 没各判一条（翻判决的该是那张表）: '
                f'{show(r)}', r)
        assert_(f'有表违例.md:{real_line(BOTH_BAD_TBL, "包括支架3。")}:' in h13[0]
                and f'有表违例.md:{real_line(BOTH_BAD_TBL, "支架（3）通过弹性件")}:' in h12[0],
                f'R12/R13 报的位点不是各自触发那一行的真号: {show(r)}', r)

        # 号集是**包级**事实：那张表常写在另一份文书的附图说明节里。
        # 两半都要钉：分两份扫 ⇒ 红；只扫摘要那份 ⇒ 未判。缺后一半的话，
        # "包级"可能只是"整包里恰好哪份都有表"的假象。
        pkg = os.path.join(d, '包级号集')
        os.makedirs(pkg, exist_ok=True)
        only_abs = '# 申请文件\n## 说明书摘要\n本发明公开一种锁扣装置，包括支架3。\n'
        open(os.path.join(pkg, '甲_摘要.md'), 'w', encoding='utf8').write(only_abs)
        open(os.path.join(pkg, '乙_对照表.md'), 'w', encoding='utf8').write('# 附图\n' + MARKS_TBL)
        r = run([PY, f'{S}/check_iron_rules.py', pkg, '--all'])
        hits = iron_hits(r.stdout, 'R13')
        assert_(r.returncode == 1 and len(hits) == 1
                and f'甲_摘要.md:{real_line(only_abs, "包括支架3。")}:' in hits[0],
                f'对照表写在另一份文书时 R13 没判红（号集不是包级事实，摘要侧永远看不见表）: '
                f'{show(r)}', r)
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(pkg, '甲_摘要.md')])
        assert_(r.returncode == 0 and 'R12/R13 未判' in r.stdout and not iron_hits(r.stdout, 'R13'),
                f'只扫摘要那份文书时该报"未判"（包级号集的另一半：单看这份确实看不见表）: '
                f'{show(r)}', r)

        # 作用域：R12 只吃「具体实施方式」区域、R13 只吃摘要区域。
        # 每张出域档都配一份"同一批字节、只把区域标题换掉"的入域正向档，
        # 否则"没开火"可能只是没进域（第 38 轮那条 R11 出域档就是这么补的正向对照）。
        R12_OUT = '# 申请文件\n## 技术领域\n支架（3）用于支撑锁扣本体。\n' + MARKS_TBL
        p = wdoc('加括号在技术领域', R12_OUT)
        r = iron_of(p)
        assert_(r.returncode == 0 and not iron_hits(r.stdout, 'R12'),
                f'「具体实施方式」区域之外的加括号标记被 R12 判了: {show(r)}', r)
        p = wdoc('加括号在实施方式', R12_OUT.replace('## 技术领域', '## 具体实施方式'))
        r = iron_of(p)
        assert_(r.returncode == 1 and len(iron_hits(r.stdout, 'R12')) == 1,
                f'出域档的前提不成立：同一批字节把标题换成「具体实施方式」后 R12 也没开火，'
                f'那条"出域不判"是空转: {show(r)}', r)
        R13_OUT = '# 申请文件\n## 权利要求书\n1. 一种锁扣装置，包括支架3。\n' + MARKS_TBL
        p = wdoc('裸标记在权利要求书', R13_OUT)
        r = iron_of(p)
        assert_(r.returncode == 0 and not iron_hits(r.stdout, 'R13'),
                f'权利要求书正文里的裸标记被 R13 判了（那一面的括号方向归 Q5 管）: {show(r)}', r)
        p = wdoc('裸标记在摘要', R13_OUT.replace('## 权利要求书', '## 说明书摘要'))
        r = iron_of(p)
        assert_(r.returncode == 1 and len(iron_hits(r.stdout, 'R13')) == 1,
                f'出域档的前提不成立：同一批字节把标题换成「说明书摘要」后 R13 也没开火，'
                f'那条"权要正文不判"是空转: {show(r)}', r)
        # "未判"提示只在文书真有那两个区域时才出：一节都没有 ⇒ 提示行本身成了噪声
        # （与 R10／R11"没有那一节就不适用"同口径，也是上面两档出域控制的前提）。
        p = wdoc('两面都不在', '# 申请文件\n## 技术领域\n装置包括支架与锁扣本体。\n')
        r = iron_of(p)
        assert_(r.returncode == 0 and 'R12/R13 未判' not in r.stdout,
                f'文书里既没有摘要也没有具体实施方式，却还是报了 R12/R13 的"未判"提示: '
                f'{show(r)}', r)

        # 门禁自报的规则区间必须与它实际定义的判据一致：总结行谎称 R1–R5 曾经无人核对，
        # 档位由脚本源码现推（不在此硬编码，否则两处各自漂移）
        irtxt = open(f'{S}/check_iron_rules.py', encoding='utf8').read()
        # 提取器自己的两档：两位数不许折成个位、断档不许被读成连续
        assert_(rule_span("Finding('R1 a')\nFinding('R10 b')\nFinding(\n    'R9 c')") == [1, 9, 10],
                'R 号提取器把两位数判据号读错了（R10 被折成 R1 那一类）', r)
        assert_(rule_span("Finding('R1 a')\nFinding('R3 b')") == [1, 3],
                'R 号提取器看不见断档，"号是否连续"那条断言是假的', r)
        assert_(rule_span("Finding('R1 a')") == [1], 'R 号提取器在最小样本上就不对', r)
        rnums = rule_span(irtxt)
        assert_(rnums == list(range(rnums[0], rnums[0] + len(rnums))) if rnums else False,
                f'判据 R 号推导有断档（说明推导正则漏读了某个 token）：{rnums}', r)
        claim = f'（规则 R{rnums[0]}–R{rnums[-1]}，'
        assert_(claim in r.stdout,
                f'门禁自报规则区间与实际判据 R1–R{rnums[-1]} 不一致：{claim}', r)

        # 输入不可用 → rc=2，不得静默判绿
        r = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '不存在.md')])
        assert_(r.returncode == 2 and '未做任何判定' in r.stdout, '文件缺失未 fail-closed', r)
    # --all 整包模式（README/SKILL 都写了它，就必须有断言消费，否则是"文档宣称未实测"）
    with tempfile.TemporaryDirectory() as d:
        for sub in ('01_交底书', '02_申请文件'):
            os.makedirs(os.path.join(d, sub))
        open(os.path.join(d, '检索报告.md'), 'w', encoding='utf8').write(
            '# 检索报告\nCN110404188A。\n')
        good = _iron()
        p1 = os.path.join(d, '01_交底书', '发明.md')
        p2 = os.path.join(d, '02_申请文件', '实用新型.md')
        open(p1, 'w', encoding='utf8').write(good)
        open(p2, 'w', encoding='utf8').write(good)
        r = run([PY, f'{S}/check_iron_rules.py', d, '--all',
                 '--search-report', os.path.join(d, '检索报告.md')])
        assert_(r.returncode == 0 and '合计违规 0' in r.stdout,
                '--all 下合规整包未全绿', r)
        assert_(p1 in r.stdout and p2 in r.stdout, '--all 未递归到子目录里的两份文书', r)

        # 违规放在第二层子目录：只有真递归才会被抓到（只扫顶层的写法会漏）
        open(p2, 'w', encoding='utf8').write(_iron(bg=IRON_OK_BG + '\n本方案填补空白。'))
        r = run([PY, f'{S}/check_iron_rules.py', d, '--all',
                 '--search-report', os.path.join(d, '检索报告.md')])
        assert_(r.returncode == 1 and '实用新型.md' in r.stdout and 'FAIL R1' in r.stdout,
                '--all 未抓到子目录内的违规', r)

        # --all 误用（指到文件）与空目录：rc=2 且必须说出原因，不许只给空列表
        r = run([PY, f'{S}/check_iron_rules.py', p1, '--all'])
        assert_(r.returncode == 2 and '--all 需要目录' in r.stdout,
                '--all 指向非目录时未说明原因', r)
        with tempfile.TemporaryDirectory() as empty:
            r = run([PY, f'{S}/check_iron_rules.py', empty, '--all'])
            assert_(r.returncode == 2 and '未找到待检文件' in r.stdout,
                    '--all 空目录未说明原因', r)
    # 这行自述曾长期硬写成 "R1–R8"（实际判据已到 R10）：清单型自述只能现算，
    # 抄一份就是一份会过期的假账（tooling-pitfalls §10 同条）。
    _rn = rule_span(open(f'{S}/check_iron_rules.py', encoding='utf8').read())
    print(f'PASS check_iron_rules（R{_rn[0]}–R{_rn[-1]} 各条成对必红必绿 + 三态 + rc=2 + --all 四档；'
          f'摘要 {n_ok}/{n_over} 字；R12/R13 三面括号方向各有正反档 + 号集门 + 包级号集 + '
          f'两张出域档都配了入域正向档）')


# ---------- R11／R10 说明书面：区域的"落点形状"夹具（模块级，探针与常驻档共用同一批字节） ----------

# 主理人 2026-09-28 复现用的那一句：真产物里【待填写】占位与引用语写在同一行，
# 一句话同时踩中细则第二十条三款的两条禁令（引用语 + 商业性宣传语），所以每档都要求两条各点一次。
SPECREG_SENT = '【待填写】如权利要求1所述的装置，性价比极高。'

# 生产扁平形状：与 `new_product_package.py`→`rebuild_package.py` 落盘的
# `02_申请文件/说明书_*.md` 逐节同形——摘要／权利要求书／说明书／五节／图中标记说明**全是 `##`**
# （本机 14 份真工件普查无一例外，另见下方"生产侧真工件"档现造一份）。
# 违规句落在 `## 具体实施方式` 底下：区域若按"止于下一个 ≤2 级标题"划，
# `## 说明书` 那块就只剩它底下那一行占位，这一档在改前 rc=0、零开火。
SPECREG_FLAT = '\n'.join([
    '# E2E 申请文件（说明书骨架）',
    '',
    '（骨架期对照表只有表头：N2–N4 报"未判"而不是判红，填了行才会被判。）',
    '',
    '## 说明书摘要',
    # 摘要里登记过的标记**必须**带括号（第 39 轮的 R13）——这份夹具是 R11/R10 的效力对照，
    # 要求"去掉那一句后整份干净"，所以摘要面自己得先按 R13 的写法摆好；
    # 具体实施方式那一面方向相反（R12 要求不加括号），两面的方向在这一份夹具里同时在场。
    '【待填写】本装置包括躯干框架（1）与锁扣本体（2）。',
    '## 权利要求书',
    # 越界捕手（第一只）：这一行**逐字含着 R11 的形状**「如权利要求1所述…」。扁平形状里
    # `## 权利要求书` 不是任何块的内部，所以区域只要肯吞到它外面去（例如退回"整篇都是区域"）
    # 这一档立刻开火。细则 20 条三款禁的是**说明书**里用这类引用语，权利要求之间的引用是
    # 22～25 条要求的东西，两张面各归各的判点，不许由 R11 一处判两边的写法。
    # 另一只捕手在下面"`# 说明书` 底下夹 `## 权利要求书`"那一档——`SPEC_REGION_STOP` 只在
    # "某个块的范围里出现 Stop 节名"时才起作用，那种罩法只有 1 级标题做得到，所以两档都要在。
    '【待填写】如权利要求1所述的装置，所述躯干框架与锁扣本体连接。',
    '## 说明书',
    '【待填写：骨架期占位，取自交底书】',
    '## 技术领域',
    '【待填写】可穿戴设备与人体外骨骼。',
    '## 背景技术',
    '【待填写：最接近的在先技术与本案区别特征】',
    '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。',
    '## 发明内容',
    '【待填写】',
    '## 附图说明',
    '（逐幅写：图 N 为……；N 从 1 起顺序编号，一幅一行）',
    '## 具体实施方式',
    SPECREG_SENT,
    '## 图中标记说明',
    '| 标记 | 名称 | 所在图号 |',
    '|---|---|---|',
    '| 1 | 躯干框架 | 图1 |',
]) + '\n'

# 第二处同名节：真产物里 `## 附图说明` 出现两次（一次模板占位、一次 rebuild 追加的真内容，
# 见 .codebuddy/attest/r69prod/说明书_E2E.md 的第 18 行与第 28 行）。
# 区域按节名认时只取第一处，等于这一整块又回到看不见的位置上。
SPECREG_FLAT_SECOND = SPECREG_FLAT + '\n'.join([
    '',
    '## 附图说明',
    '图1 为本装置主视图，图2 为锁扣处局部放大图。',
    SPECREG_SENT,
]) + '\n'

# 旧嵌套形状（`## 说明书` + `### 小节`）：第 39 轮之前唯一被走过的形态，改后必须照旧开火。
SPECREG_NESTED = '\n'.join([
    '# 申请文件',
    '## 说明书',
    '【待填写】本装置包括躯干框架。',
    '### 技术领域',
    '可穿戴设备。',
    '### 背景技术',
    '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。',
    '### 具体实施方式',
    SPECREG_SENT,
]) + '\n'

# 既没有「说明书」标题、也没有那五节任何一节的文书 ⇒ 区域为空 ⇒ 三态走"不适用"，
# 既不判红也不许新增一条"未判"噪声行。
SPECREG_NOREGION = '\n'.join([
    '# 检索关键词与 IPC 分类建议',
    'A61F5/00',
    SPECREG_SENT,
]) + '\n'


def _specreg_true_pos(text):
    """测试自己数出来的 1-based 真行号——位点断言的原点，绝不抄门禁读数。"""
    return [i for i, ln in enumerate(text.splitlines(), 1) if ln == SPECREG_SENT]


def _specreg_fired(out, tag):
    """从门禁输出里取某条判据报出的行号（iron 族真输出形状：`FAIL <判据名> 路径:行: 报文`）。
    只用它与 `_specreg_true_pos` 对账，不用它反推期望值。"""
    return [int(m.group(1)) for ln in out.splitlines() if tag in ln
            for m in [re.search(r':(\d+): ', ln)] if m]


def test_iron_spec_region_shapes():
    """R11／R10 说明书面**按落点形状**成对判：生产扁平／旧嵌套／越界节名静默／第二处同名节。

    第 39 轮的假阴性是"区域按标题层级划"造成的：生产模板把《专利法实施细则》第二十条一款那五节
    全写成 `##`，于是"止于下一个 ≤2 级标题"的说明书区域在生产包上只剩一行占位，
    R11 与 R10 说明书面在生产形态上基本不开火。修法把区域改成按**法条自己列举的节名**认，
    所以这里的档位必须两极配对：区域内那一节改名字即静默（防把假阴性修成假阳性），
    区域外的节名（权利要求书／说明书摘要／图中标记说明）必须静默（法条在那几件文书上另有判点）。
    另配一档"生产侧真工件"——手写夹具全绿时生产形态可能从没被走过，这是本仓的纪律。
    """
    def one(d, name, text):
        p = os.path.join(d, name)
        open(p, 'w', encoding='utf8').write(text)
        return run([PY, f'{S}/check_iron_rules.py', p])

    with tempfile.TemporaryDirectory() as d:
        # ① 生产扁平形状：`## 具体实施方式` 底下那句必须被 R11 与 R10 各点一条，位点=测试数出的那一行
        want = _specreg_true_pos(SPECREG_FLAT)
        assert_(len(want) == 1, f'夹具里违规句不止一处（{want}），这一档空转', None)
        r = one(d, '扁平.md', SPECREG_FLAT)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want
                and '细则第二十条三款' in r.stdout,
                f'生产扁平形状（五节全 `##`）里「## 具体实施方式」下那句未被 R11/R10 各点一条，'
                f'期望位点 {want} 且只此一处: {show(r)}', r)
        # ① 的效力对照：同一份字节补一份"合规版"必须整条门禁放行，
        # 否则"开火"可能来自夹具里别的既有违规（R2/R9 之类）而不是这一句。
        one(d, '扁平合规.md', SPECREG_FLAT.replace(SPECREG_SENT, '【待填写】装置包括框架与弹臂。'))
        r0 = run([PY, f'{S}/check_iron_rules.py', os.path.join(d, '扁平合规.md')])
        assert_(r0.returncode == 0, f'扁平夹具去掉那一句后并不干净，①的开火归因不成立: {show(r0)}', r0)

        # ② 旧嵌套形状照旧开火（修新不许忘旧），位点同样由测试自己数
        want2 = _specreg_true_pos(SPECREG_NESTED)
        r = one(d, '嵌套.md', SPECREG_NESTED)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want2
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want2,
                f'旧嵌套形状（`## 说明书` + `###` 小节）不再被 R11/R10 抓住，期望位点 {want2}: {show(r)}', r)
        # 既有射程不许因为"改按节名认"而缩掉：`##说明书`（井号后无空格）一直是
        # SPEC_DOC_HEAD 的 `\s*` 在认的，今天仍要在它底下开火。
        NOSPACE = '# 申请文件\n##说明书\n' + SPECREG_SENT + '\n'
        r = one(d, '无空格标题.md', NOSPACE)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == _specreg_true_pos(NOSPACE),
                f'无空格标题 `##说明书` 的既有射程丢了（期望位点 {_specreg_true_pos(NOSPACE)}）: {show(r)}', r)

        # ④ 违规句写在**第二处同名节**里必须开火：期望位点是两处（第一处同名节 + 第二处），
        # 只报第一处＝区域只并了第一次命中的块，等于第二处整块仍然看不见。
        want4 = _specreg_true_pos(SPECREG_FLAT_SECOND)
        assert_(len(want4) == 2, f'④ 夹具应当有两处同名节落点，实数 {want4}', None)
        r = one(d, '第二处同名节.md', SPECREG_FLAT_SECOND)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want4,
                f'第二处同名节（生产包里 `## 附图说明` 出现两次）里的违规句未被逐块报出，'
                f'期望 {want4}: {show(r)}', r)
        assert_(_specreg_fired(r.stdout, 'R10 说明书宣传用语') == want4,
                f'第二处同名节的宣传语未被 R10 说明书面逐块报出，期望 {want4}: {show(r)}', r)

        # ③ 同一批字节把节名换成区域外的节，必须**静默**（防把假阴性修成越界假红）。
        # 三份都只换标题那一行、正文一字不动：区域若"层级优先/见名就并"，这几档就会翻红。
        for sec in ('权利要求书', '说明书摘要', '图中标记说明', '说明书附图', '简要说明'):
            r = one(d, f'换名{sec}.md', SPECREG_FLAT.replace('## 具体实施方式', f'## {sec}'))
            assert_(not _specreg_fired(r.stdout, 'R11 说明书引用语')
                    and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                    f'节名换成「{sec}」后区域把它吞进来了（该节由别的判据按别的节判）: {show(r)}', r)
        # ③ 的正向对照：换回来的那一个节名（具体实施方式）就是①，见上——
        # 这里再补一条"换名只换了标题、正文没变"的自证，免得换名档把句子里的字也换掉了。
        assert_(SPECREG_SENT in SPECREG_FLAT.replace('## 具体实施方式', '## 权利要求书'),
                '③ 的夹具不是"同一批字节"：正文被一起换掉了', None)
        # 层级不救场的那一族：`# 说明书` 一级标题底下的 `## 权利要求书` 只能靠**节名**止住
        # （级数比它深的标题一律不停），所以这一档单独钉"区域看的是 SPEC_REGION_STOP 那份名单"。
        L1 = ('# 说明书\n本发明公开一种装置，包括躯干框架。\n## 权利要求书\n' + SPECREG_SENT + '\n'
              '## 具体实施方式\n装置包括框架与弹臂。\n')
        r = one(d, '一级说明书夹权要.md', L1)
        assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                f'「# 说明书」底下那一节「## 权利要求书」被并进区域了（越界假红）: {show(r)}', r)
        # 同一批字节只把那个节名换成区域内的「附图说明」必须开火，位点=测试自己数的第 4 行
        r = one(d, '一级说明书夹权要_hit.md', L1.replace('## 权利要求书', '## 附图说明'))
        assert_(r.returncode == 1 and _specreg_fired(r.stdout, 'R11 说明书引用语') == [4],
                f'换成「## 附图说明」后也没在它那一块里开火，上一条"权要不入域"是空转: {show(r)}', r)

        # 三态：既无「说明书」标题也无那五节 ⇒ 区域空 ⇒ 不判红，也不新增"未判"噪声行
        r = one(d, '无区域.md', SPECREG_NOREGION)
        assert_(r.returncode == 0
                and not [ln for ln in r.stdout.splitlines() if '说明书引用语' in ln
                         or '说明书宣传用语' in ln],
                f'区域为空时被折成违规、或新长出"未判"提示行: {show(r)}', r)
        # 同一批字节补一个区域内的节名 ⇒ 必须开火（没有这条，上面那条静默可能只是判据没接上）
        r = one(d, '无区域补节.md', SPECREG_NOREGION.replace(
            '# 检索关键词与 IPC 分类建议', '# 检索关键词与 IPC 分类建议\n## 技术领域'))
        assert_(r.returncode == 1 and 'R11 说明书引用语' in r.stdout,
                f'补上「## 技术领域」后仍不开火，上一条"区域为空不判"是空转: {show(r)}', r)

        # 共享常量的依赖方向：五节名的**定义**住在判据侧（check_iron_rules），
        # rebuild_package 从 `_cir` 取（反方向 `_load('rebuild_package')` 就是循环导入）。
        # 钉"同一个对象"而不是"相等"——两份各自可改的元组迟早分叉，等号看不见分叉。
        _rs = importlib.util.spec_from_file_location('rp_specreg', f'{S}/rebuild_package.py')
        rp = importlib.util.module_from_spec(_rs)
        _rs.loader.exec_module(rp)
        assert_(rp.SPEC_SECTIONS is rp._cir.SPEC_SECTIONS,
                'rebuild_package.SPEC_SECTIONS 不是 check_iron_rules 那份对象（有人另抄了一份，'
                '两端会各自漂移——生产侧五节与区域五节就不是同一件事了）', None)
        assert_(rp.SPEC_SECTIONS == ('技术领域', '背景技术', '发明内容', '附图说明', '具体实施方式'),
                f'五节名与《专利法实施细则》第二十条一款对不上: {rp.SPEC_SECTIONS}', None)
        # 区域函数自己也不许在函数体里另抄一份节名（那是同一处分叉的第二个入口），
        # 且判据侧那份字面量**只能有一处定义**——两处各写一遍就又是两份会各自漂移的清单。
        _isrc = open(f'{S}/check_iron_rules.py', encoding='utf8').read()
        assert_('def spec_doc_blocks' in _isrc, '区域函数不在了，R11/R10 说明书面靠什么划区域', None)
        _fn = _isrc.split('def spec_doc_blocks', 1)[1].split('\ndef ', 1)[0]
        assert_('SPEC_SECTIONS' in _fn, '区域函数没引用共享常量 SPEC_SECTIONS，它用的是哪份清单', None)
        _lits = [ln for ln in _isrc.splitlines() if ln.startswith('SPEC_SECTIONS = (')]
        assert_(len(_lits) == 1,
                f'判据侧的「SPEC_SECTIONS = (」字面量有 {len(_lits)} 处，'
                f'区域与 P12 判的就不是同一份清单了', None)

    # ---------- 生产侧真工件：手写夹具全绿不等于生产形态被走过 ----------
    # 生产真工件这一档的临时目录走系统 TMPDIR（不是仓库根）：`finally` 里会 rmtree，
    # 但中途被杀就会在仓库根留下未跟踪目录，把下一次『树干净』的断言弄成假红；
    # TMPDIR 里的残留不进跟踪面。
    work = tempfile.mkdtemp(prefix='specreg_prod_')
    try:
        pkg = os.path.join(work, 'SPECREG_专利交付包')
        r = run([PY, f'{S}/new_product_package.py', 'SPECREG', work])
        assert_(r.returncode == 0 and os.path.isdir(pkg), f'骨架生成失败: {show(r)}', r)
        spec = os.path.join(pkg, '02_申请文件', '说明书_SPECREG.md')
        assert_(os.path.isfile(spec), f'生产侧没落出 02_申请文件/说明书_*.md: {show(r)}', r)
        txt = open(spec, encoding='utf8').read()
        r = run([PY, f'{S}/check_iron_rules.py', spec])
        assert_(r.returncode == 0, f'生产骨架开箱即红，下面"注入即红"的归因不成立: {show(r)}', r)
        heads = [i for i, ln in enumerate(txt.splitlines(), 1) if ln.strip() == '## 具体实施方式']
        assert_(len(heads) == 1, f'真工件里「## 具体实施方式」标题数出 {heads} 处，档位空转', None)
        inj = '\n'.join(txt.splitlines()[:heads[0]] + [SPECREG_SENT]
                        + txt.splitlines()[heads[0]:]) + '\n'
        open(spec, 'w', encoding='utf8').write(inj)
        r = run([PY, f'{S}/check_iron_rules.py', spec])
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == [heads[0] + 1]
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == [heads[0] + 1],
                f'生产真工件的「## 具体实施方式」里塞违规句未被 R11 抓到，'
                f'期望位点 {heads[0] + 1}（测试自己数的行号）: {show(r)}', r)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print('PASS 说明书区域落点形状（生产扁平／旧嵌套／越界节名静默／第二处同名节／三态不折叠 '
          '+ 共享常量同对象 + 生产真工件开火）')


# ---------- Word 通道的区域形状档（第 41 轮）：md 那批落点形状在 .docx 上各配一份常驻件 ----------

# 为什么单开一档：md 面的 test_iron_spec_region_shapes 钉的是"区域按细则 20 条一款那五节的**节名**认"，
# 而 Word 包上同一件事要多穿一层还原——`docx_text()` 按 `w:pStyle` 把标题段还原成 `#` 行
# （`scripts/check_iron_rules.py:616-620` 那一支 `}pStyle`／`title` 的判断），
# `_head_split`/`spec_doc_blocks` 才认得出那些节名。
# 这一层一退化（样式名换了、还原步被删），Word 包上的 R11 与 R10 说明书面就**静默变成看不见**：
# 门禁照样打"违规 0"。第 40 轮只用四份手工取证件看过一次，没留常驻用例——这一档补的就是那一格。
#
# 每一项 = (kind, 级数, 文本)：'h' 走 `doc.add_heading(text, level=级数)`，'p' 走 `doc.add_paragraph(text)`。
# **一段就是展平后的一行**（docx_text 对每条 w:p 只吐一行：标题段前面拼 `#`×级数＋一个空格，正文段原样，
# 行尾一个换行），所以"第 k 个写入的段落"＝ docx_text 展平后的第 k 行——位点原点由**写入序**自己算
# （`_specreg_docx_pos`），不抄门禁打印的行号，也不借别的判据的读数（与 `_specreg_true_pos`／`qabs` 同形状）。
# 这批夹具**不放 Word 表格**：docx_text 的表格分支一张表要吐多行（表头之外还补一行分隔符），
# 写入序原点就不成立；表格通道另由 `test_docx_table_channel` 常驻，**格子里嵌的图仍是登记盲区**。
SPECREG_DOCX_FLAT = [
    ('h', 1, 'E2E 申请文件（说明书骨架）'),
    ('h', 2, '说明书摘要'),
    ('p', None, '【待填写】本装置包括躯干框架（1）与锁扣本体（2）。'),
    ('h', 2, '权利要求书'),
    # 与 md 那份 SPECREG_FLAT 同一只越界捕手：这一行逐字含着 R11 的形状，
    # 九个节同为 Heading 2 时它不该被任何块吞进来。
    ('p', None, '【待填写】如权利要求1所述的装置，所述躯干框架与锁扣本体连接。'),
    ('h', 2, '说明书'),
    ('p', None, '【待填写：骨架期占位，取自交底书】'),
    ('h', 2, '技术领域'),
    ('p', None, '【待填写】可穿戴设备与人体外骨骼。'),
    ('h', 2, '背景技术'),
    ('p', None, '【待填写：最接近的在先技术与本案区别特征】'),
    ('p', None, '以上为背景技术的初步检索结果，正式申请前建议由专利代理机构进行专业查新检索。'),
    ('h', 2, '发明内容'),
    ('p', None, '【待填写】'),
    ('h', 2, '附图说明'),
    ('p', None, '（逐幅写：图 N 为……；N 从 1 起顺序编号，一幅一行）'),
    ('h', 2, '具体实施方式'),
    ('p', None, SPECREG_SENT),
    ('h', 2, '图中标记说明'),
    ('p', None, '【待填写】标记与名称的对照见附表。'),
]
# 效力对照（档⑤）用的那一句合规正文：既不含引用语也不含宣传语，与 SPECREG_SENT 同长度量级。
SPECREG_DOCX_CLEAN_SENT = '【待填写】装置包括框架与弹臂。'
# 「# 说明书」罩（Heading 1）底下夹一节（Heading 2）——md 面那条"层级不救场"档的 Word 版：
# 罩比里面每一节都浅，`jlevel <= level` 那条一级标题规则**停不住任何东西**，
# 于是 `SPEC_REGION_STOP` 那份名单是唯一防线。上面扁平那批字节钉不到这一层。
SPECREG_DOCX_L1 = [
    ('h', 1, '说明书'),
    ('p', None, '本发明公开一种装置，包括躯干框架。'),
    ('h', 2, '权利要求书'),
    ('p', None, SPECREG_SENT),
    ('h', 2, '具体实施方式'),
    ('p', None, SPECREG_DOCX_CLEAN_SENT),
]


def _specreg_docx_rename(items, old, new):
    """只换某个**标题段**的文字，正文一个字不动——"同一批字节"这件事由它自己保证，不靠注释。"""
    return [(k, lv, new if (k == 'h' and t == old) else t) for k, lv, t in items]


def _specreg_docx_relevel(items, level):
    """把九个节的 Heading 2 全换成指定级数（文档标题那一行不动）：扁平与嵌套两种形状同源同字节。"""
    return [(k, (level if lv == 2 else lv), t) for k, lv, t in items]


def _specreg_docx_pos(items, sent=SPECREG_SENT):
    """位点原点＝段落写入序：违规句是第 k 个写入的段落，就是展平后的第 k 行（1-based）。"""
    return [i for i, (_kind, _lv, t) in enumerate(items, 1) if t == sent]


def _specreg_docx_diffs(a, b):
    """两份夹具之间不同的那几段——用来机械自证"出域档只换了标题、没顺手换正文"。"""
    return [(x, y) for x, y in zip(a, b) if x != y]


def _specreg_docx_save(path, items):
    """按写入序落一份真 .docx；段落数与写入项数不符 ⇒ 载体自己多塞了段，原点作废，当场拒。"""
    from docx import Document
    doc = Document()
    for kind, lv, text in items:
        if kind == 'h':
            doc.add_heading(text, level=lv)
        else:
            doc.add_paragraph(text)
    doc.save(path)
    assert_(len(doc.paragraphs) == len(items),
            f'python-docx 落盘的段落数 {len(doc.paragraphs)} 与写入项数 {len(items)} 不符，'
            f'"第 k 段＝第 k 行"的原点不再成立', None)
    return doc


def _specreg_docx_mapped(cir_mod, path, items, want):
    """原点自证（不是位点读数）：展平后**每段一行**（行数＝段数），且违规句真落在写入序那一行。
    位点期望值仍然只由 `_specreg_docx_pos` 从写入序算出，这里只核"原点成不成立"。"""
    lines = cir_mod.docx_text(path).splitlines()
    assert_(len(lines) == len(items),
            f'docx_text 把 {len(items)} 段展平成 {len(lines)} 行，第 k 段不再等于第 k 行，'
            f'写入序原点作废（是不是有表格分支混进来了）', None)
    for k in want:
        assert_(lines[k - 1] == SPECREG_SENT,
                f'写入序第 {k} 段应落在展平后的第 {k} 行，实得 {lines[k - 1]!r}', None)


def test_iron_spec_region_shapes_docx():
    """R11／R10 说明书面的**Word 通道**区域形状常驻档：五档成对（开火侧与静默侧各有对偶）。

    档位（违规句一律是模块级 `SPECREG_SENT`，一句话同时踩细则 20 条三款的两条禁令）：
      ① 九个节全 Heading 2（生产扁平形状），句在「具体实施方式」那节底下 ⇒ R11 与 R10 说明书面各点一条；
      ② 同一批字节只把九个节换成 Heading 3（嵌套形状）⇒ 照旧各点一条（修新不许忘旧）；
      ③ 同一批字节把那一节的**标题**换成「权利要求书」⇒ 零开火（法条在那一节**要求**这种引用语，
         并进来就是把假阴性修成假阳性）；「附图」／「说明书附图」同理各一档；
      ④ 「# 说明书」罩（Heading 1）底下夹「## 权利要求书」（Heading 2）⇒ 零开火，
         同一批字节换成「## 附图说明」⇒ 必须在同一行开火（没有这条对偶，④的静默可能只是判据没跑到）；
      ⑤ 效力对照：同一批字节把违规句换成合规正文 ⇒ **整条门禁 rc=0**，否则①的开火归因不成立；
      ⑥ 三态：既无「说明书」标题也无那五节 ⇒ 不判红、也不长出"未判"噪声行，补一个区域内的节名即开火。
    位点全部按绝对坐标判，原点由段落写入序现算；docx 表格与格子里嵌的图不在本档射程（见上面的夹具注）。
    """
    try:
        import docx  # noqa: F401  python-docx
    except ImportError:
        SKIPPED.append('iron_spec_region_shapes_docx')
        print('SKIP iron_spec_region_shapes_docx（本机无 python-docx，造不出 Word 区域形状夹具）'
              '——本档未跑过，不得计入通过')
        return
    _sp = importlib.util.spec_from_file_location('cir_specreg_docx',
                                                 os.path.join(S, 'check_iron_rules.py'))
    cir_mod = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(cir_mod)

    # 夹具形状自证：所谓"九节全 Heading 2"必须数得出来，抄在注释里不算。
    n_h2 = len([1 for k, lv, _t in SPECREG_DOCX_FLAT if k == 'h' and lv == 2])
    assert_(n_h2 == 9,
            f'Word 扁平夹具里 Heading 2 的节数是 {n_h2} 不是 9（细则 20 条一款那五节＋摘要/权要/'
            f'说明书/图中标记说明），这一档钉的形状已变', None)

    def one(d, name, items, want):
        p = os.path.join(d, name)
        _specreg_docx_save(p, items)
        _specreg_docx_mapped(cir_mod, p, items, want)
        return run([PY, f'{S}/check_iron_rules.py', p])

    with tempfile.TemporaryDirectory() as d:
        # ① 生产扁平形状（九节全 Heading 2）：句在「具体实施方式」底下，R11 与 R10 各点一条
        want = _specreg_docx_pos(SPECREG_DOCX_FLAT)
        assert_(len(want) == 1, f'① 夹具里违规句落点 {want} 不是恰好一处，这一档空转', None)
        r = one(d, '扁平.docx', SPECREG_DOCX_FLAT, want)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want
                and '细则第二十条三款' in r.stdout,
                f'Word 件九个节全 Heading 2（生产扁平形状）时「具体实施方式」底下那句未被 R11/R10 '
                f'各点一条，期望位点 {want}（段落写入序算出）且只此一处: {show(r)}', r)

        # ② 同一批字节换成 Heading 3 的嵌套形状：照旧各点一条，位点由同一支原点算出（不该漂）
        items3 = _specreg_docx_relevel(SPECREG_DOCX_FLAT, 3)
        want3 = _specreg_docx_pos(items3)
        assert_(want3 == want, f'② 只换了标题级数，落点却从 {want} 漂到 {want3}', None)
        r = one(d, '嵌套H3.docx', items3, want3)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want3
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want3,
                f'Word 件九个节换成 Heading 3 后不再被 R11/R10 各点一条（任一层级都认这件事在 '
                f'Word 通道上丢了），期望位点 {want3}: {show(r)}', r)

        # ③ 同一批字节只把那一节的**标题**换成出域节名 ⇒ 必须静默
        it_claims = _specreg_docx_rename(SPECREG_DOCX_FLAT, '具体实施方式', '权利要求书')
        diffs = _specreg_docx_diffs(SPECREG_DOCX_FLAT, it_claims)
        assert_(len(diffs) == 1 and diffs[0][0][0] == 'h'
                and diffs[0][0][2] == '具体实施方式' and diffs[0][1][2] == '权利要求书',
                f'③ 的夹具不是"同一批字节只换标题"，改动面 {len(diffs)} 处', None)
        r = one(d, '违规在权要.docx', it_claims, want)
        assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                f'Word 件扁平形状里「权利要求书」那一节的引用语被 R11/R10 说明书面判了'
                f'（细则 20 条三款禁的是说明书，权要里这类引用语是法条要求的写法）: {show(r)}', r)
        # ③ 的另外两个出域节名（附图那一件文书归专利法 27 条、摘要归细则 26 条，各有别的判点）
        for sec in ('附图', '说明书附图'):
            it = _specreg_docx_rename(SPECREG_DOCX_FLAT, '具体实施方式', sec)
            assert_(len(_specreg_docx_diffs(SPECREG_DOCX_FLAT, it)) == 1,
                    f'③/{sec} 的夹具改动面不止标题那一处', None)
            r = one(d, f'违规在{sec}.docx', it, want)
            assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                    and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                    f'Word 件里「{sec}」那一节被并进说明书区域了: {show(r)}', r)

        # ④ 「# 说明书」罩底下夹一节：级数救不了场，只有 `SPEC_REGION_STOP` 那份名单说话
        want_l1 = _specreg_docx_pos(SPECREG_DOCX_L1)
        assert_(len(want_l1) == 1, f'④ 夹具里违规句落点 {want_l1} 不是恰好一处，这一档空转', None)
        r = one(d, 'H1罩夹权要.docx', SPECREG_DOCX_L1, want_l1)
        assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                f'Word 件「# 说明书」罩底下那一节「## 权利要求书」被并进区域了（越界假红，那里用引用语是法条要求的写法）: {show(r)}', r)
        # ④ 的正向对偶：同一批字节只把那一节的标题换成**区域内**的「附图说明」⇒ 同一行必开火。
        # 没有这条，上面那条"静默"完全可能只是因为 Word 通道上整条判据根本没跑到。
        it_hit = _specreg_docx_rename(SPECREG_DOCX_L1, '权利要求书', '附图说明')
        assert_(len(_specreg_docx_diffs(SPECREG_DOCX_L1, it_hit)) == 1,
                '④ 的对偶改动面不止标题那一处', None)
        r = one(d, 'H1罩夹附图说明.docx', it_hit, want_l1)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want_l1
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want_l1,
                f'罩底下那节换成区域内的「附图说明」后也没在它那一块开火（期望位点 {want_l1}），'
                f'上一条"权要不入域"是空转: {show(r)}', r)
        # ④ 的另两个 Stop 名字在 Word 罩法下同样必须静默（名单里每一格都得说话，不只「权利要求书」）
        it_fatu = _specreg_docx_rename(SPECREG_DOCX_L1, '权利要求书', '说明书附图')
        r = one(d, 'H1罩夹说明书附图.docx', it_fatu, want_l1)
        assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                f'Word 件「# 说明书」罩底下那一节「## 说明书附图」被并进区域了（越界假红，'
                f'附图那一件归专利法第二十七条）: {show(r)}', r)
        it_fatu2 = _specreg_docx_rename(SPECREG_DOCX_L1, '权利要求书', '附图')
        r = one(d, 'H1罩夹附图.docx', it_fatu2, want_l1)
        assert_(r.returncode == 0 and not _specreg_fired(r.stdout, 'R11 说明书引用语')
                and not _specreg_fired(r.stdout, 'R10 说明书宣传用语'),
                f'Word 件「# 说明书」罩底下那一节「## 附图」被并进区域了（越界假红）: {show(r)}', r)

        # ⑤ 效力对照：同一批字节把违规句换成合规正文 ⇒ 整条门禁必须 rc=0。
        # 少了这一档，①／②那些"开火"可能来自夹具里别的既有违规（R2/R9/R13 之类），归因不成立。
        it_clean = [(k, lv, SPECREG_DOCX_CLEAN_SENT if t == SPECREG_SENT else t)
                    for k, lv, t in SPECREG_DOCX_FLAT]
        assert_(_specreg_docx_pos(it_clean) == [], '⑤ 的夹具里违规句没被换掉，效力对照空转', None)
        r = one(d, '扁平合规.docx', it_clean, [])
        assert_(r.returncode == 0,
                f'Word 扁平夹具把违规句换成合规正文后并不干净（rc 不为 0），'
                f'①②的开火归因不成立: {show(r)}', r)

        # ⑥ 三态：既无「说明书」标题也无那五节 ⇒ 区域为空 ⇒ 不判红、也不新增噪声行
        NONE = [('h', 1, '检索关键词与 IPC 分类建议'), ('p', None, 'A61F5/00'),
                ('p', None, SPECREG_SENT)]
        r = one(d, '无区域.docx', NONE, _specreg_docx_pos(NONE))
        assert_(r.returncode == 0
                and not [ln for ln in r.stdout.splitlines()
                         if '说明书引用语' in ln or '说明书宣传用语' in ln],
                f'Word 件区域为空时被折成违规、或新长出"未判"提示行: {show(r)}', r)
        # 同一批字节补一个区域内的节名（Heading 2 的「技术领域」）⇒ 必须开火，位点仍由写入序算
        NONE2 = [NONE[0], ('h', 2, '技术领域')] + NONE[1:]
        want6 = _specreg_docx_pos(NONE2)
        r = one(d, '无区域补节.docx', NONE2, want6)
        assert_(r.returncode == 1
                and _specreg_fired(r.stdout, 'R11 说明书引用语') == want6
                and _specreg_fired(r.stdout, 'R10 说明书宣传用语') == want6,
                f'Word 件补上「技术领域」后仍不在期望位点 {want6} 开火，'
                f'上一条"区域为空不判"是空转: {show(r)}', r)

    print('PASS 说明书区域落点形状·Word 通道（九节 Heading 2 扁平开火／Heading 3 嵌套开火／'
          '权利要求书与附图两类出域节名静默／H1 罩下 Stop 名单不吞权要＋同批字节正向对偶开火／'
          '合规效力对照 rc=0／区域为空三态不折叠；位点原点全部由段落写入序现算）')


def test_iron_r14_illustration():
    """R14 说明书文字部分不得有插图（《专利审查指南》2023 第一部分第一章 §4.2，PDF p25／印刷页 1-9）。

    法源逐字（本机留底 `.codebuddy/attest/zhinan2023_ahippc.txt:791-792`，在 `<<<PAGE25>>>` 之后、
    页眉「（1-9）21」之下）：「说明书文字部分可以有化学式、数学式或者表格，但不得有插图。」
    ⇒ 这一档要同时证三件事，缺一件就是拿合规形状冒充判据有牙：
      ① 开火面：md 图片语法与 `<img>` 两种形状，打在 `spec_doc_blocks()` 的**同一个区域**里
         （与 R11／R10 同一套区域、同一套逐块原点 `dstart + 1 + off`）；
      ② 豁免面是**结构上碰不到**、不是显式排掉：同一批字节换成化学式／数学式／表格行／"图 1"引用，
         整条门禁必须 rc=0——这一档既是豁免证明，也是①的开火归因对照（没有它，"开火"
         可能来自夹具里别的既有违规）；
      ③ Word 通道的**盲区不许折成合规**：`docx_text()` 只把段落里的图形对象折成一行，
         表格格子里嵌的图与页眉里的图它读不到 ⇒ zip 级 census>0 而文本面 0 命中时
         必须出那条"R14 未判"的 note，且退码仍是 0；段落里嵌图那条路必须真开火（证明未判行
         不是因为整条判据在 Word 上不说话）。
    另外两条纪律性断言：区域外不判（权利要求书那一面归 Q7、附图那一件本来就是放图的）；
    共享形状的定义只有一处（`check_claims.CLAIM_IMAGE is check_iron_rules.SPEC_IMAGE`，钉 identity 不钉相等）。
    位点一律绝对坐标：由本档自己 `enumerate` 夹具算出，不抄门禁行号。
    """
    IMG_MD = '![装置示意](图9.png)'
    IMG_HTML = '<img src="图9.png" alt="装置"/>'
    OK_BODY = ['正文里写 C₂H₅OH 与 F = m·a。', '| 部件 | 标记 |', '|---|---|', '| 躯干框架 | 1 |',
               '图 1 为本装置的整体示意。']

    def spec_md(img_line=None, section='具体实施方式'):
        body = ['# E2E 申请文件（说明书）', '', '## 说明书摘要', '【待填写】概要。', '',
                '## 权利要求书', '1. 一种锁扣装置，包括躯干框架。', '',
                '## 技术领域', '【待填写】可穿戴设备。', '',
                f'## {section}']
        if img_line is not None:
            body.append(img_line)
        body += OK_BODY
        return '\n'.join(body) + '\n'

    def one(d, name, text):
        p = os.path.join(d, name)
        open(p, 'w', encoding='utf8').write(text)
        return run([PY, f'{S}/check_iron_rules.py', p])

    def fired(out, tag='R14 说明书文字部分有插图'):
        return [int(m.group(1)) for ln in out.splitlines() if tag in ln
                for m in [re.search(r':(\d+): ', ln)] if m]

    with tempfile.TemporaryDirectory() as d:
        # ① 开火面：md 图片语法，位点＝测试自己数出来的那一行
        for label, img in (('md 图片语法', IMG_MD), ('内嵌 HTML img', IMG_HTML)):
            txt = spec_md(img)
            want = [i for i, ln in enumerate(txt.splitlines(), 1) if ln == img]
            assert_(len(want) == 1, f'{label} 夹具里图片行不止一处（{want}），这一档空转', None)
            r = one(d, f'r14_{label}.md', txt)
            assert_(r.returncode == 1 and fired(r.stdout) == want
                    and '不得有插图' in r.stdout and 'PDF p25' in r.stdout,
                    f'{label} 没被 R14 在它那一行开火（期望位点 {want}）: {show(r)}', r)
        # ② 豁免面：同一批字节不放图片形状，整条门禁必须干净
        r = one(d, 'r14_ok.md', spec_md(None))
        assert_(r.returncode == 0 and not fired(r.stdout),
                f'化学式／数学式／表格／"图N"引用被 R14 判红（法条明写允许的那一侧）: {show(r)}', r)
        # 围栏代码块不豁免：本轮量过的选择（区域内今天零命中），写出来只多一个静默口子
        fence = spec_md(None).replace('## 具体实施方式', '## 具体实施方式\n\n```text\n' + IMG_MD + '\n```')
        want_f = [i for i, ln in enumerate(fence.splitlines(), 1) if ln == IMG_MD]
        r = one(d, 'r14_fence.md', fence)
        assert_(r.returncode == 1 and fired(r.stdout) == want_f,
                f'图片形状藏进围栏代码块就从判据里消失了（期望仍在 {want_f} 开火）: {show(r)}', r)
        # ③ 区域外不判：同一行写在权利要求书／附图那两节底下
        for sec in ('权利要求书', '附图', '说明书附图', '图中标记说明'):
            r = one(d, f'r14_out_{sec}.md', spec_md(IMG_MD, section=sec))
            assert_(not fired(r.stdout),
                    f'图片行写在「{sec}」那一节却被 R14 判红（那一面另有判据或本就是放图的文书）: '
                    f'{show(r)}', r)
        # 三态：既无「说明书」标题也无那五节 ⇒ 不适用，不判红也不长未判噪声行
        NONE = '# 交底书\n\n## 一、技术方案\n' + IMG_MD + '\n'
        r = one(d, 'r14_noregion.md', NONE)
        # 缺席断言只数 R14 自己的两种行（违规行／未判行）。整份输出里 grep 'R14' 会被
        # 合计行那句自报区间「规则 R1–R14」挡成永假——本仓那条"缺席断言被门禁自己的复述挡"的老坑。
        assert_(r.returncode == 0 and not fired(r.stdout)
                and not [ln for ln in r.stdout.splitlines()
                         if ln.startswith('  FAIL R14') or 'R14 未判' in ln],
                f'区域为空时 R14 被折成违规或新长出提示行: {show(r)}', r)

        # 共享形状只有一处定义：权要那一族取的是同一个编译对象（两份正则迟早分叉）
        _ci = importlib.util.spec_from_file_location('cir_r14', f'{S}/check_iron_rules.py')
        cir_m = importlib.util.module_from_spec(_ci)
        _ci.loader.exec_module(cir_m)
        _cl = importlib.util.spec_from_file_location('ccl_r14', f'{S}/check_claims.py')
        clm = importlib.util.module_from_spec(_cl)
        _cl.loader.exec_module(clm)
        assert_(clm.CLAIM_IMAGE is cir_m.SPEC_IMAGE,
                'check_claims 的图片形状不是 check_iron_rules 那份对象（有人另抄了一份正则）', None)

    # ---------- Word 通道：段落嵌图必须开火，格子里／页眉里的嵌图必须走未判 ----------
    try:
        import docx  # noqa: F401  python-docx
    except ImportError:
        SKIPPED.append('iron_r14_illustration_docx')
        print('PASS R14 插图（md 两形状开火／豁免面 rc=0／围栏不豁免／区域外三档静默／区域为空不判 '
              '+ 共享形状同一对象；docx 档未跑）')
        return

    def png_bytes():
        """自己铸一张 2×2 白底 PNG（纯标准库）。matplotlib 本机可能没有，
        而这一档的前提是"文件里真有一个图形部件"，不能拿假字节糊。"""
        import struct
        import zlib
        w = h = 2
        raw = b''.join(b'\x00' + b'\xff' * (w * 3) for _ in range(h))

        def chunk(tag, data):
            c = struct.pack('>I', len(data)) + tag + data
            return c + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
        return (b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 2, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw, 9))
                + chunk(b'IEND', b''))

    def wdoc(d, name, build):
        p = os.path.join(d, name)
        doc = docx.Document()
        build(doc, png_bytes())
        doc.save(p)
        return p

    def heading(doc, text, level):
        doc.add_heading(text, level=level)

    with tempfile.TemporaryDirectory() as d:
        png = os.path.join(d, '图9.png')
        open(png, 'wb').write(png_bytes())

        # 段落里嵌图：docx_text 折成一行 ⇒ R14 必须开火（这条同时证明下面那条未判行不是"整条判据在 Word 上沉默"）
        def build_para(doc, _b):
            heading(doc, '说明书', 2)
            heading(doc, '具体实施方式', 2)
            doc.add_paragraph('正文。')
            doc.add_paragraph().add_run().add_picture(png)
        p1 = wdoc(d, '段落嵌图.docx', build_para)
        r = run([PY, f'{S}/check_iron_rules.py', p1])
        body = [ln for ln in r.stdout.splitlines() if 'R14 说明书文字部分有插图' in ln]
        assert_(r.returncode == 1 and len(body) == 1 and 'docx-embedded-object' in body[0],
                f'Word 段落里嵌的图没被 R14 开火（折算行没进区域？）: {show(r)}', r)
        assert_('R14 未判' not in r.stdout,
                f'文本面已经开火了还补一条"未判"（同一份文书两个口径同时说话）: {show(r)}', r)

        # 表格格子里嵌图：文本面看不见 ⇒ 必须出未判 note，退码仍是 0
        def build_cell(doc, _b):
            heading(doc, '说明书', 2)
            heading(doc, '具体实施方式', 2)
            tbl = doc.add_table(rows=1, cols=2)
            tbl.cell(0, 0).text = '部件'
            tbl.cell(0, 1).text = '示意'
            tbl.cell(0, 1).paragraphs[0].add_run().add_picture(png)
        p2 = wdoc(d, '格子里嵌图.docx', build_cell)
        r = run([PY, f'{S}/check_iron_rules.py', p2])
        assert_(r.returncode == 0 and not fired(r.stdout)
                and any('R14 未判' in ln and '表格格' in ln for ln in r.stdout.splitlines()),
                f'格子里嵌的图被读成合规（该出"R14 未判"的 note）: {show(r)}', r)

        # census 自己也得有牙：一份纯文字 Word 件不许冒出未判行（否则上面那条"未判"可能是恒真）
        def build_clean(doc, _b):
            heading(doc, '说明书', 2)
            heading(doc, '具体实施方式', 2)
            doc.add_paragraph('正文只有文字。')
        p3 = wdoc(d, '纯文字.docx', build_clean)
        r = run([PY, f'{S}/check_iron_rules.py', p3])
        assert_(r.returncode == 0 and not any('R14 未判' in ln for ln in r.stdout.splitlines()),
                f'纯文字 Word 件也报"R14 未判"（census 恒正 ⇒ 那条未判行是假信号）: {show(r)}', r)

    # ---------- 生产侧真工件：骨架开箱必须干净，注入即开火 ----------
    work = tempfile.mkdtemp(prefix='r14_prod_')
    try:
        pkg = os.path.join(work, 'R14_专利交付包')
        r = run([PY, f'{S}/new_product_package.py', 'R14', work])
        assert_(r.returncode == 0 and os.path.isdir(pkg), f'骨架生成失败: {show(r)}', r)
        spec = os.path.join(pkg, '02_申请文件', '说明书_R14.md')
        assert_(os.path.isfile(spec), f'生产侧没落出 02_申请文件/说明书_*.md: {show(r)}', r)
        r = run([PY, f'{S}/check_iron_rules.py', spec])
        assert_(r.returncode == 0 and not fired(r.stdout),
                f'生产骨架开箱即被 R14 判红（豁免面或区域划错了）: {show(r)}', r)
        txt = open(spec, encoding='utf8').read()
        heads = [i for i, ln in enumerate(txt.splitlines(), 1) if ln.strip() == '## 具体实施方式']
        assert_(len(heads) == 1, f'真工件里「## 具体实施方式」数出 {heads} 处，这一档空转', None)
        inj = '\n'.join(txt.splitlines()[:heads[0]] + [IMG_MD] + txt.splitlines()[heads[0]:]) + '\n'
        open(spec, 'w', encoding='utf8').write(inj)
        r = run([PY, f'{S}/check_iron_rules.py', spec])
        assert_(r.returncode == 1 and fired(r.stdout) == [heads[0] + 1],
                f'真工件注入的图片行未在期望位点 {heads[0] + 1} 开火: {show(r)}', r)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print('PASS R14 插图（md 两形状开火＋位点自算／化学式·数学式·表格·图N 引用 rc=0／围栏不豁免／'
          '区域外三档静默＋区域为空不判／Word 段落嵌图开火·格子嵌图走未判·纯文字不误报未判／'
          '生产真工件开箱干净且注入即红／SPEC_IMAGE 与 CLAIM_IMAGE 同一对象）')


def test_r7_title_tiers():
    """R7 发明名称字数的三档判决：把法条明确允许的那一侧从"退回修订"里救出来。

    法源是《专利审查指南》（2023）第一部分第一章 §4.1.1，逐字一句：
    「发明名称一般不得超过 25 个字，必要时可不受此限，但也不得超过 60 个字。」
    （本机留底 .codebuddy/attest/zhinan2023_ahippc.txt:629-630，该句位于 <<<PAGE 21>>> 之后、
    页标行「（1-5） 17」之下，即 PDF p21／印刷页 1-5）⇒ 25 是**软**上限、60 才是**硬**上限。
    旧实现把 25 当硬上限，26 字就 rc=1，而 60/61 这根轴根本没实现过。

    档位形状：两根轴分别钉——25/26 与 60/61 各配"合规侧静默 + 违规侧开火"的成对档。
    缺席断言一律按 iron 族的真输出形状写（违规行 `  FAIL <判据名> 路径:行: 成因 -> 摘句`、
    提示行 `  note 路径: 成因`）：`'R7' not in stdout` 那种会被自家未核行挡掉的永真断言不算断言。
    位点由本档自己 enumerate 夹具行算出，不抄门禁读数。
    """
    def named_md(dirpath, fname, title):
        """写一份只有一行发明名称的交底书，返回 (路径, 本档自己数出的 1-based 行号)。"""
        lines = ['# 专利技术交底书', '', '## 0. 著录项目', f'   - 发明名称：{title}', '']
        p = os.path.join(dirpath, fname)
        with open(p, 'w', encoding='utf8') as fobj:
            fobj.write('\n'.join(lines) + '\n')
        ln = next(i for i, txt in enumerate(lines, 1) if txt.lstrip().startswith('- 发明名称'))
        return p, ln

    def r7_lines(r):
        """按本族真输出形状把 R7 的违规行／提示行各挑出来（未核行两条都不算）。"""
        fails = [l for l in r.stdout.splitlines() if l.startswith('  FAIL R7')]
        notes = [l for l in r.stdout.splitlines()
                 if l.startswith('  note ') and '软上限' in l]
        return fails, notes

    with tempfile.TemporaryDirectory() as d:
        for n, expect in ((25, 'silent'), (26, 'note'), (60, 'note'), (61, 'fail')):
            title = '锁' * n
            assert_(len(re.sub(r'\s', '', title)) == n, f'夹具自数 {n} 字不成立')
            p, ln = named_md(d, f'命名{n}.md', title)
            r = run([PY, f'{S}/check_iron_rules.py', p])
            fails, notes = r7_lines(r)
            if expect == 'silent':
                assert_(r.returncode == 0 and not fails and not notes
                        and 'R7 未核' not in r.stdout,
                        f'{n} 字（≤{n} 即房内口径内）该整条静默，实得 rc={r.returncode} '
                        f'FAIL={fails} note={notes}', r)
            elif expect == 'note':
                assert_(r.returncode == 0 and not fails,
                        f'{n} 字落在指南允许的 25<n≤60 一侧却被判红（硬上限被退回 {n} 或 25）：'
                        f'FAIL={fails}', r)
                assert_(len(notes) == 1 and f'{n} 字' in notes[0] and '60' in notes[0],
                        f'{n} 字这一档没出"只提示不判红"的那一行（软硬两档没分开，'
                        f'或 60 那档整个关掉）: {notes}', r)
            else:
                assert_(r.returncode == 1 and len(fails) == 1,
                        f'{n} 字（>60 硬上限）该判红，实得 rc={r.returncode} FAIL={fails}', r)
                m = re.search(re.escape(p) + r':(\d+):', fails[0])
                assert_(m and int(m.group(1)) == ln,
                        f'R7 位点不对：判据给「{fails[0]}」，本档自己数到第 {ln} 行', r)
                assert_(f'{n} 字' in fails[0] and '60' in fails[0] and '审查指南' in fails[0],
                        f'硬上限的违规文案没点出 60 与法源：{fails[0]}', r)

        # 三态不许被新提示行折叠：没有那一行 → 仍是「R7 未核」，既不折成违规也不折成"核过了"
        p_missing = os.path.join(d, '无字段.md')
        with open(p_missing, 'w', encoding='utf8') as fobj:
            fobj.write('# 专利技术交底书\n\n## 0. 著录项目\n   - 申请人：某单位\n')
        r = run([PY, f'{S}/check_iron_rules.py', p_missing])
        fails, notes = r7_lines(r)
        assert_(r.returncode == 0 and '未找到「发明名称：」字段，R7 未核' in r.stdout
                and not fails and not notes,
                f'缺字段时的 R7 未核三态被改动（提示行/违规行不该出现）: FAIL={fails} note={notes}', r)

        # docx 通道：R7 认的那一行是正文段落，与节标题还原无关，Word 件上必须照判
        try:
            from docx import Document
        except ImportError:
            SKIPPED.append('r7_title_tiers_docx')
            print('  SKIP r7_title_tiers_docx（本机无 python-docx，造不出 Word 夹具）')
            print('PASS r7_title_tiers（md 两根轴四档成对 + 未核三态；docx 档未跑）')
            return
        for n, expect in ((26, 'note'), (61, 'fail')):
            paras = ['专利技术交底书', f'   - 发明名称：{"锁" * n}', '正文：一种装置。']
            dx = os.path.join(d, f'命名{n}.docx')
            doc = Document()
            for txt in paras:
                doc.add_paragraph(txt)
            doc.save(dx)
            # 段落一支一段一行 → 本档按自己塞进去的段落序数出抽取文本的行号
            ln = next(i for i, txt in enumerate(paras, 1) if '发明名称' in txt)
            r = run([PY, f'{S}/check_iron_rules.py', dx])
            fails, notes = r7_lines(r)
            if expect == 'note':
                assert_(r.returncode == 0 and not fails and len(notes) == 1 and f'{n} 字' in notes[0],
                        f'docx 通道上 {n} 字（法条允许侧）没按"只提示不判红"判：'
                        f'rc={r.returncode} FAIL={fails} note={notes}', r)
            else:
                assert_(r.returncode == 1 and len(fails) == 1,
                        f'docx 通道上 {n} 字（>60）没被判红（说明抽取后那一行没吃上 R7）：'
                        f'rc={r.returncode} FAIL={fails}', r)
                m = re.search(re.escape(dx) + r':(\d+):', fails[0])
                assert_(m and int(m.group(1)) == ln,
                        f'docx 通道 R7 位点不对：判据给「{fails[0]}」，按段落序数到第 {ln} 行', r)
    print('PASS r7_title_tiers（25/26 与 60/61 两根轴各成对 + 未核三态未折叠 + docx 通道照判）')


def test_battery_crash_attribution():
    """电池分类器自身的六条控制：崩溃与断言红不许互相冒充，且崩溃要能报出落点。

    第 20 轮实测一条正常 KILL 被旧的"全文搜 AssertionError"判法读成 CRASH-KILL，
    读数里没有任何落点信息，导致复算时既无法复现也无法归因——这把尺子量别人之前，
    得先量得准自己。
    """
    import importlib.util as ilu
    sp = ilu.spec_from_file_location('mb_attr', os.path.join(ROOT, 'tests/mutation_battery.py'))
    mb = ilu.module_from_spec(sp)
    sp.loader.exec_module(mb)

    def tb(t, msg=''):
        return ('Traceback (most recent call last):\n'
                '  File "/x/tests/test_scripts.py", line 2274, in <module>\n'
                '    t()\n'
                '  File "/x/tests/test_scripts.py", line 35, in assert_\n'
                f'    raise {t}(...)\n'
                f'{t}: {msg}\n')

    assert_(mb.fatal_exception(tb('AssertionError', '正文出现节名却没被认成域内文书'))
            == 'AssertionError', '真断言红被读成崩溃（KILL 记成 CRASH-KILL）', None)
    assert_(mb.fatal_exception(tb('OSError', 'Too many open files')) == 'OSError',
            '资源型崩溃没被认出来（会被记成抓红）', None)
    # 关键一案：崩溃消息里恰好抄进一段含 AssertionError 字样的子进程输出
    crashed = tb('OSError', 'rc=1\n--stdout--\nAssertionError: 别的档先红\n--stderr--\n')
    assert_(mb.fatal_exception(crashed) == 'OSError',
            '按整段子串判崩溃/断言：消息里出现该字样就翻档（旧判法的失效形状）', None)
    assert_(mb.fatal_exception('全部 PASS\n') is None, '没有 Traceback 时被折成某种异常', None)
    # 最阴的一案：抓红本身没错，但断言消息里嵌了一份**子进程**的 Traceback。
    # "取最后一段 Traceback"的写法会把它当成崩溃现场，把一次正常抓红读成 CRASH-KILL
    # （第 20 轮 doc 与 vsr 两条实测各错一次，两趟读数互相矛盾才暴露）。
    embedded = tb('AssertionError', 'rc=1\n--stdout--\n合规\n--stderr--\n'
                  + 'Traceback (most recent call last):\n'
                    '  File "/work/scripts/regen_docx.py", line 56, in find_stale\n'
                    '    os.path.getmtime(d)\n'
                    "FileNotFoundError: No such file or directory: '/tmp/x/README.docx'\n")
    assert_(mb.fatal_exception(embedded) == 'AssertionError',
            '断言消息里嵌着子进程 Traceback 时被读成崩溃（正常抓红记成 CRASH-KILL）', None)
    notes = mb.crash_notes(tb('OSError', 'Too many open files'))
    assert_(any('test_scripts.py' in n for n in notes) and any(n.startswith('OSError') for n in notes),
            f'崩溃归因打不出落点: {notes}', None)
    print('PASS 电池崩溃归因（断言红/资源崩溃/消息内含该字样/消息嵌子进程 Traceback/无 Traceback 五案 + 落点可打印）')


def test_docs_scripts_contract():
    """文档↔脚本双向契约：文档不得虚指不存在的判据/脚本/参数，脚本新加的判据与参数也不许漏写文档。
    单向检查会假绿——只核"文档引用都存在"时，脚本新增一条无人引用的判据照样绿。"""
    doc_paths = [p for p in ([os.path.join(ROOT, f) for f in ('README.md', 'SKILL.md')]
                            + [os.path.join(ROOT, 'references', f)
                               for f in sorted(os.listdir(os.path.join(ROOT, 'references')))
                               if f.endswith('.md')])
                 if os.path.isfile(p)]
    scripts = {f: open(os.path.join(S, f), encoding='utf8').read()
               for f in sorted(os.listdir(S)) if f.endswith('.py')}
    # 分母自证：任一侧为空 ⇒ 本检查是空转，必须判红而不是判绿
    assert_(len(doc_paths) >= 5 and len(scripts) >= 4,
             f'分母异常（文档 {len(doc_paths)} 篇 / 脚本 {len(scripts)} 个），本检查空转')

    doctxt = '\n'.join(open(p, encoding='utf8').read() for p in doc_paths)

    # 取号模式：判据号 1–99。先自测提取器，再信它给出的集合。
    # 原先四处都只认一位数字 → 任一族扩到第 10 条时：脚本侧把 R10 切成 R1（虚指一条不存在的判据）、
    # docstring 行「  R10 …」与文档侧 [1-9] 干脆扫不到它——两头各自失效，而这个检查看起来仍是
    # "双向对齐 PASS"。今天所有族都 ≤9，所以它是潜伏缺陷；潜伏缺陷的修法必须自带反证。
    # 号一律从 1 起 ⇒ 首位排除 0：只放宽成 \d 的第一版当场把 P0（审查红线那一档）与 R0 读成判据号、
    # 报出两条"文档虚指"——扩字符类前先在真语料上量假阳性，这一条又是它的一次实测。
    SCRIPT_RES = (r"Finding\(\s*['\"]([RCFVEGKNQTP][1-9]\d?)(?!\d)",
                  r'^\s+([RCFVEGKNQTP][1-9]\d?)\s',
                  r'\u2192 ([NVEGKT][1-9]\d?)(?!\d)')
    DOC_RE = r'\b([RCFVEGKNQTP][1-9]\d?)\b'
    # 文档里的 URL 常带百分号转义（中文链接），`%E5%AE%A1` 里的 "E5" 前后都是非单词字符，
    # \b 会把它当成一个判据号——第 38 轮 README 写 CNIPA 指南链接时被自己的契约判成
    # "文档虚指 E5/E6"。取号前先剥掉 %XX：剥了只会少看见转义垃圾，真引用没人用 URL 表达。
    PCT_ESC = r'%[0-9A-Fa-f]{2}'

    def _doc_tokens(t):
        return set(re.findall(DOC_RE, re.sub(PCT_ESC, '', t)))

    def _extract_scripts(src):
        out = set()
        # re.M 不可省：模式 2 的 ^\s+ 要靠行首锚定才认 docstring 里的判据行；少了它只匹配整个
        # 字符串开头、一条也取不到——这条自测的第一版就是这么把我抓住的。
        for pat in SCRIPT_RES:
            out |= set(re.findall(pat, src, re.M))
        return out

    # 自测双向：两位数必须被看见；一位数不许被切成两位；0 号与普通文字不算判据号。
    _probe = (r"Finding('R10 十号判据')" + '\n  R10 两位数行\n  R9 一位数行\n'
              '  T3 单行\n→ V12\n→ V3\nR1 不该被上面任何一行造出来\n'
              '  R0 与 P0 也不是判据号（P0 是审查红线那一档）\n')
    _got = _extract_scripts(_probe)
    assert_({'R9', 'R10', 'T3', 'V12', 'V3'} == _got,
            f'提取器对两位数漏判、或把 0 号读成判据: {sorted(_got)}', None)
    _got_doc = _doc_tokens('R10 与 R9 并列，`T3` 也提一次；R1 单独出现也算；'
                           'P0/R0 这类优先级与占位号不算；'
                           '链接 …/attach/0/%E4%B8%93%E5%88%A9%E5%AE%A1%E6%9F%A5%E6%8C%87%E5%8D%97.pdf'
                           ' 里夹着的转义垃圾不算判据号')
    assert_({'R10', 'R9', 'T3', 'R1'} == _got_doc,
            f'文档侧取号不认两位数或误收 0 号: {sorted(_got_doc)}', None)
    # 正向对照：不剥 %XX 时那串 URL 确实会被读成两个号——没有这一条，上面"URL 不算号"
    # 可能只是那串文本本来就取不出号（空转）。注意别把这两个号的字面写进被扫的文本里，
    # 那样它们会作为真 token 被取到，反向档立刻自指失效（本轮实测踩过一次）。
    _raw_url_tokens = set(re.findall(DOC_RE, '%E4%B8%93%E5%88%A9%E5%AE%A1%E6%9F%A5%E6%8C%87%E5%8D%97'))
    assert_({'E4', 'E5', 'E6'} == _raw_url_tokens,
            f'百分号转义的正向对照不成立（裸 DOC_RE 读到 {sorted(_raw_url_tokens)}），'
            f'剥转义那一步无从证明它咬过东西', None)

    defined_rules, flags_by_script = set(), {}
    rule_home = {}
    for name, s in scripts.items():
        found = _extract_scripts(s)
        for t in found:
            rule_home.setdefault(t, set()).add(name)
        defined_rules |= found
        flags_by_script[name] = set(re.findall(r"add_argument\('(--[a-z\-]+)'", s))
    doc_rules = _doc_tokens(doctxt)
    assert_(doc_rules == defined_rules,
            f'判据 token 不对齐 文档虚指={sorted(doc_rules - defined_rules)} '
            f'文档漏写={sorted(defined_rules - doc_rules)}（脚本判据须全部有文档出处，反之亦然）')
    # 同号两义防线：一个判据号只许有一个脚本定义它
    coll = {t: sorted(v) for t, v in rule_home.items() if len(v) > 1}
    assert_(not coll, f'判据号被两个脚本各自定义，读者无法分辨指代: {coll}')

    # ---- 同一份文件内的对账：脚本"打得出去的号"必须出现在它自己的模块 docstring 清单里 ----
    # 上面那份 `defined_rules` 是三个取号模式**跨文件**的并集，天生看不见同一文件里的两栏不对账：
    # 第 39 轮 R12/R13 落地时 docstring 清单还停在 R11、`Finding(` 已经打到 R13，
    # 而 README 与 hard-rules 同时补了这两个号 ⇒ 并集两侧一起涨、跨文件契约照样绿
    # （本轮现算差集 = {R12, R13}，靠人眼发现的；这一格把它变成机器发现）。
    # 判决面的形状各族不同，这里只列"真打得出去"的两种：`Finding('R1 …')` 与报文里的 `→ 号`。
    # claims 那一族的 Q 号是 f'… → Q7（…）' 的括号形状、不在 `Finding(` 里，
    # 所以它不进这一格——硬凑只会把分母撑大而让断言永真；那一族仍由上面那条跨文件对账管。
    SAME_FILE_EMIT = (SCRIPT_RES[0], SCRIPT_RES[2])

    def _same_file_missing(src):
        """该脚本自己打得出去、却没在自己模块 docstring 清单里逐条列出的判据号。"""
        _emit = set()
        for _pat in SAME_FILE_EMIT:
            _emit |= set(re.findall(_pat, src, re.M))
        return sorted(_emit - set(re.findall(SCRIPT_RES[1], src, re.M)))

    # 牙齿自证：这一档在真语料上今天读到的必然全是"空"，而那既是合规的形状也是恒真的形状。
    # 所以先喂两份最小样本——打了没列的那份必须点名 R2，补了清单的那份必须闭嘴。
    assert_(_same_file_missing("  R1 列了\nFinding('R2 打了没列')\n") == ['R2'],
            '同文件审计在最小组样上就不咬人（打了 R2 没列 R2 却读成空）', None)
    assert_(_same_file_missing("  R1 列了\n  R2 也列了\nFinding('R2 打了也列了')\n") == [],
            '同文件审计在合规样本上误咬（清单补齐了还报缺）', None)

    _sf_scripts = _sf_ids = 0
    for _n, _s in scripts.items():
        _miss = _same_file_missing(_s)
        assert_(not _miss,
                f'{_n} 的模块 docstring 清单漏写自己打得出去的判据号 {_miss}'
                f'（跨文件那份并集看不见这一格：文档侧同时补号就会抵消成绿）')
        _sf_scripts += 1
        _sf_ids += len(set(re.findall(SAME_FILE_EMIT[0], _s, re.M))
                       | set(re.findall(SAME_FILE_EMIT[1], _s, re.M)))
    # 分母自证：审到 0 个脚本＝这条从没跑过。本机实测：14 个脚本全部过审，
    # 其中 7 个"打得得出号"（iron 走 `Finding(`，另外 6 个走报文里的 `→ 号`），号数合计 41；
    # 收尾行报的两个数都由这个循环自己累加，不抄注释。
    # 只设下限：新增脚本自动进分母，哪天取号模式被改窄或判据被整批搬走，这里才红。
    assert_(_sf_scripts >= 6 and _sf_ids >= 25,
            f'同文件对账的分母塌了（脚本 {_sf_scripts} 个、号 {_sf_ids} 个）：'
            f'要么取号模式被改窄、要么判据被整批搬走，这条对账已经不再覆盖任何东西', None)

    doc_scripts = set(re.findall(r'scripts/([A-Za-z0-9_\-]+\.py)', doctxt))
    assert_(doc_scripts == set(scripts),
            f'脚本名不对齐 虚指={sorted(doc_scripts - set(scripts))} '
            f'未被文档提及={sorted(set(scripts) - doc_scripts)}')

    all_flags = set().union(*flags_by_script.values())
    declared_only = {n: fl for n, fl in flags_by_script.items() if fl}
    assert_(declared_only, '脚本侧无 argparse 参数声明，参数契约检查空转')
    # 方向一：与某脚本同行的 --flag 必须属于该脚本（限定作用域，避免误伤 soffice 等外部命令参数）
    for ln_no, line in enumerate(doctxt.splitlines(), 1):
        named = [n for n in scripts if f'scripts/{n}' in line]
        if not named:
            continue
        allowed = set().union(*(flags_by_script[n] for n in named))
        for flag in re.findall(r'(?<![\w-])(--[a-z][a-z\-]{2,})', line):
            assert_(flag in allowed,
                    f'文档第 {ln_no} 行给 {named} 挂了未声明的参数 {flag}')
    # 方向二：脚本声明的每个参数都要至少在文档出现一次
    for flag in sorted(all_flags):
        assert_(flag in doctxt, f'脚本参数 {flag} 无任何文档出处')
    # mdtable 的「共用」清单只能现算不能抄：本轮开工时 README 列 5 个、树上是 7 个。
    MD_LOAD_A = "_load('mdtable')"
    MD_LOAD_B = 'import mdtable'

    def _md_consumers(srcs):
        return {n for n, s in srcs.items() if n != 'mdtable.py'
                and (MD_LOAD_A in s or MD_LOAD_B in s)}

    # 先证这把尺子会开火：两种拼写各认得，量具自己不算消费者。
    _syn = {'a.py': MD_LOAD_A, 'b.py': MD_LOAD_B + '\n',
            'mdtable.py': MD_LOAD_A, 'c.py': 'pass\n'}
    assert_(_md_consumers(_syn) == {'a.py', 'b.py'},
            f'消费者现算漏了某种拼写或把量具自己算了进去: {sorted(_md_consumers(_syn))}', None)
    tree_md = _md_consumers(scripts)
    assert_(len(tree_md) >= 5, f'消费者现算只读到 {sorted(tree_md)}，本检查在空转')

    def _md_doc_list(txt):
        """取 README 里 `scripts/mdtable.py` 那一条（含其续行）列出的 *.py 名字。"""
        lines = txt.splitlines()
        for i, ln in enumerate(lines):
            if 'scripts/mdtable.py' not in ln:
                continue
            out = set()
            for cont in lines[i:]:
                if not cont.strip() or (cont.startswith('- ') and 'mdtable' not in cont):
                    break
                out |= set(re.findall(r'`([a-z_]+\.py)`', cont))
            out.discard('mdtable.py')
            return out
        assert_(False, '文档里再没有 `scripts/mdtable.py` 那一条，共用清单没地方对账', None)
        return set()

    doc_md = _md_doc_list(doctxt)
    # 抽取器自己的必开火对照：名字写在续行里也要取到（只认首行的话，这条对账是恒真的）
    _doc_syn = ('- `scripts/mdtable.py`：markdown 表格读取的唯一实现，\n'
                '  由 `check_evt.py`、`check_claims.py` 共用。\n'
                '  这一行不点名。\n'
                '\n'
                '- 下一条 bullet\n')
    assert_(_md_doc_list(_doc_syn) == {'check_evt.py', 'check_claims.py'},
            f'清单抽取器没从续行里取到名字（那这条对账取不到东西）: '
            f'{sorted(_md_doc_list(_doc_syn))}', None)
    assert_(doc_md == tree_md,
            f'mdtable 共用清单不对账 文档漏写={sorted(tree_md - doc_md)} '
            f'文档虚指={sorted(doc_md - tree_md)}（消费者一律按 scripts/ 树现算）')

    # 任何提到本门禁并给出规则区间的文档行，区间都必须等于脚本源码现推的判据范围
    # （README 用法行与 pipeline-stages 的"出 R1–R5 红点"都曾谎报且无人核对）
    rnums = rule_span(scripts['check_iron_rules.py'])
    span = f'R{rnums[0]}–R{rnums[-1]}'
    hit = 0
    for ln_no, line in enumerate(doctxt.splitlines(), 1):
        if 'check_iron_rules' not in line:
            continue
        for claimed in re.findall(r'R\d+–R\d+', line):
            hit += 1
            assert_(claimed == span,
                    f'文档第 {ln_no} 行自报 {claimed}，脚本实际判据 {span}')
    assert_(hit >= 2, f'只核到 {hit} 处自报区间，覆盖面过窄（曾有两处各自漂移）')
    print(f'PASS 文档↔脚本契约（判据 {len(defined_rules)} 条、脚本 {len(scripts)} 个、'
          f'参数 {len(all_flags)} 项，双向对齐；自报区间 {span} 核对 {hit} 处；'
          f'同文件对账 {_sf_scripts} 个脚本/{_sf_ids} 个号——打得出去的号必须在自己 docstring 里列出）')


def test_check_evt():
    """EVT 诚实性门禁 E1–E4：判定三态、非✅带下一步、物理实测列不得有实测值、偏差标注。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('check_evt', os.path.join(S, 'check_evt.py'))
    ce = ilu.module_from_spec(spec)
    spec.loader.exec_module(ce)

    HDR = ('| # | 验证项目 | 物理实测项 | 判定 |\n|---|---|---|---|\n')
    OK = '# EVT 报告\n## 2. 投产判定\n' + HDR + (
        '| 1 | 立杆屈曲 | 屈曲载荷，样本量 5 只，判据：不断裂（待物理实测） | ✅ |\n'
        '| 2 | 关节噪声 | 预测值 42 N（待物理实测） | ⚠️ 缺口：无样机；关闭判据：实测≤3 dB |\n'
        '| 3 | 折叠锁疲劳 | 跌落台架，Not Run | ❌ 改法：换锁舌材料并重算 |\n')
    bad, notes = ce.check_text('04_EVT验证/EVT.md', OK)
    assert_(bad == [], f'合规 EVT 报告被 E1–E4 误判: {bad}', None)
    assert_(notes == [], f'域内文书却报了未判: {notes}', None)

    # 引用号普查：标准号/IPC/条款号里的数字不得当成疑似实测值。
    # 第 1 行刻意不带"待物理实测"字样——否则 PENDING 先把行救下，豁免根本没吃上力，
    # 这条断言就成了假绿（上一版正是这样，变异"取消引用号豁免"因此存活）。
    cite = ('# EVT\n## 投产判定\n' + HDR +
            '| 1 | 织物 | 依据 GB/T 31701-2015 第 4.3 条与 IPC A42B3 类工装判定 | ✅ |\n'
            '| 2 | 电池 | 送检 UN 38.3 全项，Not Run | ✅ |\n')
    bad, _ = ce.check_text('04_EVT验证/EVT.md', cite)
    assert_(bad == [], f'标准号/IPC 号被当成实测值: {bad}', None)
    # 配套必红：把"待物理实测"换成真写了一个测量结果，E3 必须开火
    real = cite.replace('UN 38.3 全项，Not Run', 'UN 38.3 测得 47 mg/kg 甲醛')
    bad, _ = ce.check_text('04_EVT验证/EVT.md', real)
    assert_(sum('E3' in x for x in bad) == 1, f'编造的实测值未被 E3 抓到: {bad}', None)

    # E1 必红：无符号措辞 / 两个符号并存；E2 必红：⚠️ 缺关闭判据、❌ 缺改法。
    # 四行各配一条独立断言——合在一条"总数 2+2"上时，任一档失守都会由总数那档先红，
    # 红因就归不到具体条款上（变异电池把这暴露得很清楚）。
    worst = ('# EVT\n## 投产判定\n' + HDR +
             '| 1 | 立杆 | 待物理实测 | 基本通过 |\n'
             '| 2 | 关节 | 待物理实测 | ✅ ❌ |\n'
             '| 3 | 锁 | 待物理实测 | ⚠️ 缺口：无样机 |\n'
             '| 4 | 疲劳 | 待物理实测 | ❌ |\n')
    bad, _ = ce.check_text('04_EVT验证/EVT.md', worst)
    for probe, msg in (('未落三态', 'E1 空判定（含糊措辞）未判红'),
                       ('同时出现', 'E1 双符号并存未判红'),
                       ('缺口与关闭判据', 'E2 ⚠️ 缺关闭判据未判红'),
                       ('未给改法', 'E2 ❌ 缺改法未判红')):
        assert_(sum(probe in b for b in bad) == 1, f'{msg}（实得 {bad}）', None)
    # 配套必绿：四行都补全后必须零违规
    fixed = ('# EVT\n## 投产判定\n' + HDR +
             '| 1 | 立杆 | 待物理实测 | ✅ |\n'
             '| 2 | 关节 | 待物理实测 | ⚠️ 缺口：无样机；关闭判据：实测 ≤3 dB |\n'
             '| 3 | 锁 | 待物理实测 | ❌ 改法：换材料重算 |\n')
    bad, _ = ce.check_text('04_EVT验证/EVT.md', fixed)
    assert_(bad == [], f'判定齐全的报告仍被判红: {bad}', None)

    # E4：偏差>10% 未标注必红；标了原因必绿；只给一侧走三态
    e4_bad = '# EVT\n## 投产判定\n复算 设计值 12.0 mm，复算值 15.0 mm。\n'
    e4_ok = '# EVT\n## 投产判定\n复算 设计值 12.0 mm，复算值 15.0 mm，偏差 25% 原因：载荷谱保守。\n'
    e4_half = '# EVT\n## 投产判定\n设计值 12.0 mm（复算待做）。\n'
    bad, _ = ce.check_text('EVT随记.md', e4_bad)
    assert_(sum('E4' in x for x in bad) == 1, f'偏差 25% 未标注未被 E4 抓到: {bad}', None)
    bad, _ = ce.check_text('EVT随记.md', e4_ok)
    assert_(sum('E4' in x for x in bad) == 0, f'已标注偏差原因仍被 E4 判红: {bad}', None)
    bad, notes = ce.check_text('EVT随记.md', e4_half)
    assert_(sum('E4' in x for x in bad) == 0, f'缺复算值被折成 E4 违规（应走未判）: {bad}', None)
    assert_(any('E4 未判' in n for n in notes), f'缺一侧值没报 E4 未判: {notes}', None)

    # 缺"验证总表"的两种写法要分轴处置：交付物（04_EVT 目录内）缺表 = 判红；
    # 只是正文提到投产判定的文档 = 未判。否则散文体的 EVT 报告会在 E1–E3 上白白通过。
    prose = '# EVT 报告\n## 2. 投产判定\n立杆稳定，判定 ✅。\n'
    bad, notes = ce.check_text('04_EVT验证/EVT报告.md', prose)
    assert_(len(bad) == 1 and '无从判起' in bad[0],
            f'交付物缺判定表却未判红（散文写法被白白放行）: {bad}', None)
    bad, notes = ce.check_text('EVT随记.md', prose)
    assert_(bad == [] and len(notes) == 1 and 'E1–E3 未判' in notes[0],
            f'规则类文档缺表被误判红，或未报 E1–E3 未判: bad={bad} notes={notes}', None)

    # 域外文书：不判、不折成合规；rc=2 说明"本次未做任何判定"
    bad, notes = ce.check_text('01_交底书/交底书.md', '# 交底书\n普通内容\n')
    assert_(bad == [] and len(notes) == 1 and '非 EVT 文书' in notes[0],
            f'域外文书未走三态或未说明成因: bad={bad} notes={notes}', None)

    with tempfile.TemporaryDirectory() as d:
        evt = os.path.join(d, '04_EVT验证'); os.makedirs(evt)
        open(os.path.join(evt, 'EVT报告.md'), 'w', encoding='utf8').write(OK)
        open(os.path.join(d, '交底书.md'), 'w', encoding='utf8').write('# 交底书\n普通内容\n')
        r = run([PY, f'{S}/check_evt.py', d, '--all'])
        assert_(r.returncode == 0 and '实核 EVT 文书 1 份' in r.stdout,
                '整包 --all 未只把 EVT 域内文书计入实核数', r)
        os.remove(os.path.join(evt, 'EVT报告.md'))
        r = run([PY, f'{S}/check_evt.py', d, '--all'])
        assert_(r.returncode == 2 and '没有一份落在 EVT 适用域内' in r.stdout,
                '域内文书为零时被当成"已通过"', r)
        r = run([PY, f'{S}/check_evt.py', os.path.join(d, '不存在.md')])
        # 只核 rc 与"输入不可用"前缀会被另一条同类消息顶包（V 门禁那边实测过同一形状）
        assert_(r.returncode == 2 and '不存在.md' in r.stdout and '既不是文件也不是目录' in r.stdout,
                '路径不存在未按要求说清成因并 fail-closed', r)
    print('PASS check_evt（E1–E4 各成对 + 引用号普查 + 域外三态 + rc=2）')


def test_check_regulatory():
    """法规/裁决门禁 G1–G5：每条判据都要有"必开火"与"合规侧必不开火"两案，
    且不开火那案必须真被该判据读到（seen 集合里有它），否则是空转的绿。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('check_regulatory', f'{S}/check_regulatory.py')
    cr = ilu.module_from_spec(spec)
    spec.loader.exec_module(cr)

    P = '05_法规与裁决/法规_T.md'

    def judge(body, path=P):
        return cr.check_text(path, body)

    def n_of(bad, tag):
        return sum(1 for x in bad if f'→ {tag}' in x)

    APPLIC = ('## 适用性判定\n| 标准/法规 | 判定 | 依据 |\n|---|---|---|\n'
              '| GB 6675.1-2014 | 适用 | 属 6675 系列玩具范围 |\n'
              '| GB 19865-2005 | 不适用 | 电能来源条款与本产品无关 |\n')
    MAP = ('## 逐条映射\n| 条款 | 要求 | 结论 |\n|---|---|---|\n'
           '| 第 4.3 条 | 可触及边缘不得锐利 | 符合 |\n'
           '| 第 5.1 条 | 小零件不得脱落 | 无法判定 |\n')
    GAP = ('## 合规缺口清单\n| 编号 | 缺口 | 修订建议 | 实测规程 |\n|---|---|---|---|\n'
           '| Q1 | 拉脱力未验证 | 表带根部加卡扣倒钩 | 待物理实测：拉脱力 ≥90N |\n'
           '| Q2 | 电池仓未做开启试验 | 改为需工具开启 | |\n')
    ARBIT = ('## 裁决总表\n| 冲突项 | 结论 | 依据 | 约束 | 生效范围 |\n|---|---|---|---|---|\n'
             '| 表带厚度 | 维持 2.4mm | EVT 复算 2.31mm | 投产后不得回退 | XR-7 全部 SKU |\n'
             '| 螺丝规格 | 待定 | 维持冻结值，转 EVT 实测裁决 | 实测前不得投产 | XR-7 全部 SKU |\n')
    COST = ('## 送检包清单\n| 项目 | 费用 | 周期 |\n|---|---|---|\n'
            '| 机械物理试验 | 约 1.2 万元（公开信息估算） | 约 15 个工作日（公开信息估算） |\n')

    # 合规总案：五张表全绿，且五条判据都真的落到了行上
    bad, notes, seen = judge('# 法规与裁决\n\n' + APPLIC + '\n' + MAP + '\n' + GAP
                             + '\n' + ARBIT + '\n' + COST)
    assert_(bad == [], f'合规法规文书被判红: {bad}', None)
    assert_(seen == {'G1', 'G2', 'G3', 'G4', 'G5'}, f'五条判据未全部真判: {sorted(seen)}', None)

    def swap(table, old, new):
        assert table.count(old) == 1, f'锚点在夹具里不唯一: {old}'
        return table.replace(old, new)

    # G1 三态：含糊措辞 / 两态并列 / 有判定无依据 各必开火，且只有 G1 开火
    for body, needle in ((swap(APPLIC, '| 适用 |', '| 基本适用 |'), '判定列未落三态'),
                         (swap(APPLIC, '| 适用 | 属', '| 适用 不适用 | 属'), '同时出现'),
                         (APPLIC.replace('| 属 6675 系列玩具范围 |', '| |'), '有判定却无依据')):
        bad, notes, seen = judge('# 法规与裁决\n\n' + body)
        assert_(n_of(bad, 'G1') == 1, f'G1 未恰好开火一条（{needle}）: {bad}', None)
        assert_(needle in '\n'.join(bad), f'G1 开火但成因不是 {needle}: {bad}', None)
        assert_(n_of(bad, 'G2') == 0, f'G1 的夹具把 G2 也带红了: {bad}', None)
    # 同义列名（适用性/出处）也要认——不认就会整条判据静默不判
    bad, notes, seen = judge('# 法规与裁决\n\n'
                             '| 法规名称 | 适用性 | 出处 |\n|---|---|---|\n'
                             '| GB 6675.1-2014 | 部分适用 | 见 S8 记录 |\n')
    assert_(bad == [] and 'G1' in seen, f'同义列名未认，G1 空转: {bad} seen={sorted(seen)}', None)
    # 缺「依据」列：整表报一条，不随行数放大
    bad, notes, seen = judge('# 法规与裁决\n\n| 标准 | 判定 |\n|---|---|\n'
                             '| GB A | 适用 |\n| GB B | 不适用 |\n')
    assert_(n_of(bad, 'G1') == 1 and '缺「依据」列' in '\n'.join(bad),
            f'缺列被放大成逐条或没报: {bad}', None)

    # G2：空结论 / "详见正文" 必红；"无法判定"与"不符合"是合法结论（子串边界要站得住）
    bad, notes, seen = judge('# 法规与裁决\n\n'
                             '| 条款 | 要求 | 结论 |\n|---|---|---|\n'
                             '| 4.3 | 边缘 | |\n| 5.1 | 小零件 | 详见正文 |\n')
    assert_(n_of(bad, 'G2') == 2 and 'G1' not in seen,
            f'G2 两条未各自开火，或被 G1 抢判: {bad} seen={sorted(seen)}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n'
                             '| 条款 | 要求 | 结论 |\n|---|---|---|\n'
                             '| 4.3 | 边缘 | 不符合 |\n| 5.1 | 小零件 | 符合（附条件） |\n')
    assert_(bad == [] and 'G2' in seen, f'合法结论被判红（子串边界失效）: {bad}', None)

    # G3：两栏都空必红；只给一侧即合规；两类列都没有→整表一条
    bad, notes, seen = judge('# 法规与裁决\n\n' + GAP.replace('| 改为需工具开启 | |\n',
                                                              '| | |\n'))
    assert_(n_of(bad, 'G3') == 1 and '缺口既无修订建议也无实测规程' in '\n'.join(bad),
            f'G3 未开火或放大: {bad}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n' + GAP)
    assert_(bad == [] and 'G3' in seen, f'只给修订建议的缺口被判红: {bad}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n| 编号 | 缺口 |\n|---|---|\n'
                             '| Q1 | 甲 |\n| Q2 | 乙 |\n')
    assert_(n_of(bad, 'G3') == 1 and '既无「修订建议」也无「实测规程」列' in '\n'.join(bad),
            f'缺口清单缺列被放大成逐条或没报: {bad}', None)

    # G4：四要素缺格必红、依据不引证据必红；"转实测裁决"措辞与"公开复算"证据必绿；缺列整表一条
    bad, notes, seen = judge('# 法规与裁决\n\n| 冲突项 | 结论 | 依据 | 约束 | 生效范围 |\n'
                             '|---|---|---|---|---|\n'
                             '| 螺丝 | 维持 M2 | 会议纪要 | 无 | |\n')
    joined = '\n'.join(bad)
    assert_(n_of(bad, 'G4') == 2 and '裁决缺「生效范围」' in joined and '既未引 EVT 侧证据' in joined,
            f'G4 两半未各自开火: {bad}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n| 冲突项 | 结论 | 依据 | 约束 | 生效范围 |\n'
                             '|---|---|---|---|---|\n'
                             '| 螺丝 | 待定 | 维持冻结值，转 EVT 实测裁决 | 实测前不得投产 | 全 SKU |\n'
                             '| 厚度 | 维持 2.4mm | 独立复算 2.31mm，偏差 3.8% | 不得回退 | 全 SKU |\n')
    assert_(bad == [] and 'G4' in seen, f'合规裁决（含过渡口径）被判红: {bad}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n| 冲突项 | 结论 | 依据 | 生效范围 |\n'
                             '|---|---|---|---|\n'
                             '| 甲 | 维持 | 复算 | 全 SKU |\n| 乙 | 维持 | 复算 | 全 SKU |\n')
    assert_(n_of(bad, 'G4') == 1 and "裁决表缺列 ['约束']" in '\n'.join(bad),
            f'裁决缺列被放大成逐条或没报: {bad}', None)

    # G5：数字不带口径必红（费用、周期两列都要看）；带"公开…估算"或无数字必绿
    bad, notes, seen = judge('# 法规与裁决\n\n' + COST.replace('（公开信息估算）', ''))
    assert_(n_of(bad, 'G5') == 2 and '未标' in '\n'.join(bad),
            f'G5 未把费用/周期两列都核到: {bad}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n| 项目 | 费用 | 周期 |\n|---|---|---|\n'
                             '| 机械物理试验 | 待定 | 待认证机构回复 |\n')
    assert_(bad == [] and 'G5' in seen, f'没给数字的行被 G5 误伤: {bad}', None)

    # 三态：残行不按位取列、只有表头的表、域外文书、正文认域
    # 第二行只有一格：按位读会把 j_ap 读成空 → 假 G1。它必须只进未判注记。
    bad, notes, seen = judge('# 法规与裁决\n\n' + APPLIC
                             + '| 多出一格 | 适用 | 依据 | 又多了 |\n| 少了 |\n')
    assert_(bad == [], f'残行仍被按位取列判红: {bad}', None)
    assert_(any('不按位取列' in n and '第3、4行' in n for n in notes),
            f'残行未报"不按位取列"注记: notes={notes}', None)
    bad, notes, seen = judge('# 法规与裁决\n\n| 标准/法规 | 判定 | 依据 |\n|---|---|---|\n')
    assert_(bad == [] and any('只有表头没有数据行' in n for n in notes) and 'G1' not in seen,
            f'空表被折成合规或判红: bad={bad} notes={notes} seen={sorted(seen)}', None)
    bad, notes, seen = judge('# 交底书\n普通内容\n', path='01_交底书/交底书.md')
    assert_(bad == [] and len(notes) == 1 and '非法规/裁决文书' in notes[0] and seen == set(),
            f'域外文书未走三态: bad={bad} notes={notes}', None)
    bad, notes, seen = judge('# 会议记录\n\n## 裁决总表\n'
                             '| 冲突项 | 结论 | 依据 | 约束 | 生效范围 |\n|---|---|---|---|---|\n'
                             '| 甲 | 维持 | 会议纪要 | 无 | 全 SKU |\n', path='notes/会议.md')
    assert_(n_of(bad, 'G4') == 1 and 'G4' in seen,
            f'正文按表名认域未生效（域外散文躲过了 G4）: bad={bad} seen={sorted(seen)}', None)

    # CLI：合规 rc=0、违规 rc=1、域内为零 rc=2、输入不可用 rc=2 且点名路径与成因
    with tempfile.TemporaryDirectory() as d:
        rd = os.path.join(d, '05_法规与裁决')
        os.makedirs(rd)
        ok_path = os.path.join(rd, '法规_T.md')
        with open(ok_path, 'w', encoding='utf8') as f:
            f.write('# 法规与裁决\n\n' + APPLIC)
        r = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(r.returncode == 0 and '实核法规文书 1 份' in r.stdout, '合规包未 rc=0', r)
        with open(os.path.join(d, 'README.md'), 'w', encoding='utf8') as f:
            f.write('# 包说明\n\n列出 05_法规与裁决/ 目录而已。\n')
        r = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(r.returncode == 0 and '实核法规文书 1 份' in r.stdout,
                '包 README 只是提到目录名，却被当成域内文书', r)
        with open(ok_path, 'w', encoding='utf8') as f:
            f.write('# 法规与裁决\n\n' + APPLIC.replace('| 适用 |', '| 基本适用 |'))
        r = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(r.returncode == 1 and '→ G1' in r.stdout, '违规包未 rc=1', r)
        os.remove(ok_path)
        r = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(r.returncode == 2 and '没有一份落在法规/裁决适用域内' in r.stdout,
                '域内文书为零时被当成"已通过"', r)
        for extra in [f for f in os.listdir(d) if f.endswith('.md')]:
            os.remove(os.path.join(d, extra))
        r = run([PY, f'{S}/check_regulatory.py', d, '--all'])
        assert_(r.returncode == 2 and '未找到任何 .md' in r.stdout,
                '目录里没有 .md 时未说清"一份都没扫到"这条成因', r)
        r = run([PY, f'{S}/check_regulatory.py', os.path.join(d, '不存在.md')])
        assert_(r.returncode == 2 and '不存在.md' in r.stdout and '既不是文件也不是目录' in r.stdout,
                '路径不存在未说清成因并 fail-closed', r)
    print('PASS check_regulatory（G1–G5 各成对 + 同义列名 + 整表只报一条 + 三态 + rc=2）')


def test_check_design_completion():
    """设计补全门禁 K1–K5：四类表各自的成对正反案 + 触发式的 K5 + 三条适用域轴 + rc 档。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('check_design_completion',
                                       f'{S}/check_design_completion.py')
    dc = ilu.module_from_spec(spec)
    spec.loader.exec_module(dc)

    P = '03_设计补全/补全_T.md'

    def judge(body, path=P):
        return dc.check_text(path, body)

    def n_of(bad, tag):
        return sum(1 for x in bad if f'→ {tag}' in x)

    REG = ('## 1. 缺失项登记表\n' + dc.header_row('K1') + '\n' + dc.separator_row('K1') + '\n'
           '| M1 | 专利1 | 锁扣结构未画 | | 设计补全 | 决策树：机构结构→执行补全 '
           '| 高 | 连杆卡扣三视图 | 已补全 |\n'
           '| M2 | 专利1 | 供应商硬度 | 交底书 §5 | 保留占位-第三方确认 | 决策树：Q1 只能第三方 '
           '| 中 | 保留占位三字段 | 开放 |\n')
    CARD_ROW = ('| 驱动方式 | 连杆驱动、气动顶出、弹簧复位 | 连杆驱动 | 与冻结厚度 2.4mm 兼容 '
                '| 不得增加零件数 | 回退为弹簧复位，不动独权 |\n')
    CARD = '## 2. 设计决策卡\n' + dc.header_row('K2') + '\n' + dc.separator_row('K2') + '\n' + CARD_ROW

    CONF = ('## 3. 冲突记录\n' + dc.header_row('K3') + '\n' + dc.separator_row('K3') + '\n'
            '| CON-01 | 倒钩深度 | 0.6mm | 0.75mm | 0.6mm 拉脱力不足（独立复算） '
            '| 采纳 0.75 并更新处置表 | 待裁决 |\n')
    IFACE = ('## 4. 接口定义\n' + dc.header_row('K4') + '\n' + dc.separator_row('K4') + '\n'
             '| 表带-锁扣 | 机械 | 卡扣 | 拉脱力 90N | 120N | 倒钩剪断 | 待物理实测：拉脱试验 |\n')
    GUARDED = ('## 9. 步态对称性优化\n以对称性指数为优化目标。退化解审查：只压指数可由拖慢健侧达成，'
               '故目标函数加守护项（健侧步速下限 0.8m/s）。\n')
    UNGUARDED = '## 9. 步态对称性优化\n以对称性指数为优化目标，把步速差压到 2% 以内。\n'

    # 合规总案：四类表全绿，K1–K4 都真落到行上，K5 由守护记录判过
    bad, notes, seen = judge('# 补全\n\n' + REG + '\n' + CARD + '\n' + CONF + '\n' + IFACE
                             + '\n' + GUARDED)
    assert_(bad == [], f'合规设计补全文书被判红: {bad}', None)
    assert_(seen == {'K1', 'K2', 'K3', 'K4', 'K5'}, f'五条判据未全部真判: {sorted(seen)}', None)

    # K1 类型裁定：两类互不包含，所以子串计数就够；"补全"这种半截写法必须不开火
    for cell, needle in (('补全', '未落在'), ('设计补全 保留占位-第三方确认', '同时出现'),
                         ('待定', '未落在')):
        body = REG.replace('| 设计补全 | 决策树：机构结构→执行补全 |', f'| {cell} | 决策树 |')
        assert_(body != REG, f'夹具锚点没命中，这一案实际没改任何东西: {cell}', None)
        bad, notes, seen = judge('# 补全\n\n' + body)
        assert_(n_of(bad, 'K1') == 1 and needle in '\n'.join(bad),
                f'K1 未恰好开火一条（{cell}/{needle}）: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n' + REG.replace('| 已补全 |', '| |'))
    assert_(n_of(bad, 'K1') == 1 and '「状态」空着' in '\n'.join(bad),
            f'状态空着未报 K1: {bad}', None)
    # 缺列整表报一条（两行数据也只报一条），且不再逐行放大
    bad, notes, seen = judge('# 补全\n\n| 编号 | 缺失项 | 类型裁定 | 裁定依据 |\n|---|---|---|---|\n'
                             '| M1 | 甲 | 设计补全 | 决策树 |\n| M2 | 乙 | 设计补全 | 决策树 |\n')
    assert_(n_of(bad, 'K1') == 1 and '缺列' in '\n'.join(bad),
            f'K1 缺列被放大成逐行或没报: {bad}', None)

    # K2 可选方案：单候选必红，两个候选（含 3 个）必绿，且不会牵动别的档
    bad, notes, seen = judge('# 补全\n\n' + CARD.replace('连杆驱动、气动顶出、弹簧复位', '连杆驱动'))
    assert_(n_of(bad, 'K2') == 1 and '只有一个候选' in '\n'.join(bad),
            f'单候选选型未被 K2 抓到: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n' + CARD.replace('| 不得增加零件数 |', '| |'))
    assert_(n_of(bad, 'K2') == 1 and '「约束条件」空着' in '\n'.join(bad),
            f'决策卡约束条件空着未报: {bad}', None)

    # K3 / K4：逐格必填的那几列，空着必红；缺列只报一条
    bad, notes, seen = judge('# 补全\n\n' + CONF.replace('| 采纳 0.75 并更新处置表 |', '| |'))
    assert_(n_of(bad, 'K3') == 1 and '「建议处置」空着' in '\n'.join(bad),
            f'冲突记录无建议处置未报 K3: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n| 编号 | 事项 | 冻结值 | 设计值 | 冲突理由 | 状态 |\n'
                             '|---|---|---|---|---|---|\n| C1 | 甲 | 1 | 2 | 理由 | 开放 |\n')
    assert_(n_of(bad, 'K3') == 1 and "['建议处置']" in '\n'.join(bad),
            f'K3 缺列未报: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n' + IFACE.replace('| 120N |', '| |'))
    assert_(n_of(bad, 'K4') == 1 and '「极限值」空着' in '\n'.join(bad),
            f'接口极限值空着未报 K4: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n| 名称 | 方向 | 类型 | 额定值 | 极限值 | 失效模式 |\n'
                             '|---|---|---|---|---|---|\n| 甲 | 机械 | 卡扣 | 90N | 120N | 剪断 |\n')
    assert_(n_of(bad, 'K4') == 1 and "['验证方法']" in '\n'.join(bad),
            f'K4 缺验证方法列未报: {bad}', None)

    # K5 触发式：有代理指标无守护 → 红；带守护记录 → 绿且算真判；没触发 → 未判
    bad, notes, seen = judge('# 补全\n\n' + UNGUARDED)
    assert_(n_of(bad, 'K5') == 1 and '没有守护项' in '\n'.join(bad),
            f'代理指标无守护记录未被 K5 抓到: {bad}', None)
    bad, notes, seen = judge('# 补全\n\n' + GUARDED)
    assert_(bad == [] and 'K5' in seen, f'带守护记录的节被 K5 误伤: {bad}', None)
    # 只命中一根识别列的表不该被认成任何一类：否则一张"参数对照表"会被 K3 按缺列判红
    bad, notes, seen = judge('# 补全\n\n| 项目 | 冻结值 | 说明 |\n|---|---|---|\n'
                             '| 壁厚 | 2.4mm | 外观组要求 |\n')
    assert_(bad == [] and seen == set(),
            f'只凭一根识别列就被当成登记表/冲突记录: bad={bad} seen={sorted(seen)}', None)
    bad, notes, seen = judge('# 补全\n\n' + REG)
    assert_(bad == [] and 'K5' not in seen
            and any('未出现代理指标' in n for n in notes),
            f'没触发的 K5 被折成合规或被漏报未判: bad={bad} notes={notes}', None)

    bad, notes, seen = judge('# 补全\n\n' + GUARDED + '\n' + UNGUARDED)
    assert_(n_of(bad, 'K5') == 1 and '没有守护项' in '\n'.join(bad),
            f'K5 被另一节的守护记录遮挡（跨节漏水）: {bad}', None)
    # 适用域第二条轴：正文只出现节名（表认不出来、路径也不在 03），仍须进域
    bad, notes, seen = judge('# 说明\n\n## 接口定义\n（本节待补）\n', path='02_申请文件/杂项.md')
    assert_(all('非设计补全文书' not in n for n in notes),
            f'正文出现节名却没被认成域内文书: notes={notes}', None)
    # 适用域第三条轴：正文既不提表名也不在 03 目录，但真有一张决策卡 → 仍要进域
    bare = ('# 会议记录\n\n' + dc.header_row('K2') + '\n' + dc.separator_row('K2')
            + '\n' + CARD_ROW)
    assert_('决策卡' not in bare and '03_设计补全' not in bare,
            '夹具里混进了表名，第三条轴就没被单独验到', None)
    bad, notes, seen = judge(bare, path='01_交底书/杂记.md')
    assert_(bad == [] and 'K2' in seen,
            f'按表类认域这条轴没生效（散文里的决策卡躲过了 K2）: bad={bad} seen={sorted(seen)}',
            None)
    bad, notes, seen = judge('# 交底书\n普通内容\n', path='01_交底书/交底书.md')
    assert_(bad == [] and len(notes) == 1 and '非设计补全文书' in notes[0] and seen == set(),
            f'域外文书未走三态: bad={bad} notes={notes}', None)
    # 空表与残行都走未判，不折成合规也不折成违规
    bad, notes, seen = judge('# 补全\n\n' + dc.header_row('K2') + '\n'
                             + dc.separator_row('K2') + '\n')
    assert_(bad == [] and any('只有表头没有数据行' in n for n in notes) and 'K2' not in seen,
            f'骨架式空表未走未判: bad={bad} notes={notes} seen={sorted(seen)}', None)
    bad, notes, seen = judge('# 补全\n\n' + IFACE + '| 又多一格 | 机械 | 卡扣 | 90N | 120N '
                             '| 剪断 | 待实测 | 多了 |\n')
    assert_(any('不按位取列' in n for n in notes), f'残行未报不按位取列: notes={notes}', None)

    # CLI 四档
    with tempfile.TemporaryDirectory() as d:
        dd = os.path.join(d, '03_设计补全')
        os.makedirs(dd)
        doc = os.path.join(dd, '补全_T.md')
        with open(doc, 'w', encoding='utf8') as f:
            f.write('# 补全\n\n' + REG + '\n' + CARD)
        r = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(r.returncode == 0 and '实核设计补全文书 1 份' in r.stdout, '合规包未 rc=0', r)
        with open(doc, 'w', encoding='utf8') as f:
            f.write('# 补全\n\n' + REG + '\n' + UNGUARDED)
        r = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(r.returncode == 1 and '→ K5' in r.stdout, '违规包未 rc=1', r)
        os.remove(doc)
        with open(os.path.join(d, '交底书.md'), 'w', encoding='utf8') as f:
            f.write('# 交底书\n普通内容，没有这四类表。\n')
        r = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(r.returncode == 2 and '没有一份落在设计补全适用域内' in r.stdout,
                '域内文书为零时被当成"已通过"', r)
        os.remove(os.path.join(d, '交底书.md'))
        r = run([PY, f'{S}/check_design_completion.py', d, '--all'])
        assert_(r.returncode == 2 and '未找到任何 .md' in r.stdout,
                '目录里没有 .md 时未说清"一份都没扫到"这条成因', r)
        r = run([PY, f'{S}/check_design_completion.py', os.path.join(d, '不存在.md')])
        assert_(r.returncode == 2 and '不存在.md' in r.stdout and '既不是文件也不是目录' in r.stdout,
                '路径不存在未说清成因并 fail-closed', r)
    print('PASS check_design_completion（K1–K5 各成对 + 触发式未判 + 三条适用域轴 + rc=2）')


def test_check_figure_labels():
    """附图标记门禁 N1–N4：每条判据都要有"必开火"与"合规侧必不开火"两案，
    且不开火那案必须真被该判据读到（seen 里有它），否则是空转的绿。
    N3/N4 另各带一条"不许自证"的反案——正文遮掉表格行这件事必须由判红来证明。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('check_figure_labels', f'{S}/check_figure_labels.py')
    cf = ilu.module_from_spec(spec)
    spec.loader.exec_module(cf)

    P = '02_申请文件/说明书_T.md'
    HDR = '| 标记 | 名称 | 所在图号 |\n|---|---|---|'
    ROWS = '| 12 | 底座 | 1、2 |\n| 13 | 支架 | 1 |'
    OK = ('# 整机 说明书\n'
          '## 附图说明\n图 1 为本机构整体示意图；图 2 为底座剖视图。\n'
          '## 具体实施方式\n所述底座 12 与支架 13 连接，所述支架 13 上装有弹性卡扣。\n'
          f'## 图中标记说明\n{HDR}\n{ROWS}\n')

    def n_of(bad, tag):
        return sum(1 for x in bad if f'→ {tag}' in x)

    # 合规总案：四条判据都真读到，且一条都不开火
    bad, notes, seen = cf.check_text(P, OK)
    assert_(bad == [], f'合规说明书底稿被误判红: {bad}', None)
    assert_(seen == {'N1', 'N2', 'N3', 'N4'}, f'合规案未把四条判据都判到: {sorted(seen)}', None)

    # N1 缺列（掉「所在图号」）：整表报一条，且不逐行放大
    bad, notes, seen = cf.check_text(P, OK.replace(HDR, '| 标记 | 名称 |\n|---|---|'))
    assert_(n_of(bad, 'N1') == 1 and "['所在图号']" in bad[0] and n_of(bad, 'N2') == 0,
            f'N1 缺列读数不对（放大成逐行、或整表一条都没报）: {bad}', None)

    # N1 识别列掉一格也要认得出是这张表：报"缺名称列"而不是"没有对照表"
    bad, _, _ = cf.check_text(P, OK.replace(HDR, '| 标记 | 编号 | 所在图号 |\n|---|---|---|'))
    assert_(n_of(bad, 'N1') == 1 and "['名称']" in bad[0],
            f'掉识别列时成因说错（应报缺名称列，而不是无表）: {bad}', None)

    # N1 有附图说明节却整张表缺席 → 判红（散文写的附图说明不能白过）
    bad, notes, seen = cf.check_text(P, OK.split('## 图中标记说明')[0])
    assert_(n_of(bad, 'N1') == 1 and '却没有图中标记说明对照表' in bad[0],
            f'02 目录下无对照表的说明书未判红: {bad} / {notes}', None)

    # N1 域外豁免的另一侧：交底书有附图说明节只报未判，不硬判红
    bad, notes, seen = cf.check_text('01_交底书/交底书_T.md',
                                     '# 交底书\n## 附图说明\n图 1 为整体示意。\n')
    assert_(bad == [] and 'N1 未判' in ''.join(notes) and seen == set(),
            f'交底书被硬判红，或未如实说未判: {bad} / {notes}', None)

    # N2 标记不是阿拉伯数字
    bad, _, seen = cf.check_text(P, OK.replace(ROWS, '| 十二 | 底座 | 1、2 |\n| 13 | 支架 | 1 |'))
    assert_(n_of(bad, 'N2') == 1 and '不是阿拉伯数字' in bad[0] and 'N2' in seen,
            f'汉字标记未判红: {bad}', None)

    # N2 三格逐格必填（名称空着）
    bad, _, _ = cf.check_text(P, OK.replace(ROWS, '| 12 | 底座 | 1、2 |\n| 13 |  | 1 |'))
    assert_(n_of(bad, 'N2') == 1 and '「名称」空着' in bad[0], f'空格子未判红: {bad}', None)

    # N2 同名两标记 / 同号两名：表内自相矛盾必须各判一条
    bad, _, _ = cf.check_text(P, OK.replace(ROWS, ROWS + '\n| 14 | 支架 | 2 |'))
    assert_(n_of(bad, 'N2') == 1 and '既挂 13 又挂 14' in bad[0],
            f'同一名称挂两个标记未判红: {bad}', None)
    bad, _, _ = cf.check_text(P, OK.replace(ROWS, ROWS + '\n| 13 | 卡箍 | 1 |'))
    assert_(n_of(bad, 'N2') == 1 and '既指「支架」又指「卡箍」' in bad[0],
            f'同一标记挂两个名称未判红: {bad}', None)

    # N3 正文号与表不符（借"同号异名"对账方向，词表取自权威表）
    bad, _, seen = cf.check_text(P, OK.replace('所述支架 13 上', '所述支架 15 上'))
    assert_(n_of(bad, 'N3') == 1 and '而表内「支架」的标记是 13' in bad[0] and 'N3' in seen,
            f'正文标记与表错配未判红: {bad}', None)

    # N3 合规侧：正文与表一致时不许开火（上面总案已核，这里核"未核"注记不该出现）
    bad, notes, _ = cf.check_text(P, OK)
    assert_(not any('B3 未核' in x or 'N3 未核' in x for x in notes),
            f'一致正文被记成未核: {notes}', None)

    # N3 取最长匹配：表里同时有「支架」和「弹性支架」时，"弹性支架 14"不许按短名「支架」判错
    bad, _, _ = cf.check_text(P, OK.replace(ROWS, ROWS + '\n| 14 | 弹性支架 | 1 |')
                              .replace('装有弹性卡扣', '装有弹性支架 14'))
    assert_(bad == [], f'最长匹配失效，按短名误判了: {bad}', None)

    # N3 不许误伤：名称前还有未登记前缀（"合金支架"里的"支架"）→ 只记未核
    bad, notes, _ = cf.check_text(P, OK.replace('所述支架 13 上', '所述合金支架 15 上'))
    assert_(bad == [] and any('N3 未核' in x for x in notes),
            f'更长前缀被折成违规或缺少未核说明: {bad} / {notes}', None)

    # N3 不许误伤：紧贴单位的量值不是标记号。这里刻意用"底座 14mm"——名称正好落在
    # 边界上、数字又与表内 12 不符，豁免支路一关就必然开火（"底座厚度 12mm"那种写法
    # 连名称匹配都到不了，测不到这条豁免）。
    bad, _, _ = cf.check_text(P, OK.replace('所述底座 12 与', '底座 14mm 以上的规格同样成立，所述底座 12 与'))
    assert_(bad == [], f'带单位的量值被当成正文标记错配: {bad}', None)

    # N4 所在图号没声明过 → 判红
    bad, _, seen = cf.check_text(P, OK.replace('| 13 | 支架 | 1 |', '| 13 | 支架 | 7 |'))
    assert_(n_of(bad, 'N4') == 1 and '不在本文声明的图号集合' in bad[0] and 'N4' in seen,
            f'未声明图号未判红: {bad}', None)

    # N4 不许自证：表里自己写"图 7"不算声明了一个图号——正文遮掉表格行才作数
    bad, _, _ = cf.check_text(P, OK.replace('| 13 | 支架 | 1 |', '| 13 | 支架 | 图 7 |'))
    assert_(n_of(bad, 'N4') == 1, f'表内自写图号被当成已声明（N4 成了自证）: {bad}', None)

    # N4 未判一侧：正文一个图号都没声明
    bad, notes, seen = cf.check_text(P, OK.replace(
        '图 1 为本机构整体示意图；图 2 为底座剖视图。', '附图见随文图纸。'))
    assert_(bad == [] and any('N4 未判' in x for x in notes),
            f'正文无图号声明时未走未判: {bad} / {notes}', None)

    # 空表骨架：有表头零行 → 未判不判红（但 N1 算判到了，缺列才有机会出声）
    bad, notes, seen = cf.check_text(P, OK.replace(ROWS, ''))
    assert_(bad == [] and '只有表头没有数据行' in ''.join(notes) and seen == {'N1'},
            f'空表骨架读数不对: {bad} / {notes} / {sorted(seen)}', None)

    # 适用域第三条轴：路径不在 02、正文既不写「附图说明」也不写「标记说明」，
    # 只有一张被分类器认出的表 → 必须进域真判。（早先这档误用 OK 当夹具，
    # 而 OK 的节标题里就带"附图说明"，命中的是第二条轴，第三轴等于没测。）
    only_table = ('# 部件与图号对照\n## 具体实施方式\n所述底座 12 与支架 13 连接（见图 1、图 2）。\n'
                  f'## 部件清单\n{HDR}\n{ROWS}\n')
    assert_('附图说明' not in only_table and '标记说明' not in only_table,
            '第三轴夹具里混进了第二轴的关键词，测不到要测的那条轴', None)
    bad, notes, seen = cf.check_text('01_交底书/交底书_T.md', only_table)
    assert_(bad == [] and seen == {'N1', 'N2', 'N3', 'N4'},
            f'第三条适用域轴（表被认出即域内）未生效: {sorted(seen)} / {notes}', None)

    # 域外文书：一句"未判"交代成因，不折成合规
    bad, notes, seen = cf.check_text('01_交底书/交底书_T.md', '# 交底书\n普通内容。\n')
    assert_(bad == [] and len(notes) == 1 and '非附图文书' in notes[0],
            f'域外文书未走三态或未说明成因: {bad} / {notes}', None)

    # 整包三态与退出码：rc=0 真判 / rc=2 域内为零 / rc=2 输入不可用
    with tempfile.TemporaryDirectory() as d:
        pkg = os.path.join(d, '包_专利交付包')
        ok_dir = os.path.join(pkg, '02_申请文件')
        os.makedirs(ok_dir)
        doc = os.path.join(ok_dir, '说明书.md')
        # 域外文书留在树里：域内为零与"树里没有文件"是两个不同的 rc=2 成因，
        # 只建一棵空树会让后者顶掉前者，那条分支就等于没测。
        open(os.path.join(pkg, 'README.md'), 'w', encoding='utf8').write('# 包 README\n普通内容。\n')
        open(doc, 'w', encoding='utf8').write(OK)
        r = run([PY, f'{S}/check_figure_labels.py', pkg, '--all'])
        assert_(r.returncode == 0 and '实核附图标记文书 1 份' in r.stdout,
                '整包 --all 未把 02 目录内文书计入实核数', r)
        open(doc, 'w', encoding='utf8').write(
            OK.replace('所述支架 13 上', '所述支架 15 上'))
        r = run([PY, f'{S}/check_figure_labels.py', pkg, '--all'])
        assert_(r.returncode == 1 and '→ N3' in r.stdout, '脏文书未按要求判红', r)
        os.remove(doc)
        r = run([PY, f'{S}/check_figure_labels.py', pkg, '--all'])
        assert_(r.returncode == 2 and '没有一份落在附图标记适用域内' in r.stdout,
                '域内文书为零时被当成"已通过"', r)
        r = run([PY, f'{S}/check_figure_labels.py', os.path.join(d, '不存在.md')])
        assert_(r.returncode == 2 and '不存在.md' in r.stdout and '既不是文件也不是目录' in r.stdout,
                '路径不存在未按要求说清成因并 fail-closed', r)
    print('PASS check_figure_labels（N1–N4 各成对 + 域内分轴 + 不许自证 + rc=2 三态）')


def test_verify_search_report():
    """检索报告门禁 V1–V6：默认不碰网络（fetch 被桩替），网络路径另有 live 档。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('verify_search_report',
                                       os.path.join(S, 'verify_search_report.py'))
    vsr = ilu.module_from_spec(spec)
    spec.loader.exec_module(vsr)

    HDR = ('| # | 类型 | 标识符 | 标题 | 关键日期 | 核验出处 | 核验日期 |\n'
           '|---|---|---|---|---|---|---|\n')
    P = '| 1 | 专利 | CN110404188A | 一种节点 | 公开日 2019-07-26 | CNIPA 著录页 | 2026-09-25 |'
    A = '| 2 | 预印本（arXiv） | arXiv:1706.03762 | Attention | 2017-06-12 | arXiv 摘要页 | 2026-09-25 |'
    D = '| 3 | 论文 | doi:10.1038/nature14539 | Deep learning | 2015-05-27 | Nature | 2026-09-25 |'

    def rpt(rows, hdr=HDR):
        return '# 检索报告\n## 2. 已核验条目\n' + hdr + ''.join(r + '\n' for r in rows)

    orig_fetch, orig_probe = vsr.fetch_json, vsr.verify_online
    try:
        # 必绿：三条合规条目全字段齐、在线源说"有"——且在线计数只算 DOI+arXiv 两条
        vsr.fetch_json = lambda url: ('ok', b'<entry>')
        bad, notes, ck, n_ent = vsr.check_report('r.md', rpt([P, A, D]))
        assert_(bad == [], f'合规检索报告被 V1/V2/V3 误判: {bad}', None)
        assert_(ck == 2, f'在线核成应只数 DOI+arXiv 两条（专利不得算在线），实得 {ck}', None)
        # 合规侧那一档必须是"判过且合规"，不能是"没看着所以绿"
        assert_(not any('V4 未判' in x for x in notes),
                f'合规报告里 arXiv 已标预印本，V4 却报未判（说明列没被认出来）: {notes}', None)

        # V4 三档：标错→必红；没有「类型」列→未判；表里没有 arXiv 条目→未判
        bad, notes, _, _ = vsr.check_report('r.md', rpt([P, A.replace('预印本（arXiv）', '论文'), D]))
        assert_(len(bad) == 1 and 'V4' in bad[0] and '预印本' in bad[0],
                f'arXiv 行标成"论文"没被 V4 抓到（或牵连报出别的）: {bad}', None)
        HDR2 = ('| # | 标识符 | 标题 | 关键日期 | 核验出处 | 核验日期 |\n'
                '|---|---|---|---|---|---|\n')
        A2 = '| 2 | arXiv:1706.03762 | Attention | 2017-06-12 | arXiv 摘要页 | 2026-09-25 |'
        bad, notes, _, _ = vsr.check_report('r.md', rpt([A2], hdr=HDR2))
        assert_(bad == [] and any('没有「类型」列' in x and 'V4 未判' in x for x in notes),
                f'缺「类型」列被折成违规或折成合规（该走未判）: bad={bad} notes={notes}', None)
        bad, notes, _, _ = vsr.check_report('r.md', rpt([P, D]))
        assert_(bad == [] and any('没有 arXiv 条目' in x and 'V4 未判' in x for x in notes),
                f'无 arXiv 条目时 V4 未报未判: bad={bad} notes={notes}', None)

        # V3 必红：源明确说查无此项
        vsr.fetch_json = lambda url: ('absent', None)
        bad, _, ck, _ = vsr.check_report('r.md', rpt([A, D]))
        assert_(len(bad) == 2 and all('V3' in b for b in bad),
                f'源说查无此项却未判 V3: {bad}', None)
        assert_(ck == 0, f'未核成却计数 {ck}', None)

        # V3 三态：源不可达 → 只报未核，不折成违规也不折成合规
        vsr.fetch_json = lambda url: ('unreachable', None)
        bad, notes, ck, n_ent = vsr.check_report('r.md', rpt([A, D]))
        assert_(bad == [], f'网络不可达被判成引用造假: {bad}', None)
        assert_(len(notes) == 2 and ck == 0,
                f'不可达未走三态（notes={notes}, ck={ck}）', None)

        # arXiv 特有的坑：不存在的 id 也回 200，必须数 <entry> 而不是看状态码
        vsr.fetch_json = lambda url: ('ok', b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
        bad, _, _, _ = vsr.check_report('r.md', rpt([A]))
        assert_(len(bad) == 1 and 'V3' in bad[0],
                f'arXiv 空 feed 被当成存在: {bad}', None)

        # V1 必红：无可机检标识
        vsr.fetch_json = lambda url: ('ok', b'<entry>')
        bad, _, _, _ = vsr.check_report('r.md', rpt(
            ['| 4 | 网页 | 某博客文章 | 无标识 | 2020-01-01 | URL | 2026-09-25 |']))
        assert_(len(bad) == 1 and 'V1' in bad[0], f'无标识条目未判 V1: {bad}', None)

        # V2 必红：专利缺关键日期 + 缺核验出处
        vsr.fetch_json = lambda url: ('ok', b'<entry>')
        bad, _, _, _ = vsr.check_report('r.md', rpt(
            ['| 1 | 专利 | CN110404188A | 一种节点 |  |  | 2026-09-25 |']))
        assert_(len(bad) == 2 and all('V2' in b for b in bad),
                f'缺字段未逐条判 V2: {bad}', None)

        # 缺列只报一条：整列不存在时不得把一条缺陷放大成 N 条"未填"
        # （列名与单元格要同时去掉那一列，否则测的是"行列数不符"而不是"缺列"）
        nohdr = ('| # | 类型 | 标识符 | 标题 | 关键日期 | 核验日期 |\n'
                 '|---|---|---|---|---|---|\n')
        P6 = '| 1 | 专利 | CN110404188A | 一种节点 | 公开日 2019-07-26 | 2026-09-25 |'
        bad, _, _, _ = vsr.check_report('r.md', rpt([P6], hdr=nohdr))
        assert_(len(bad) == 1 and '缺列' in bad[0] and 'source' in bad[0],
                f'整列缺失被放大成逐条违规: {bad}', None)
        # 配套必绿：把缺的列补回去，同一行必须零违规
        bad, _, _, _ = vsr.check_report('r.md', rpt([P]))
        assert_(bad == [], f'补回列后仍判违规（缺列判定过头）: {bad}', None)

        # 行列数与表头不符：宁可报格式错，也不按位取列把"出处"读成"核验日期"
        bad, _, _, _ = vsr.check_report('r.md', rpt([P + ' 多余 |']))
        assert_(len(bad) == 1 and '列与表头' in bad[0],
                f'多出一格的行未被报出（可能已被按位读错列）: {bad}', None)

        # 无小节与无表分别给成因（两者修法不同）
        bad, _, _, _ = vsr.check_report('r.md', '# 检索报告\n正文里没有小节\n')
        assert_(len(bad) == 1 and '小节' in bad[0], f'无小节成因不对: {bad}', None)
        bad, _, _, _ = vsr.check_report('r.md', '# 检索报告\n## 2. 已核验条目\n表还没填\n')
        assert_(len(bad) == 1 and '没有表格' in bad[0], f'无表成因不对: {bad}', None)
    finally:
        vsr.fetch_json, vsr.verify_online = orig_fetch, orig_probe

    # 公开号形状必须与 R5 同一处定义：两份正则各自漂移时，报告里"合法"的号
    # 可能在铁律门禁那边判"越界"，反之亦然。
    s2 = ilu.spec_from_file_location('cir_cmp', os.path.join(S, 'check_iron_rules.py'))
    cir = ilu.module_from_spec(s2)
    s2.loader.exec_module(cir)
    assert_(vsr.PUB_NO.pattern == cir.PUB_NO.pattern,
            f'V1 与 R5 的公开号形状各写了一份：{vsr.PUB_NO.pattern!r} vs {cir.PUB_NO.pattern!r}',
            None)

    # ---- CLI 档（全部走 --offline 或死代理，不碰真网络）----
    with tempfile.TemporaryDirectory() as d:
        good = os.path.join(d, '检索报告.md')
        open(good, 'w', encoding='utf8').write(rpt([P, A, D]))
        r = run([PY, f'{S}/verify_search_report.py', good, '--offline'])
        assert_(r.returncode == 0 and '在线核成 0 条' in r.stdout and '未核' in r.stdout,
                '--offline 合规报告未全绿或未说明未核', r)
        r = run([PY, f'{S}/verify_search_report.py', os.path.join(d, '不存在.md')])
        # 必须指名"哪条路径、因为什么"：只核 '输入不可用' 前缀的话，
        # "一个文件都没挑出来"那条消息会把"路径不存在"的失守顶包（变异实测如此）
        assert_(r.returncode == 2 and '不存在.md' in r.stdout and '既不是文件也不是目录' in r.stdout,
                '路径不存在未按要求说清成因并 fail-closed', r)
        # 目录模式：只挑 *检索*.md，别的文书不得混进来被判
        open(os.path.join(d, '交底书.md'), 'w', encoding='utf8').write('# 交底书\n无关内容\n')
        r = run([PY, f'{S}/verify_search_report.py', d, '--offline'])
        assert_(r.returncode == 0 and good in r.stdout and '交底书.md' not in r.stdout,
                '目录模式挑文件不对', r)
        # 死代理强制"源不可达"：--require-online 必须 rc=2 说"本次判定不成立"，
        # 既不得判绿（假装核过）也不得判红（把网络故障算成造假）
        env = dict(os.environ, https_proxy='http://127.0.0.1:9/',
                   HTTP_PROXY='http://127.0.0.1:9/', http_proxy='http://127.0.0.1:9/')
        p = subprocess.run([PY, f'{S}/verify_search_report.py', good, '--require-online'],
                           cwd=d, capture_output=True, text=True, env=env)
        assert_(p.returncode == 2 and '本次判定不成立' in p.stdout,
                '--require-online 在源全不可达时未 rc=2', p)
        r = run([PY, f'{S}/verify_search_report.py', good])
        assert_(r.returncode == 0, '默认档（不带 --require-online）受网络故障影响被误判红', r)

    # V5/V6：检索式与分类号的句法形状（§2.1 里机械判得动的部分）。
    # 第一档刻意直接用 templates §10 那行示范式：判据打自己的范本是最贵的一种假红。
    with open(os.path.join(ROOT, 'references', 'templates.md'), encoding='utf-8') as f:
        tpl = [l.strip() for l in f if l.strip().startswith('- 检索式：')][0]
    def qm(body):
        return vsr.check_method('检索_X.md', body)
    b, n = qm(tpl + '\n')
    assert_(b == [] and n == [], f'模板 §10 的示范检索式被 V5/V6 误伤: {b} / {n}', None)
    b, n = qm('# 报告\n- 检索式：锁扣 弹性 卡齿 lock mechanism\n'
              '- 分类号：A42B3/20、A61F5/00\n')
    assert_(b == [] and n == [], f'合规两段式报告被误伤: {b} / {n}', None)
    b, _ = qm('# 报告\n- 检索式：一种用于康复训练的锁定装置及其工作方法\n')
    assert_(any('V5' in x and '一整串无空格中文' in x for x in b),
            f'整串中文检索式未被 V5 抓到: {b}', None)
    b, _ = qm('# 报告\n- 检索式：a b c d e f g h i\n')
    assert_(any('V5' in x and '不在 2–8 之内' in x for x in b),
            f'块数越界未被 V5 抓到: {b}', None)
    b, _ = qm('# 报告\n- 检索式：lockmechanism\n')
    assert_(any('V5' in x and '1 个语义块' in x for x in b),
            f'单个长块未被 V5 抓到: {b}', None)
    b, _ = qm('# 报告\n- 检索式：锁扣 方法 系统\n')
    assert_(any('V5' in x and '碎块/泛义词' in x for x in b),
            f'泛义词块未被 V5 抓到: {b}', None)
    b, _ = qm('# 报告\n- 检索式：锁扣 弹性 增\n')
    assert_(any('V5' in x and '（增）' in x for x in b),
            f'单字碎块未被 V5 抓到: {b}', None)
    b, n = qm('# 报告\n- 检索式：【待填写】\n')
    assert_(b == [] and any('V5 未判' in x and '占位' in x for x in n),
            f'占位检索式被折成违规或不吭声: {b} / {n}', None)
    b, _ = qm('# 报告\n- 检索式：\n')
    assert_(any('V5' in x and '是空的' in x for x in b), f'空检索式没被 V5 抓到: {b}', None)
    b, n = qm('# 报告\n只有条目表，没有检索式行\n')
    assert_(b == [] and any('V5 未判' in x for x in n) and any('V6 未判' in x for x in n),
            f'两行都缺时应双双未判而不是合规: {b} / {n}', None)
    b, n = qm('# 报告\n- 检索式：锁扣 弹性\n')
    assert_(b == [] and any('V6 未判' in x for x in n) and not any('V5 未判' in x for x in n),
            f'V6 未判连带把 V5 也说成未判: {b} / {n}', None)
    b, _ = qm('# 报告\n- 分类号：42B3、A42B3/20\n')
    # 只断"坏的那一条被点名、好的一条没进来"：消息里本身举着正例（如 A42B3/20），
    # 拿"消息里不许出现 A42B3/20"当检验会被判据自己的复述挡住——那是假红的检验形状。
    assert_(len(b) == 1 and b[0].startswith('检索_X.md: 分类号 42B3 不是')
            and b[0].count('IPC/CPC 形状') == 1,
            f'坏分类号没被抓到、或把好的也一起报了: {b}', None)
    b, _ = qm('# 报告\n- 检索式：(S1) 锁扣 AND 弹性；(S2) IPC 42B3\n')
    assert_(any('分类号 42B3 不是' in x for x in b),
            f'检索式里挂在 IPC 后面的坏分类号没人管: {b}', None)
    # ---- live 档：真打 Crossref / arXiv，无网络时如实 SKIP ----
    if orig_fetch('https://api.crossref.org/works/10.1038/nature14539')[0] == 'unreachable':
        print('     SKIP 检索报告 live 档：本机网络到不了核验源，不把"没跑"说成"跑过"')
    else:
        # 每个源都先立一根控制探针，再把正反两判一起挂在它下面：
        # 服务限流/错误页与"查无此项"在返回体上同形，没有控制时"真 id 被判不存在"
        # 这种红分不清是判据坏了还是网络坏了（第 16 轮在临时副本里实测到 arXiv 限流）。
        ctl_doi = vsr.verify_online('doi', '10.1038/nature14539')
        if ctl_doi != 'ok':
            print(f'     SKIP live 档 DOI 两判：真 DOI 本次读到 {ctl_doi}，'
                  '源侧读数此刻不可信，不把服务异常说成引用造假（SKIP 不计入通过）')
        else:
            assert_(vsr.verify_online('doi', '10.1038/definitely-not-a-real-doi-99999') == 'absent',
                    '假 DOI 未被源判为不存在（控制探针本次正常，判定可信）', None)
        # arXiv 的控制探针：无查询词的列表页一定返回条目；返回 0 条即"0 entry"
        # 这种读法此刻不可信，两判一起跳过。
        ctl = vsr.fetch_json('https://export.arxiv.org/api/query?max_results=1')
        if ctl[0] != 'ok' or b'<entry' not in (ctl[1] or b''):
            print('     SKIP live 档 arXiv 两判：控制探针本次没返回任何条目，'
                  '无从区分"查无此项"与"服务异常"（SKIP 不计入通过）')
        else:
            assert_(vsr.verify_online('arxiv', '1706.03762') == 'ok',
                    '真 arXiv id 被源判为不存在（控制探针本次正常，判定可信）', None)
            assert_(vsr.verify_online('arxiv', '9999.99999') == 'absent',
                    '假 arXiv id 未被源判为不存在（控制探针本次正常，判定可信）', None)
        assert_(vsr.verify_online('patent', 'CN110404188A') == 'unreachable',
                '专利公开号在无源可用时被当成了"核过"', None)

        print('PASS verify_search_report（V1–V6 成对 + 三态 + 模板示范行不误伤 + 死代理 rc=2 '
              '+ live 档两源各配控制探针）')


def test_search_report_docx_channel():
    """检索报告的 docx 通道：V 读的是权威引用清单，交付场景里它就是一份 Word 报告。
    上一轮给四把表门禁接 docx 时 V 被留在外面——同一份 read_text，两套读法。"""
    try:
        import docx  # noqa: F401  python-docx
    except ImportError:
        SKIPPED.append('search_report_docx_channel')
        print('SKIP search_report_docx_channel（本机无 python-docx，造不出 Word 检索报告）')
        return
    from docx import Document
    import shutil
    import zipfile

    H = ['#', '类型', '标识符', '标题', '关键日期', '核验出处', '核验日期']

    def rep(path, rows):
        doc = Document()
        doc.add_heading('2. 已核验条目', level=2)
        t = doc.add_table(rows=len(rows), cols=len(rows[0]))
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                t.cell(i, j).text = v
        doc.save(path)

    with tempfile.TemporaryDirectory() as d:
        ok = os.path.join(d, '检索_报告.docx')
        rep(ok, [H, ['1', '专利', 'CN220572449U', '一种脚手架减振节点',
                     '2024-03-15', 'CNIPA 著录', '2026-09-20']])
        r = run([PY, f'{S}/verify_search_report.py', ok, '--offline'])
        assert_(r.returncode == 0 and '条目 1 条' in r.stdout,
                f'Word 检索报告未被 V 真判（表格没吃到）: {show(r)}', r)

        nodate = os.path.join(d, '检索_缺日期.docx')
        rep(nodate, [H, ['1', '专利', 'CN220572449U', '一种节点',
                         '2024-03-15', 'CNIPA 著录', '']])
        r = run([PY, f'{S}/verify_search_report.py', nodate, '--offline'])
        assert_(r.returncode == 1 and '未填核验日期 → V2' in r.stdout,
                f'Word 报告里缺核验日期未判红: {show(r)}', r)

        noid = os.path.join(d, '检索_无标识.docx')
        rep(noid, [H, ['1', '论文', '见附件', '一种节点',
                       '2024-03-15', 'Crossref', '2026-09-20']])
        r = run([PY, f'{S}/verify_search_report.py', noid, '--offline'])
        assert_(r.returncode == 1 and '无可机检标识' in r.stdout and '→ V1' in r.stdout,
                f'Word 报告里"见附件"式标识未判红: {show(r)}', r)

        # 目录模式：只有 Word 件时也必须挑得到（旧逻辑只收 .md，等于对 Word 包完全隐形）
        only = os.path.join(d, '只有docx包')
        os.makedirs(only)
        shutil.copy(ok, os.path.join(only, '检索_Y.docx'))
        r = run([PY, f'{S}/verify_search_report.py', only, '--offline'])
        assert_(r.returncode == 0 and '条目 1 条' in r.stdout,
                f'目录模式未收 .docx 检索报告: {show(r)}', r)

        # 同名成对：挑可编辑源 .md，且必须说清"这份 docx 没参与判定"
        pair = os.path.join(d, '成对包')
        os.makedirs(pair)
        shutil.copy(ok, os.path.join(pair, '检索_X.docx'))
        # md 侧故意带一条 V1 违规：读到的红必须来自 md，而不是两份混在一起
        open(os.path.join(pair, '检索_X.md'), 'w', encoding='utf8').write(
            '# 检索报告\n## 2. 已核验条目\n'
            '| ' + ' | '.join(H) + ' |\n|' + '---|' * len(H) + '\n'
            '| 1 | 专利 | CN111 | 一种节点 | 2024-03-15 | CNIPA | 2026-09-20 |\n')
        r = run([PY, f'{S}/verify_search_report.py', pair, '--offline'])
        hits = [x for x in r.stdout.splitlines() if '→ V1' in x]
        assert_(r.returncode == 1 and len(hits) == 1 and '检索_X.md' in hits[0],
                f'成对时没挑 md（或两份都算进去了）: {show(r)}', r)
        assert_('条目 1 条' in r.stdout and '与同名 .md 成对' in r.stdout,
                f'成对挑选没说出被丢的那份，或条目数被翻倍: {show(r)}', r)

        # fail-closed：恶意 Word 件必须 rc=2 说成因，不许 traceback 的退码 1 冒充违规
        evil = os.path.join(d, '检索_恶意.docx')
        with zipfile.ZipFile(ok) as src, zipfile.ZipFile(evil, 'w') as dst:
            for n in src.namelist():
                b = src.read(n)
                if n == 'word/document.xml':
                    b = b.replace(b'<w:document',
                                  b'<!DOCTYPE w:document [<!ENTITY x "y">]>\n<w:document', 1)
                dst.writestr(n, b)
        r = run([PY, f'{S}/verify_search_report.py', evil])
        assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'DOCTYPE' in r.stdout,
                f'含 DTD 的 Word 检索报告未按要求拒绝并说成因: {show(r)}', r)

        broken = os.path.join(d, '检索_坏件.docx')
        open(broken, 'wb').write(b'not a zip')
        r = run([PY, f'{S}/verify_search_report.py', broken])
        assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'Traceback' not in r.stderr,
                f'非 zip 的 .docx 抛裸异常或退码不是 2: {show(r)} / {r.stderr[-160:]}', r)
    print('PASS search_report_docx_channel（Word 报告真判 + V1/V2 开火 + 成对挑 md + 两档 fail-closed）')


def test_check_claims():
    """权利要求形状门禁 Q1–Q13：每条各一支开火夹具 + 一支合规 + 三态 + docx 通道。

    合规档必须先过：Q4/Q5 这种"两支互斥"的判据一旦把合规写法也判红，整套就是永久红灯。
    q4 档刻意写成"引用号都在前"，让它只点亮 Q4——同档撞两支判据时，读数说不清是谁在咬。
    Q9–Q11（法源换成《专利审查指南》2023）按同一条规矩配档：每支必红档都用 `fired()` 断言
    "这一档只点亮它自己那一支"，反向档则钉住中文没有词边界时那些同形却合规的写法。
    Q13（指南 §3.3.2：从权引用部分须重述被引权项的主题名称）规格点名"不许误伤的四侧各要一档常驻"，
    所以它配了八档：①正确重述 ②多项择一（同组静默＋跨组静默＋全不同名才开火——跨组那一档是
    "择一口径"的判别量，把它改成"必须同名于全部被引项"就只有它看得见） ③并列独立权利要求零开火
    ④带限定词的合法写法静默／丢限定词开火，外加两档三态（被引号查无此号、引用部分认不出形状）、
    一档"没有从属权利要求⇒不适用，连提示行都不出"。三态那两档的判据是 note 行里有 Q13、
    违规行里没有——把未判折成合规与折成违规是同一种错，两头都钉。
    """
    TBL = ('## 图中标记说明\n| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
           '| 1 | 躯干框架 | 1 |\n| 2 | 锁扣本体 | 1 |\n')
    OK = ('# 说明书\n## 权利要求书\n'
          '1. 一种锁扣装置，包括躯干框架（1）与锁扣本体（2），其特征在于：所述锁扣本体（2）与所述躯干框架（1）铰接。\n'
          '2. 根据权利要求 1 所述的锁扣装置，其特征在于：所述锁扣本体（2）的弹臂拉脱力 90N。\n'
          '3. 根据权利要求1或2所述的锁扣装置，其特征在于：所述弹臂为钛合金。\n'
          # 4–8 是纯合规填充：Q6 判从属条数（发明 7–10／实用新型 4–8），
          # 这份「合规档」若只有 2 项从属，合不合规就说不清了。
          + ''.join(f'{i}. 根据权利要求 1 所述的锁扣装置，其特征在于：所述锁扣本体设有卡齿{i}。\n'
                  for i in range(4, 9)) + TBL)

    def mkpkg(root, body):
        os.makedirs(os.path.join(root, '02_申请文件'), exist_ok=True)
        open(os.path.join(root, '02_申请文件', '说明书.md'), 'w', encoding='utf8').write(body)
        return root

    def fired(out):
        """违规行（非 note 行）里点到的判据号集合——开火与否按整号取，不按子串。

        两个实测的坑都在这把尺子上：①三态的 note 行也写 `→ Q5 未核`／`→ Q6 部分未判`，
        拿子串判"开火"会把未判读成判红（Q6 那档已经踩过一次）；②`→ Q1` 是 `→ Q11` 的前缀，
        逐条 `in` 判会把 Q11 的开火读成 Q1 的开火。Q9–Q11 的归因（"这一档只点亮它自己"）
        全靠整号集合，函数头那句"同档撞两支判据时读数说不清是谁在咬"到这里才有机器可判的形状。
        """
        return set(re.findall(r'→ (Q\d+)(?!\d)',
                              '\n'.join(ln for ln in out.splitlines()
                                        if ln.startswith('  ') and not ln.startswith('  note '))))

    def ledger(out):
        """收尾那行的覆盖账 (违规数, 实判判据数)——第二个数就是本轮缺陷的主语。

        `实判判据 N 条` 判的是覆盖（这条判据的适用域读到了没有），不是开火；所以它**不能**
        拿 fired() 去核：合规档 fired() 是空集，而覆盖账必须是 13，两者一比就等于把
        "跑了没发现问题"折成"根本没跑"（第 36 轮 Q7/Q8、第 39 轮 Q12 都是这一形状，
        合规模具因此只自报 9 条）。这里只按门禁自己打印的那一行逐字取数，不抄判据号。
        """
        m = re.search(r'违规 (\d+)｜实判判据 (\d+) 条', out)
        assert_(m is not None, f'门禁没打印覆盖账那一行（读者拿不到分母）: {out}', None)
        return int(m.group(1)), int(m.group(2))

    with tempfile.TemporaryDirectory() as d:
        ok = mkpkg(os.path.join(d, 'ok'), OK)
        r = run([PY, f'{S}/check_claims.py', ok])
        # 覆盖账主钉：三节齐（说明书＋权利要求书＋标记对照表）、形状全合规 ⇒ 违规 0 且 13 条。
        # 13 = **适用数**（Q1–Q6、Q9–Q11、Q13 判在解析出的八项权项上，Q7／Q8／Q12 扫过这一节就记），
        # 不是开火数——这一档开火 0 条，所以拿 fired() 核对分母等于把"跑了没发现问题"
        # 折成"根本没跑"（第 36 轮 Q7/Q8、第 39 轮 Q12 的登记都写在 `if 命中:` 里，
        # 合规权要因此只自报 9 条）。缺陷若退回原位，第一红就是这一条。
        assert_(r.returncode == 0 and ledger(r.stdout) == (0, 13) and '→ Q' not in r.stdout,
                f'合规权要被判红，或十三条没各判到: {show(r)}', r)
        # 填充本身要合规：7 项从属两档都容得下，所以既不该红、也不该冒出"部分未判"的噪声
        assert_('Q6 部分未判' not in r.stdout, f'两档都容得下时 Q6 仍报未判: {show(r)}', r)

        # ── 覆盖账常驻钉：三节齐（说明书＋权利要求书＋标记对照表）、形状全合规 ──
        # 上面那档钉的是**分母等于适用数**（12），不是分母等于开火数：同一份读数里 fired() 恒为空集，
        # 所以"节面三条只在开火时才记进分母"那个缺陷只有覆盖账看得见。
        # 这一档钉的是同一件事的另一半：合计行也得把这份"跑了、没发现问题"的包算成**已判 1 个包**
        # （`judged += 1 if seen else 0` 走的是包级账，跟 len(seen) 不是同一格）——
        # 少报这一格，读者从合计行照样会把"读到了没问题"读成"这包没人判过"，同一种把已判折成未报。
        assert_(fired(r.stdout) == set() and '实判 1 个包' in r.stdout and '合计违规 0' in r.stdout,
                f'合规包（零开火）没被合计行算作已判的 1 个包: {show(r)}', r)
        # 适用域少一格、分母就必须跟着少一格：去掉「标记｜名称」对照表 ⇒ Q5 没得对照 ⇒ 12 条。
        # 这一档证明那个 13 是现算的覆盖账、不是写死的常量；反方向（把没读到的折成已判）
        # 由下面 noclaims 档的"0 条 + 实判 0 个包"钉住。
        p = os.path.join(d, 'nomarks')
        mkpkg(p, OK.replace(TBL, ''))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and ledger(r.stdout) == (0, 12) and '→ Q5 未判' in r.stdout,
                f'去掉标记对照表后覆盖账没跟着让出 Q5 这一格（未判被折成已判）: {show(r)}', r)

        p = os.path.join(d, 'q1')
        mkpkg(p, OK.replace('\n3. 根据权利要求1或2', '\n4. 根据权利要求1或2'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '不是从 1 起的连续号' in r.stdout and '→ Q1' in r.stdout,
                f'权项跳号未被 Q1 抓到: {show(r)}', r)

        p = os.path.join(d, 'q2')
        mkpkg(p, OK.replace('1. 一种锁扣装置', '3. 一种锁扣装置')
                .replace('2. 根据权利要求 1 所述', '1. 根据权利要求 3 所述')
                .replace('3. 根据权利要求1或2所述', '2. 根据权利要求1或3所述'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '排在从属权利要求' in r.stdout and '→ Q2' in r.stdout,
                f'独权排在从权之后未被 Q2 抓到: {show(r)}', r)

        p = os.path.join(d, 'q3')
        mkpkg(p, OK.replace('2. 根据权利要求 1 所述', '2. 根据权利要求 3 所述'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '引用了在后的' in r.stdout and '→ Q3' in r.stdout,
                f'从权向后引用未被 Q3 抓到: {show(r)}', r)

        p = os.path.join(d, 'q4')
        # 3 本身是多项从属（引 1或2），4 又以它为引用基础 → Q4；引用号全都在前，Q3 不陪跑
        mkpkg(p, OK.replace('## 图中标记说明',
                            '9. 根据权利要求1或3所述的锁扣装置，其特征在于：所述弹臂表面镀硬铬。\n'
                            '## 图中标记说明'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '同为多项从属' in r.stdout and '→ Q4' in r.stdout,
                f'多项从权引多项基础未被 Q4 抓到: {show(r)}', r)
        # 同档不许顺手点亮 Q3：引用号都在前，Q4 的开火才归因得清
        assert_('→ Q3' not in r.stdout, f'Q4 夹具同时点亮 Q3，读数无法归因: {show(r)}', r)

        p = os.path.join(d, 'q5')
        mkpkg(p, OK.replace('躯干框架（1）与锁扣本体（2）', '躯干框架 1 与锁扣本体（2）'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '写在括号外' in r.stdout and '→ Q5' in r.stdout,
                f'附图标记写在括号外未被 Q5 抓到: {show(r)}', r)
        # "根据权利要求 1" 里的 1 是权项号不是标记；"拉脱力 90N" 是量值不是标记。
        # 这两处若被判红，Q5 就是一把造假红的尺子——合规档（上面第一支）同时钉着这条。

        # Q6 从属条数：红档按类型各钉一条，绿档各钉一种"不该判红"的理由。
        def q6pkg(tag, ndep):
            return mkpkg(os.path.join(d, 'q6_' + tag),
                         '# 说明书\n## 权利要求书\n1. 一种锁扣装置，包括躯干框架与锁扣本体。\n'
                         + ''.join(f'{i}. 根据权利要求 1 所述的锁扣装置，其特征在于：设有卡齿{i}。\n'
                                   for i in range(2, ndep + 2)))
        for tag, ndep, flags, want_red in (
                ('发明7', 7, ['--type', '发明'], False),      # 发明档下沿，必绿
                ('发明5', 5, ['--type', '发明'], True),       # 差 2 项，必红
                ('实用新型3', 3, ['--type', '实用新型'], True),
                ('实用新型8', 8, ['--type', '实用新型'], False),
                ('不给类型2', 2, [], True),                    # 并集 4–10 也拦得住"太薄"
                ('不给类型5', 5, [], False),                   # 并集内、只一型容得下 → 绿＋说明
                # 这两档才是"分型有没有真分对"的判别量：5 在实用新型档内、发明档外，
                # 9 反过来。只测 3／8 那种两边同判的数，把 --type 读错型也照样全绿。
                ('实用新型5', 5, ['--type', '实用新型'], False),
                ('实用新型9', 9, ['--type', '实用新型'], True)):
            r = run([PY, f'{S}/check_claims.py', q6pkg(tag, ndep)] + flags)
            # 红与"部分未判"的 note 都以 `→ Q6` 收尾，只看这个子串会把未判读成判红——
            # 开火与否必须按"这一行是不是违规行"来断。
            red = any('→ Q6' in l and '部分未判' not in l for l in r.stdout.splitlines())
            assert_(red == want_red and r.returncode == (1 if want_red else 0),
                    f'Q6 档位判错（{tag}，{ndep} 项从属）: rc={r.returncode} {show(r)}', r)
        r = run([PY, f'{S}/check_claims.py', q6pkg('不给类型5b', 5)])
        assert_('Q6 部分未判' in r.stdout and '未给 --type' in r.stdout,
                f'只有一型容得下时没说出"为什么没判红": {show(r)}', r)
        r = run([PY, f'{S}/check_claims.py', q6pkg('怪类型5', 5), '--type', '外观设计'])
        assert_('既不是发明也不是实用新型' in r.stdout,
                f'认不出的 --type 被当成"没给"了: {show(r)}', r)

        p = os.path.join(d, 'noclaims')
        os.makedirs(p)
        open(os.path.join(p, '交底书.md'), 'w', encoding='utf8').write('# 交底书\n暂无权要。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        # 反方向那一半也得钉住：没读到节 ⇒ 覆盖账 0 条、包级账也不算已判的包，
        # 本次改动（扫过节就记）不许把"没读到"折成"已判"。
        assert_(r.returncode == 0 and 'Q1–Q13 未判' in r.stdout
                and '实判判据 0 条' in r.stdout and '实判 0 个包' in r.stdout,
                f'没有权利要求书节被折成合规或未上报: {show(r)}', r)
        # 三态的另一半：有节却一行权项都没解析出。未判的理由必须是「无项」而不是「无节」，
        # 否则读者按提示回去找那一节，会发现节好好地在那里。
        p = os.path.join(d, 'unparsed')
        mkpkg(p, '# 说明书\n## 权利要求书\n一种锁扣装置，包括躯干框架与锁扣本体。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and '一行权项都没解析出' in r.stdout
                and '没有「权利要求书」节' not in r.stdout and ledger(r.stdout) == (0, 3),
                f'有节无项被折成合规，或未判理由报错了对象: {show(r)}', r)

        r = run([PY, f'{S}/check_claims.py', os.path.join(ok, '02_申请文件', '说明书.md')])
        assert_(r.returncode == 2 and '只接目录' in r.stdout,
                f'传文件未说成因并 fail-closed: {show(r)}', r)

        # docx 通道：交付物只有 Word 件时 Q 必须照判（与 T/N/V 同口径）
        try:
            from docx import Document
        except ImportError:
            print('  SKIP check_claims 的 docx 通道（无 python-docx）')
        else:
            wd = os.path.join(d, 'wordonly')
            os.makedirs(wd)
            doc = Document()
            for ln in OK.replace('## 图中标记说明\n'
                                 '| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
                                 '| 1 | 躯干框架 | 1 |\n| 2 | 锁扣本体 | 1 |\n', '').splitlines():
                if ln.startswith('## '):
                    doc.add_heading(ln[3:], level=2)
                elif ln.startswith('# '):
                    doc.add_heading(ln[2:], level=1)
                elif ln.strip():
                    doc.add_paragraph(ln)
            t = doc.add_table(rows=3, cols=3)
            for i, row in enumerate((('标记', '名称', '所在图号'), ('1', '躯干框架', '1'),
                                     ('2', '锁扣本体', '1'))):
                for j, v in enumerate(row):
                    t.cell(i, j).text = v
            doc.save(os.path.join(wd, '说明书.docx'))
            r = run([PY, f'{S}/check_claims.py', wd])
            assert_(r.returncode == 0 and '实判判据 13 条' in r.stdout,
                    f'Word-only 权要未被 Q 真判（只认 md 的话这里假绿或成串假红）: {show(r)}', r)
            bad_doc = os.path.join(d, 'wordbad')
            os.makedirs(bad_doc)
            doc = Document()
            doc.add_heading('权利要求书', level=2)
            for ln in ('1. 一种装置，包括甲。', '2. 根据权利要求 3 所述的装置，其特征在于：乙。',
                       '3. 根据权利要求 1 所述的装置，其特征在于：丙。'):
                doc.add_paragraph(ln)
            doc.save(os.path.join(bad_doc, '说明书.docx'))
            r = run([PY, f'{S}/check_claims.py', bad_doc])
            assert_(r.returncode == 1 and '引用了在后的' in r.stdout and '→ Q3' in r.stdout,
                    f'Word 件里的向后引用未被 Q3 抓到: {show(r)}', r)
            # Q11 在 Word 面上是另一种形状：docx_text 把一个 w:p 折成一行，所以
            # "一项拆成两段、首段以分号或逗号收尾"必须不判，"同一段里两个句号"必须开火。
            # 这两档都不看退码——只有一项从属时 Q6 一定开火，拿 rc 断言会把归因搅浑。
            for tag, paras, want in (
                    ('q11wred', ('1. 一种装置，包括躯干框架（1）。所述锁扣本体（2）铰接。',
                                 '2. 根据权利要求 1 所述的装置，其特征在于：弹臂为钛合金。'), True),
                    ('q11wgreen', ('1. 一种装置，包括躯干框架（1），',
                                   '   所述锁扣本体（2）与所述框架铰接。',
                                   '2. 根据权利要求 1 所述的装置，其特征在于：弹臂为钛合金。'), False)):
                wdir = os.path.join(d, tag)
                os.makedirs(wdir)
                doc = Document()
                doc.add_heading('权利要求书', level=2)
                for x in paras:
                    doc.add_paragraph(x)
                doc.save(os.path.join(wdir, '说明书.docx'))
                r = run([PY, f'{S}/check_claims.py', wdir])
                assert_(('→ Q11' in r.stdout) == want,
                        f'Word 件的句号位点读数不符（{tag} 期望开火={want}）: {show(r)}', r)
            open(os.path.join(bad_doc, '坏件.docx'), 'wb').write(b'not a zip')
            r = run([PY, f'{S}/check_claims.py', bad_doc])
            assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'Traceback' not in r.stderr,
                    f'读不动的 docx 崩成异常或退码不是 2: {show(r)} / {r.stderr[-140:]}', r)

            # Q7 的 docx 通道：真嵌一张图（不是折算行手抄），看 docx_text 有没有把图形对象
            # 折算成文本面上的那一行。控制档就是上面 wordonly 那份无图 Word 件（它必须全绿）。
            imgd = os.path.join(d, 'wordimg')
            os.makedirs(imgd)
            tiny = os.path.join(d, 'tiny.png')
            Image.new('RGB', (16, 8), (255, 0, 0)).save(tiny)
            doc = Document()
            doc.add_heading('权利要求书', level=2)
            doc.add_paragraph('1. 一种装置，包括甲。')
            doc.add_picture(tiny)
            doc.save(os.path.join(imgd, '说明书.docx'))
            r = run([PY, f'{S}/check_claims.py', imgd])
            assert_(r.returncode == 1 and '→ Q7' in r.stdout,
                    f'Word 件里嵌入的插图未被 Q7 抓到（折算行没生效）: {show(r)}', r)

        # Q7／Q8（细则 22 条一款）：权要里不得有插图、不得用"如图…所示／如说明书…部分所述"指回别处。
        # 必红各配对向：合规档不红（第一档已顺带证）、"如图…"写在说明书节里不归 Q 管
        # （Q 只吃权要节）、括注式写法不是 22 条禁的那种指回。
        p = os.path.join(d, 'q7')
        # 插图必须落在**权要节内**：OK 的结尾是「图中标记说明」表（另一个节），
        # 追加在文件尾的话 Q7 根本看不见——那测的是"节切分"不是"插图"。
        mkpkg(p, OK.replace('\n## 图中标记说明', '\n![结构图](图1.png)\n## 图中标记说明'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '→ Q7' in r.stdout,
                f'权要里的插图未被 Q7 抓到: {show(r)}', r)
        p = os.path.join(d, 'q7clean')
        mkpkg(p, OK)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and '→ Q7' not in r.stdout,
                f'合规权要被 Q7 误伤: {show(r)}', r)
        p = os.path.join(d, 'q8')
        mkpkg(p, OK.replace('其特征在于：所述锁扣本体设有卡齿4。',
                            '其特征在于：所述弹臂如图 3 所示布置。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and '→ Q8' in r.stdout,
                f'权要里"如图…所示"未被 Q8 抓到: {show(r)}', r)
        p = os.path.join(d, 'q8spec')
        mkpkg(p, OK.replace('其特征在于：所述锁扣本体设有卡齿4。',
                            '其特征在于：如说明书第三部分所述，所述弹臂设有卡齿。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_('→ Q8' in r.stdout, f'"如说明书…部分所述"未被 Q8 抓到: {show(r)}', r)
        p = os.path.join(d, 'q8scope')
        mkpkg(p, OK + '\n## 说明书\n如图 1 所示，装置包括框架。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        assert_('→ Q8' not in r.stdout,
                f'说明书节里的"如图…所示"被 Q8 越域判了（Q 只吃权要节）: {show(r)}', r)

        # ── Q12（《专利审查指南》2023 第一部分第一章 §4.4：编号前不得冠"权利要求"或"权项"）──
        # 这条与 Q7／Q8 同属**节面**判据：判在整节的文本面上，与权项切不切得出来无关。
        # Q1 管那句话的前半句（顺序编号），Q12 只管后半句（不得冠词）——
        # 光秃秃的「1.」编号是法定形状，判严了就是把指南没写的禁令造出来。
        def qhits(out, rule):
            return [ln for ln in out.splitlines() if ln.startswith('  ')
                    and not ln.startswith('  note ') and f'→ {rule}（' in ln]

        def real_line(text, needle):
            """needle 在夹具里的真 1-based 行号，由测试自己数——不抄门禁的读数。"""
            got = [i for i, ln in enumerate(text.splitlines(), 1) if needle in ln]
            assert_(len(got) == 1, f'夹具不自洽：「{needle}」命中 {got} 行，这一档会空转', None)
            return got[0]

        Q12_BAD = ('# 说明书\n## 权利要求书\n'
                   '权利要求1、一种锁扣装置，包括躯干框架与锁扣本体。\n'
                   '权项2、根据权利要求1所述的锁扣装置，其特征在于：所述锁扣本体设有卡齿。\n')
        p = os.path.join(d, 'q12')
        mkpkg(p, Q12_BAD)
        r = run([PY, f'{S}/check_claims.py', p])
        hits = qhits(r.stdout, 'Q12')
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q12'} and len(hits) == 2,
                f'权项编号前冠"权利要求／权项"未被 Q12 抓到（两种冠词各一条）: {show(r)}', r)
        assert_(f':{real_line(Q12_BAD, "权利要求1、一种锁扣装置")}: 权项编号' in hits[0]
                and f':{real_line(Q12_BAD, "权项2、根据权利要求1")}: 权项编号' in hits[1],
                f'Q12 报的位点不是各自触发行（真号 '
                f'{real_line(Q12_BAD, "权利要求1、")}／{real_line(Q12_BAD, "权项2、")}）: '
                f'{show(r)}', r)
        assert_('§4.4' in hits[0], f'Q12 没把指南那句法源带上: {show(r)}', r)
        # 正向对照的反面：把两个冠词去掉、其余形状不动，必须一条都不红
        # （这一档也是"判严方向"那个变异臂的合规控制——把 `N.` 本身判红的话它当场翻脸）
        Q12_CLEAN = ('# 说明书\n## 权利要求书\n'
                     '1. 一种锁扣装置，包括躯干框架与锁扣本体。\n'
                     + ''.join(f'{i}. 根据权利要求1所述的锁扣装置，其特征在于：'
                               f'所述锁扣本体设有卡齿{i}。\n' for i in range(2, 9)) + TBL)
        p = os.path.join(d, 'q12clean')
        mkpkg(p, Q12_CLEAN)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'合规的「N.」顺序编号被 Q12 判红（指南只禁编号前冠词，不禁编号本身）: '
                f'{show(r)}', r)
        # 顺序档＝本轮那条结构性改动的回归钉：通篇都冠着"权利要求"的权要书里，
        # CLAIM_ITEM 一行也解析不出（那些行以"权"字起头），旧顺序下整族被"无项早退"挡在门外、
        # 报成"Q1–Q12 未判"，而 Q12 恰恰是唯一看得见这种写法的那一条。
        # 于是两句必须同时出：Q12 的红，和那句点名"哪几条判不起"的注记——只出一句都不算对。
        Q12_ALLPRE = ('# 说明书\n## 权利要求书\n'
                      '权利要求1、一种锁扣装置，包括躯干框架与锁扣本体。\n'
                      '权利要求2、根据权利要求1所述的锁扣装置，其特征在于：所述锁扣本体设有卡齿。\n'
                      '权利要求3、根据权利要求1所述的锁扣装置，其特征在于：所述弹臂为钛合金。\n')
        p = os.path.join(d, 'q12allpre')
        mkpkg(p, Q12_ALLPRE)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and len(qhits(r.stdout, 'Q12')) == 3,
                f'通篇冠"权利要求"的权要书里 Q12 没判满三条（节面条目被"无项早退"挡在门外了）: '
                f'{show(r)}', r)
        assert_('→ Q1–Q6、Q9–Q11、Q13 未判（有节却无项，那几条判不起）' in r.stdout,
                f'"有节却无项"那档没点名到底是哪几条判不起（Q13 扩员后这条必须跟着点名）: '
                f'{show(r)}', r)
        assert_('没有「权利要求书」节' not in r.stdout,
                f'明明读到了节却报"没有权利要求书节"（两档未判混成一档）: {show(r)}', r)
        # 实判判据那一格也跟着走：一行权项都没解析出，但**这一节扫过了**，节面三条
        # （Q7／Q8／Q12）就都该记进覆盖账——判没判红与记不记无关（这里 Q7／Q8 零开火也记）。
        # 旧写法把登记写在 `if 命中:` 里，这一档只自报 1 条，把"跑了没发现问题"折成"没跑"。
        assert_('实判判据 3 条' in r.stdout,
                f'扫过这一节却没把节面三条记进实判分母（登记还留在开火分支里）: {show(r)}', r)

        # ── Q9／Q10／Q11（《专利审查指南》2023 第二部分第二章 §3.2.2 与 §3.3）──────────
        # 三条的主语都是"权利要求中／每一项权利要求"，判在**每一项权项之内**：
        # 正向档各钉一支"咬得动"，反向档各钉一支"中文没有词边界时不许越界咬人"。
        # 归因一律走 fired()——同档撞两支判据时读数说不清是谁在咬（见函数头）。
        # 位点都用权项 3 那一行：它既是合规档的一部分，改它就不动别的判据的输入。
        for term in ('例如', '最好是', '尤其是', '必要时'):
            p = os.path.join(d, 'q9_' + term)
            mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                                '其特征在于：所述弹臂为金属材料' + term + '钛合金。'))
            r = run([PY, f'{S}/check_claims.py', p])
            assert_(r.returncode == 1 and fired(r.stdout) == {'Q9'}
                    and f'权利要求 3 里出现「{term}」' in r.stdout,
                    f'权要里的模糊用语未被 Q9 抓到（「{term}」）: {show(r)}', r)
        # 反向：指南同一节还有"厚／薄／强／弱"那支，本门禁**没收**——中文无词边界，
        # "压缩强度"里的"强"会当场开火。这条合规写法钉住"词表没被悄悄扩宽"。
        p = os.path.join(d, 'q9clean')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                            '其特征在于：所述弹臂的压缩强度高于所述锁扣本体，弹性模量随之提高。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'合规权要被 Q9 误伤（压缩强度里的强不在指南点名的那四个词里）: {show(r)}', r)

        # Q10 两半各自成对：数值形状「约＋数字」与逐字短语「或类似物」是两条独立触发路径，
        # 合在一条断言里会让"关掉一半"的变异读起来像"整条还在"。
        p = os.path.join(d, 'q10num')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                            '其特征在于：所述弹臂的厚度约 2mm。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q10'}
                and '权利要求 3 里「约 2」' in r.stdout and '限定数值' in r.stdout,
                f'权要里"约＋数字"未被 Q10 抓到: {show(r)}', r)
        p = os.path.join(d, 'q10sim')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                            '其特征在于：所述弹臂为钛合金或类似物。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q10'}
                and '权利要求 3 里出现「或类似物」' in r.stdout,
                f'权要里「或类似物」未被 Q10 抓到: {show(r)}', r)
        # 反向：指南同一句里的"接近"与"等"两个词登记为**不判**——"接近开关"是真实部件名、
        # "等待"与"约定"是构词成分。约字要撞上也只在"约＋数字"那一支撞，"约定的…0.2mm" 不撞。
        p = os.path.join(d, 'q10clean')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                            '其特征在于：所述弹臂装有接近开关，锁扣等待到位信号后释放，'
                            '弹臂与锁扣本体约定的配合间隙为 0.2mm。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'接近开关／等待／约定这类同形合规写法被 Q10 误伤: {show(r)}', r)

        # Q11 只判"结尾之前出现句号"：①一行里两个句号 ②多行权项里非末那行以句号收尾。
        p = os.path.join(d, 'q11')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。',
                            '其特征在于：所述弹臂为钛合金。所述弹臂表面镀硬铬。'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q11'}
                and '权利要求 3 在结尾之前出现了句号' in r.stdout,
                f'权要一行里结尾之前的句号未被 Q11 抓到: {show(r)}', r)
        p = os.path.join(d, 'q11mid')
        mkpkg(p, OK.replace('\n## 图中标记说明',
                            '\n9. 根据权利要求 1 所述的锁扣装置，其特征在于：所述弹臂设有卡齿。\n'
                            '   且所述卡齿表面镀硬铬。\n## 图中标记说明'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q11'}
                and '权利要求 9 在结尾之前出现了句号' in r.stdout,
                f'多行权项里非结尾那行的句号未被 Q11 抓到: {show(r)}', r)
        # 反向①：整项没有结尾句号。**不判**——指南那句是给句号划界，不是设"必须以句号收尾"的
        # 义务，反过来判等于自造一条法条里没有的禁令（电池 claims 档那条判严臂咬的就是这格）。
        p = os.path.join(d, 'q11open')
        mkpkg(p, OK.replace('其特征在于：所述弹臂为钛合金。', '其特征在于：所述弹臂为钛合金'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'权要结尾没有句号被 Q11 判红（那句是划界不是义务）: {show(r)}', r)
        # 反向②：合规的多行权项——分行处分号／逗号收尾，只有末行带句号（实用新型 §7.4 那句
        # "分行和分小段处只可用分号或逗号"的正面写法）。
        p = os.path.join(d, 'q11mlclean')
        mkpkg(p, OK.replace('\n## 图中标记说明',
                            '\n9. 根据权利要求 1 所述的锁扣装置，其特征在于：所述弹臂设有卡齿；\n'
                            '   所述卡齿表面镀硬铬，且与锁扣本体铰接。\n## 图中标记说明'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'合规的多行权项被 Q11 误伤: {show(r)}', r)

        # 位点控制：Q11 报的行必须是"触发那个句号所在的那一行"，不是权项抬头行、也不是节首行。
        # 坐标不抄门禁自己的行号基准（它这里报的是 body 下标，比 check_iron_rules／check_figures
        # 的 1-based 小一行——本轮不改 scripts/，已写进收尾报告），而是拿同一次读数里 Q6 报出的
        # 权项抬头行当原点：两档只差"多余的句号落在该项第几行"，报的号必须跟着走一步。
        # Q11 若永远报抬头行，B 档当场红；若报项末行，A 档当场红。
        def coord(out):
            m = re.search(r':(\d+): 从属权利要求', out)
            return int(m.group(1)) if m else None

        for tag, item, want_off in (
                # 多余句号落在抬头那一行（该项还有第二行，所以抬头那行的句号不是结尾）
                ('A', '1. 一种锁扣装置，包括躯干框架（1）与锁扣本体（2）。\n所述弹臂为钛合金。\n', 0),
                # 同一项多写一行，把多余句号推到第二行
                ('B', '1. 一种锁扣装置，包括躯干框架（1）与锁扣本体（2）\n'
                     '所述弹臂为钛合金。\n所述卡齿设有倒角。\n', 1)):
            p = os.path.join(d, 'q11line' + tag)
            mkpkg(p, '# 说明书\n## 权利要求书\n' + item + TBL)
            r = run([PY, f'{S}/check_claims.py', p])
            n0, hits = coord(r.stdout), [ln for ln in r.stdout.splitlines() if '→ Q11' in ln]
            assert_(r.returncode == 1 and n0 is not None and len(hits) == 1
                    and f':{n0 + want_off}:' in hits[0],
                    f'Q11 报的行号没跟着触发句号那一行走（{tag} 档应报抬头行 {n0} 之后第 {want_off} 行）'
                    f': {show(r)}', r)

        # 绝对坐标档：真行号由测试自己 enumerate 夹具文本算出，既不抄门禁的读数、
        # 也不像上面 A／B 档那样借另一条判据（Q6）当原点——那一档只钉得住"报的行随触发行移动"，
        # 钉不住整体偏一行。Q 族的 where 今天按 0-based 报（实测：触发行真号 4、门禁报 3），
        # 所以这一档在改之前必须是红的。
        ABS = ('# 说明书\n## 权利要求书\n'
               '1. 一种锁扣装置，包括躯干框架（1）。所述锁扣本体（2）与所述框架铰接。\n'
               '2. 根据权利要求 1 所述的锁扣装置，其特征在于：所述弹臂为钛合金。\n'
               '3. 根据权利要求 1 所述的锁扣装置，其特征在于：例如弹臂为铜。\n' + TBL)
        p = os.path.join(d, 'qabs')
        mkpkg(p, ABS)
        real_q11 = [i for i, ln in enumerate(ABS.splitlines(), 1) if '。所述锁扣本体' in ln]
        real_q9 = [i for i, ln in enumerate(ABS.splitlines(), 1) if '例如弹臂为铜' in ln]
        assert_(len(real_q11) == 1 and len(real_q9) == 1,
                f'夹具不自洽：Q11 触发点 {real_q11} 处、Q9 触发点 {real_q9} 处，档位会空转', None)
        r = run([PY, f'{S}/check_claims.py', p])
        h11 = [ln for ln in r.stdout.splitlines() if '→ Q11' in ln]
        h9 = [ln for ln in r.stdout.splitlines() if '→ Q9' in ln]
        assert_(len(h11) == 1 and f':{real_q11[0]}:' in h11[0],
                f'Q11 报的位点不是触发行真号 {real_q11[0]}: {show(r)}', r)
        assert_(len(h9) == 1 and f':{real_q9[0]}:' in h9[0],
                f'Q9 报的位点不是触发行真号 {real_q9[0]}: {show(r)}', r)

        # 作用域：三条都判在权项之内——同一批词与同一批句号写在说明书节里，一律不许开火
        # （与 q8scope 同一形状的控制，只是原告换成指南那三句的词表）。
        p = os.path.join(d, 'q9to11scope')
        mkpkg(p, OK + '\n## 具体实施方式\n例如将弹臂设为钛合金，必要时把厚度设为约 2mm。'
                      '装置包括框架。框架包括底座。底座装有接近开关。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'说明书节里的例如／必要时／约＋数字／行中句号被 Q9–Q11 越域判了（三条只吃权项之内）'
                f': {show(r)}', r)

        # ── Q13（《专利审查指南》2023 第二部分第二章 §3.3.2：从权引用部分须重述被引权项的主题名称）──
        # 法源本轮逐字重开留底核对：.codebuddy/attest/zhinan2023_ahippc.txt:5994-5997
        # （页标 `<<<PAGE 169>>>` 在 txt:5974，该页页眉自标「（2-33） 165」，节标题 3.3.2 在 txt:5984）
        # ——「从属权利要求的引用部分应当写明引用的权利要求的编号，其后应当重述引用的权利要求的主题
        # 名称。例如，一项从属权利要求的引用部分应当写成："根据权利要求1所述的金属纤维拉拔装置，……"」。
        # 夹具的主题名称一律直接用指南这句里的原名，免得"合规"是本仓造的。
        B13 = ('# 说明书\n## 权利要求书\n'
               '1. 一种金属纤维拉拔装置，包括机架、夹头与驱动轮。\n'
               '2. 根据权利要求1所述的金属纤维拉拔装置，其特征在于：所述夹头设有耐磨衬套。\n'
               '3. 根据权利要求1或2所述的金属纤维拉拔装置，其特征在于：所述耐磨衬套为碳化钨。\n'
               + ''.join(f'{i}. 根据权利要求 1 所述的金属纤维拉拔装置，其特征在于：'
                         f'所述驱动轮设有齿槽{i}。\n' for i in range(4, 9)) + TBL)
        # ②多项择一的另一种写法，照指南 txt:6005 的第二例"根据权利要求 2、4、6 或 8 所述的……"
        B13M = B13.replace('\n## 图中标记说明',
                           '\n9. 根据权利要求2、4、6或8所述的金属纤维拉拔装置，其特征在于：'
                           '所述衬套配有垫圈。\n## 图中标记说明')

        # ①正确重述（同时是④的静默侧）：1 项是"一种金属纤维拉拔装置"，从权逐字重述同一个名字。
        p = os.path.join(d, 'q13clean')
        mkpkg(p, B13)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'① 正确重述（指南那句"根据权利要求1所述的金属纤维拉拔装置"）被 Q13 误伤: '
                f'{show(r)}', r)

        # ④开火侧：只把限定词"金属纤维"丢掉。这两档（④静默／④开火）合起来才是判据的牙齿——
        # 只测"同名即放"看不见"丢限定词"，只测开火又看不见误伤，所以必须成对。
        DROP13 = B13.replace('2. 根据权利要求1所述的金属纤维拉拔装置',
                             '2. 根据权利要求1所述的拉拔装置')
        p = os.path.join(d, 'q13drop')
        mkpkg(p, DROP13)
        r = run([PY, f'{S}/check_claims.py', p])
        h13 = qhits(r.stdout, 'Q13')
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q13'} and len(h13) == 1,
                f'④ 少了限定词的重述未被 Q13 抓到（该判的没判）: {show(r)}', r)
        assert_('「拉拔装置」' in h13[0] and '「金属纤维拉拔装置」' in h13[0]
                and '§3.3.2' in h13[0] and '重述引用的权利要求的主题名称' in h13[0],
                f'Q13 的报文没把"重述成了什么／被引项自己写的是什么／法源是哪一句"说全: {show(r)}', r)
        assert_(f':{real_line(DROP13, "2. 根据权利要求1所述的拉拔装置")}:' in h13[0],
                f'Q13 报的位点不是引用部分那一行（真号 '
                f'{real_line(DROP13, "2. 根据权利要求1所述的拉拔装置")}）: {show(r)}', r)

        # ②多项择一·静默侧：同组"1或2"（B13 的第 3 项）与"2、4、6或8"（第 9 项）都与被引项同名。
        p = os.path.join(d, 'q13multiclean')
        mkpkg(p, B13M)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'② 多项择一引用（与所引各项同名）被 Q13 误伤: {show(r)}', r)
        # ②择一口径的开火侧：与**每一项**被引权项都不同名才判红。
        p = os.path.join(d, 'q13multifire')
        mkpkg(p, B13M.replace('9. 根据权利要求2、4、6或8所述的金属纤维拉拔装置',
                              '9. 根据权利要求2、4、6或8所述的拉拔装置'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 1 and fired(r.stdout) == {'Q13'},
                f'② 多项择一引用与所有被引项都不同名却没判（择一口径失灵）: {show(r)}', r)
        # ②口径的判别量：跨组择一。1 是"金属纤维拉拔方法"、7 是"金属纤维拉拔装置"，
        # 第 8 项写"根据权利要求1或7所述的金属纤维拉拔装置"——与 1 不同名、与 7 同名。
        # 口径若写成"必须同名于全部被引项"，这一档当场被误伤；写成"提到编号就判红"则由上面
        # ①②的静默档反证。所以这两档合起来才把 docstring 里那个"任一即放"的选择钉住。
        XG = ('# 说明书\n## 权利要求书\n'
              '1. 一种金属纤维拉拔方法，包括连续拉拔步骤。\n'
              '2. 根据权利要求1所述的金属纤维拉拔方法，其特征在于：步骤A设定张力。\n'
              '3. 根据权利要求1所述的金属纤维拉拔方法，其特征在于：步骤B设定速度。\n'
              '4. 根据权利要求1所述的金属纤维拉拔方法，其特征在于：步骤C设定温度。\n'
              '5. 一种金属纤维拉拔装置，包括机架。\n'
              '6. 根据权利要求5所述的金属纤维拉拔装置，其特征在于：所述机架设有夹头。\n'
              '7. 根据权利要求5所述的金属纤维拉拔装置，其特征在于：所述夹头为硬质合金。\n'
              '8. 根据权利要求1或7所述的金属纤维拉拔装置，其特征在于：所述夹头设有衬套。\n' + TBL)
        p = os.path.join(d, 'q13xgroupclean')
        mkpkg(p, XG)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_('Q13' not in fired(r.stdout),
                f'② 跨组择一引用（只与其中一项同名）被 Q13 判红——口径被改成了"必须同名于全部": '
                f'{show(r)}', r)
        p = os.path.join(d, 'q13xgroupfire')
        mkpkg(p, XG.replace('8. 根据权利要求1或7所述的金属纤维拉拔装置',
                           '8. 根据权利要求1或7所述的拉拔装置'))
        r = run([PY, f'{S}/check_claims.py', p])
        assert_('Q13' in fired(r.stdout),
                f'② 跨组择一引用与两项被引权项都不同名却没判: {show(r)}', r)

        # ③并列独立权利要求（§3.1.2，txt:5674-5686，PDF p161／2-25）——规格要求的"注入正例证明"。
        # 指南那四句原样喂进去：它们引用在前的独权，却不写"根据权利要求N所述的X"那种引用部分，
        # 而 Q13 认的就是那个形状，所以豁免是结构性的，不靠注释声明（这一档就是那句声明的反证）。
        # 包里同时留 4 项真从属（5–8 逐字重述 1 的主题名），免得读成"Q13 在这档里根本没跑"。
        PAR = ('# 说明书\n## 权利要求书\n'
               '1. 一种金属纤维拉拔方法，包括连续拉拔步骤。\n'
               '2. 一种实施权利要求1的方法的装置，包括机架。\n'
               '3. 一种制造权利要求1的产品的设备，包括模具。\n'
               '4. 与权利要求1的拉拔方法相配合的插头，包括弹性卡口。\n'
               + ''.join(f'{i}. 根据权利要求1所述的金属纤维拉拔方法，其特征在于：'
                         f'步骤{i - 4}设定张力。\n' for i in range(5, 9)) + TBL)
        p = os.path.join(d, 'q13par')
        mkpkg(p, PAR)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set() and '→ Q13' not in r.stdout,
                f'③ 并列独立权利要求（"一种实施权利要求1的方法的装置"）被 Q13 判红: {show(r)}', r)
        # 这一档里从属项确实在场（否则"零开火"可能只是没跑）——用 Q13 记进覆盖账这件事反证：
        # 同一份包去掉 5–8 四项从属后，覆盖账要少一格（见下面 q13nodeps 的账）。
        assert_('实判判据 12 条' in r.stdout,
                f'③ 并列独权那档的覆盖账不是现算的（从属项在场却少记／无项却多记）: {show(r)}', r)

        # 没有从属权利要求 ⇒ 不适用：既不判红、也不出提示行，且不记进覆盖账（与 Q3／Q4 同口径）。
        NODEPS = ('# 说明书\n## 权利要求书\n'
                  '1. 一种金属纤维拉拔方法，包括连续拉拔步骤。\n'
                  '2. 一种实施权利要求1的方法的装置，包括机架。\n'
                  '3. 一种制造权利要求1的产品的设备，包括模具。\n' + TBL)
        p = os.path.join(d, 'q13nodeps')
        mkpkg(p, NODEPS)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(fired(r.stdout) == {'Q6'} and '→ Q13' not in r.stdout and ledger(r.stdout) == (1, 10),
                f'没有从属权利要求时 Q13 不适用这一档读错了（出了提示行，或被记进了覆盖账）: '
                f'{show(r)}', r)

        # 三态①：被引的号在本包解析出的权项里找不到（这里是跳号——权项没有 5，而 6 引用 5）。
        # 这一条对那一项走未判：note 行点名 Q13，违规行里不许出现它（既不判红也不折成合规）。
        MISS13 = ('# 说明书\n## 权利要求书\n'
                  '1. 一种金属纤维拉拔装置，包括机架。\n'
                  + ''.join(f'{i}. 根据权利要求1所述的金属纤维拉拔装置，其特征在于：'
                            f'设有卡齿{i}。\n' for i in range(2, 5))
                  + '6. 根据权利要求5所述的金属纤维拉拔装置，其特征在于：所述卡齿表面镀硬铬。\n' + TBL)
        p = os.path.join(d, 'q13missing')
        mkpkg(p, MISS13)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_('→ Q13 未判' in r.stdout and 'Q13' not in fired(r.stdout)
                and fired(r.stdout) == {'Q1'},
                f'被引项查无此号时 Q13 没走未判（判红了，或被折成合规了）: {show(r)}', r)

        # 三态②：带引用语却认不出「根据权利要求N所述的<主题>」这个形状（这里漏了"所述的"）。
        # 与 Q4"认不出多项写法就不判"同口径：看不见主题名称就不猜，但必须把"没判"说出口。
        SHAPE13 = ('# 说明书\n## 权利要求书\n'
                   '1. 一种金属纤维拉拔装置，包括机架。\n'
                   + ''.join(f'{i}. 根据权利要求1所述的金属纤维拉拔装置，其特征在于：'
                             f'设有卡齿{i}。\n' for i in range(2, 9))
                   + '9. 根据权利要求1，其特征在于所述机架为钢。\n' + TBL)
        p = os.path.join(d, 'q13shape')
        mkpkg(p, SHAPE13)
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and '→ Q13 未判' in r.stdout and 'Q13' not in fired(r.stdout),
                f'引用部分认不出形状时 Q13 硬猜了（判红）或闷掉了（不报未判）: {show(r)}', r)

        # 作用域与 Q9–Q11 同生死：一行权项都解析不出时 Q13 判不起，由上面"有节却无项"那档的
        # 注记点名（已扩号）；而"根据权利要求1"写在说明书节里时 Q13 不许越域判（权要节之外没有它）。
        p = os.path.join(d, 'q13scope')
        mkpkg(p, B13 + '\n## 具体实施方式\n根据权利要求1所述的金属纤维拉拔装置，步骤A设定张力。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and fired(r.stdout) == set(),
                f'说明书节里的引用语被 Q13 越域判了（它只吃解析出的权项）: {show(r)}', r)
    print('PASS check_claims（Q1–Q13 各成对 + 合规档同过 + 引用号不当标记 + 三态 + docx 通道 + '
          'Q7 嵌图两通道 + Q8 引用语作用域 + Q9 四词各一档 + Q10 两半各成对（约＋数字／或类似物）'
          '+ Q11 两种位点／无结尾句号不判红／合规多行权项 + 行号随触发行移动 + Q9–Q11 出域不判 '
          '+ Q12 冠词正反档／通篇冠词仍判满（节面条目排在无项早退之前）'
          '+ Q13 四侧不误伤（正确重述／多项择一含跨组档／并列独权零开火／丢限定词才开火）'
          '+ Q13 两档未判（被引号查无此号、引用部分认不出形状）＋无从权不适用不入覆盖账＋出域不判'
          '+ 覆盖账：合规 13 条／无对照表 12 条／有节无项 3 条／无节 0 条（包级账同步 1／0 个包）+ rc=2）')


def test_figure_text_channel():
    """图↔文书对账 T1–T7：清单由画图那段代码自己产出，判据读的是产出而不是手抄登记表。

    两半都要验：① `write_manifest` 写了什么（不依赖 matplotlib，否则这条断言会随环境
    一起 SKIP，判据只剩消费侧有牙）；② 门禁对真包开不开火、三态走不走得对。"""
    import json
    _sp = importlib.util.spec_from_file_location('pf_tt', f'{S}/patent_figure.py')
    pf = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(pf)

    with tempfile.TemporaryDirectory() as d:
        mp = pf.write_manifest(os.path.join(d, '图1.png'),
                               {13: '支架', 12: '底座'},
                               ['躯干框架', '躯干框架', '横移速度 ≤25mm/s'])
        man = json.load(open(mp, encoding='utf8'))
        assert_(sorted(man) == ['figure', 'marks', 'texts'],
                f'清单键不对，读者无从按形状取用: {sorted(man)}', None)
        assert_(man['figure'] == '图1.png' and man['marks'] == {'12': '底座', '13': '支架'},
                f'figure/marks 内容不对: {man}', None)
        assert_(man['texts'] == ['躯干框架', '横移速度 ≤25mm/s'],
                f'框内文字要按绘制顺序去重留出底，实得: {man["texts"]}', None)
        assert_(mp.endswith('图1.manifest.json') and os.path.isfile(mp),
                f'清单没有与 PNG 并排落盘: {mp}', None)

    DOCS = ('# 说明书\n## 附图说明\n图 1 为整体示意。\n'
            '## 图中标记说明\n| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
            '| 12 | 底座 | 1 |\n| 13 | 支架 | 1 |\n'
            '## 具体实施方式\n横移速度 ≤25mm/s；躯干框架由铝合金制成。\n')
    MAN = '{"figure": "图1.png", "marks": {"12": "底座", "13": "支架"}, ' \
          '"texts": ["躯干框架", "横移速度 ≤25mm/s"]}'

    def make(root, man=MAN, docs=DOCS, png_only=False, pngs=('图1',), manifest_for='图1'):
        os.makedirs(os.path.join(root, '02_申请文件', 'figures'), exist_ok=True)
        os.makedirs(os.path.join(root, '01_交底书'), exist_ok=True)
        open(os.path.join(root, '01_交底书', '交底书.md'), 'w', encoding='utf8').write(docs)
        for name in pngs:
            open(os.path.join(root, '02_申请文件', 'figures', name + '.png'), 'wb'
                 ).write(b'\x89PNG\r\n\x1a\n' + b'0' * 40)
        if not png_only and manifest_for in pngs:
            fig = os.path.join(root, '02_申请文件', 'figures', manifest_for + '.png')
            open(os.path.splitext(fig)[0] + '.manifest.json', 'w', encoding='utf8').write(man)

    def fire(out):
        return sorted({t for t in ('T1', 'T2', 'T3')
                       for ln in out.splitlines()
                       if ln.startswith('  ') and not ln.startswith('  note ')
                       and f'→ {t}' in ln and '未判' not in ln})

    with tempfile.TemporaryDirectory() as d:
        ok = os.path.join(d, 'ok')
        make(ok)
        r = run([PY, f'{S}/check_figure_text.py', ok])
        assert_(r.returncode == 0 and not fire(r.stdout),
                f'图与文书逐字一致却被判红: {show(r)}', r)
        # 配对靠的是去掉 '.manifest.json' 这个双后缀，不是 splitext：用 splitext 得到
        # '图1.manifest'，与 '图1.png' 的 stem 配不上，合规包会被读成"有 PNG 没有清单"。
        assert_('没有配套 manifest' not in r.stdout,
                f'并排的 <图名>.manifest.json 没配上 <图名>.png（双后缀被 splitext 切错）: {show(r)}', r)
        assert_('实判判据 7 条' in r.stdout, f'合规案没把七条判据都判到: {show(r)}', r)

        # 五档必红各写一条独立断言（不写成循环）：断言消息要留字面量，
        # 电池的 expect 才核得动——f-string 里插 label 会让"哪一档"只剩在运行时。
        def neg(tag, man, want, msg):
            p = os.path.join(d, 'n' + tag)
            make(p, man=man)
            r = run([PY, f'{S}/check_figure_text.py', p])
            assert_(r.returncode == 1 and fire(r.stdout) == want, msg + ': ' + show(r), None)

        neg('1', MAN.replace('"躯干框架"', '"碳纤维摇臂"'), ['T1'],
            '图上有文书没有的部件未按预期开火')
        neg('2', MAN.replace('≤25mm/s', '≤35mm/s'), ['T2'],
            '图中数值差一个数字未按预期开火')
        neg('3', MAN.replace('≤25mm/s', '≤25mm/min'), ['T2'],
            '图中单位写法不同未按预期开火')
        neg('4', MAN.replace('"13": "支架"', '"13": "卡箍"'), ['T1', 'T3'],
            '图上标号与对照表名称不一致未按预期开火')
        neg('5', MAN.replace('{"12"', '{"21": "销轴", "12"'), ['T1', 'T3'],
            '图上标号在对照表里不存在未按预期开火')

        # 只归一"符号与数字之间的空白"，别的一个字都不许放过
        p = os.path.join(d, 'space')
        make(p, man=MAN.replace('≤25mm/s', '≤ 25mm/s'))
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 0, f'符号后空白被当成不一致（该归一的不归一）: {show(r)}', r)
        p = os.path.join(d, 'digit')
        make(p, man=MAN.replace('躯干框架', '躯干 框架'))
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 1 and '→ T1' in r.stdout,
                f'部件名中间塞空格就蒙混过关（归一过头）: {show(r)}', r)

        # 三态三档
        p = os.path.join(d, 'notext')
        make(p, man=MAN.replace(', "texts": ["躯干框架", "横移速度 ≤25mm/s"]',
                               ', "texts": ["躯干框架"]'))
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 0 and 'T2 未判' in r.stdout,
                f'图上无数值被折成合规或违规: {show(r)}', r)
        p = os.path.join(d, 'badman')
        make(p, man='{"figure": "图1.png", "marks": {}}')
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 1 and '清单缺键' in r.stdout and 'texts' in r.stdout,
                f'清单形状不对却没点名成因（或崩在 KeyError 上）: {show(r)}', r)
        p = os.path.join(d, 'orphan')
        make(p, png_only=True)
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 2 and '无从查证' in r.stdout,
                f'有 PNG 无 manifest 被当成"核过了"或"发现违规": {show(r)}', r)
        # 混合档：一张有清单、一张手画 PNG。旧写法把"看孤儿"关在 `if not mans` 里，
        # 于是"12 张图混 1 张手画"这个最像真相的形态被读成"实判 3 条 / 违规 0"。
        p = os.path.join(d, 'mixed')
        make(p)
        open(os.path.join(p, '02_申请文件', 'figures', '图2.png'), 'wb').write(b'\x89PNG\r\n\x1a\n')
        r = run([PY, f'{S}/check_figure_text.py', p])
        # 注意：这张没人引用的 图2.png 既是"缺清单"（→ 不完整）也是 T5 的真违规，
        # 所以退码按"判出的违规优先"落 1；"不完整"那半句仍要打出来。
        assert_(r.returncode == 1 and '图2.png' in r.stdout and '实判判据 6 条' in r.stdout
                and '→ T5' in r.stdout and '另有:' in r.stdout and 'T7 未判' in r.stdout,
                f'部分图没有清单被当成核过了（判到多少报多少，但包级不完整要说清是谁）: {show(r)}', r)
        # 优先级：真判出的违规不许被"对账不完整"降级成环境档
        p = os.path.join(d, 'mixedbad')
        make(p, man=MAN.replace('≤25mm/s', '≤35mm/s'))
        open(os.path.join(p, '02_申请文件', 'figures', '图2.png'), 'wb').write(b'\x89PNG\r\n\x1a\n')
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 1 and fire(r.stdout) == ['T2'] and '另有:' in r.stdout,
                f'判出的违规被"对账不完整"盖掉: {show(r)}', r)
        p = os.path.join(d, 'nofig')
        os.makedirs(os.path.join(p, '01_交底书'))
        open(os.path.join(p, '01_交底书', '交底书.md'), 'w', encoding='utf8').write('# 交底书\n无图。\n')
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 0 and 'T1–T3 未判' in r.stdout,
                f'没有图的包被硬判: {show(r)}', r)
        p = os.path.join(d, '不存在')
        r = run([PY, f'{S}/check_figure_text.py', p])
        assert_(r.returncode == 2 and '不是目录' in r.stdout,
                f'路径不可用未说成因并 fail-closed: {show(r)}', r)
        # ---- T4–T6 图号对账（第 21 轮从《专利法实施细则》第四十六/二十一条捡回来的） ----
        # 旧状下"说明书写了图2、包里只有图1"能一路全绿：N4 只核表里的所在图号，
        # T1–T3 只看得到有清单的那几张图，两边都不看"声明过却没这张图"。
        d4 = os.path.join(d, 't4')
        make(d4, docs=DOCS.replace('图 1 为整体示意。', '图 1 为整体示意，图 2 为局部放大。'))
        r = run([PY, f'{S}/check_figure_text.py', d4])
        assert_(r.returncode == 1 and '声明了 图2' in r.stdout and '→ T4' in r.stdout,
                f'正文声明图2而包里没有这张图未被 T4 抓到: {show(r)}', r)

        d5 = os.path.join(d, 't5')
        make(d5, pngs=('图1', '图2'), manifest_for='图1')
        r = run([PY, f'{S}/check_figure_text.py', d5])
        assert_(r.returncode == 1 and '图2.png' in r.stdout and '→ T5' in r.stdout,
                f'多一张没人引用的图未被 T5 抓到: {show(r)}', r)

        d6 = os.path.join(d, 't6')
        make(d6, docs=DOCS.replace('图 1 为整体示意。', '图 1 为整体示意，图 2 为局部放大。'),
             pngs=('图1', '图3'))
        r = run([PY, f'{S}/check_figure_text.py', d6])
        assert_(r.returncode == 1 and '图号不是从 1 起连续编号（缺 [2]）' in r.stdout and '→ T6' in r.stdout,
                f'图号跳号未被 T6 抓到: {show(r)}', r)
        # T6 的分母只用实存文件：这张夹具里正文声明了 图2，若把声明并进分母，
        # {1,2,3} 就成了"连续"，跳号被缺图反向补圆——两码事必须各报各的。
        assert_('声明了 图2' in r.stdout and '→ T4' in r.stdout and '→ T5' in r.stdout,
                f'同一夹具里缺图/未引用两条没同时报出: {show(r)}', r)

        d7 = os.path.join(d, 't7')
        make(d7, docs=DOCS.replace('| 13 | 支架 | 1 |\n', '| 13 | 支架 | 1 |\n| 14 | 缓冲垫 | 1 |\n'))
        r = run([PY, f'{S}/check_figure_text.py', d7])
        assert_(r.returncode == 1 and '14=缓冲垫' in r.stdout and '→ T7' in r.stdout,
                f'表里多写一个图上没有的标记号未被 T7 抓到: {show(r)}', r)
        # T7 的方向必须是"表有而图无"：图有的号表里必须有，那一向是 T3 的地盘，
        # 这里若把夹具改成"图上多个号"就会撞进 T3，两支判据到底谁在咬就读不出来了。
        assert_('→ T3' not in r.stdout, f'同一夹具同时点亮 T3，T7 的开火无法归因: {show(r)}', r)

        d7u = os.path.join(d, 't7_orphan')
        make(d7u, docs=DOCS.replace('图 1 为整体示意。', '图 1 为整体示意，图 2 为局部放大。')
             .replace('| 13 | 支架 | 1 |\n', '| 13 | 支架 | 1 |\n| 14 | 缓冲垫 | 1 |\n'),
             pngs=('图1', '图2'), manifest_for='图1')
        r = run([PY, f'{S}/check_figure_text.py', d7u])
        # 包里有手画无留底的 PNG 时，表里那个号也许正画在它上面——看不见不许折成违规。
        # 这层守卫被摘掉时本档会翻成 rc=1 并打出违规句，两支断言同时看见。
        # 注意缺席断言取的是违规原话，不是 '→ T7'：未判那句自述里就写着「→ T7 未判」，
        # 拿前缀当 needle 会命中自己的说明文字，断言永远为假。
        assert_(r.returncode == 2 and 'T7 未判' in r.stdout
                and '但没有任何一张图真的标着' not in r.stdout,
                f'有手画无留底图时表里的号被硬判成 T7 违规（看不见≠违规）: {show(r)}', r)

        d_un = os.path.join(d, 't_unjudged')
        make(d_un, docs=DOCS.replace('图 1 为整体示意。', '整体示意见附件。'),
             pngs=('主视图',), manifest_for='主视图')
        r = run([PY, f'{S}/check_figure_text.py', d_un])
        assert_(r.returncode == 0 and 'T4–T6 未判' in r.stdout and '主视图.png' in r.stdout,
                f'文件名认不出图号时被折成合规或违规（不猜号才对）: {show(r)}', r)

        # ---- docx 通道：交付物只有 Word 件时 T 必须照判 ----
        # 第十八轮给 E/G/K/N 四把按列读的门禁接上 docx 通道，T 是第二十轮新立的，
        # 若不接就出现"文书池只认 md"：真交付件（Word）里的对照表与数值读不到，
        # 图上每个部件名都会被判成"文书里没有"——假红成串，且没有一条用例会喊。
        try:
            import docx  # noqa: F401
        except ImportError:
            print('  note T 档的 docx 通道未跑（本机无 python-docx，造不出带表格的 Word 夹具）')
        else:
            from docx import Document
            def wordpkg(root, speed='≤25mm/s', name12='底座'):
                os.makedirs(os.path.join(root, '02_申请文件', 'figures'), exist_ok=True)
                fig = os.path.join(root, '02_申请文件', 'figures', '图1.png')
                open(fig, 'wb').write(b'\x89PNG\r\n\x1a\n' + b'0' * 40)
                open(os.path.splitext(fig)[0] + '.manifest.json', 'w', encoding='utf8').write(MAN)
                doc = Document()
                doc.add_heading('附图说明', level=2)
                doc.add_paragraph('图 1 为整体示意图。躯干框架由铝合金制成。')
                doc.add_heading('具体实施方式', level=2)
                doc.add_paragraph(f'横移速度 {speed}。')
                doc.add_heading('图中标记说明', level=2)
                rows = [['标记', '名称', '所在图号'], ['12', name12, '1'], ['13', '支架', '1']]
                t = doc.add_table(rows=len(rows), cols=3)
                for i, row in enumerate(rows):
                    for j, v in enumerate(row):
                        t.cell(i, j).text = v
                doc.save(os.path.join(root, '说明书.docx'))
            w_ok = os.path.join(d, 'word_ok')
            wordpkg(w_ok)
            rw = run([PY, f'{S}/check_figure_text.py', w_ok])
            assert_(rw.returncode == 0 and '实判判据 7 条' in rw.stdout,
                    f'Word-only 交付包未被 T 真判（文书池只认 md 的话这里会成串假红）: {show(rw)}', rw)
            w_bad = os.path.join(d, 'word_bad')
            wordpkg(w_bad, speed='≤35mm/s')
            rw2 = run([PY, f'{S}/check_figure_text.py', w_bad])
            assert_(rw2.returncode == 1 and '量值「≤25mm/s」' in rw2.stdout and '→ T2' in rw2.stdout,
                    f'Word 件里的数值改了而图未改，T2 未开火: {show(rw2)}', rw2)
            w_t3 = os.path.join(d, 'word_t3')
            wordpkg(w_t3, name12='卡箍')
            rw3 = run([PY, f'{S}/check_figure_text.py', w_t3])
            assert_(rw3.returncode == 1 and '→ T3' in rw3.stdout and '12=底座' in rw3.stdout,
                    f'Word 对照表同号异名未被 T3 抓到（表没被还原成可取列的行）: {show(rw3)}', rw3)
            w_evil = os.path.join(d, 'word_evil')
            wordpkg(w_evil)
            open(os.path.join(w_evil, '说明书.docx'), 'wb').write(b'PK\x03\x04' + b'not a real zip')
            rw4 = run([PY, f'{S}/check_figure_text.py', w_evil])
            assert_(rw4.returncode == 2 and 'Traceback' not in rw4.stdout + rw4.stderr,
                    f'读不动的 docx 未走 rc=2（或未把 traceback 当违规）: {show(rw4)}', rw4)
    print('PASS check_figure_text（清单形状 + T1–T7 各成对 + 归一范围钉死 + 三档三态 + Word-only 通道）')


def test_check_figures_colour():
    """C5 与色彩豁免轴（《专利法实施细则》第三十条）：豁免看文书声明，不看目录名。

    这条轴补的是以前的假红面：彩色申请只要没把图放进 views/外观设计 目录，C1 就把合法件判违规；
    反方向也钉住——写了"请求保护色彩"却交一套黑白件，那是第三十条要求的反面。
    """
    from PIL import Image

    def build(root, doc_text, colour=True, blank=False):
        figs = os.path.join(root, '02_申请文件', 'figures')
        os.makedirs(figs, exist_ok=True)
        img = Image.new('RGB', (80, 80), (255, 0, 0) if colour else 'white')
        if not colour and not blank:            # 黑白但非空白：画条黑线，免得撞 C2
            for x in range(10, 70):
                img.putpixel((x, 40), (0, 0, 0))
        img.save(os.path.join(figs, '图1.png'))
        open(os.path.join(root, '02_申请文件', '说明书.md'), 'w',
             encoding='utf8').write(doc_text)
        return root

    DECL = '# 说明书\n简要说明：申请人请求保护色彩。\n'
    NONE = '# 说明书\n简要说明：本外观设计不请求保护色彩。\n'
    with tempfile.TemporaryDirectory() as d:
        ok = build(os.path.join(d, 'declared'), DECL)
        r = run([PY, f'{S}/check_figures.py', ok])
        assert_(r.returncode == 0 and '请求保护色彩' in r.stdout
                and 'C1 彩色像素' not in r.stdout and '说明书.md:2' in r.stdout,
                f'声明了请求保护色彩的彩色件仍被 C1 误伤，或豁免没说出依据在哪: {show(r)}', r)

        bw = build(os.path.join(d, 'declared_bw'), DECL, colour=False)
        r = run([PY, f'{S}/check_figures.py', bw])
        assert_(r.returncode == 1 and '-> C5' in r.stdout,
                f'写了请求保护色彩却交一套黑白件，没被 C5 抓到: {show(r)}', r)

        undecl = build(os.path.join(d, 'undeclared'), NONE, colour=False)
        r = run([PY, f'{S}/check_figures.py', undecl])
        assert_(r.returncode == 0 and 'C5' not in r.stdout,
                f'没声明色彩保护却被 C5 判红（第三十条只约束声明过的申请）: {show(r)}', r)

        nodir = build(os.path.join(d, 'undeclared_colour'), NONE)
        r = run([PY, f'{S}/check_figures.py', nodir])
        assert_(r.returncode == 1 and 'C1 彩色像素' in r.stdout,
                f'未声明的彩色件不再被 C1 判红（豁免轴串到了不该豁免的一侧）: {show(r)}', r)

        empty = os.path.join(d, 'noimg', '02_申请文件')
        os.makedirs(empty)
        open(os.path.join(empty, '说明书.md'), 'w', encoding='utf8').write(DECL)
        r = run([PY, f'{S}/check_figures.py', os.path.join(d, 'noimg')])
        assert_(r.returncode == 0 and 'C5 未判' in r.stdout,
                f'声明了但扫不到图时被硬判成 C5 违规（应是未判）: {show(r)}', r)

        # 读不动的文书既不能当"没声明"（否则后面那份真声明会被丢掉→合法彩色件被误伤），
        # 也不能悄悄当"已声明"。两向各一档：
        unread = build(os.path.join(d, 'unreadable'), DECL)
        open(os.path.join(unread, '01_坏件.docx'), 'wb').write(b'not a zip')
        r = run([PY, f'{S}/check_figures.py', unread])
        assert_('未全核' in r.stdout and r.returncode == 0 and 'C1 彩色像素' not in r.stdout,
                f'一份文书读不动就把后面的声明也丢了（豁免轴提前退出）: {show(r)}', r)

        un2 = build(os.path.join(d, 'unreadable_nodecl'), NONE)
        open(os.path.join(un2, '01_坏件.docx'), 'wb').write(b'not a zip')
        r = run([PY, f'{S}/check_figures.py', un2])
        # 断言取的是 C1 行上那句"1 份文书读不动"——扫描时的 note 里也有"未全核"，
        # 拿它当 needle 的话，把计数归零的变异照样过，等于没钉。
        assert_(r.returncode == 1 and 'C1 彩色像素' in r.stdout and '1 份文书读不动' in r.stdout,
                f'未核这件事没跟着真开火的 C1 一起出去（只沉在开头 note 里＝等于没说）: {show(r)}', r)
    print('PASS check_figures_colour（声明豁免带出处 / C5 开火 / 未声明不误伤 / 无图未判 / 读不动未核）')


def test_check_figures_input_guard():
    """C 门禁的输入档：未知 flag / 不存在的路径 / 零参数一律 rc=2 说成因，空目录不误伤。

    这里曾经是 `for d in sys.argv[1:]` 把每个实参直接喂给 os.listdir：
    `<目录> --all` 以 FileNotFoundError 崩在 C4 并退 1，而退码 1 在本仓专属"存在违规"，
    等于给一次环境错误发了张违规单；零参数则 total_bad=0 静默退 0，把"没判"报成"通过"。
    两个方向都在撒谎，所以三档各钉一条，并留一档合规侧防止输入档过严误伤真目录。

    --help/-h 是这条输入档上唯一的豁免（九把门禁里曾只有这一把没有用法出口，
    其余八把靠 argparse 自带 -h/--help），豁免必须只给这两个名字：
    所以正向钉"打了用法且退 0"，反向钉"--al/--foo 仍 rc=2"。
    """
    with tempfile.TemporaryDirectory() as d:
        r = run([PY, f'{S}/check_figures.py', d, '--all'])
        assert_(r.returncode == 2 and '不认 flag' in r.stdout
                and 'Traceback' not in r.stdout + r.stderr,
                f'未知 flag 被当成目录喂进 C 门禁（崩一次就是一张假违规单）: {show(r)}', r)
        r = run([PY, f'{S}/check_figures.py', os.path.join(d, '不存在')])
        assert_(r.returncode == 2 and '不是目录' in r.stdout,
                f'路径不存在未说清成因并 fail-closed: {show(r)}', r)
        r = run([PY, f'{S}/check_figures.py'])
        assert_(r.returncode == 2 and '未做任何判定' in r.stdout,
                f'一个目录都没接却被当成已通过: {show(r)}', r)
        r = run([PY, f'{S}/check_figures.py', d])
        assert_(r.returncode == 0 and '0 幅图' in r.stdout,
                f'合规空目录被输入档误伤: {show(r)}', r)
        # 正向：--help / -h 必须真的打印用法并退 0（用法串逐字取自 scripts/check_figures.py 的 USAGE）
        for flag in ('--help', '-h'):
            r = run([PY, f'{S}/check_figures.py', flag])
            assert_(r.returncode == 0
                    and '用法: python3 check_figures.py' in r.stdout
                    and '除 -h/--help 外不认任何其它 flag' in r.stdout
                    and 'C3 目录内每个 docx 嵌入的 media 图片数' in r.stdout
                    and '退出码: 0 合规或未判' in r.stdout
                    and 'Traceback' not in r.stdout + r.stderr,
                    f'{flag} 出口未打印用法并退 0（被输入档当成未知 flag 吞掉）: {show(r)}', r)
        # 反向：豁免只给 --help/-h，其余 - 开头的参数一律继续 rc=2，不许顺手宽容解析
        for flag in ('--al', '--foo'):
            r = run([PY, f'{S}/check_figures.py', flag])
            assert_(r.returncode == 2 and '不认 flag' in r.stdout
                    and '用法: python3 check_figures.py <申请文件目录' not in r.stdout
                    and 'Traceback' not in r.stdout + r.stderr,
                    f'{flag} 被 --help 豁免连带宽容掉了（退码契约要求未知 flag 仍 rc=2）: '
                    f'{show(r)}', r)
    print('PASS check_figures 输入档（未知 flag / 不存在路径 / 零参数三档 rc=2 + 空目录不误伤 '
          '+ --help/-h 打印用法退 0 + --al/--foo 仍 rc=2）')


def test_battery_needle_census():
    """变异电池自己的牙：每条 needle 必须在其目标脚本里恰好命中一次。

    命中 0 次＝脚本改了而电池没同步，那一支变异要等整档跑完十几分钟才以 PROBE-FAIL 现身；
    命中 >1 次＝`replace(old, new, 1)` 会打到**第一个**同形片段，未必是被指控的那段代码
    （第 16 轮实测：C3 与 C4 各有一段一模一样的 docx 循环，锚点歧义到体检这一步才暴露）。
    电池 baseline 会先跑本套件，所以这条断言等于给整支电池加了"落锤前体检"。

    跑批时的例外：电池每次只换掉一条 needle，那一条（以及共用同一 (脚本, needle) 的兄弟）
    当然"找不到"——所以它认 PP_MUTATING（`组/标签`，由 suite() 传入），跳过正在生效的那一支
    以及** needle 与被改写片段有包含关系的姐妹条目**：fig 档有两支变异打在同一条 `if` 上，
    一支只看这行、另一支连着下一行，needle 互为前缀，动其中一支另一支就"找不到"。
    baseline 不带这个变量，体检仍是全量。
    """
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('mb_needle_census',
                                       os.path.join(ROOT, 'tests', 'mutation_battery.py'))
    mb = ilu.module_from_spec(spec)
    spec.loader.exec_module(mb)
    # 空变异：new 与 old 一字不差的臂改不动任何东西，那一支永远只能读出"存活/注入无效"，
    # 却照样被计入"跑了 N 条"。记忆里"登记对照前先数 old 恰好一处、new 不许是原文"讲的就是这格，
    # 此前只有前半（needle 命中数）被常驻挡着，后半没人管。
    noop = [f'{g}/{a[0]}' for g, entries in mb.MUTS.items() for a in entries if a[2] == a[3]]
    assert_(not noop, f'这些变异臂改写前后完全相同（空变异，读不出任何牙）: {noop}', None)
    # 臂表总数留一份，下面用来证明"体检的分母 == 臂表全量"（没被静默跳过）
    n_arms = sum(len(v) for v in mb.MUTS.values())
    # 只挡"电池此刻正在改写的那一片"：同脚本内 needle 相等、互为包含的都算被波及
    # （一次 replace 会让它们同时看不见锚点，报失配是体检在诬告变异）
    mutating = os.environ.get('PP_MUTATING', '').strip()
    applied = []
    if mutating:
        for group, entries in mb.MUTS.items():
            for label, rel, old, new, expect in entries:
                if f'{group}/{label}' == mutating:
                    applied.append((rel, old))
        assert applied, f'PP_MUTATING={mutating!r} 在 MUTS 里找不到，电池与套件对不上号'

    def covered(rel, old):
        return any(arel == rel and (aold == old or aold in old or old in aold)
                   for arel, aold in applied)
    texts, miss, dup, total, skipped = {}, [], [], 0, 0
    for group, entries in mb.MUTS.items():
        assert entries, f'{group} 档是空的，电池在冒充有多档'
        for label, rel, old, new, expect in entries:
            if mutating and covered(rel, old):
                skipped += 1
                continue
            total += 1
            if rel not in texts:
                p = os.path.join(ROOT, rel)
                texts[rel] = open(p, encoding='utf8').read() if os.path.isfile(p) else None
            src = texts[rel]
            n = 0 if src is None else src.count(old)
            if n == 0:
                miss.append(f'{group}/{label} → {rel}')
            elif n > 1:
                dup.append(f'{group}/{label} → {rel} 命中 {n} 次')
    assert_(total + skipped == n_arms,
            f'体检的分母比臂表全量少 {n_arms - total - skipped} 条：有臂被静默跳过（跳过的口子只有'
            f'「电池正在生效的那一支」，其余一律该数进来）: 数到 {total} + 跳过 {skipped} ≠ 臂表 {n_arms}',
            None)
    assert_(len(texts) >= 6 and total >= 100,
            f'分母异常（{total} 条变异 / {len(texts)} 个目标脚本），本检查空转', None)
    assert_(not mutating or skipped >= 1, f'跳过分母为 0，PP_MUTATING 没起作用: {mutating}', None)
    assert_(not miss, f'这些 needle 在目标脚本里找不到，跑批只会整条 PROBE-FAIL: {miss}', None)
    assert_(not dup, f'这些 needle 命中多次，变异会打到同形的另一处: {dup}', None)
    tail = f'，另跳过电池正在生效的 {skipped} 条' if skipped else ''
    # 用法行里的 arm 清单是手抄的：抄漏一支，那支电池就等于不存在（没人会去跑它）
    listed = re.search(r'只跑一支（([a-z|]+)）', mb.__doc__ or '')
    assert_(listed is not None, '电池 docstring 没有「只跑一支（…）」这份清单，反漂移断言空转', None)
    got = sorted(listed.group(1).split('|'))
    want = sorted(mb.MUTS)
    assert_(got == want, f'电池 docstring 的 arm 清单与 MUTS 键不对齐: {got} vs {want}', None)

    # 每条 expect 必须是测试文件里真存在的断言消息（否则那一支变异翻红时无人点名它，
    # 读成 MISRED 却是 expect 自己在撒谎）。两处归一化：折叠跨行隐式拼接的字面量接缝，
    # 以及抹掉 f-string 的 {表达式}——消息在运行时才拼出来的部分不该要求源文本逐字含有。
    tsrc = open(os.path.join(ROOT, 'tests', 'test_scripts.py'), encoding='utf8').read()
    flat = re.sub(r"\{[^{}]*\}", '', re.sub(r"'\s*\n\s*'", '', tsrc))
    dead = [f'{g}/{label} → {w}' for g, entries in mb.MUTS.items()
            for label, rel, _o, _n, exp in entries
            for w in ([exp] if isinstance(exp, str) else list(exp)) if w not in flat]
    assert_([d for d in dead] == [], f'电池里有 expect 在测试文件里找不到对应断言: {dead}', None)

    print(f'PASS 变异电池锚点体检（{total} 条 needle × {len(texts)} 个脚本 / {len(want)} 档，'
          f'全部恰好命中一次{tail}）')


def test_patent_figure():
    """绘图期约束 F1–F6：几何/图题/标记/框内文字/线宽/灰底与位图。缺 matplotlib 时如实 SKIP，不冒充跑过。"""
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        SKIPPED.append('patent_figure')
        print('SKIP patent_figure（本机无 matplotlib；装上后本档自动启用，见环境自检）')
        return
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('patent_figure', os.path.join(S, 'patent_figure.py'))
    pf = ilu.module_from_spec(spec)
    spec.loader.exec_module(pf)

    with tempfile.TemporaryDirectory() as d:
        # 必绿：按纪律默认值出图，几何与像素均应通过
        f = pf.Figure('图1', fig_w_cm=15.0, dpi=200)
        assert_(f.violations == [], f'合规几何参数被建图即判红: {f.violations}')
        right = f.box(1, 4, 3, 2, text='躯干框架')
        assert_(f.violations == [], f'合规框内文字被 F4 误判: {f.violations}')
        f.label(1, '躯干框架', at=(5.2, 5.0), anchor=right)
        p = f.save(os.path.join(d, '图1.png'))
        assert_(f.verify_saved(p) == [], 'verify_saved 复检未全绿（F1/F2/F3 任一误伤都落这里）')
        with __import__('PIL').Image.open(p) as im:
            w_px = im.size[0]
        assert_(abs(w_px / 200 * 2.54 - 15.0) < 0.1, f'实际图宽 {w_px}px@200dpi 不落在 15cm')

        # F5：带宽判在入参侧。两向都要钉——出带必红，带边（0.8/1.5 闭区间）与
        # 引出线 0.6pt（规则自己要求的细直线，显式豁免类）必不红。
        for w, tag in ((0.5, 'F5'), (0.79, 'F5'), (1.51, 'F5'), (2.0, 'F5')):
            bad = pf.Figure('图F5')
            bad.line([(0, 0), (9, 9)], width=w)
            assert_(any(tag in v for v in bad.violations), f'线宽 {w}pt 未被 F5 拦住: {bad.violations}')
        for w in (0.8, 1.0, 1.5):
            okfig = pf.Figure('图F5ok')
            okfig.line([(0, 0), (9, 9)], width=w)
            okfig.label(2, '部件', at=(4, 4), anchor=(6, 6))     # 引出线走 0.6pt 豁免
            assert_(okfig.violations == [], f'带宽内的合法线宽被 F5 误伤（{w}pt）: {okfig.violations}')

        # F6 灰底／半透明／内嵌位图／colormap 集合：判在画布对象上（像素侧被实测否决，
        # 见 tooling-pitfalls §9）。四红三绿，三支绿的每支都是一次"收紧就误伤"的对照：
        # 常规框线、规则自己要求的 45° 剖面 hatch、实心白填充。
        def _f6(name, draw):
            g = pf.Figure(name)
            draw(g)
            got = g.scan_vector()
            g._plt.close(g.fig)        # 不关就会撞上 matplotlib 的 20 图上限告警
            return got

        def _gray(g):
            g.box(2, 3, 4, 3)
            g.ax.add_patch(g._plt.Rectangle((2, 3), 4, 3, fill=True, facecolor='0.5',
                                            edgecolor='none'))

        def _alpha(g):
            g.ax.add_patch(g._plt.Rectangle((2, 3), 4, 3, fill=True, facecolor='white',
                                            alpha=0.4, edgecolor='none'))

        def _img(g):
            g.ax.imshow([[0, 1], [1, 0]], cmap='gray', aspect='auto')

        def _contour(g):
            import numpy as _np
            xx, yy = _np.meshgrid(_np.linspace(0, 1, 6), _np.linspace(0, 1, 6))
            g.ax.contourf(xx, yy, xx + yy, levels=5)

        for tag, draw in (('灰底填充', _gray), ('半透明填充', _alpha),
                          ('内嵌位图', _img), ('等高线渐变', _contour)):
            got = _f6('图F6红', draw)
            assert_(any('F6' in v for v in got), f'F6 未拦住{tag}: {got}')
        # 合规侧三支：常规出图、剖面斜线（规则要的画法）、实心白填充
        right6 = pf.Figure('图F6绿')
        anchor6 = right6.box(1, 4, 3, 2, text='躯干框架')
        right6.label(1, '躯干框架', at=(5.2, 5.0), anchor=anchor6)
        assert_(right6.scan_vector() == [], f'F6 误伤常规出图: {right6.scan_vector()}')
        def _hatch(g):
            g.ax.add_patch(g._plt.Rectangle((6, 4), 3, 2, fill=True, facecolor='none',
                                            edgecolor='black', hatch='///', linewidth=1.0))
        assert_(_f6('图F6剖面', _hatch) == [], 'F6 把规则自己要求的 45° 剖面斜线判红了')
        def _white(g):
            g.ax.add_patch(g._plt.Rectangle((1, 4), 3, 2, fill=True, facecolor='white',
                                            edgecolor='black', linewidth=1.0))
        assert_(_f6('图F6白填', _white) == [], 'F6 把实心白填充判红了（白底是纪律要求的底色）')
        # F6 必须挂在 save() 上：只在 scan_vector 里判、save 不调用，等于出图照样落盘
        refuse = pf.Figure('图F6拒')
        _gray(refuse)
        try:
            refuse.save(os.path.join(d, '不该存在的图.png'))
            fired = False
        except SystemExit:
            fired = True
        assert_(fired, 'F6 没接进 save()：灰底图照样落盘')
        assert_(not os.path.exists(os.path.join(d, '不该存在的图.png')),
                'F6 拒绝出图却没有删掉文件（违规件会被打包带走）')

        # F1 必红：dpi 不足 / 图宽越界
        for kw, tag in ((dict(dpi=100), 'F1'), (dict(fig_w_cm=20.0), 'F1')):
            bad = pf.Figure('图X', **kw)
            assert_(any(tag in v for v in bad.violations), f'F1 未拦住 {kw}')

        # F4 必红：框内文字 >12 字
        g = pf.Figure('图Y')
        g.box(1, 1, 5, 2, text='一二三四五六七八九十十一十二')
        assert_(any('F4' in v for v in g.violations), 'F4 未拦超长框内文字')

        # F2 必红：把图题塞进图内
        h = pf.Figure('图Z')
        h.box(1, 1, 3, 2, text='载荷带')
        try:
            h.save(os.path.join(d, '图Z.png'), caption='图Z 主视图')
            raised = False
        except SystemExit as e:
            raised = 'F2' in str(e)
        assert_(raised, 'save(caption=) 未拒绝嵌图题')

        # F3 必红 + 拒绝交付：同一编号在同图内指两个部件 → save 报错并删掉该文件
        k = pf.Figure('图W')
        a = k.box(1, 1, 2, 2, text='框架')
        b = k.box(6, 1, 2, 2, text='驱动')
        k.label(1, '框架', at=(4, 2), anchor=a)
        k.label(1, '驱动', at=(5, 2), anchor=b)
        wp = os.path.join(d, '图W.png')
        try:
            k.save(wp)
            raised = False
        except SystemExit as e:
            raised = 'F3' in str(e)
        assert_(raised, '同图内同号异件未被 F3 抓到')
        assert_(not os.path.exists(wp), '自检未过的图仍留在盘上（会被打包带走）')

        # F3 跨图：一致必绿、不一致必红
        bad, _ = pf.check_cross_figure({'图1': {1: '框架'}, '图2': {1: '框架'}})
        assert_(bad == [], f'跨图同号一致却报红: {bad}')
        bad, _ = pf.check_cross_figure({'图1': {1: '框架'}, '图2': {1: '驱动'}})
        assert_(any('F3' in x for x in bad), '跨图同号异件未抓到')

        # F3 出图当场对登记表核对：同号异件必红、同号同件必绿
        q = pf.Figure('图Q', parts={1: '躯干框架'})
        aq = q.box(2, 1, 3, 2, text='驱动带')
        q.label(1, '驱动带', at=(6, 2), anchor=aq)
        assert_(any('F3' in x for x in q.verify_saved(p)),
                '与本案登记表同号异件未在出图当场抓到')
        w = pf.Figure('图W', parts={1: '躯干框架'})
        aw = w.box(2, 1, 3, 2, text='驱动带')
        w.label(1, '躯干框架', at=(6, 2), anchor=aw)
        assert_(not any('F3' in x for x in w.verify_saved(p)),
                '与登记表同号同件被 F3 误判')

        # --check CLI：合规整目录必绿
        parts = os.path.join(d, 'parts.json')
        open(parts, 'w', encoding='utf8').write('{"图1.png": {"1": "躯干框架"}}')
        r = run([PY, f'{S}/patent_figure.py', '--check', d, '--parts', parts])
        assert_(r.returncode == 0 and '违规 0' in r.stdout, '--check 合规目录未全绿', r)
        # 离线档必须自己说清"这一档不判 F4/F5"：F5 事后没有 witness，
        # 不打印这句的话，"违规 0"会被读成"F1–F6 全核过"。（needle 与电池注入共用那半句）
        assert_('F5 线宽无位图侧 witness' in r.stdout,
                '--check 未打印离线覆盖面自述，违规 0 会被读成全核过', r)

        # --check 必红：混入一张彩色图（带 dpi 元数据，让它走几何已核那条路，
        # 免得"几何三态"的变异被这一档抢先判红，红因就归不到正确的条款上）
        _line_figure(os.path.join(d, '图9.png'), w=1181, tint=(255, 0, 0), dpi=200)
        r = run([PY, f'{S}/patent_figure.py', '--check', d, '--parts', parts])
        assert_(r.returncode == 1 and 'F2 C1' in r.stdout, '--check 未拦彩色图', r)
        os.remove(os.path.join(d, '图9.png'))

        # --check 必红：PNG 自带 dpi 且换算图宽 25.4cm → F1 必须现判
        _line_figure(os.path.join(d, '图7_超宽.png'), w=2000, dpi=200)
        r = run([PY, f'{S}/patent_figure.py', '--check', d, '--parts', parts])
        assert_(r.returncode == 1 and 'F1 图宽' in r.stdout,
                'PNG 带 dpi 元数据时 --check 未核图宽', r)
        # --check 必绿：同一张图改回 15cm（1181px@200dpi）必须整条放行
        os.remove(os.path.join(d, '图7_超宽.png'))
        _line_figure(os.path.join(d, '图7_合规宽.png'), w=1181, dpi=200)
        r = run([PY, f'{S}/patent_figure.py', '--check', d, '--parts', parts])
        assert_(r.returncode == 0 and '违规 0' in r.stdout,
                '带 dpi 的合规宽度图被 --check 判红', r)
        os.remove(os.path.join(d, '图7_合规宽.png'))

        # 三态：PNG 无 dpi 元数据时 F1 报未核。2000px 宽按纪律下限 200dpi 反推是 25.4cm，
        # 若脚本拿假定 dpi 反推就会把这张图误判违规——正是这条断言要钉住的。
        _line_figure(os.path.join(d, '图8_无dpi元数据.png'), w=2000)
        r = run([PY, f'{S}/patent_figure.py', '--check', d])
        assert_(r.returncode == 0 and 'F1 几何未核' in r.stdout,
                '无 dpi 元数据时 F1 未走三态（可能被假定 dpi 反推误判）', r)
        # 配套必红：几何未核不得把同一张图的像素判据一起免检
        os.remove(os.path.join(d, '图8_无dpi元数据.png'))
        _line_figure(os.path.join(d, '图8_无dpi元数据.png'), w=2000, tint=(255, 0, 0))
        r = run([PY, f'{S}/patent_figure.py', '--check', d])
        assert_(r.returncode == 1 and 'F2 C1' in r.stdout and 'F1 几何未核' in r.stdout,
                'F1 三态把该图的像素判据一起免检了', r)
        os.remove(os.path.join(d, '图8_无dpi元数据.png'))

        # 三态：不给 parts 时 F3 报未核，既不折成违规也不折成合规
        r = run([PY, f'{S}/patent_figure.py', '--check', d])
        assert_(r.returncode == 0 and 'F3 跨图同号未核' in r.stdout,
                '缺 parts 登记表时 F3 未走三态', r)

        # 输入不可用两类，均须 rc=2 并说出成因
        r = run([PY, f'{S}/patent_figure.py', '--check', os.path.join(d, '图1.png')])
        assert_(r.returncode == 2 and '--check 需要目录' in r.stdout, '--check 指文件未说明成因', r)
        with tempfile.TemporaryDirectory() as empty:
            r = run([PY, f'{S}/patent_figure.py', '--check', empty])
            assert_(r.returncode == 2 and '未找到 .png' in r.stdout, '--check 空目录未说明成因', r)
    print('PASS patent_figure（F1–F6 各自成对 + 跨图同号 + 三态 + rc=2；真 matplotlib 出图）')


if __name__ == '__main__':
    missing = probe_env()
    TESTS = [test_check_figures, test_check_figures_media_count, test_check_figures_embedded,
             test_new_product_package, test_rebuild_package, test_check_claims,
             test_check_figures_colour,
             test_regen_docx,
             test_regen_docx_stale, test_check_iron_rules, test_check_iron_rules_docx,
             test_iron_spec_region_shapes, test_iron_spec_region_shapes_docx,
             test_iron_r14_illustration, test_r7_title_tiers,
             test_check_evt, test_check_regulatory, test_check_design_completion,
             test_docx_table_channel,
             test_check_figure_labels, test_verify_search_report,
             test_search_report_docx_channel, test_figure_text_channel, test_battery_needle_census,
             test_patent_figure, test_docs_scripts_contract,
             test_battery_crash_attribution, test_check_figures_input_guard]
    # 分母自证：清单里漏掉一个已定义的 test_* 函数，就等于那档从没跑过却按通过上报
    defined = {n for n, v in globals().items()
               if n.startswith('test_') and callable(v)}
    unrun = sorted(defined ^ {t.__name__ for t in TESTS})
    assert not unrun, f'测试清单与模块内定义的 test_* 不对齐: {unrun}'
    TOTAL_TESTS = len(TESTS)
    for t in TESTS:
        t()
    ran = TOTAL_TESTS - len(SKIPPED)
    tail = f'另有 {len(missing)} 项环境依赖缺失，见上方环境自检' if missing else ''
    if SKIPPED:
        print(f'\n{ran}/{TOTAL_TESTS} 项冒烟测试 PASS，{len(SKIPPED)} 项 SKIP（{", ".join(SKIPPED)}）'
              f'——SKIP 的档未跑过，不得计入通过' + (f'（{tail}）' if tail else ''))
    else:
        print(f'\n全部 {ran} 项冒烟测试 PASS' + (f'（{tail}）' if tail else ''))
