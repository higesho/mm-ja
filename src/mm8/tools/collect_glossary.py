"""A 組（名前の表）の訳と #TERM から、長文を訳す人のための translation/glossary_names.tsv を作る。

英語<TAB>訳<TAB>出どころ。同じ英語に別の訳があれば知らせる。
"""
import os, sys, re, glob

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')
NAME_IDS = r'^(NPCDATA\.txt|placemon\.txt|roster\.txt|mapstats\.txt|MONSTERS\.txt|npctopic\.txt):|^2DEvents\.txt:\d+:[567]$|^ITEMS\.txt:\d+:2$|^Spells\.txt:\d+:2$|^SPCITEMS\.TXT:\d+:1$|^STDITEMS\.TXT:\d+:1$'


def main():
    en = {}
    for p in glob.glob(os.path.join(TR, 'work', 'A*_in.tsv')):
        for l in open(p, encoding='utf-8'):
            k, v = l.rstrip('\n').split('\t', 1)
            en[k] = v
    out = {}
    conflicts = []

    def add(e, j, src):
        e, j = e.strip(), j.strip()
        if not e or not j or j == 'KEEP':
            return
        if e in out and out[e][0] != j:
            conflicts.append(f'{e}: {out[e][0]}（{out[e][1]}） / {j}（{src}）')
            return
        out.setdefault(e, (j, src))

    for p in sorted(glob.glob(os.path.join(TR, 'work', 'A*_out.tsv'))):
        terms = []
        for l in open(p, encoding='utf-8'):
            l = l.rstrip('\n')
            if l.startswith('#TERM'):
                parts = l[5:].strip().split('\t')
                if len(parts) >= 2:
                    terms.append((parts[0], parts[1]))
                continue
            if '\t' not in l:
                continue
            k, v = l.split('\t', 1)
            if re.search(NAME_IDS, k) and k in en:
                add(en[k], v, k.split(':')[0])
        for e, j in terms:
            add(e, j, os.path.basename(p) + ' #TERM')
    with open(os.path.join(TR, 'glossary_names.tsv'), 'w', encoding='utf-8', newline='\n') as fp:
        fp.write('# 英語<TAB>訳<TAB>出どころ（名前の表の訳と、訳した人が決めた語）\n')
        for e in sorted(out, key=str.lower):
            fp.write(f'{e}\t{out[e][0]}\t{out[e][1]}\n')
    print(f'{len(out)} 語、食い違い {len(conflicts)}')
    for c in conflicts[:80]:
        print('  ', c)


if __name__ == '__main__':
    main()
