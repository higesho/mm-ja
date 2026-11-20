# -*- coding: utf-8 -*-
"""手分けして訳すための組を translation/work/ に作る。

python tools/make_work.py [組の大きさ（英文のバイト数、既定 18000）]

- cc_NN.tsv: 地図の文などの組（鍵<TAB>使われ方<TAB>英文）。同じ英文は最初の1つだけ。
  地名・呪文名・材質・人名・物の名前（用語集で埋めるもの）、答え（英語のまま）、英字のない文は入れない。
- con_NN.tsv: 画面の部品の文の組（鍵<TAB>英文）。ファイル名などと、用語集で埋める名前の表は入れない。
訳は translation/work/out/<同じ名前> に「鍵<TAB>訳」で書く。
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

WORK = os.path.join(TR, 'work')


def has_letters(s):
    s = re.sub(r'\\x[0-9A-F]{2}|\\[tv]\d{3}|\\f(\d\d|d)|\\[nr]', '', s)
    return re.search(r'[A-Za-z]{2}', s) is not None


def glossary_kind(note, fname):
    if fname in ('spells.xen', 'mae.xen'):
        return True
    if note.startswith('地名'):
        return True
    if note in ('名前', '物の名前（誰が〜の見出し）'):
        return True
    return False


def main():
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 18000
    os.makedirs(os.path.join(WORK, 'out'), exist_ok=True)
    rows = read_tsv(os.path.join(TR, 'cc_en.tsv'))
    seen = set()
    groups = []
    cur, cur_size, cur_file = [], 0, None
    n_skip = {'用語集': 0, '答え': 0, '英字なし': 0, '重複': 0}
    for r in rows:
        k, en = r[0], r[1]
        note = r[2] if len(r) > 2 else ''
        fname = r[3] if len(r) > 3 else ''
        if glossary_kind(note, fname):
            n_skip['用語集'] += 1
            continue
        if '答え' in note:
            n_skip['答え'] += 1
            continue
        if not has_letters(en):
            n_skip['英字なし'] += 1
            continue
        if en in seen:
            n_skip['重複'] += 1
            continue
        seen.add(en)
        fkey = k.rsplit(':', 1)[0]
        if cur and cur_size >= size and fkey != cur_file:
            groups.append(cur)
            cur, cur_size = [], 0
        cur.append((k, note, en))
        cur_size += len(en)
        cur_file = fkey
    if cur:
        groups.append(cur)
    for i, g in enumerate(groups, 1):
        with open(os.path.join(WORK, 'cc_%02d.tsv' % i), 'w', encoding='utf-8', newline='\n') as f:
            for k, note, en in g:
                f.write('%s\t%s\t%s\n' % (k, note, en))
        print('cc_%02d.tsv' % i, len(g), '件', sum(len(x[2]) for x in g), 'バイト')
    print('除いたもの', n_skip)

    # 画面の部品の文
    crow = read_tsv(os.path.join(TR, 'constants_en.tsv'))
    items = []
    for r in crow:
        k, en = r[0], (r[1] if len(r) > 1 else '')
        b = const_base(k)
        if b in CONST_SKIP or b in CONST_GLOSSARY or not has_letters(en):
            continue
        items.append((k, en))
    half = (len(items) + 1) // 2
    for i, part in enumerate((items[:half], items[half:]), 1):
        with open(os.path.join(WORK, 'con_%02d.tsv' % i), 'w', encoding='utf-8', newline='\n') as f:
            for k, en in part:
                f.write('%s\t%s\n' % (k, en))
        print('con_%02d.tsv' % i, len(part), '件', sum(len(x[1]) for x in part), 'バイト')


if __name__ == '__main__':
    main()
