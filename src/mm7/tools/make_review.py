"""読み直し用の組を作る: translation/review_in/rNN.tsv（鍵<TAB>英文<TAB>今の訳<TAB>手がかり）。
同じ英文は 1 回だけ（直しは collect.py が同じ英文の全部の鍵に当てる…ではなく、鍵ごと。代表の鍵だけ載せ、
直しは代表の鍵に書けば、collect の by_en で同じ英文にも広がるよう、review は英文単位で当てる）。
使い方: python tools/make_review.py [1 組の英字数]"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import esc, unesc
import collect, make_work

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')


def main():
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 40000
    en = collect.en_map()
    tr = {}
    for line in open(os.path.join(TR, 'ja', 'all.tsv'), encoding='utf-8'):
        k, _, v = line.rstrip('\n').partition('\t')
        tr[k] = unesc(v)
    ctx = make_work.context()
    out_dir = os.path.join(TR, 'review_in')
    os.makedirs(out_dir, exist_ok=True)
    seen = set()
    rows = []
    for stage in (1, 2):
        for k, s in en.items():
            if k not in tr or s in seen or make_work.is_name(k) != (stage == 1):
                continue
            seen.add(s)
            rows.append((k, s, tr[k], ctx.get(k, '')))
    chunks, cur, n = [], [], 0
    for r in rows:
        if cur and n + len(r[1]) > size and r[0].split(':')[0] != cur[-1][0].split(':')[0] or (cur and n + len(r[1]) > size * 1.25):
            chunks.append(cur); cur, n = [], 0
        cur.append(r); n += len(r[1])
    chunks.append(cur)
    for i, c in enumerate(chunks, 1):
        p = os.path.join(out_dir, f'r{i:02d}.tsv')
        with open(p, 'w', encoding='utf-8', newline='\n') as f:
            for k, s, j, cx in c:
                f.write('\t'.join([k, esc(s), esc(j), esc(cx)]) + '\n')
        print(os.path.basename(p), len(c), '件', sum(len(r[1]) for r in c), '字', c[0][0].split(':')[0], '〜', c[-1][0].split(':')[0])


if __name__ == '__main__':
    main()
