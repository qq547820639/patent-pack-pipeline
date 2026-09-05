#!/usr/bin/env python3
"""重建交付包 zip 并做"目录↔zip 全文件比对"（脆文件系统安全模式）。
用法: python3 rebuild_package.py <包目录>   # 产出 同级 <包目录>.zip
注意：必须用 Python zipfile 写包——Info-ZIP zip(1) 在本环境不写 UTF-8 标志位（0x800），
导致中文文件名在 Windows 资源管理器/部分解压软件下显示乱码。Python zipfile 对非 ASCII
文件名自动置 UTF-8 标志位，Windows/macOS/Linux 全兼容。
"""
import os, sys, subprocess, time, zipfile

def files_of(root):
    out = []
    for dp,_,fs in os.walk(root):
        for f in fs: out.append(os.path.join(dp,f))
    return sorted(out)

def main(pkg):
    pkg = pkg.rstrip('/')
    ztmp = pkg + '_v2.zip'; zfin = pkg + '.zip'
    for z in (ztmp, zfin):
        if os.path.exists(z): os.remove(z)
    subprocess.run(['sync']); time.sleep(1)
    # Python zipfile：非 ASCII 文件名自动置 UTF-8 标志位（0x800），Windows 兼容
    with zipfile.ZipFile(ztmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files_of(pkg):
            arc = os.path.join(os.path.basename(pkg), os.path.relpath(f, pkg))
            zf.write(f, arc)
    os.rename(ztmp, zfin)
    # 比对
    want = [x[len(pkg)+1:] for x in files_of(pkg)]
    with zipfile.ZipFile(zfin) as z:
        got = sorted(i.filename for i in z.infolist() if not i.filename.endswith('/'))
    want_rel = sorted(os.path.join(os.path.basename(pkg), w) for w in want)
    if want_rel == got:
        # 编码验证：全部非 ASCII 条目必须置 UTF-8 标志位
        with zipfile.ZipFile(zfin) as z:
            non_ascii = [i for i in z.infolist() if any(ord(c)>127 for c in i.filename)]
            bad = [i.filename for i in non_ascii if not (i.flag_bits & 0x800)]
        if bad:
            print(f"ENCODING-FAIL: {len(bad)} 个非 ASCII 条目未置 UTF-8 标志位"); sys.exit(1)
        print(f"OK {zfin}: {len(got)} files, {os.path.getsize(zfin)} bytes, fully synced, UTF-8 filenames OK")
    else:
        print("MISMATCH:")
        for x in set(want_rel)^set(got): print('  only in', 'folder' if x in want_rel else 'zip', ':', x)
        sys.exit(1)

if __name__ == '__main__':
    main(sys.argv[1])
