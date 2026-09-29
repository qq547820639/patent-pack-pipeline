#!/usr/bin/env python3
"""提交标题 ↔ diff 新增判据号 的对账尺（记账面工具，不是文书判据）。

为什么要有这把尺：同一处手误连踩两轮——`f5535f2`（实为 R29）与 `1e56514`（实为 R30）的提交标题
都写成了**上一条**判据的号，正文里补一句更正，读 `git log --oneline` 的人看不到。"下次记得写对"
不是防线，所以这里有一把尺：判据的身份在本仓是**字面写在 `Finding('RNN …')` 里**的（这条纪律
本身由 `test_docs_scripts_contract` 钉着），于是"这次提交到底引入了哪几条判据"可以从 diff 里现取，
再拿它去核对标题——标题里的号必须是新增号的子集，且至少要含一个新增号。

用法:
  python3 scripts/commit_rule_check.py --subject "feat: R30 …" --diff-file a.diff
  python3 scripts/commit_rule_check.py --rev 1e56514                # 自己取该提交的标题与 diff
  python3 scripts/commit_rule_check.py --self-test                  # 内置控制档，证明这把尺会开火
退出码: 0 相符或未涉及新增判据 / 1 标题与 diff 不符 / 2 输入问题（读不到 rev、没有 .git 等）

`--rev` 依赖 git，只在有仓库的工作树里能用；`--diff-file` 是纯函数档，常驻套件与变异电池在
**没有 .git 的临时副本**里也能跑，所以那两档才是常驻断言的依据，`--rev` 供人现查历史。

取号与判定的细则，都是在真历史上量出来的（不是先验设计）：
1. **只有 `+++ b/scripts/**` 那个文件的新增行算引入位。** README 里把某条判据的 Finding 字面
   抄了一遍，不等于这次提交新增了那条判据——`f5535f2` 的 diff 里正是有这样一行，第一版因此把
   "新增号"读成了别的族的号，把写对了的标题抓成不相交。
2. **删除侧出现过的号先减掉。** 只改判据措辞的提交在 `-` 与 `+` 两侧带着同一个号，那不是新增；
   不减，每个 `fix:` 都会被逼着在标题里写号（假阳性）。
3. **号有两种字面形状，只认一种等于瞎一半**：一行式（号紧跟在 `Finding(` 之后）与本仓实际写的
   两行式（`findings.append(Finding(` 收尾、号在下一行的引号里）。第一版按"同一行"匹配，
   续行那种写法整条看不见，"新增号"读成空 ⇒ 标题写成什么它都放行。
4. **只判"标题与新增号有交集"，不判"标题是新增号的子集"**：标题里提一条本次只是被改动的判据、
   或写一个区间（`R1–R8` 这种），都不是错。
5. 尺子的边界：**它只核对号**。`f5535f2` 那次是号写对了、文案抄了上一条判据的内容，这把尺看不见；
   要钉文案就得逼每个标题复述判据内容，今天不付这个代价。
6. **量具不读自己的身子**：`scripts/commit_rule_check.py` 自己也排除在引入位之外——本文件正文里就写着
   Finding 的夹具字面（上面那些控制档要靠它），第一次自举（拿这把尺对它自己的提交跑 `--diff-file`）
   就因为它读自己而报出"diff 新增了判据 X22"，常驻档第⑩档从此钉住这一面。

`--diff-file` 的输入若一个 `+++` 头都没有，按全文处理：宁可多报一条，也不要在读不到文件归属时
沉默判"未涉及新增判据"。
"""
import argparse, os, re, subprocess, sys

# 判据号形状： families 用的是"字母前缀 + 数字"（R/Q/T/N/E/G/K/V/P/F/C），且必须成词
RULE_ID = re.compile(r'\b([A-Z]{1,3}\d+)\b')
# 形状一：号紧贴 `Finding(`（本仓的纪律由 `test_docs_scripts_contract` 钉着）
FINDING = re.compile(r"Finding\(\s*['\"]([A-Z]{1,3}\d+)(?!\d)")
# 形状二：续行——一整行就是 `'R28 …', path, …`，号是这一行引号里的第一个字面
CONT = re.compile(r"^\s*['\"]([A-Z]{1,3}\d+)(?!\d)")


def _lit_id(line):
    """这一行是否把一个判据号当作 Finding 的标题字面写了出来；是则返回那个号。"""
    m = FINDING.search(line) or CONT.match(line)
    return m.group(1) if m else None


