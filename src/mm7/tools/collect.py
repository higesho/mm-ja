"""訳した組（translation/out/*.tsv）を集めて translation/ja/all.tsv を作る。
同じ英文のほかの鍵にも同じ訳を入れる。KEEP は英語のまま。#TERM 行は translation/new_terms.tsv に集める。
手直しは translation/ja_fix.tsv（鍵<TAB>訳）に書くと、それが優先される。
names.tsv（英語<TAB>訳、第2段の用語に使う）も作る。"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import esc, unesc

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')
EN = os.path.join(TR, 'en')
OUT = os.path.join(TR, 'out')
WORK = os.path.join(TR, 'work')


def en_map():
    m = {}
    for p in sorted(glob.glob(os.path.join(EN, '*.tsv'))):
        for line in open(p, encoding='utf-8'):
            k, _, s = line.rstrip('\n').partition('\t')
            m[k] = unesc(s)
    return m


def read_out():
    """out の訳: 鍵 → 訳（KEEP を含む）、と #TERM"""
    tr, terms = {}, []
    for p in sorted(glob.glob(os.path.join(OUT, '*.tsv'))):
        for line in open(p, encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if not line:
                continue
            if line.startswith('#TERM'):
                terms.append(line[5:].strip())
                continue
            if line.startswith('#'):
                continue
            k, _, v = line.partition('\t')
            tr[k.strip()] = v
    return tr, terms


def known_en():
    """訳済みの英文の集まり"""
    en = en_map()
    tr, _ = read_out()
    return {en[k] for k in tr if k in en}


def main():
    en = en_map()
    tr, terms = read_out()
    by_en = {}
    for k, v in tr.items():
        if k in en:
            by_en.setdefault(en[k], v)
        else:
            print('知らない鍵', k)
    fix = {}
    # 読み直しの直し（translation/review/*.tsv、鍵<TAB>直した訳）。ja_fix.tsv がさらに優先
    for rp_ in sorted(glob.glob(os.path.join(TR, 'review', '*.tsv'))):
        for line in open(rp_, encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if line and not line.startswith('#') and '\t' in line:
                k, _, v = line.partition('\t')
                k = k.strip()
                if k in en:
                    # 代表の鍵の直しは、同じ英文のほかの鍵にも当てる
                    for k2, s2 in en.items():
                        if s2 == en[k] and k2 not in fix:
                            fix[k2] = v
                    fix[k] = v
    fp = os.path.join(TR, 'ja_fix.tsv')
    if os.path.exists(fp):
        for line in open(fp, encoding='utf-8'):
            line = line.rstrip('\r\n')
            if line and not line.startswith('#'):
                k, _, v = line.partition('\t')
                fix[k] = v
    # 用語のそろえ: replace.tsv（直す前<TAB>直した後）を訳全体に当てる
    reps = []
    rp = os.path.join(TR, 'replace.tsv')
    if os.path.exists(rp):
        for line in open(rp, encoding='utf-8'):
            line = line.rstrip('\r\n')
            if line and not line.startswith('#') and '\t' in line:
                a, b = line.split('\t', 1)
                reps.append((a, b))
    out = []
    missing = 0
    for k, s in en.items():
        v = fix.get(k, tr.get(k, by_en.get(s)))
        if v is None:
            missing += 1
            continue
        if v == 'KEEP':
            continue
        v = unesc(v)
        if True:
            for a, b in reps:
                v = v.replace(a, b)
        out.append((k, v))
    os.makedirs(os.path.join(TR, 'ja'), exist_ok=True)
    with open(os.path.join(TR, 'ja', 'all.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for k, v in out:
            f.write(k + '\t' + esc(v) + '\n')
    with open(os.path.join(TR, 'new_terms.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for t in terms:
            f.write(t + '\n')
    # 名前の一覧（第1段の訳）: 英語 → 訳
    import make_work
    with open(os.path.join(TR, 'names.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        seen = set()
        for k, s in en.items():
            if make_work.is_name(k) and k in tr and tr[k] != 'KEEP' and s not in seen and len(s) < 60:
                seen.add(s)
                f.write(esc(s) + '\t' + tr[k] + '\n')
    print(f'訳 {len(out)} 件、未訳 {missing} 件、用語 {len(terms)} 件')


if __name__ == '__main__':
    main()
