# 工具与环境陷阱（血泪教训固化）

## 目录
pandoc 中文路径与 locale｜图片像素扫描｜zip 同步核验｜脆文件系统对策｜图片型 PDF｜matplotlib 字体

---

## 1. pandoc 中文路径与 locale（最高频坑）
- **必须** `LC_ALL=C.utf8 LANG=C.utf8 pandoc 输入.md -o 输出.docx`。POSIX locale 下中文文件名图片报 `WARNING: Could not fetch resource` 且静默丢失图片。
- pandoc 2.17 对**非 ASCII 图片文件名**可能抓取失败（按字面查找百分编码名）——若图片丢失且 locale 已正确，改用 ASCII 文件名暂存副本转换。
- 转后必须验证：python-docx 可开 + `unzip -l` 核对 `word/media/` 图片数=附图数。批量用 `scripts/regen_docx.py`。
- **重大事故教训**：任何一波"更正/修订"后，部分代理重转 docx 时曾用错误方法（根目录执行/无 locale/ASCII 暂存失败）导致 12 个 docx 图片静默丢失——**每一波修订结束后必须全量复扫**（对全部申请文件目录跑 scripts/check_figures.py，media 数≠附图数即修复）。修订波与图片复扫是绑定的同一动作。
  - 该比对即 `check_figures.py` 的 **C3**（目录内每份 docx 逐个核对，不是只查第一份），**违规计入退出码**：media≠附图数 → rc=1。此前版本只打印 `MISMATCH` 而 `total_bad` 不计数，实测同一丢图夹具下 **rc=0 放行**——防线只体现在日志里，门禁仍是绿的；已修，且配套"同目录第二份 docx 缺图"的夹具进测试。
  - 反向注意：python-docx 按图片字节哈希去重 media part，两张**逐字节相同**的附图只会落 1 个 `word/media/` 条目，此时 C3 报的是图数不一致而不是丢图。专利附图本就该张张不同（同部件跨图同号），真遇到该情形先核对是否误用了同一张图。
- **前置依赖缺失 ≠ 转换失败**：`scripts/regen_docx.py` 开跑前先解析两项前置依赖——pandoc（PATH → `PYPANDOC_PANDOC`/pypandoc 常见安装位）与 python-docx。任一缺失即 **exit 2 并打印对应安装指引、一个文件都不转**，不抛 traceback，也不混进逐文件的 `failed:` 计数。看到 rc=2 是环境问题，按提示装完重跑；rc=1 才是真有文件失败。实测动因：早期版本在 python-docx 缺失的 venv 里把一次成功转换记成 `failed: 1`，调用方会去改 md 文件而不是装依赖。

## 2. 图片像素扫描
- `scripts/check_figures.py <dir>` 的像素判据为两条，违规行会标明触发的是哪条（图数比对 C3 见 §1）：
  - **C1 彩色像素=0**：扫描 R/G/B 通道差（>8 记一个），线条图染红即违规。
  - **C2 非空白**：全图非白像素数为 0 判违规（拦空白图/空导出）。
- **判据度量选错代理量的实案**：旧版本用「文件字节 < 10240 判违规」当空白代理。白底线条图 PNG 压缩极好，字节数由内容密度支配，不是空白与否的度量。实测（matplotlib 3.11.2，按本 skill 纪律 2 口径：白底黑线、dpi=200、图宽 15cm、`ax.grid(False)`，图元数 1→80 共 9 档）：**1/2/3/5 图元四档合规图被误判违规**（字节 6055/6801/7640/8903，彩色像素全为 0，非白像素 2576/5158/7750/12940），8 图元及以上（11304~47809 字节）才恰好越过阈值。也就是说最容易被误伤的正是在专利里很常见的**稀疏框图与流程示意图**。已改为直接数非白像素（ink==0 判空白，对任何有墨迹的图零误判）。教训：度量要用内容量（像素），不要用压缩后字节数这类受内容密度支配的间接量；改判据必须同时配「合规样本必须放行」的对照夹具——旧测试只在违规样本上断红，所以这个误判存在了很久都没被发现。
- matplotlib 默认 `axes.grid=True` 会产生灰色网格污染——显式 `ax.grid(False)` 或建图后关闭。

