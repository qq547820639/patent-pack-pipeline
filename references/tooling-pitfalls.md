# 工具与环境陷阱（血泪教训固化）

## 目录
pandoc 中文路径与 locale｜图片像素扫描｜zip 同步核验｜脆文件系统对策｜图片型 PDF｜matplotlib 字体

---

## 1. pandoc 中文路径与 locale（最高频坑）
- **必须** `LC_ALL=C.utf8 LANG=C.utf8 pandoc 输入.md -o 输出.docx`。POSIX locale 下中文文件名图片报 `WARNING: Could not fetch resource` 且静默丢失图片。
- pandoc 2.17 对**非 ASCII 图片文件名**可能抓取失败（按字面查找百分编码名）——若图片丢失且 locale 已正确，改用 ASCII 文件名暂存副本转换。
- 转后必须验证：python-docx 可开 + `unzip -l` 核对 `word/media/` 图片数=附图数。批量用 `scripts/regen_docx.py`。
- **重大事故教训**：任何一波"更正/修订"后，部分代理重转 docx 时曾用错误方法（根目录执行/无 locale/ASCII 暂存失败）导致 12 个 docx 图片静默丢失——**每一波修订结束后必须全量复扫**（对全部申请文件目录跑 scripts/check_figures.py，media 数≠附图数即修复）。修订波与图片复扫是绑定的同一动作。

## 2. 图片像素扫描
- 专利线条图强制彩色像素=0：`scripts/check_figures.py <dir>` 扫描 R/G/B 通道差。
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
