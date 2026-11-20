"""icons.lod から取り出した表・文字列集から、訳す欄を抜き出して translation/src/<ファイル>.tsv に書く。

  python extract_text.py

src の TSV: key <TAB> en <TAB> 参考（欄の名前・行の名前など）
en は cp1252 で読み、\\t \\n \\r \\\\ をエスケープ。build.py は cp1252 に戻して照合する。
"""
import os, re, sys, glob, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B

WORK = B.WORK
SRC = os.path.join(WORK, 'translation', 'src')

NUM = 'num'   # 先頭の欄が数字の行だけ

# ファイル: (訳す欄, 行の条件, 参考に出す欄)
RULES = {
    'GLOBAL.TXT':   ([1], 2, [0]),
    '2DEvents.txt': ([5, 6, 7, 23], 2, [2]),
    'Autonote.txt': ([1], 1, [2]),
    'Awards.txt':   ([1], 1, []),
    'Class.txt':    ([0, 1], 1, []),
    'MapStats.txt': ([1], 3, [2]),
    'Merchant.txt': ([1, 2, 3, 4], 1, [0]),
    'NPCNews.txt':  ([2, 3], 2, [1]),
    'NPCdata.txt':  ([1], 2, [13]),
    'PROFTEXT.txt': (list(range(2, 16)), 2, [1]),
    'Quests.txt':   ([1], 1, [2]),
    'Scroll.txt':   ([1], 1, []),
    'Spells.txt':   ([2, 4, 8, 9, 10, 11], NUM, []),
    'Trans.txt':    ([1], 1, []),
    'npcbtb.txt':   (list(range(2, 15)), NUM, [1]),
    'npcnames.txt': ([0, 1], 1, []),
    'npcprof.txt':  ([1, 5, 6, 7], NUM, []),
    'npctext.txt':  ([1], 2, [2]),
    'npctopic.txt': ([1], 2, []),
    'stats.txt':    ([0, 1], 1, []),
    'ITEMS.TXT':    ([2, 10, 15], NUM, [1]),
    'MONSTERS.TXT': ([2], NUM, [1]),
    'SKILLDES.TXT': ([0, 1, 2, 3, 4], 1, []),
    'SPCITEMS.TXT': ([0, 1], 4, [16]),
    'STDITEMS.TXT': ([1], 4, [0]),
}


def cp(b):
    return b.decode('cp1252', errors='replace')


def header_names(rows, n=3):
    """欄の名前（頭の数行から、空でないものを使う）"""
    names = {}
    for r in rows[:n]:
        for i, c in enumerate(r):
            s = cp(c).strip()
            if s:
                names[i] = s
    return names


def extract_table(name):
    cols, cond, ref = RULES[name]
    rows = B.split_table(B.load_orig(name))
    hn = header_names(rows)
    out = []
    for r, row in enumerate(rows):
        if cond == NUM:
            if not row or not re.match(rb'^\d+$', row[0].strip()):
                continue
        elif r < cond:
            continue
        refs = ' / '.join(cp(row[i]).strip() for i in ref if i < len(row) and row[i].strip())
        for c in cols:
            if c >= len(row):
                continue
            cell = row[c]
            s = cp(cell)
            if s.startswith('"') and s.endswith('"') and len(s) >= 2:
                s = s[1:-1]
            if not s.strip() or s.strip().lower() in ('n/a', '0'):
                continue
            if not re.search(r'[A-Za-z]', s):
                continue
            out.append(('%d:%d' % (r, c), s, ('[%s] ' % hn.get(c, c)) + refs))
    return out


# ---- EVT（マップのイベント）から、質問の答えになる文字列の番号を集める ----
def answer_indices(evt):
    ans = set()
    i = 0
    while i < len(evt):
        n = evt[i]
        if n == 0:
            break
        cmd = evt[i + 1:i + 1 + n]
        if len(cmd) >= 4 and cmd[3] == 0x1A and len(cmd) >= 4 + 12:
            q, a1, a2 = struct.unpack_from('<iii', cmd, 4)
            ans.add(a1)
            ans.add(a2)
        i += n + 1
    return ans


def used_indices(evt):
    """文字列番号を使う命令（Hint 0x04, MazeInfo 0x05, Question 0x1A, StatusText 0x1D, SetMessage 0x1E）"""
    use = {}
    i = 0
    while i < len(evt):
        n = evt[i]
        if n == 0:
            break
        cmd = evt[i + 1:i + 1 + n]
        op = cmd[3] if len(cmd) > 3 else -1
        if op in (0x04, 0x05) and len(cmd) > 4:
            use.setdefault(cmd[4], set()).add({4: 'hint', 5: 'maze'}[op])
        elif op in (0x1D, 0x1E) and len(cmd) >= 8:
            use.setdefault(struct.unpack_from('<i', cmd, 4)[0], set()).add({0x1D: 'status', 0x1E: 'msg'}[op])
        elif op == 0x1A and len(cmd) >= 16:
            q, a1, a2 = struct.unpack_from('<iii', cmd, 4)
            use.setdefault(q, set()).add('question')
            use.setdefault(a1, set()).add('ANSWER')
            use.setdefault(a2, set()).add('ANSWER')
        i += n + 1
    return use


def extract_str(name):
    strs = B.split_strs(B.load_orig(name))
    base = name[:-4]
    evt = None
    for e in glob.glob(os.path.join(B.EXTRACT, '*.EVT')) + glob.glob(os.path.join(B.EXTRACT, '*.evt')):
        if os.path.basename(e)[:-4].lower() == base.lower():
            evt = open(e, 'rb').read()
    use = used_indices(evt) if evt else {}
    out = []
    for i, s in enumerate(strs):
        t = cp(s)
        if not t.strip() or not re.search(r'[A-Za-z]', t):
            continue
        u = use.get(i, set())
        if u == {'ANSWER'}:
            continue        # 答えは英語のまま（プレイヤーが打ち込む）
        out.append((str(i), t, ','.join(sorted(u)) if u else ('intro' if base.lower() == 'intro' else 'unused?')))
    return out


def main():
    os.makedirs(SRC, exist_ok=True)
    total = 0
    summary = []
    for name in sorted(RULES):
        ents = extract_table(name)
        write(name, ents)
        n = sum(len(e[1]) for e in ents)
        summary.append((name, len(ents), n))
        total += n
    strs = sorted(f for f in os.listdir(B.EXTRACT) if f.lower().endswith('.str'))
    nstr = 0
    for name in strs:
        ents = extract_str(name)
        if ents:
            write(name, ents)
        nstr += sum(len(e[1]) for e in ents)
    for s in summary:
        print('%-14s %5d 件 %7d 字' % s)
    print('STR %d 本 %d 字' % (len(strs), nstr))
    print('合計 %d 字' % (total + nstr))


def write(name, ents):
    with open(os.path.join(SRC, name + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for k, en, ref in ents:
            f.write('%s\t%s\t%s\n' % (k, B.esc(en), B.esc(ref)))


if __name__ == '__main__':
    main()
