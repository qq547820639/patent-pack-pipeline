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
  F5 线宽落在 0.8–1.5pt（**房内口径，非法条**：《专利法实施细则》这页没有任何线宽数值，
     官方出处未亲验——所以本条只约束走本库出图的线，不得冒充法定要求）
  F6 不得有灰底/半透明填充/内嵌位图/带 colormap 的集合（§5「禁止灰度照片/渐变」的执行点；
     判在**画布对象**上而不是像素上，理由与被否决的像素量法见 §9 与 scan_vector 的 docstring）

F5 为什么判在**矢量侧**（入参），而不是回读像素量笔画：
  像素量法在这台机器上连"带内/带外"都分不开，四条读数各足以否掉它（完整表与固定量法见
  `references/tooling-pitfalls.md` §8；设定值 0.8/1.0/1.2/1.5pt 全部落在带内）：
  · 带下沿自己被削到带外——0.8pt 的水平线（理想情形）在 dpi=200 与 300 都读 **0.72pt**；
  · 带内两档并成一个读数——1.0pt 与 1.2pt @200 都读 **1.08pt**（1pt 只有 2.78 像素，
    0.7pt 宽的带宽被栅格量化成两档）；
  · 任意角度整体偏高——1.5pt 的 45° 斜线读 **1.916pt**，带上沿直接出带；
    竖向游程中位数还非单调（0.8→1.08 与 1.0→1.08 同值）；
  · 真图里框线、引出线、斜线粘成同一连通域——三张合法图按连通域量到 **1.26–6.26pt**（@200）。
  任何像素阈值都会在合法图上假红；而"出图一律走本库"这条纪律已经保证入参就是唯一的现场，
  矢量侧判它既准确又不会误伤。
  引出线 0.6pt 是 §5「阿拉伯数字标记＋细直线引线」自己要求的细线，属规则内的显式豁免类，
  不是绕开带宽（见 LEADER_W）。

用法:
  from patent_figure import Figure          # 见 tests/test_scripts.py 的真实用例
  python3 patent_figure.py --check <figures 目录> [--parts parts.json]
离线 --check 只判 F1/F2/F3：F4 走 manifest（check_figure_text.py），F5 无位图侧 witness，
这句话由 --check 自己在开头打印出来（不许被删，常驻与电池各有一支盯着）。