# 量具不读自己的身子。本文件正文里就写着 `Finding('X22 发明人数超限')` 这样的字面——那是给
# "文档侧不算引入位"那一档准备的夹具。这把尺不是判据脚本、永远不往外打 Finding，所以它的正文
# 不构成"本次引入了一条判据"。2026-09-29 第一次自举（拿它对着自己的提交跑 `--diff-file`）
# 就报出"diff 新增了判据 X22"，那次自举本身把它抓出来的。
SELF = 'scripts/' + os.path.basename(__file__)


def _in_scope(path):
    return path.startswith('scripts/') and path != SELF


def _sides_by_file(diff_text):
    """按 `+++ b/<path>` 把 diff 切成脚本侧的 (新增行, 删除行) 两组。

    没有文件头（`saw_header=False`）时不按路径过滤——一份裸的 added-lines 输入宁可多报，
    也不要在归属读不到时沉默判"未涉及新增判据"。
    """
    added, removed, cur, saw_header = [], [], None, False
    for ln in diff_text.splitlines():
        if ln.startswith('+++ '):
            saw_header = True
            cur = ln[4:].strip()
            cur = cur[2:] if cur.startswith('b/') else cur
            continue
        if ln.startswith('--- '):
            continue
        if saw_header and not _in_scope(cur or ''):
            continue
        if ln.startswith('+'):
            added.append(ln[1:])
        elif ln.startswith('-'):
            removed.append(ln[1:])
    return added, removed


def new_rule_ids(diff_text):
    """本次 diff 在脚本侧真引入的判据号：新增行里有、删除行里没出现过的这些。"""
    added, removed = _sides_by_file(diff_text)
    gone = {_lit_id(ln) for ln in removed}
    out = []
    for ln in added:
        i = _lit_id(ln)
        if i and i not in out and i not in gone:
            out.append(i)
    return out


def subject_rule_ids(subject):
    """标题里出现的判据号形状串（含 R1–R31 这种区间里的两端，都算"标题涉及的号"）。"""
    return [m.group(1) for m in RULE_ID.finditer(subject or '')]


def audit(subject, diff_text):
    """返回 (ok, 说明)。ok=False 就是该拒这次提交标题。

    只判"相交"，不判"子集"：标题里带一个 diff 没新增的号不是错。这一条由真历史量的——
    105 个提交里有新增判据号的 25 个，其中 6 个（`19f33d5` 提 Q7、`a48ddf4` 提 Q12、
    `bad9ee5` 写 F1–F5、`c0b64a0` 写 K1-K5、`d001b00` 写 R1–R8、`1eb36b5` 提 P11）
    都在标题里提到了**本次被改动而不是被引入**的判据或一个区间两端。第一版按子集判红，
    一上来就报出这 6 条假阳性，而它要抓的那次误写（`1e56514`）只靠"不相交"就抓住了。
    """
    new, sub = new_rule_ids(diff_text), subject_rule_ids(subject)
    if not new:
        return True, ('未涉及新增判据（脚本侧新增行里没有新写的 `Finding(\'RNN …\')`），'
                      '标题不必含判据号')
    if not sub:
        return False, ('diff 新增了判据 ' + '、'.join(new) + '，标题却没写任何一个号'
                       '（读 log 的人无法从标题知道这次落了哪条）')
    if not any(s in new for s in sub):
        return False, ('标题写的号 ' + '、'.join(sub) + ' 与 diff 实际新增的 '
                       + '、'.join(new) + ' 不相交——这就是"张冠李戴"')
    return True, ('相符：标题含 ' + '、'.join([s for s in sub if s in new])
                  + '，diff 新增 ' + '、'.join(new)
                  + (('；标题另提到的 ' + '、'.join([s for s in sub if s not in new])
                     + ' 不是本次引入的号（允许）') if any(s not in new for s in sub) else ''))


_S = 'scripts/x.py'


def _hunk(path, body):
    return '\n'.join([f'diff --git a/{path} b/{path}', f'--- a/{path}', f'+++ b/{path}',
                      '@@ -1 +1 @@'] + body)


def _add(i):
    """生产侧的字面形状：`Finding(` 收尾，号在下一行的引号里。"""
    return ['+        findings.append(Finding(', f"+            '{i} 例子', path, 1, '措辞')"]


