# -*- coding: utf-8 -*-
"""訳語のそろい具合を調べる。

python tools/terms.py
  → translation/work/terms.txt
  1. 各組の #TERM（英語<TAB>訳）を集め、同じ英語に違う訳があるもの・用語集と違うもの
  2. 英文に用語集の人名・地名（2 語以上か 5 字以上のもの）が出てくるのに、訳にその訳語が無い文の数（語ごと）
"""
import sys, os, re, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from gather import gather_cc


def main():
    by_kind, by_en = load_glossary()
    terms = collections.defaultdict(set)
    for p in sorted(glob.glob(os.path.join(TR, 'work', 'out', '*.tsv'))):
        g = os.path.basename(p)
        for line in open(p, encoding='utf-8-sig'):
            if line.startswith('#TERM'):
                parts = line.rstrip('\n')[5:].strip().split('\t')
                if len(parts) >= 2:
                    terms[parts[0].strip()].add((parts[1].strip(), g))
    out = ['## #TERM の食い違い・用語集との違い']
    for en in sorted(terms):
        jas = set(j for j, g in terms[en])
        gl = by_en.get(en)
        if len(jas) > 1 or (gl and gl not in jas):
            out.append('%s\t用語集=%s\t%s' % (en, gl or '-', ' / '.join('%s(%s)' % (j, g) for j, g in sorted(terms[en]))))

    rows, trans, src = gather_cc()
    names = {}
    for (kind, en), ja in by_kind.items():
        if kind not in ('人名', '地名'):
            continue
        core = en.split('\\n')[0].strip().rstrip(',')
        jcore = ja.split('\\n')[0].strip()
        if len(core) >= 5 and not re.match(r'^Area [A-Z]\d', core) and jcore and jcore != 'KEEP':
            names[core] = jcore
    miss = collections.Counter()
    ex = {}
    for r in rows:
        k, en = r[0], r[1]
        ja = trans.get(k)
        if not ja or ja == 'KEEP' or src.get(k) == 'glossary':
            continue
        for n, jn in names.items():
            if re.search(r'\b%s\b' % re.escape(n), en) and jn not in ja:
                miss[n] += 1
                ex.setdefault(n, (k, ja[:60]))
    out.append('')
    out.append('## 英文に名前があるのに訳に用語集の訳語が無い（名前<TAB>用語集の訳<TAB>件数<TAB>例）')
    for n, c in miss.most_common():
        out.append('%s\t%s\t%d\t%s %s' % (n, names[n], c, ex[n][0], ex[n][1]))
    with open(os.path.join(TR, 'work', 'terms.txt'), 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(out) + '\n')
    print('食い違い', sum(1 for l in out if '\t用語集=' in l), '訳語の無い名前', len(miss))


if __name__ == '__main__':
    main()
