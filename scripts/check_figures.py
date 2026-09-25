#!/usr/bin/env python3
"""专利线条图合规检查（三条判据，违规行标明触发的是哪条）:
  C1 彩色像素必须为 0（外观设计与渲染图除外）
  C2 不得为空白图：全图非白像素数为 0 判违规
  C3 目录内每个 docx 嵌入的 media 图片数必须等于 figures 目录图片数
判据 C1/C2 刻意用像素内容而非文件字节数——白底线条图 PNG 压缩后仅数 KB，
按字节设阈值会把合法的稀疏框图误判为违规（实测读数见 references/tooling-pitfalls.md §2）。
用法: python3 check_figures.py <申请文件目录或figures目录> [...]
退出码: 0 合规 / 1 存在违规（C1/C2/C3 任一触发均为 1）
"""
import os, sys, zipfile
from PIL import Image
import numpy as np


def pixel_stats(path):
    """返回 (彩色像素数, 非白像素数)。彩色=通道间差>8；非白=与纯白任一通道差>8。"""
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    colored = int(((abs(a[..., 0] - a[..., 1]) > 8) | (abs(a[..., 1] - a[..., 2]) > 8)).sum())
    ink = int((np.abs(a - 255).max(axis=2) > 8).sum())
    return colored, ink


def verdict(path):
    """单图判据裁决，返回违规原因列表（空=合规）。改判据只改这里。"""
    colored, ink = pixel_stats(path)
    reasons = []
    if colored > 0:
        reasons.append(f'C1 彩色像素={colored}')
    if ink == 0:
        reasons.append('C2 空白图（全图无非白像素）')
    return reasons, colored, ink


def check_dir(d):
    # 外观设计专利使用渲染图/照片（允许彩色），线条图规则不适用
    if 'views' in d or '外观设计' in d:
        print(f"{d}: 外观设计视图目录，跳过线条图像素规则")
        return 0
    figs = []
    for dp, _, fs in os.walk(d):
        for f in fs:
            if f.lower().endswith('.png'):
                figs.append(os.path.join(dp, f))
    bad = []
    for f in figs:
        reasons, _, _ = verdict(f)
        if reasons:
            bad.append((f, reasons, os.path.getsize(f)))
    print(f"{d}: {len(figs)} 幅图, 违规 {len(bad)}")
    for f, reasons, sz in bad:
        print(f"  FAIL {f} 字节={sz} -> {'; '.join(reasons)}")
    return len(bad)


def check_docx_media(d):
    """C3 每个 docx 嵌入的 media 图片数须等于 figures 目录 png 数，返回违规条目列表。
    这条必须计入退出码：docx 静默丢图是本仓库记录在案的重大事故（12 个 docx 丢图），
    只打印 MISMATCH 不判红，等于给放行开绿灯。"""
    bad = []
    figdir = os.path.join(d, 'figures')
    if not os.path.isdir(figdir):
        return bad
    nfig = len([x for x in os.listdir(figdir) if x.lower().endswith('.png')])
    for f in sorted(os.listdir(d)):
        if not f.endswith('.docx'):
            continue
        p = os.path.join(d, f)
        try:
            with zipfile.ZipFile(p) as z:
                media = [x for x in z.namelist() if x.startswith('word/media/')]
        except Exception as e:
            print(f"  FAIL {f}: docx 无法按 zip 打开 -> {e}")
            bad.append(p)
            continue
        if len(media) == nfig:
            print(f"  {f}: media={len(media)} vs figures={nfig} -> OK")
        else:
            print(f"  FAIL {f}: media={len(media)} vs figures={nfig} -> C3 图数不一致")
            bad.append(p)
    return bad


def main():
    total_bad = 0
    for d in sys.argv[1:]:
        total_bad += check_dir(d)
        total_bad += len(check_docx_media(d))
    sys.exit(1 if total_bad else 0)


if __name__ == '__main__':
    main()