退出码: 0 合规 / 1 存在违规 / 2 前置依赖缺失或未检到图（环境问题，未做判定）
"""
import argparse, importlib.util, json, os, sys

DPI_MIN = 200
WIDTH_CM_RANGE = (14.0, 16.0)
BOX_TEXT_MAX = 12
LINE_W_RANGE = (0.8, 1.5)   # F5 带宽（房内口径）
LEADER_W = 0.6              # 标记引出线：规则要求的"细直线"，F5 的显式豁免类
BOX_W = 1.0                 # 框线，落在带宽内


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
            (x, y), w, h, fill=False, edgecolor='black', linewidth=BOX_W))
        if text:
            self.ax.text(x + w / 2, y + h / 2, text, ha='center', va='center',
                         fontsize=9, color='black')
            self._texts.append(text)
        return (x + w, y + h / 2)

    def line(self, pts, width=0.8):
        """F5：线宽出带即记违规（保存时会被拒），带宽是房内口径不是法条。"""
        if not (LINE_W_RANGE[0] <= width <= LINE_W_RANGE[1]):
            self.violations.append(
                f'F5 线宽 {width}pt 不在 {LINE_W_RANGE[0]}–{LINE_W_RANGE[1]}pt 内')
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.ax.plot(xs, ys, color='black', linewidth=width, solid_capstyle='butt')

    def label(self, num, part, at, anchor):
        """阿拉伯数字标记 + 细直线引线。同一 num 跨图必须指同一部件（F3）。"""
        self.ax.plot([at[0], anchor[0]], [at[1], anchor[1]], color='black', linewidth=LEADER_W)
        self.ax.text(at[0], at[1], str(num), ha='center', va='center',
                     fontsize=9, color='black',
                     bbox=dict(facecolor='white', edgecolor='none', pad=0.1))
        self._pending_labels.append((num, part))

    def scan_vector(self):
        """F6：在**画布对象**上查灰底／半透明／内嵌位图与渐变。

        为什么又走矢量侧（与 F5 同因，但这次是量出来才定的）：按像素量"中灰占比"在
        这台机器上分不开——合法但字多的图会一路顶高，违规的小面积灰底又几乎不动读数：
        48 框 × 11 汉字的**合法**图 mid=4.91%，而只填一块灰底的违例图 mid=12.68%、
        渐变 14.96%、照片状 39.43%；把阈值定在 8% 上下各只剩 1.6 倍余量，
        而合法侧的读数随文字密度往上走（24 框 2.12% → 48 框 4.91%，本探针没测过更高的密度，
        也就是说这条阈值**没有已知的安全上界**）。
        完整表与量法见 references/tooling-pitfalls.md §9。
        矢量侧不需要猜：灰底就是 facecolor 不透明非白，半透明就是 alpha∉(0,1)，
        照片/渐变就是 ax.images / 带 colormap 的 collection——三条都是对象形状。
        规则自己要的 45° 剖面斜线（hatch，facecolor='none'）因此天然落在允许侧。
        """
        from matplotlib.colors import to_rgba
        bad = []
        for p in self.ax.patches:
            try:
                r, g, b, a = to_rgba(p.get_facecolor())
            except (ValueError, TypeError):
                bad.append(f'F6 填充色读不出（无法判白底）：{type(p).__name__} {p.get_facecolor()!r}')
                continue
            if p.get_fill() and a > 0.999 and not (r > 0.95 and g > 0.95 and b > 0.95):
                bad.append(f'F6 填充面不是白底（灰底/阴影渲染）：{type(p).__name__} '
                           f'facecolor=({r:.2f},{g:.2f},{b:.2f})')
            elif 0.0 < a < 0.999:
                bad.append(f'F6 半透明填充＝灰度效果：{type(p).__name__} alpha={a:.3f}')
        if len(self.ax.images):
            bad.append(f'F6 内嵌位图 {len(self.ax.images)} 张（照片/渲染图/渐变不得进线条图）')
        for col in self.ax.collections:
            cmap = getattr(col, 'cmap', None)
            if cmap is not None and getattr(col, 'get_array', lambda: None)() is not None:
                bad.append(f'F6 带 colormap 的集合＝渐变/密度图：{type(col).__name__}')
                continue
            fcs = getattr(col, 'get_facecolor', lambda: None)()
            for c in (fcs if fcs is not None and len(fcs) else []):
                try:
                    r, g, b, a = to_rgba(c)
                except (ValueError, TypeError):
                    continue
                if a > 0.999 and not (r > 0.95 and g > 0.95 and b > 0.95):
                    bad.append(f'F6 集合填充非白底：{type(col).__name__} '
                               f'facecolor=({r:.2f},{g:.2f},{b:.2f})')
                    break
        return bad

    def save(self, path, caption=None):
        """保存并自检，成功返回路径；任一判据不过就删掉该文件并 SystemExit——
        留一张违规图在 figures/ 里比直接报错更糟（打包时会被当合规件带走）。"""
        if caption:
            self.violations.append('F2 图内不得嵌图题，图题请写在 md 引用处')
        self.violations += self.scan_vector()      # F6：画布对象上还看得见，存成 PNG 就没了
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
    # 覆盖面先说清：离线这一档**不是**"F1–F6 全核一遍"。
    # F4 事后还能核是因为出图时留了 <图名>.manifest.json（由 check_figure_text.py T1/T2 读）；
    # F5 事后没有任何 witness——线宽只活在矢量入参里，位图上量不出来（量法与被否决的读数见 §8）。
    print('本档离线只判 F1（几何）/ F2（像素 C1/C2）/ F3（须给 --parts）；'
          'F4 由 manifest 交给 check_figure_text.py 事后核，'
          'F5 线宽无位图侧 witness、本档一律不判（不是"核过且合规"）；'
          'F6 灰底/位图/渐变同为矢量侧判据，存成 PNG 就没有对象可查——本档也不判。')
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
