#!/usr/bin/env python3
"""专利附图绘制期约束（SKILL.md 纪律 2 / hard-rules §5 里可机械固化的那部分）。

为什么要这个封装：纪律 2 的 dpi≥200、图宽 14–16cm、白底黑线、关网格、框内文字≤12 字、
阿拉伯数字标记配直线引线、同部件跨图同号——过去全靠写手记住，而其中每一条都能做成结构。
本模块不重写绘图库（底座仍是 matplotlib），只把约束变成默认值 + 保存即自检。

判据不复制：像素侧直接调用同目录 check_figures.verdict()（C1 彩色 / C2 空白），
避免两处判据各写一遍而漂移。

自身判据（保存与 --check 时强制，违规计入退出码）:
  F1 几何：dpi≥200 且图宽落在 14–16cm
  F2 图内不得嵌图题（图题只写 md 引用处）；且像素侧过 C1/C2
  F3 标记须有引线，且同一编号跨图必须指同一部件（读 parts 登记表）
  F4 框内文字 ≤12 字

用法:
  from patent_figure import Figure          # 见 tests/test_scripts.py 的真实用例
  python3 patent_figure.py --check <figures 目录> [--parts parts.json]

退出码: 0 合规 / 1 存在违规 / 2 前置依赖缺失或未检到图（环境问题，未做判定）
"""
import argparse, importlib.util, json, os, sys

DPI_MIN = 200
WIDTH_CM_RANGE = (14.0, 16.0)
BOX_TEXT_MAX = 12


