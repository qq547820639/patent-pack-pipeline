#!/usr/bin/env python3
"""专利线条图合规检查（五条判据 C1–C5，违规行标明触发的是哪条）:
  C1 彩色像素必须为 0（外观设计与渲染图除外；文书写明"请求保护色彩"时也豁免，见 C5）
  C2 不得为空白图：全图非白像素数为 0 判违规
  C3 目录内每个 docx 嵌入的 media 图片数必须等于 figures 目录图片数
  C4 每个 docx 内嵌的无损位图也要过 C1/C2（交付物是 docx，图就活在 docx 里）
  C5 文书写了"申请人请求保护色彩的"却没有任何一张彩色图判违规
     （《专利法实施细则》第三十条：申请人请求保护色彩的，应当提交彩色图片或者照片。
      条号与句子由本人重开**合并现行全文**逐句定位核到（留底 .codebuddy/attest/xzfg1697.htm，
      该句正落在「第三十条」块内、「第三十一条」之前），不是转述；
      ⚠ 别引 769 号《修改决定》那份来下"细则没有某句"的否定结论——它只引被改动的条文。）
判据 C1/C2 刻意用像素内容而非文件字节数——白底线条图 PNG 压缩后仅数 KB，
按字节设阈值会把合法的稀疏框图误判为违规（实测读数见 references/tooling-pitfalls.md §2）。
用法: python3 check_figures.py <申请文件目录或figures目录> [...]（递归是默认行为，没有 --all）
      -h/--help 是本门禁唯一的 flag 出口：打印用法后退 0，其余 - 开头的参数一律 rc=2。
退出码: 0 合规或未判 / 1 存在违规（C1/C2/C3/C4/C5 任一触发均为 1）
        2 未接目录、参数不是目录或混进未知 flag —— 环境不可用，未做任何判定，不算通过
"""
import importlib.util as _ilu
import os, re, sys, zipfile
from PIL import Image
import numpy as np

S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 文书侧只读一份抽取：docx 通道复用 check_iron_rules.read_text（全仓唯一那份 docx 解析）。
# 自己再写一套"怎么读 Word 件"的话，色彩豁免轴和铁律门禁迟早各读各的。
_cir = _load('check_iron_rules')

# 真会打印的用法，不是 docstring 的复读：docstring 写给读源码的人，
# 这份写给在终端敲错命令的人（退码三档含义必须在他眼前，否则 rc=2 只有一句"不认 flag"）。
USAGE = """用法: python3 check_figures.py <申请文件目录或figures目录> [...]
  递归扫描目录是默认行为：本门禁只接目录，除 -h/--help 外不认任何其它 flag（没有 --all）。
判据（违规行会标明触发的是哪条）:
  C1 彩色像素必须为 0（外观设计与渲染图目录整档跳过；文书写明"请求保护色彩"时也豁免）
  C2 不得为空白图：全图非白像素数为 0 判违规
  C3 目录内每个 docx 嵌入的 media 图片数必须等于 figures 目录图片数
  C4 每个 docx 内嵌的无损位图同样过 C1/C2（交付物是 docx，图就活在 docx 里）
  C5 文书写了"请求保护色彩"却没有一张彩色图（实施细则第三十条；豁免以文书声明为准，
     命中会打出 file:行 与原句）
退出码: 0 合规或未判 / 1 真存在违规（C1–C5 任一触发）
        2 输入不可用（零参数、未知 flag、参数不是目录）—— 未做任何判定，不算通过
"""


def pixel_stats(path):
    """返回 (彩色像素数, 非白像素数)。彩色=通道间差>8；非白=与纯白任一通道差>8。"""
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    colored = int(((abs(a[..., 0] - a[..., 1]) > 8) | (abs(a[..., 1] - a[..., 2]) > 8)).sum())
    ink = int((np.abs(a - 255).max(axis=2) > 8).sum())
    return colored, ink


