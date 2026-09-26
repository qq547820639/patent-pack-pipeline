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
    ('matplotlib', 'matplotlib', '专利附图出图 scripts/patent_figure.py（F1–F4 与出图自检，SKILL 纪律 2）'),
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
                '骨架底稿未通过 V1–V3，或未如实报出"条目 0 条"', rv)
        ri = run([PY, f'{S}/check_iron_rules.py', d, '--all'])
        assert_(ri.returncode == 0, '新生成的包未通过铁律门禁（底稿措辞与 R 判据打架）', ri)
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
        pkg = os.path.join(d, 'T包_交付包'); os.makedirs(os.path.join(pkg, '01_交底书'))
        src = os.path.join(pkg, '01_交底书', '交底书.md')
        BODY = '中文内容测试' * 8
        open(src, 'w', encoding='utf8').write(BODY)
        r = run([PY, f'{S}/rebuild_package.py', pkg])
        assert_(r.returncode == 0 and 'SHA-256+CRC+UTF-8 标志位全过' in r.stdout, '打包或 P1–P4 校验异常', r)
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
    print('PASS rebuild_package（P1 截断 / P2 换字 / P3 CRC 单报 / 名单差集 / 合规包零误报 / rc=2 三档）')


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
IRON_OK_BG = '现有技术 CN110404188A 公开了一种髋关节助力结构，与本案的区别在于载荷传递路径。'
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

        # 三态：没有标题样式的 docx 找不到节 → 必须说"未核"，不能拿"违规 0"冒充核过
        naked = os.path.join(d, '无节标题.docx')
        doc = Document()
        doc.add_paragraph('本实用新型公开了一种节点，摘要字数无从判断。' * 20)
        doc.save(naked)
        r = run([PY, f'{S}/check_iron_rules.py', naked])
        assert_(r.returncode == 0 and '未识别到节标题样式' in r.stdout,
                f'无节标题的 docx 未报三态: {show(r)}', r)

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


