#!/usr/bin/env python3
"""patent-pack-pipeline 脚本冒烟测试（吸收 K-Dense CI 纪律：带 scripts/ 的技能必须带 tests/）。
运行: python3 tests/test_scripts.py（仓库根目录执行）
同时兼作环境自检：打印各依赖是否就绪、缺失影响哪个环节。
"""
import importlib.util
import os, sys, tempfile, subprocess, zipfile, stat
import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')
PY = sys.executable

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
    ('matplotlib', 'matplotlib', '专利附图代码绘制（SKILL.md 关键操作纪律 2）'),
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

def _line_figure(path, w=1260, h=900, elements=1, tint=None):
    """生产口径白底黑线附图：16cm@200dpi≈1260px 宽。tint 给定时叠加彩色像素。
    elements=1 刻意取"稀疏但合法"的框图——它压缩后仅约 5.4KB，用来钉住字节阈值回归。"""
    im = Image.new('RGB', (w, h), (255, 255, 255))
    d = ImageDraw.Draw(im)
    for i in range(elements):
        y = 20 + i * (h - 40) // max(elements, 1)
        d.line([(30, y), (w - 30, y)], fill=(0, 0, 0), width=3)
        d.rectangle([60 + i * 5, y + 3, 90 + i * 5, y + 14], outline=(0, 0, 0), width=2)
    if tint:
        a = np.array(im); a[100, 100] = tint
        im = Image.fromarray(a)
    im.save(path)
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



def test_new_product_package():
    with tempfile.TemporaryDirectory() as d:
        r = run([PY, f'{S}/new_product_package.py', 'TESTX', d])
        assert_(r.returncode == 0, '骨架生成失败', r)
        for sub in ['01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决']:
            assert_(os.path.isdir(os.path.join(d, 'TESTX_专利交付包', sub)), f'缺目录 {sub}：{r.stdout}')
        assert_(os.path.exists(os.path.join(d, 'TESTX_专利交付包', 'README.md')), '缺 README.md')
    print('PASS new_product_package（五段目录+README）')


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


if __name__ == '__main__':
    missing = probe_env()
    test_check_figures(); test_check_figures_media_count()
    test_new_product_package(); test_rebuild_package(); test_regen_docx()
    print('\n全部 5 项冒烟测试 PASS'
          + (f'（另有 {len(missing)} 项环境依赖缺失，见上方环境自检）' if missing else ''))
