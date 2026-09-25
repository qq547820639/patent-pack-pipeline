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
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith('.md') and os.path.exists(os.path.join(dp, f[:-3] + '.docx')):
                p = subprocess.run([pandoc, f, '-o', f[:-3] + '.docx'],
                                   cwd=dp, env=env, capture_output=True)
                if p.returncode != 0:
                    fail.append((os.path.join(dp, f),
                                 f'rc={p.returncode} ' + p.stderr.decode('utf8', 'replace')))
                    continue
                try:
                    Document(os.path.join(dp, f[:-3] + '.docx'))
                    ok += 1
                except Exception as e:
                    fail.append((os.path.join(dp, f), f'python-docx 复核失败: {e}'))
    print(f'regenerated OK: {ok}; failed: {len(fail)}')
    for f, e in fail:
        print(' FAIL', f, e[:400].replace('\n', ' | '))
    sys.exit(1 if fail else 0)


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '.')