## 3. zip 同步核验与中文文件名编码（打包最后一步必做）
- **中文文件名乱码（领导反馈实案）**：本环境 Info-ZIP `zip(1)` 不写 UTF-8 标志位（0x800），中文条目名在 Windows 资源管理器/部分解压软件下按 GBK 误读即乱码。**必须用 Python zipfile 写包**（非 ASCII 文件名自动置 0x800 标志位，Windows/macOS/Linux 全兼容）；`scripts/rebuild_package.py` 已内置该方法与标志位验证，禁止回退到 zip(1) 命令行打包。
- zip 重建后：`find 包目录 -type f | sort` 与 zip 条目逐一 diff；缺一即重建；并验证非 ASCII 条目全部置 UTF-8 标志位。
- 重建用临时名（`_v2.zip` 后 rename），直接覆盖偶发 I/O 错误。
- **时机教训**：大批量拷贝刚结束时立即 zip 曾丢 4 个文件（写入未落盘）——拷贝与 zip 之间 `sync; sleep 1`；zip 后必做比对再交付。

## 4. 脆文件系统对策
- 长链 `&&` + glob 的大批量拷贝曾出现静默部分失败——**逐目录拷贝+哈希核验**（参考 scripts/rebuild_package.py 的 sync_tree 逻辑）。
- `rm` 后立刻重建同名 zip 偶发 "File exists"——`sync; sleep 1` 再操作。
- shutil.copytree 偶发 `FileExistsError`/`No such file or directory`——用"拷到临时目录→核验→rename"模式。

## 5. 图片型 PDF
- 先测文字层（PyMuPDF `get_text()` 长度为 0 即图片型）；逐页渲染 PNG（dpi≥110）后用视觉逐页识读。
- 外观设计视图裁剪：只许净化"与画布边框连通的背景连通域"（泛洪法），产品本体像素一律不动；阈值纯白化会误伤银色高光（已有事故）。

## 6. matplotlib 中文字体
- 环境已配好中文字体；**禁止**改 rcParams 的 font.family/font.sans-serif/axes.unicode_minus。
- 个别环境需逐文本 FontProperties 指定 Noto Sans CJK——先试默认，缺字形再局部指定。

## 平台级执行新增陷阱（步行康复平台项目实测）

1. **pytest 环境分裂**：不同 python 版本各自有/无 pytest 与科学计算库（实测 pytest 在 3.11 但 pandas 在 3.12）；安装后偶发丢失需重装；**各测试目录必须分开跑**——同名模块（如多个 `synthetic_cohort.py`）同会话收集会撞名失败（非代码缺陷）。
2. **共享挂载文件系统竞态**：同名文件反复创建/删除会被外部 watcher 同步删除（实测报告文件写入 1 秒内消失）→ 一律 per-run 时间戳文件名 + 容错重写；批量产物连续 3 轮验证稳定后再交付。
3. **合并单元格占位计数虚高**：python-docx 对合并单元格重复计数（实测【待团队补充】原始计数 370 次，去重后仅 8 组）→ 占位管理以"组"为单位，不以字符串出现次数。
4. **老 .doc 官方模板**：先 `soffice --headless --convert-to docx` 转换再 python-docx 原位填充；转换后必须做 表格数/固定文本逐字/样式名/转 PDF 逐页目检 四项抽查（详见 references/grant-application.md §4）。
5. **文献署名核实**：PMID/DOI 正确但作者署名可能误记（实测 Evidence Table 将 Hiengkaew 2012 误署名 Liaw，被论文产线核查发现）→ 著录信息引用前必须联网核实署名，著录与查新结论分离原则不变。
6. **质量门脚本自身缺陷**：自动判定脚本的正则/传参错误会误报 FAIL（实测 Q3 取错列、Q6 pytest 多目标传参）→ 门脚本也要被验证，修复留痕。同类实例见 §2「字节阈值误判合法稀疏框图」——误报不一定是写错正则，也可能是判据选错了度量对象。
