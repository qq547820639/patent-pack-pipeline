#!/usr/bin/env python3
"""重建交付包 zip，并把"目录↔zip"比到**内容级**（脆文件系统安全模式）。
用法: python3 rebuild_package.py <包目录>   # 产出 同级 <包目录>.zip

为什么比内容而不是比名单：这工具存在的理由就是"脆文件系统会静默写坏东西"
（zip 重建后目录里少过 4 个文件、拷贝出现过静默部分失败）。
只比相对路径集合时，某个文件被写成截断/半截而名字还在——照样读成 "fully synced"，
工具恰好在自己最该起作用的那种故障上失明。

判据（都计入退出码）：
  P1 每条条目的字节数与目录里的源文件一致；
  P2 每条条目的内容与源文件 SHA-256 逐条一致（两边都流式读，不把整包吸进内存）；
  P3 `zipfile.testzip()` 必须返回 None，即每条 CRC 都过；
  P4 全部非 ASCII 条目名必须置 UTF-8 标志位 0x800（见下方"为什么必须用 Python 写包"）。
名单不齐时仍对**交集**做内容比对：名字差集不该把截断这件事一起藏掉。

退出码: 0 全过 / 1 存在不符（P1–P4 任一）/ 2 输入不可用（zip 打不开等，说清成因）。
注意：必须用 Python zipfile 写包——Info-ZIP zip(1) 在本环境不写 UTF-8 标志位（0x800），
导致中文文件名在 Windows 资源管理器/部分解压软件下显示乱码。Python zipfile 对非 ASCII
文件名自动置 UTF-8 标志位，Windows/macOS/Linux 全兼容。
"""
import hashlib
import os
import subprocess
import sys
import time
import zipfile

CHUNK = 1 << 20


def files_of(root):
    out = []
    for dp, _, fs in os.walk(root):
        for f in fs:
            out.append(os.path.join(dp, f))
    return sorted(out)


def sha256_of(fp):
    h = hashlib.sha256()
    with fp:
        for chunk in iter(lambda: fp.read(CHUNK), b''):
            h.update(chunk)
    return h.hexdigest()


def verify(pkg, zfin):
    """比对 目录↔zip，返回不符清单（空＝全过）。
    单独成一个函数，是因为 main() 每次都重打包：真要在"名单对得上而内容不对"这种
    zip 上验证过判据，只能把成品交进来比对——否则 P1/P2 永远是绿的说谎话。"""
    base = os.path.basename(pkg.rstrip('/'))
    try:
        z = zipfile.ZipFile(zfin)
    except (OSError, zipfile.BadZipFile) as e:
        print(f"输入不可用，未做任何判定: {zfin}（{type(e).__name__}: {e}）")
        sys.exit(2)
    bad = []
    with z:
        crc_bad = z.testzip()                                   # P3
        if crc_bad is not None:
            bad.append(f"P3 CRC 校验失败: {crc_bad}")
        infos = {i.filename: i for i in z.infolist() if not i.filename.endswith('/')}
        want_rel = sorted(os.path.join(base, w) for w in
                          (x[len(pkg.rstrip('/')) + 1:] for x in files_of(pkg)))
        got = sorted(infos)
        for x in sorted(set(want_rel) ^ set(got)):
            bad.append(f"{'目录有、zip 里没' if x in want_rel else 'zip 有、目录里没有'}: {x}")
        for rel in sorted(set(want_rel) & set(got)):            # P1/P2 只看两边都在的
            src = os.path.join(pkg.rstrip('/'), rel[len(base) + 1:])
            sz = os.path.getsize(src)
            if infos[rel].file_size != sz:
                bad.append(f"P1 字节数不符: {rel}（目录 {sz}／zip {infos[rel].file_size}）"
                           f"——脆文件系统截断的典型形状")
                continue
            a, b = sha256_of(open(src, 'rb')), None
            try:
                b = sha256_of(z.open(rel))
            except zipfile.BadZipFile as e:
                # testzip() 只报第一个坏条目；其余的在真读时才露头。
                # 不接住就是带着 traceback 退 1，等于把"包坏了"伪装成"发现违规"之外的一回事。
                # 已经被 testzip 点过名的不再报第二遍——同一件事报两次会淹掉别的原告。
                if rel != crc_bad:
                    bad.append(f"P3 条目读不出（CRC/格式坏）: {rel}（{e}）")
                continue
            if a != b:
                bad.append(f"P2 内容不符: {rel}（目录 {a[:12]}…／zip {b[:12]}…）")
        # P4 编码验证：全部非 ASCII 条目必须置 UTF-8 标志位
        non_ascii = [i for i in z.infolist() if any(ord(c) > 127 for c in i.filename)]
        noflag = [i.filename for i in non_ascii if not (i.flag_bits & 0x800)]
        if noflag:
            bad.append(f"P4 {len(noflag)} 个非 ASCII 条目未置 UTF-8 标志位: "
                       f"{'、'.join(noflag[:3])}{' 等' if len(noflag) > 3 else ''}")
    return bad


def main(pkg):
    pkg = pkg.rstrip('/')
    base = os.path.basename(pkg)
    ztmp = pkg + '_v2.zip'
    zfin = pkg + '.zip'
    for z in (ztmp, zfin):
        if os.path.exists(z):
            os.remove(z)
    subprocess.run(['sync'])
    time.sleep(1)
    # Python zipfile：非 ASCII 文件名自动置 UTF-8 标志位（0x800），Windows 兼容
    with zipfile.ZipFile(ztmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in files_of(pkg):
            zf.write(f, os.path.join(base, os.path.relpath(f, pkg)))
    os.rename(ztmp, zfin)

    bad = verify(pkg, zfin)
    if bad:
        print("MISMATCH（P1–P4）:")
        for b in bad:
            print('  ✗', b)
        sys.exit(1)
    n = len([f for f in files_of(pkg)])
    print(f"OK {zfin}: {n} files, {os.path.getsize(zfin)} bytes, "
          f"名单+逐条字节数+逐条 SHA-256+CRC+UTF-8 标志位全过")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(f"用法: python3 {os.path.basename(sys.argv[0])} <包目录>（实得 {len(sys.argv) - 1} 个参数）"
              f" → 未做任何判定")
        sys.exit(2)
    target = sys.argv[1]
    if not os.path.isdir(target):
        print(f"输入不可用，未做任何判定: {target}（本工具只接包目录）")
        sys.exit(2)
    main(target)
