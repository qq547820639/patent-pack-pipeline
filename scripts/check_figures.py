#!/usr/bin/env python3
"""专利线条图合规检查：彩色像素必须为 0，且 docx 嵌入图片数应等于 figures 目录图片数。
用法: python3 check_figures.py <申请文件目录或figures目录> [...]
"""
import os, sys, zipfile
from PIL import Image
import numpy as np

def colored_pixels(path):
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    return int(((abs(a[...,0]-a[...,1])>8) | (abs(a[...,1]-a[...,2])>8)).sum())

def check_dir(d):
    # 外观设计专利使用渲染图/照片（允许彩色），线条图规则不适用
    if 'views' in d or '外观设计' in d:
        print(f"{d}: 外观设计视图目录，跳过线条图像素规则")
        return 0
    figs = []
    for dp,_,fs in os.walk(d):
        for f in fs:
            if f.lower().endswith('.png'): figs.append(os.path.join(dp,f))
    bad = []
    for f in figs:
        n = colored_pixels(f)
        sz = os.path.getsize(f)
        if n > 0 or sz < 10240:
            bad.append((f, n, sz))
    print(f"{d}: {len(figs)} 幅图, 违规 {len(bad)}")
    for f,n,sz in bad: print(f"  FAIL {f} 彩色像素={n} 字节={sz}")
    return len(bad)

def main():
    total_bad = 0
    for d in sys.argv[1:]:
        total_bad += check_dir(d)
        # 若目录内含 docx，核对嵌入数
        for f in os.listdir(d):
            if f.endswith('.docx'):
                p = os.path.join(d,f)
                with zipfile.ZipFile(p) as z:
                    media = [x for x in z.namelist() if x.startswith('word/media/')]
                nfig = len([x for x in os.listdir(os.path.join(d,'figures')) if x.endswith('.png')]) if os.path.isdir(os.path.join(d,'figures')) else None
                if nfig is not None:
                    status = 'OK' if len(media)==nfig else f'MISMATCH media={len(media)} figs={nfig}'
                    print(f"  {f}: media={len(media)} vs figures={nfig} -> {status}")
    sys.exit(1 if total_bad else 0)

if __name__ == '__main__':
    main()