def verdict(path, allow_color=False):
    """单图判据裁决，返回违规原因列表（空=合规）。改判据只改这里。

    allow_color 只由文书声明打开（见 colour_declaration）：第三十条说"申请人请求保护色彩的，
    应当提交彩色图片或者照片"，那么彩色件是**被要求的**，C1 再判红就是拿纪律去罚合法交付。
    目录名那条豁免（views/外观设计）照旧保留——外观设计的图片本来就允许有色彩，
    但它不能替代声明：写在非外观目录里的彩色申请以前会被 C1 误伤，这就是 C5 这一轴存在的原因。"""
    colored, ink = pixel_stats(path)
    reasons = []
    if colored > 0 and not allow_color:
        reasons.append(f'C1 彩色像素={colored}')
    if ink == 0:
        reasons.append('C2 空白图（全图无非白像素）')
    return reasons, colored, ink


COLOUR_DECL = re.compile(r'(?<![不未没无])请求保护色彩')
# 否定写法必须排除：简要说明里"不请求保护色彩"是最常见的一句反向声明，
# 按子串匹配会把它当成"请求了保护色彩"，于是黑白件被判 C5、彩色件反而被豁免——两头都错。


def colour_declaration(root):
    """返回 (声明命中列表, 读不动的文书数)。命中形如 [(路径, 行号, 原句)]。

    命中带 `file:行` 与原句，是为了让人复查"这条豁免凭什么成立"，不是靠一个 bool。
    计数单独返回：读不到一份文书 ≠ 这份文书没写声明——两者在 C1 那句话上必须分得开。
    否定写法（"不请求保护色彩"）由 COLOUR_DECL 的负向前瞻挡掉，不当声明。"""
    hits, unreadable = [], 0
    for dp, _, fs in os.walk(root):
        for f in sorted(fs):
            if not f.lower().endswith(('.md', '.docx')):
                continue
            p = os.path.join(dp, f)
            try:
                text = _cir.read_text(p)
            except Exception as e:
                unreadable += 1
                print(f'  note {p}: 读不动（{type(e).__name__}: {e}）→ 色彩豁免轴未全核')
                continue
            for i, ln in enumerate(text.splitlines(), 1):
                if COLOUR_DECL.search(ln):
                    hits.append((p, i, ln.strip()[:70]))
    return hits, unreadable


def check_dir(d, allow_color=False, stats=None, unreadable=0):
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
        reasons, colored, _ = verdict(f, allow_color)
        if stats is not None:
            stats['images'] += 1
            if colored > 0:
                stats['colored'] += 1
        if reasons and unreadable and any(r.startswith('C1') for r in reasons):
            # 读不动的文书不能当"没声明"：把这句挂在真开火的行上，
            # 让"这条 C1 可能只是豁免没被读到"跟着违规一起出去，而不是沉在开头的 note 里。
            reasons = reasons + [f'（色彩豁免轴未全核：{unreadable} 份文书读不动；'
                                 f'若本包确已写明请求保护色彩，请先修好该文书）']
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


