#!/usr/bin/env python3
"""批量 md→docx 重转（强制 UTF-8 locale）+ python-docx 验证。
用法: python3 regen_docx.py <根目录>   # 递归处理所有存在同名 .docx 的 .md
"""
import os, sys, subprocess

def main(root):
    env = {**os.environ, 'LC_ALL': 'C.utf8', 'LANG': 'C.utf8'}
    ok, fail = 0, []
    for dp,_,fs in os.walk(root):
        for f in fs:
            if f.endswith('.md') and os.path.exists(os.path.join(dp, f[:-3]+'.docx')):
                p = subprocess.run(['pandoc', f, '-o', f[:-3]+'.docx'], cwd=dp, env=env, capture_output=True)
                if p.returncode != 0:
                    fail.append((os.path.join(dp,f), p.stderr.decode()[:120])); continue
                try:
                    from docx import Document
                    Document(os.path.join(dp, f[:-3]+'.docx'))
                    ok += 1
                except Exception as e:
                    fail.append((os.path.join(dp,f), str(e)[:120]))
    print(f"regenerated OK: {ok}; failed: {len(fail)}")
    for f,e in fail: print(' FAIL', f, e)
    sys.exit(1 if fail else 0)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv)>1 else '.')