def _del(i):
    return [f"-            '{i} 旧措辞', path, 1, '措辞')"]


# 控制档里的号一律用 X 前缀：`test_docs_scripts_contract` 会把 scripts/*.py 里任何
# `Finding('RNN …'` 字面当成"这条判据存在"，写 R31 就当场报"文档漏写 R31"（本轮实测）。
# X 不属于本仓任何判据家族，契约取不到它，而这把尺自己的形状 [A-Z]{1,3}\d+ 照样取得到。
CASES = [
    ('标题与 diff 相符', 'feat: X30 委托代理机构那四件', _hunk(_S, _add('X30')), True),
    ('标题写成上一条号', 'feat: X28 声明了生物材料保藏那五件', _hunk(_S, _add('X30')), False),
    ('一次新增两条、标题含两条', 'feat: X30 与 X31 两族落地',
     _hunk(_S, _add('X30') + _add('X31')), True),
    ('diff 不含新判据', 'test: 收紧三处列齐极', _hunk(_S, ["+        body.append('别的')"]), True),
    ('标题提到既有判据号不算夹带', 'feat: X30 委托代理那四件——与 X23 同轴',
     _hunk(_S, _add('X30')), True),
    ('新增判据而标题一个号都没写', 'feat: 把委托代理那四件接进门禁', _hunk(_S, _add('X30')), False),
    ('文档里的判据字面不算引入位', 'docs: 把代理人数那条的引文抄进清单',
     _hunk('README.md', ["+README：字面写作 `Finding('X22 发明人数超限')` 一条"]), True),
    ('只改措辞不算新增', 'fix: 把保藏那条的位点改到声明那一行',
     _hunk(_S, _del('X28') + _add('X28')), True),
    ('量具不读自己的身子', 'feat: 给对账尺补一档控制', _hunk(SELF, _add('X24')), True),
]


def self_test():
    """每一档都要各就各位：该放的放行、该红的点名（不开火的尺子等于没有）。"""
    bad = []
    for name, subj, diff, want in CASES:
        ok, why = audit(subj, diff)
        if ok is not want:
            bad.append(f'{name}：期望 {"放行" if want else "判红"}，实得 {"放行" if ok else "判红"}（{why}）')
        print(f'  [{"✓" if ok is want else "✗"}] {name} → {"放行" if ok else "判红"}：{why}')
    if bad:
        print('SELFTEST-FAIL')
        for b in bad:
            print('   ', b)
        return 1
    print(f'SELFTEST-OK（{len(CASES)} 档控制各就各位）')
    return 0


def git(*args):
    try:
        r = subprocess.run(['git'] + list(args), capture_output=True, text=True)
    except OSError as e:
        return 2, '', f'git 不可用：{e}'
    return r.returncode, r.stdout, r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser(description='提交标题与 diff 新增判据号对账')
    ap.add_argument('--subject', help='提交标题；与 --diff-file 搭配用')
    ap.add_argument('--diff-file', help='unified diff 文本所在文件（- 表示从标准输入读）')
    ap.add_argument('--rev', help='从 git 取该提交的标题与 diff（需要有仓库工作树）')
    ap.add_argument('--self-test', action='store_true', help='跑内置控制档')
    a = ap.parse_args(argv)
    if a.self_test:
        return self_test()
    if a.rev:
        rc, subj, err = git('log', '-1', '--format=%s', a.rev)
        if rc != 0:
            print(f'读不到 {a.rev} 的标题（rc={rc}）：{err.strip()[:200]}')
            return 2
        rc, diff, err = git('show', '--format=', '--no-color', a.rev)
        if rc != 0:
            print(f'读不到 {a.rev} 的 diff（rc={rc}）：{err.strip()[:200]}')
            return 2
        subj = subj.strip()
    else:
        if not a.subject or not a.diff_file:
            print('用法：--subject 与 --diff-file 成对给，或给 --rev，或 --self-test')
            return 2
        subj = a.subject
        if a.diff_file == '-':
            diff = sys.stdin.read()
        else:
            if not os.path.isfile(a.diff_file):
                print(f'读不到 diff 文件：{a.diff_file}')
                return 2
            with open(a.diff_file, encoding='utf8') as f:
                diff = f.read()
    ok, why = audit(subj, diff)
    print('标题：' + subj)
    print(('PASS  ' if ok else 'FAIL  ') + why)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
