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
  P5 §8 固定的五段子目录都在（`PKG_DIRS`，`new_product_package.py` 生成骨架时 import 同一份清单）；
  P6 包根有 README.md 且里面有「专利清单」表；
  P7 02_申请文件 不是空目录；
  P8 「专利清单」每一行的**类型**得是三类之一（第四十四条（六）：专利申请类别（发明、实用新型
     或者外观设计）不明确或者难以确定的，不予受理）。写成【待填写】式占位走未判——占位是"还没定"，
     不是"定错了"，把它判红等于替纪律新增一条"打包时不许留占位"的要求。
  P9 列了**实用新型**的包必须找得到图。法源逐字是第四十四条（一）"发明或者实用新型专利申请缺少
     请求书、说明书（**实用新型无附图**）或者权利要求书的"——括注挂在"说明书"底下，
     意思是实用新型缺说明书附图就按"缺说明书"处理，同一档不予受理。
     图按两处找：包内任意非 0 字节的图片文件，以及任一 .docx 里的 word/media/*
     （只查 figures/ 会漏：交付物是 Word 时图活在 media 里，与 C4 同一条理由）。
P5–P9 看的是**包本身**而不是 zip：P1–P4 全绿而包里本来就缺一整段、或整包是"没附图的实用新型"，
是这两种判据的分界。P9 的判红条件刻意取最强形态（**全包一张图都没有**）——这种时候说明书附图
必然也没有；"有图但说明书没引到"那种弱形态归 T4/T5/T6，不在这里重复判。
三态：清单里没有带「类型」列的表／一条专利都没列／docx 读不动 ⇒ P8、P9 走未判，不折成合规。

退出码: 0 全过或未判 / 1 存在不符（P1–P9 任一）/ 2 输入不可用（zip 打不开等，说清成因）。
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
import importlib.util as _ilu

CHUNK = 1 << 20
S = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = _ilu.spec_from_file_location(name, os.path.join(S, name + '.py'))
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_t = _load('mdtable')                  # 专利清单按列读，读表实现由 mdtable 唯一持有
_ck = _load('check_claims')            # 专利类别清单由 Q 族一处持有，这里不另抄一份
IMG_EXT = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp')


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


# §8 固定的五段（README.md 另算，见 P6）。这张清单**由判据侧持有**：
# new_product_package.py 生成骨架时 import 它，于是"生成器写了第六段而判据不知道"这种漂移
# 从两端同时消失——和 补全表头取自 check_design_completion.SPECS、对照表表头取自
# check_figure_labels.COLS 是同一条纪律。
PKG_DIRS = ('01_交底书', '02_申请文件', '03_设计补全', '04_EVT验证', '05_法规与裁决')
README_HEAD = '专利清单'


def shape_state(pkg):
    """P5–P9 包形状，返回 (违规, 未判/提示)。
    这些条不依赖 zip：zip 对得上而包本来就缺一整段，P1–P4 会全绿——那正是它们看不见的那种坏。
    txt 先给 None：README 根本不存在时下面那段读表不能拿一个没赋过值的变量当"读不出"。"""
    bad, notes, txt = [], [], None
    for d in PKG_DIRS:
        if not os.path.isdir(os.path.join(pkg, d)):
            bad.append(f'P5 缺 §8 固定段 {d}（目录不存在，整段交付物无从谈起）')
    rd = os.path.join(pkg, 'README.md')
    if not os.path.isfile(rd):
        bad.append('P6 包根没有 README.md（§8 六件套之一）')
    else:
        try:
            with open(rd, encoding='utf8', errors='replace') as f:
                txt = f.read()
        except OSError as e:
            bad.append(f'P6 README.md 读不出，未判（不当成合规）：{e}')
            txt = None
        if txt is not None and README_HEAD not in txt:
            bad.append(f'P6 README 里没有「{README_HEAD}」表（提交前须知与清单都挂在这张表上）')
    app = os.path.join(pkg, '02_申请文件')
    if os.path.isdir(app):
        # 「一个非空文件都没有」而不是「目录里有东西」：放一个 0 字节的 说明书.md 进去
        # 照样能骗过前者——那种包打开就是空的，判据不该被一个文件名哄住。
        if not any(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(app) for f in fs):
            bad.append('P7 02_申请文件 里没有任何非空文件（要交的那一段根本没写，打包只会交出一个空壳）')

    # P8／P9：读「专利清单」的类型列。没表、没行、或 docx 读不动 ⇒ 未判，不折成合规。
    if txt is None:
        notes.append('P8／P9 未判：包根没有可读的 README.md，类型列与附图要求都判不起')
    else:
        header, rows = claim_rows(txt)
        if header is None:
            notes.append('P8／P9 未判：「专利清单」里没有带「类型」列的表'
                         '（P6 只核表在不在，列名对不对归这里）')
        elif not rows:
            notes.append('P8／P9 未判：「专利清单」一张专利都没列（没声明类型，'
                         '第四十四条（一）（六）两条都判不起）')
        else:
            ti = _t.col(header, '类型')
            declared = []
            for i, row in enumerate(rows, 1):
                cell = row[ti] if ti is not None and ti < len(row) else ''
                # 占位要先认，再认类别：底稿写的是「【待填写：发明/实用新型】」，
                # 里面真含着"发明"两个字——顺序反过来就把"还没定"读成"定了发明"（与 C5 那条
                # "不请求保护色彩"含子串是同一个文本面陷阱）。
                if '【' in cell and '】' in cell:
                    notes.append(f'P8 第 {i} 行类型还是占位「{cell}」→ 未判：'
                                 f'还没定类别，第四十四条（六）要等定了才判得动')
                    continue
                key = _ck.type_of(cell)
                if key:
                    declared.append(key)
                    continue
                if not cell.strip():
                    bad.append(f'P8 专利清单第 {i} 行没写类型（类别不明确＝第四十四条（六）不予受理级）')
                else:
                    bad.append(f'P8 专利清单第 {i} 行的类型「{cell}」不是 '
                               f'{"／".join(_ck.PATENT_TYPES)} 之一'
                               f'（第四十四条（六）：类别不明确或者难以确定＝不予受理级）')
            if '实用新型' in declared:
                n = image_count(pkg)
                if n is None:
                    notes.append('P9 未判：包里有读不动的 docx，无从确认"全包没图"（不猜）')
                elif n == 0:
                    bad.append('P9 专利清单列了实用新型，可全包找不到一张图'
                               '（图片文件与 docx 内嵌件都是零）——第四十四条（一）'
                               '"说明书（实用新型无附图）"按缺说明书处理，不予受理级')
    return bad, notes


def claim_rows(text):
    """「专利清单」节里第一张带「类型」列的表 → (表头, 数据行)；整行全空的行不算一条专利。
    找不到带类型列的表返回 (None, [])，由调用方按未判处理而不是"零违规"。"""
    for title, body in _t.sections(text):
        if README_HEAD not in title:
            continue
        for header, rows in _t.table_blocks(body):
            if _t.col(header, '类型') is None:
                continue
            return header, [r for r in rows if any(c.strip() for c in r)]
    return None, []


def image_count(pkg):
    """包里有几张看得见的图；碰到读不动的 docx 返回 None——看不见不等于没有。"""
    n = 0
    for dp, _, fs in os.walk(pkg):
        for f in fs:
            low = f.lower()
            if low.endswith(IMG_EXT) and os.path.getsize(os.path.join(dp, f)):
                n += 1
            elif low.endswith('.docx'):
                try:
                    with zipfile.ZipFile(os.path.join(dp, f)) as z:
                        n += sum(1 for i in z.infolist()
                                 if i.filename.startswith('word/media/') and i.file_size)
                except (OSError, zipfile.BadZipFile):
                    return None
    return n


def shape_violations(pkg):
    """只要违规清单（未判/提示在 shape_state 的第二项）。verify() 消费这一份，
    返回形状不许改——它被 6 处常驻断言直接当列表用。"""
    return shape_state(pkg)[0]


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
    bad = shape_violations(pkg)                                  # P5–P9：包形状先看
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

    for n in shape_state(pkg)[1]:
        print('  note ' + n)                       # 未判单独说，不混进不符清单
    bad = verify(pkg, zfin)
    if bad:
        print("MISMATCH（P1–P9）:")
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
