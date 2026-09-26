#!/usr/bin/env python3
"""批量 md→docx 重转（强制 UTF-8 locale）+ python-docx 验证。
用法: python3 regen_docx.py <根目录>   # 递归处理所有存在同名 .docx 的 .md
退出码: 0 全部成功 / 1 有文件转换失败 / 2 前置依赖缺失（环境问题，未做任何转换）
"""
import os, shutil, subprocess, sys

MISSING_PANDOC = """pandoc 未安装或不在 PATH 中 → md→docx 环节无法执行，本次未转换任何文件。
安装任选其一（本脚本不会替你自动安装）:
  macOS            brew install pandoc
  跨平台 pip 方案  pip install pypandoc-binary   # 自带 pandoc 二进制(约 25MB, GPL-2.0)
  其他平台         https://pandoc.org/installing.html
已装但不在 PATH: 把 pandoc 所在目录加入 PATH, 或设环境变量 PYPANDOC_PANDOC=<pandoc 路径> 并安装 pypandoc。
"""

MISSING_DOCX = """python-docx 未安装 → 无法复核转换产物，本次未转换任何文件。
安装: pip install python-docx   （导入名是 docx，包名是 python-docx）
"""


def resolve_pandoc():
    """定位可调用的 pandoc；返回路径或 None。pypandoc 会额外探 bundled 与常见安装位置。"""
    path = shutil.which('pandoc')
    if path:
        return path
    try:
        import pypandoc
    except ImportError:
        return None
    try:
        return pypandoc.get_pandoc_path()
    except Exception:
        return None


def doc_pairs(root):
    """会被重转的 (md, docx) 成对项：只认"同名 docx 已在场"的 md。
    转换与 --check 陈旧检测共用这一条配对规则，避免两处各自定义而漂移。"""
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.md'):
                md = os.path.join(dp, f)
                d = os.path.join(dp, f[:-3] + '.docx')
                if os.path.exists(d):
                    out.append((md, d))
    return sorted(out)


def find_stale(root):
    """md 比同名 docx 新 = 改过文书忘了重转。刻意不需要 pandoc：这是只读检查，
    缺 pandoc 的机器也要能问"我落后了几份"。同一秒内写完用 1 秒容差免假阳；
    全新 git 检出后 mtime 是检出时刻，那种场合先真实转一遍再拿本判据复核。"""
    pairs = doc_pairs(root)
    stale = [(md, d) for md, d in pairs
             if os.path.getmtime(md) > os.path.getmtime(d) + 1]
    return sorted(stale), len(pairs)


def main(root):
    # 前置依赖一次性解析：缺 pandoc / 缺 python-docx 都属环境问题，走 rc=2，
    # 不能混进逐文件的 failed: 计数（否则调用方会去改 md 文件而不是装依赖）。
    env_missing = []
    pandoc = resolve_pandoc()
    if not pandoc:
        env_missing.append(MISSING_PANDOC)
    Document = None
    try:
        from docx import Document
    except ImportError:
        env_missing.append(MISSING_DOCX)
    if env_missing:
        for msg in env_missing:
            print(msg)
        print('regenerated OK: 0; failed: skipped(前置依赖缺失)')
        sys.exit(2)

    env = {**os.environ, 'LC_ALL': 'C.utf8', 'LANG': 'C.utf8'}
    ok, fail = 0, []
    for md, out in doc_pairs(root):
        p = subprocess.run([pandoc, md, '-o', out], env=env, capture_output=True)
        if p.returncode != 0:
            fail.append((md, f'rc={p.returncode} ' + p.stderr.decode('utf8', 'replace')))
            continue
        try:
            Document(out)
            ok += 1
        except Exception as e:
            fail.append((md, f'python-docx 复核失败: {e}'))
    print(f'regenerated OK: {ok}; failed: {len(fail)}')
    for f, e in fail:
        print(' FAIL', f, e[:400].replace('\n', ' | '))
    sys.exit(1 if fail else 0)


def cli():
    # 与其他门禁一致走 argparse：判据类脚本的参数必须"可被声明处查到"，
    # 手工扫 sys.argv 会让文档↔脚本契约看不见这个参数（实测就是这样漏过一次）。
    import argparse
    ap = argparse.ArgumentParser(description='批量 md→docx 重转，或只做陈旧检查')
    ap.add_argument('target', nargs='?', default='.', help='交付包根目录')
    ap.add_argument('--check', action='store_true',
                    help='只列出待重转（md 比同名 docx 新）的成对文书，不做转换、不需要 pandoc')
    args = ap.parse_args()

    if args.check:
        if not os.path.isdir(args.target):
            print(f'--check 需要目录，实得不是目录: {args.target}（未做任何判定）')
            sys.exit(2)
        stale, n = find_stale(args.target)
        for md, d in stale:
            print(f'  陈旧 {md} 比 {os.path.basename(d)} 新 → 须重转')
        print(f'成对文书 {n} 份，待重转 {len(stale)} 份')
        if not n:
            print('无 md/docx 同名成对文件 → 无从判陈旧，视为合规（不是未判）')
        sys.exit(1 if stale else 0)
    main(args.target)


if __name__ == '__main__':
    cli()
