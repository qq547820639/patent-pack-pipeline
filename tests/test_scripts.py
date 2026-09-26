#!/usr/bin/env python3
"""patent-pack-pipeline 脚本冒烟测试（吸收 K-Dense CI 纪律：带 scripts/ 的技能必须带 tests/）。
运行: python3 tests/test_scripts.py（仓库根目录执行）
同时兼作环境自检：打印各依赖是否就绪、缺失影响哪个环节。
"""
import importlib.util
import os, re, shutil, sys, tempfile, subprocess, zipfile, stat
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
PY = sys.executable
SKIPPED = []   # 整档未跑的测试记这里，收尾行不得把它们算成 PASS
TOTAL_TESTS = 12

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
    print('PASS new_product_package（五段目录+README+检索/EVT 两份底稿，开箱即过 R/V/E 三门禁）')


def test_rebuild_package():
    with tempfile.TemporaryDirectory() as d:
        pkg = os.path.join(d, 'T包_交付包'); os.makedirs(pkg)
        open(os.path.join(pkg, '测试_文件.md'), 'w', encoding='utf8').write('中文内容测试')
        r = run([PY, f'{S}/rebuild_package.py', pkg])
        assert_(r.returncode == 0 and 'UTF-8 filenames OK' in r.stdout, '打包或 UTF-8 标志位异常', r)
        with zipfile.ZipFile(pkg + '.zip') as z:
            i = [x for x in z.infolist() if '测试_文件.md' in x.filename][0]
            assert_(i.flag_bits & 0x800, 'UTF-8 标志位未置', r)
            assert_(z.read(i.filename).decode('utf8') == '中文内容测试', 'zip 内容损坏', r)
    print('PASS rebuild_package（同步+UTF-8 标志位+内容完整）')


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
        found = (set(re.findall(r"Finding\(\s*['\"]([RCFVE]\d)", s))
                 | set(re.findall(r'^\s+([RCFVE]\d)\s', s, re.M))
                 | set(re.findall(r'\u2192 ([VE]\d)', s)))
        for t in found:
            rule_home.setdefault(t, set()).add(name)
        defined_rules |= found
        flags_by_script[name] = set(re.findall(r"add_argument\('(--[a-z\-]+)'", s))
    doc_rules = set(re.findall(r'\b([RCFVE][1-9])\b', doctxt))
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
        assert_(vsr.verify_online('doi', '10.1038/nature14539') == 'ok',
                '真 DOI 被源判为不存在', None)
        assert_(vsr.verify_online('doi', '10.1038/definitely-not-a-real-doi-99999') == 'absent',
                '假 DOI 未被源判为不存在', None)
        assert_(vsr.verify_online('arxiv', '1706.03762') == 'ok',
                '真 arXiv id 被源判为不存在', None)
        # 控制探针：arXiv 无查询词的列表页一定返回条目。它返回 0 条说明这一侧的
        # "0 entry = 查无此项"读法此刻不可信（服务错误页/限流也长这样），
        # 只能跳过假 id 那一判，不能让它把服务异常报成"引用造假"。
        ctl = vsr.fetch_json('https://export.arxiv.org/api/query?max_results=1')
        if ctl[0] != 'ok' or b'<entry' not in (ctl[1] or b''):
            print('     SKIP live 档的假 id 一判：arXiv 控制探针本次没返回任何条目，'
                  '无从区分"查无此项"与"服务异常"')
        else:
            assert_(vsr.verify_online('arxiv', '9999.99999') == 'absent',
                    '假 arXiv id 未被源判为不存在（控制探针本次正常，判定可信）', None)
        assert_(vsr.verify_online('patent', 'CN110404188A') == 'unreachable',
                '专利公开号在无源可用时被当成了"核过"', None)
        print('PASS verify_search_report（V1–V3 成对 + 三态 + 死代理 rc=2 + live 四判）')


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
    test_check_figures(); test_check_figures_media_count(); test_check_figures_embedded()
    test_new_product_package(); test_rebuild_package(); test_regen_docx()
    test_check_iron_rules(); test_check_iron_rules_docx(); test_check_evt(); test_verify_search_report()
    test_patent_figure()
    test_docs_scripts_contract()
    ran = TOTAL_TESTS - len(SKIPPED)
    tail = f'另有 {len(missing)} 项环境依赖缺失，见上方环境自检' if missing else ''
    if SKIPPED:
        print(f'\n{ran}/{TOTAL_TESTS} 项冒烟测试 PASS，{len(SKIPPED)} 项 SKIP（{", ".join(SKIPPED)}）'
              f'——SKIP 的档未跑过，不得计入通过' + (f'（{tail}）' if tail else ''))
    else:
        print(f'\n全部 {ran} 项冒烟测试 PASS' + (f'（{tail}）' if tail else ''))