def check_docx_embedded(d, tmp, allow_color=False, stats=None):
    """C4：交付物是 docx，图就活在 docx 里。只查 figures/ 的话，
    在 Word 里换掉一张彩色图而不动 figures/，C1/C2 永远看不到。
    这里把 word/media/ 解出来，复用同一个 verdict()（不重抄像素判据）。

    有损格式（JPEG 等）单独走"未核"：黑白线条图存成 JPEG 也会因压缩产生色度噪声，
    按 C1 判红就是把纪律没要求的格式当成违规。外观设计与渲染图目录整档跳过。"""
    bad, noted, seq = [], 0, [0]
    if 'views' in d or '外观设计' in d:
        print(f'  note {d}: 外观设计视图目录，C4 内嵌图像素规则不适用')
        return bad
    for f in sorted(os.listdir(d)):
        if not f.endswith('.docx'):
            continue
        p = os.path.join(d, f)
        try:
            with zipfile.ZipFile(p) as z:
                names = [x for x in z.namelist() if x.startswith('word/media/')]
                for n in names:
                    ext = os.path.splitext(n)[1].lower()
                    if ext not in ('.png', '.tif', '.tiff', '.bmp', '.gif'):
                        noted += 1
                        print(f'  note {f}: {os.path.basename(n)} 为 {ext or "?"} '
                              f'（有损或非常规位图），C4 未核')
                        continue
                    seq[0] += 1
                    out = os.path.join(tmp, f'{seq[0]}{ext}')
                    with open(out, 'wb') as w:
                        w.write(z.read(n))
                    try:
                        reasons, colored, ink = verdict(out, allow_color)
                        if stats is not None:
                            stats['images'] += 1
                            if colored > 0:
                                stats['colored'] += 1
                    except Exception as e:
                        # 解不开的内嵌件是交付件本身坏了，不是"看不见"——判违规并说清成因
                        bad.append(f'{f}: {os.path.basename(n)} 内嵌图无法解码 -> {e}')
                        print(f'  FAIL {f}: {os.path.basename(n)} -> C4 无法解码：{e}')
                        continue
                    if reasons:
                        why = '; '.join(reasons)
                        bad.append(f'{f}: {os.path.basename(n)} -> C4 {why}')
                        print(f'  FAIL {f}: {os.path.basename(n)} 彩色={colored} 非白={ink} '
                              f'-> C4 {why}')
        except Exception as e:
            print(f'  note {f}: docx 无法按 zip 打开（C3 已判），C4 未核 -> {e}')
    if noted:
        print(f'  note {d}: {noted} 个内嵌件按有损/非常规格式跳过 C4')
    return bad


def main():
    """参数一律当目录处理（递归本就是默认行为，没有 --all）。

    这里曾经是 `for d in sys.argv[1:]` 直接把每个实参喂给 os.listdir：
    打错的 flag（如 `<dir> --all`）会以 FileNotFoundError 崩在 C4，退码 1
    ——把"没做判定"报成"存在违规"，方向上等于给一次环境错误发了张放行条。

    --help/-h 是这条守卫上唯一的豁免：九把门禁里曾只有这一把没有用法出口
    （其余八把走 argparse 的自带 -h/--help），敲 `--help` 的人拿到的是一句"不认 flag"
    而不是用法。豁免只给这两个名字，且放在输入档之前——
    零参数与其余未知 flag 仍一律 rc=2，退码契约不动（本门禁不用 argparse，
    所以用法串与这条豁免都是手写的，别指望 add_argument 顺带宽容解析）。
    """
    import tempfile
    args = sys.argv[1:]
    if any(a in ('-h', '--help') for a in args):
        print(USAGE)
        sys.exit(0)
    if not args:
        print('用法: python3 check_figures.py <目录> [...]，一个目录都没接 → 未做任何判定')
        sys.exit(2)
    for d in args:
        if d.startswith('-'):
            print(f'输入不可用，未做任何判定: {d}（本门禁只接目录，不认 flag；递归是默认行为）')
            sys.exit(2)
        if not os.path.isdir(d):
            print(f'输入不可用，未做任何判定: {d}（不是目录）')
            sys.exit(2)
    total_bad = 0
    for d in args:
        decl, unread = colour_declaration(d)
        allow_color = bool(decl)
        stats = {'images': 0, 'colored': 0}
        for p, i, ln in decl:
            print(f'  note 文书声明请求保护色彩: {p}:{i}「{ln}」→ C1 豁免、C5 生效')
        total_bad += check_dir(d, allow_color, stats, unread)
        total_bad += len(check_docx_media(d))
        with tempfile.TemporaryDirectory() as tmp:
            total_bad += len(check_docx_embedded(d, tmp, allow_color, stats))
        if decl and stats['images'] and stats['colored'] == 0:
            print(f'  FAIL {d}: 声明了请求保护色彩，扫到的 {stats["images"]} 幅图里'
                  f'却没有一张有彩色像素 -> C5（第三十条要求提交彩色图片或者照片）')
            total_bad += 1
        elif decl and not stats['images']:
            print(f'  note {d}: 声明了请求保护色彩，但本目录扫不到可判的图 → C5 未判')
    sys.exit(1 if total_bad else 0)


if __name__ == '__main__':
    main()