def _load_pixel_judge():
    """复用 check_figures.verdict，不在这里重抄一份像素判据。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'check_figures.py')
    spec = importlib.util.spec_from_file_location('check_figures', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.verdict


def _require_matplotlib():
    """返回 pyplot 模块。注意 `import matplotlib` 不会自动带上 pyplot，必须显式导入。"""
    try:
        import matplotlib
    except ImportError:
        print('matplotlib 未安装 → 专利附图绘制环节无法执行，本次未生成任何图。')
        print('安装: pip install matplotlib   （专利附图禁止改用 AI 生成图，见 README §7）')
        sys.exit(2)
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    return plt


class Figure:
    """一张专利附图。fig_w_cm 与 dpi 决定像素尺寸，落不进纪律区间就不让建图。"""

    def __init__(self, name, fig_w_cm=15.0, fig_h_cm=10.0, dpi=200, parts=None):
        """parts 传入本案已登记的 {编号: 部件}（通常由 parts.json 读出），
        重画单图时也能在出图当场核 F3 同号异件，而不是等离线 --check 才发现。"""
        self.violations = []
        if dpi < DPI_MIN:
            self.violations.append(f'F1 dpi={dpi} < {DPI_MIN}')
        if not (WIDTH_CM_RANGE[0] <= fig_w_cm <= WIDTH_CM_RANGE[1]):
            self.violations.append(
                f'F1 图宽 {fig_w_cm}cm 不在 {WIDTH_CM_RANGE[0]}–{WIDTH_CM_RANGE[1]}cm')
        self._plt = _require_matplotlib()
        self.name = name
        self.dpi = dpi
        self.parts = dict(parts or {})
        self._pending_labels = []
        # 图上真画出来的每一段文字都要留底：F4 量完字数就丢，事后没人知道图上写了什么，
        # "图中数值与文书逐字一致"就只能靠人眼。留底由画图这段代码自己产出，
        # 不是手抄第二份登记表——抄件互比只能证明两份抄得像。
        self._texts = []
        self._marks_seen = {}
        self.fig = self._plt.figure(
            figsize=(fig_w_cm / 2.54, fig_h_cm / 2.54), dpi=dpi, facecolor='white')
        self.ax = self.fig.add_axes([0.04, 0.04, 0.92, 0.92])
        self.ax.set_axis_off()
        self.ax.grid(False)          # 默认灰网格会污染像素扫描（tooling-pitfalls §2）
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(0, 10)

    def box(self, x, y, w, h, text=''):
        """画一个部件框。框内文字超 12 字直接拒（F4）。"""
        if len(text) > BOX_TEXT_MAX:
            self.violations.append(f'F4 框内文字 {len(text)} 字 > {BOX_TEXT_MAX}：{text[:16]}')
        self.ax.add_patch(self._plt.Rectangle(
            (x, y), w, h, fill=False, edgecolor='black', linewidth=1.0))
        if text:
            self.ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
                         fontsize=9, color='black')
            self._texts.append(text)
        return (x + w, y + h / 2)

    def line(self, pts, width=0.8):
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.ax.plot(xs, ys, color='black', linewidth=width, solid_capstyle='butt')

    def label(self, num, part, at, anchor):
        """阿拉伯数字标记 + 细直线引线。同一 num 跨图必须指同一部件（F3）。"""
        self.ax.plot([at[0], anchor[0]], [at[1], anchor[1]], color='black', linewidth=0.6)
        self.ax.text(at[0], at[1], str(num), ha='center', va='center',
                     fontsize=9, color='black',
                     bbox=dict(facecolor='white', edgecolor='none', pad=0.1))
        self._pending_labels.append((num, part))

    def save(self, path, caption=None):
        """保存并自检，成功返回路径；任一判据不过就删掉该文件并 SystemExit——
        留一张违规图在 figures/ 里比直接报错更糟（打包时会被当合规件带走）。"""
        if caption:
            self.violations.append('F2 图内不得嵌图题，图题请写在 md 引用处')
        if self.violations:
            raise SystemExit(f'{self.name}: 拒绝出图\n  ' + '\n  '.join(self.violations))
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.fig.savefig(path, facecolor='white', dpi=self.dpi)
        self._plt.close(self.fig)
        bad = self.verify_saved(path)
        if bad:
            os.remove(path)
            raise SystemExit(f'{self.name}: 出图自检未过，已删除 {path}\n  ' + '\n  '.join(bad))
        self.write_manifest(path)
        return path

    def write_manifest(self, png_path):
        return write_manifest(png_path, self._marks_seen, self._texts)

    def verify_saved(self, path):
        """回读像素与几何，跑 F1/F2(C1/C2)。返回违规列表。"""
        bad = []
        from PIL import Image
        with Image.open(path) as im:
            w_px = im.size[0]
        w_cm = w_px / self.dpi * 2.54
        if not (WIDTH_CM_RANGE[0] - 0.05 <= w_cm <= WIDTH_CM_RANGE[1] + 0.05):
            bad.append(f'F1 出图实际图宽 {w_cm:.2f}cm 越界')
        reasons, _, _ = _load_pixel_judge()(path)
        bad += [f'F2 {r}' for r in reasons]
        # 同图内与跨图都要查：先按号聚合本次待登记的，再与已登记历史比
        seen = {}
        for num, part in self._pending_labels:
            prev = seen.get(num)
            if prev is not None and prev != part:
                bad.append(f'F3 编号 {num} 在本图内指向不一致：{prev} / {part}')
            seen[num] = part
            self._marks_seen = seen
            hist = self.parts.get(num)
            if hist is not None and hist != part:
                bad.append(f'F3 编号 {num} 与已登记部件不一致：{hist} / {part}')
        self.parts.update(seen)
        return bad


def write_manifest(png_path, marks, texts):
    """与 PNG 并排写 <图名>.manifest.json：图上画的标记号→部件，以及每一段框内文字。
    自检不过的图不写（那会儿 PNG 已被删，留一份清单就成了无图之账）。
    做成模块级函数是为了让"清单里到底写了什么"能在不装 matplotlib 的环境下被测——
    否则这条断言会随解释器环境一起 SKIP，判据的牙就只剩一半。"""
    manifest = {'figure': os.path.basename(png_path),
                'marks': {str(k): marks[k] for k in sorted(marks, key=str)},
                'texts': list(dict.fromkeys(texts))}
    dst = os.path.splitext(png_path)[0] + '.manifest.json'
    with open(dst, 'w', encoding='utf8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
    return dst


def check_cross_figure(parts_by_fig):
    """F3 跨图核对：同一编号在所有图里必须指同一部件。parts_by_fig = {图名: {号: 部件}}"""
    seen, bad = {}, []
    for fig, mapping in sorted(parts_by_fig.items()):
        for num, part in sorted(mapping.items()):
            if num in seen and seen[num][1] != part:
                bad.append(f'F3 编号 {num} 跨图不一致：{seen[num][0]}={seen[num][1]} / {fig}={part}')
            else:
                seen.setdefault(num, (fig, part))
    return bad, len(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', metavar='DIR', help='核对已出图的几何/像素与 parts 登记表')
    ap.add_argument('--parts', help='parts.json：{图名: {"1": "躯干框架", ...}}')
    args = ap.parse_args()

    if not args.check:
        print('本模块作绘图库使用；离线核对请带 --check <figures 目录>')
        sys.exit(2)
    if not os.path.isdir(args.check):
        print(f'--check 需要目录，实得不是目录: {args.check}（未做判定）')
        sys.exit(2)
    figs = sorted(f for f in os.listdir(args.check) if f.lower().endswith('.png'))
    if not figs:
        print(f'目录下未找到 .png，未做任何判定: {args.check}')
        sys.exit(2)
    try:
        import matplotlib
        matplotlib.use('Agg')
        from PIL import Image
    except ImportError as e:
        print(f'前置依赖缺失（{e.name}）→ 无法核对已出图，本次未做判定。')
        sys.exit(2)

    bad_total = 0
    parts_by_fig = {}
    if args.parts:
        if not os.path.isfile(args.parts):
            print(f'parts 登记表不存在: {args.parts}（未做判定）')
            sys.exit(2)
        parts_by_fig = json.load(open(args.parts, encoding='utf8'))

    for f in figs:
        p = os.path.join(args.check, f)
        reasons, colored, ink = _load_pixel_judge()(p)
        probs = [f'F2 {r}' for r in reasons]
        with Image.open(p) as im:
            w_px = im.size[0]
            dpi = (im.info.get('dpi') or (0,))[0]
        # 按 PNG 自带 dpi 换算真实图宽；读不到 dpi 就报"未核"，
        # 绝不拿假定 dpi 反推出来的数字当违规（300dpi 的合规图会被这样误判）。
        if dpi and dpi >= DPI_MIN - 1:
            w_cm = w_px / dpi * 2.54
            if not (WIDTH_CM_RANGE[0] - 0.05 <= w_cm <= WIDTH_CM_RANGE[1] + 0.05):
                probs.append(f'F1 图宽 {w_cm:.2f}cm @dpi={int(dpi)} 不在 14–16cm')
        else:
            print(f'  note {p}: PNG 无 dpi 元数据，F1 几何未核（不折成违规也不折成合规）')
        for x in probs:
            print(f'  FAIL {x} -> {p}')
        bad_total += len(probs)
        print(f'{p}: 彩色像素={colored} 非白像素={ink} 违规 {len(probs)}')

    if parts_by_fig:
        cbad, n = check_cross_figure(parts_by_fig)
        for x in cbad:
            print(f'  FAIL {x}')
        bad_total += len(cbad)
        print(f'跨图编号 {n} 个，不一致 {len(cbad)} 处')
    else:
        print('未给 --parts，F3 跨图同号未核（不折成违规也不折成合规）')
    sys.exit(1 if bad_total else 0)


if __name__ == '__main__':
    main()
