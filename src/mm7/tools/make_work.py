"""translation/en/*.tsv から手分け用の組を作る。同じ英文は最初の 1 件だけ載せる。
第1段（p1_*）: 名前の類（Global、表の名前の欄、STR）。第2段（p2_*）: 説明・会話などの長い文。
すでに訳のある英文（translation/ja/*.tsv、out/*.tsv）は載せない。
使い方: python tools/make_work.py <段 1|2> [1 組の字数]"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import esc, unesc
import collect

HERE = os.path.dirname(os.path.abspath(__file__))
EN = os.path.join(HERE, '..', 'translation', 'en')
WORK = os.path.join(HERE, '..', 'translation', 'work')

NAME_COLS = {
    'Global.txt': None, 'MAPSTATS.TXT': None, 'MONSTERS.TXT': None, 'Npcdata.txt': None,
    'NPCNAMES.TXT': None, '2DEvents.txt': None, 'NPCTOPIC.TXT': None, 'PlaceMon.txt': None,
    'STDITEMS.TXT': None, 'SPCITEMS.TXT': {1}, 'ITEMS.TXT': {2, 10}, 'SPELLS.TXT': {2, 4},
    'POTION.TXT': {1, 2}, 'POTNOTES.TXT': {1, 2}, 'AWARDS.TXT': None, 'NPCPROF.TXT': {1},
}


def is_name(key):
    parts = key.split(':')
    f = parts[0]
    if f.upper().endswith('.STR'):
        return True
    if f not in NAME_COLS:
        return False
    cols = NAME_COLS[f]
    return cols is None or int(parts[2]) in cols


def context():
    """鍵 → 手がかり（話し手など）。NPCTEXT は Notes と Owner、npcgreet は Owner"""
    import tables
    ctx = {}
    for name, cols in (('NPCTEXT.TXT', (2, 3)), ('npcgreet.txt', (3, 4)), ('NPCTOPIC.TXT', (3, 5))):
        rows = tables.parse(open(os.path.join(tables.ORIG, name), 'rb').read())
        for r, row in enumerate(rows):
            vals = [tables.cell_text(row[c]).strip() for c in cols if c < len(row)]
            vals = [v.replace('\n', ' ').replace('\t', ' ') for v in vals if v]
            if vals:
                for c in range(len(row)):
                    ctx[f'{name}:{r}:{c}'] = ' / '.join(vals)
    return ctx


def all_units():
    us = []
    for p in sorted(glob.glob(os.path.join(EN, '*.tsv'))):
        for line in open(p, encoding='utf-8'):
            k, _, s = line.rstrip('\n').partition('\t')
            us.append((k, unesc(s)))
    return us


def main():
    stage = int(sys.argv[1])
    size = int(sys.argv[2]) if len(sys.argv) > 2 else (8000 if stage == 1 else 18000)
    done = collect.known_en()
    ctx = context() if stage == 2 else {}
    os.makedirs(WORK, exist_ok=True)
    seen = set()
    rows = []
    for k, s in all_units():
        if s in seen or s in done:
            continue
        if (stage == 1) != is_name(k):
            continue
        seen.add(s)
        rows.append((k, s))
    # 同じファイルが続くように並びはそのまま。字数で切る
    chunks, cur, n = [], [], 0
    for k, s in rows:
        if cur and n + len(s) > size and k.split(':')[0] != cur[-1][0].split(':')[0] or (cur and n + len(s) > size * 1.3):
            chunks.append(cur); cur, n = [], 0
        cur.append((k, s)); n += len(s)
    if cur:
        chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        name = os.path.join(WORK, f'p{stage}_{i:02d}.tsv')
        with open(name, 'w', encoding='utf-8', newline='\n') as f:
            for k, s in c:
                cx = ctx.get(k, '')
                f.write(k + '\t' + esc(s) + ('\t' + esc(cx) if cx else '') + '\n')
        print(os.path.basename(name), len(c), '件', sum(len(s) for k, s in c), '字')


if __name__ == '__main__':
    main()