def test_check_iron_rules():
    """铁律门禁 R1–R5：每条判据各自成对（注入即红 / 合规必绿），外加三态与输入不可用档。"""
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

        # R7 发明名称 ≤25 字（templates §0）：超限必红，合规必绿，字段缺失报未核
        named = '# 专利技术交底书\n\n## 0. 著录项目\n   - 发明名称：{t}\n'
        long_name = '一种' + '腰部助力外骨骼控制装置' * 3
        assert_(len(long_name) > 25, f'必红夹具仅 {len(long_name)} 字，未超限')
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

        # 门禁自报的规则区间必须与它实际定义的判据一致：总结行谎称 R1–R5 曾经无人核对，
        # 档位由脚本源码现推（不在此硬编码，否则两处各自漂移）
        irtxt = open(f'{S}/check_iron_rules.py', encoding='utf8').read()
        # \s* 不可省：R8 的 Finding( 与实参之间有换行，紧凑写法会漏读成 R1–R7
        rnums = sorted({int(x) for x in re.findall(r"Finding\(\s*['\"]R(\d)", irtxt)})
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
    print(f'PASS check_iron_rules（R1–R8 各条成对必红必绿 + 三态 + rc=2 + --all 四档；'
          f'摘要 {n_ok}/{n_over} 字）')


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

    defined_rules, flags_by_script = set(), {}
    rule_home = {}
    for name, s in scripts.items():
        found = (set(re.findall(r"Finding\(\s*['\"]([RCFVEGKNQTP]\d)", s))
                 | set(re.findall(r'^\s+([RCFVEGKNQTP]\d)\s', s, re.M))
                 | set(re.findall(r'\u2192 ([NVEGKT]\d)', s)))
        for t in found:
            rule_home.setdefault(t, set()).add(name)
        defined_rules |= found
        flags_by_script[name] = set(re.findall(r"add_argument\('(--[a-z\-]+)'", s))
    doc_rules = set(re.findall(r'\b([RCFVEGKNQTP][1-9])\b', doctxt))
    assert_(doc_rules == defined_rules,
            f'判据 token 不对齐 文档虚指={sorted(doc_rules - defined_rules)} '
            f'文档漏写={sorted(defined_rules - doc_rules)}（脚本判据须全部有文档出处，反之亦然）')
    # 同号两义防线：一个判据号只许有一个脚本定义它
    coll = {t: sorted(v) for t, v in rule_home.items() if len(v) > 1}
    assert_(not coll, f'判据号被两个脚本各自定义，读者无法分辨指代: {coll}')

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
    # 任何提到本门禁并给出规则区间的文档行，区间都必须等于脚本源码现推的判据范围
    # （README 用法行与 pipeline-stages 的"出 R1–R5 红点"都曾谎报且无人核对）
    rnums = sorted({int(x) for x in re.findall(r"Finding\(\s*['\"]R(\d)",
                                               scripts['check_iron_rules.py'])})
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
          f'参数 {len(all_flags)} 项，双向对齐；自报区间 {span} 核对 {hit} 处）')


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
    """检索报告门禁 V1–V3：默认不碰网络（fetch 被桩替），网络路径另有 live 档。"""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location('verify_search_report',
                                       os.path.join(S, 'verify_search_report.py'))
    vsr = ilu.module_from_spec(spec)
    spec.loader.exec_module(vsr)

    HDR = ('| # | 类型 | 标识符 | 标题 | 关键日期 | 核验出处 | 核验日期 |\n'
           '|---|---|---|---|---|---|---|\n')
    P = '| 1 | 专利 | CN110404188A | 一种节点 | 公开日 2019-07-26 | CNIPA 著录页 | 2026-09-25 |'
    A = '| 2 | 论文 | arXiv:1706.03762 | Attention | 2017-06-12 | arXiv 摘要页 | 2026-09-25 |'
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
        print('PASS verify_search_report（V1–V3 成对 + 三态 + 死代理 rc=2 + live 档两源各配控制探针）')


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
    """权利要求形状门禁 Q1–Q5：每条各一支开火夹具 + 一支合规 + 三态 + docx 通道。

    合规档必须先过：Q4/Q5 这种"两支互斥"的判据一旦把合规写法也判红，整套就是永久红灯。
    q4 档刻意写成"引用号都在前"，让它只点亮 Q4——同档撞两支判据时，读数说不清是谁在咬。
    """
    TBL = ('## 图中标记说明\n| 标记 | 名称 | 所在图号 |\n|---|---|---|\n'
           '| 1 | 躯干框架 | 1 |\n| 2 | 锁扣本体 | 1 |\n')
    OK = ('# 说明书\n## 权利要求书\n'
          '1. 一种锁扣装置，包括躯干框架（1）与锁扣本体（2），其特征在于：所述锁扣本体（2）与所述躯干框架（1）铰接。\n'
          '2. 根据权利要求 1 所述的锁扣装置，其特征在于：所述锁扣本体（2）的弹臂拉脱力 90N。\n'
          '3. 根据权利要求1或2所述的锁扣装置，其特征在于：所述弹臂为钛合金。\n' + TBL)

    def mkpkg(root, body):
        os.makedirs(os.path.join(root, '02_申请文件'), exist_ok=True)
        open(os.path.join(root, '02_申请文件', '说明书.md'), 'w', encoding='utf8').write(body)
        return root

    with tempfile.TemporaryDirectory() as d:
        ok = mkpkg(os.path.join(d, 'ok'), OK)
        r = run([PY, f'{S}/check_claims.py', ok])
        assert_(r.returncode == 0 and '实判判据 5 条' in r.stdout and '→ Q' not in r.stdout,
                f'合规权要被判红，或五条没各判到: {show(r)}', r)

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
                            '4. 根据权利要求1或3所述的锁扣装置，其特征在于：所述弹臂表面镀硬铬。\n'
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

        p = os.path.join(d, 'noclaims')
        os.makedirs(p)
        open(os.path.join(p, '交底书.md'), 'w', encoding='utf8').write('# 交底书\n暂无权要。\n')
        r = run([PY, f'{S}/check_claims.py', p])
        assert_(r.returncode == 0 and 'Q1–Q5 未判' in r.stdout,
                f'没有权利要求书节被折成合规或未上报: {show(r)}', r)

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
            assert_(r.returncode == 0 and '实判判据 5 条' in r.stdout,
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
            open(os.path.join(bad_doc, '坏件.docx'), 'wb').write(b'not a zip')
            r = run([PY, f'{S}/check_claims.py', bad_doc])
            assert_(r.returncode == 2 and '输入不可用' in r.stdout and 'Traceback' not in r.stderr,
                    f'读不动的 docx 崩成异常或退码不是 2: {show(r)} / {r.stderr[-140:]}', r)
    print('PASS check_claims（Q1–Q5 各成对 + 合规档同过 + 引用号不当标记 + 三态 + docx 通道 + rc=2）')


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
    """绘图期约束 F1–F4：几何/图题/标记/框内文字。缺 matplotlib 时如实 SKIP，不冒充跑过。"""
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
    print('PASS patent_figure（F1–F4 各自成对 + 跨图同号 + 三态 + rc=2；真 matplotlib 出图）')


if __name__ == '__main__':
    missing = probe_env()
    TESTS = [test_check_figures, test_check_figures_media_count, test_check_figures_embedded,
             test_new_product_package, test_rebuild_package, test_check_claims,
             test_regen_docx,
             test_regen_docx_stale, test_check_iron_rules, test_check_iron_rules_docx,
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
