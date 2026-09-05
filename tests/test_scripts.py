#!/usr/bin/env python3
"""patent-pack-pipeline 脚本冒烟测试（吸收 K-Dense CI 纪律：带 scripts/ 的技能必须带 tests/）。
运行: python3 tests/test_scripts.py（仓库根目录执行）
"""
import os, sys, tempfile, subprocess, zipfile
import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = os.path.join(ROOT, 'scripts')

def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

def test_check_figures():
    with tempfile.TemporaryDirectory() as d:
        fd = os.path.join(d, 'figures'); os.makedirs(fd)
        # 纯白图（应通过）
        Image.new('RGB', (400, 300), (255,255,255)).save(f'{fd}/图1_白.png')
        # 含彩色像素图（应失败）
        a = np.full((400,300,3), 255, dtype=np.uint8); a[100,100] = [255,0,0]
        Image.fromarray(a).save(f'{fd}/图2_彩.png')
        r = run([sys.executable, f'{S}/check_figures.py', d])
        assert r.returncode == 1 and '图2_彩.png' in r.stdout, r.stdout
        print('PASS check_figures（白图过/彩图拦）')

def test_new_product_package():
    with tempfile.TemporaryDirectory() as d:
        r = run([sys.executable, f'{S}/new_product_package.py', 'TESTX', d])
        assert r.returncode == 0
        for sub in ['01_交底书','02_申请文件','03_设计补全','04_EVT验证','05_法规与裁决']:
            assert os.path.isdir(os.path.join(d, 'TESTX_专利交付包', sub)), sub
        assert os.path.exists(os.path.join(d, 'TESTX_专利交付包', 'README.md'))
        print('PASS new_product_package（五段目录+README）')

def test_rebuild_package():
    with tempfile.TemporaryDirectory() as d:
        pkg = os.path.join(d, 'T包_交付包'); os.makedirs(pkg)
        open(os.path.join(pkg, '测试_文件.md'), 'w', encoding='utf8').write('中文内容测试')
        r = run([sys.executable, f'{S}/rebuild_package.py', pkg])
        assert r.returncode == 0 and 'UTF-8 filenames OK' in r.stdout, r.stdout
        with zipfile.ZipFile(pkg + '.zip') as z:
            i = [x for x in z.infolist() if '测试_文件.md' in x.filename][0]
            assert i.flag_bits & 0x800, 'UTF-8 标志位未置'
            assert z.read(i.filename).decode('utf8') == '中文内容测试'
        print('PASS rebuild_package（同步+UTF-8 标志位+内容完整）')

def test_regen_docx():
    with tempfile.TemporaryDirectory() as d:
        md = os.path.join(d, '测试.md')
        open(md, 'w', encoding='utf8').write('# 标题\n\n中文段落测试。\n')
        open(os.path.join(d, '测试.docx'), 'w').write('')  # 占位使 regen 拾取
        r = run([sys.executable, f'{S}/regen_docx.py', d])
        assert r.returncode == 0 and 'failed: 0' in r.stdout, r.stdout
        from docx import Document
        doc = Document(os.path.join(d, '测试.docx'))
        assert any('中文段落测试' in p.text for p in doc.paragraphs)
        print('PASS regen_docx（UTF-8 locale 转换+可开）')

if __name__ == '__main__':
    test_check_figures(); test_new_product_package(); test_rebuild_package(); test_regen_docx()
    print('\n全部 4 项冒烟测试 PASS')
