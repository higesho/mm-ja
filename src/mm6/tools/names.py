"""名前の組（p01・p02）の訳から、長い文を訳す人が引く「名前の対訳表」を作る。

  python names.py   → translation/名前の対訳.tsv（英語<TAB>訳<TAB>どこの名前か）

同じ英語に違う訳があれば、最後に一覧を出す（そろえる手がかり）。
"""
import os, sys, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B

WORK = B.WORK
PK = os.path.join(WORK, 'translation', 'work')
OUT = os.path.join(WORK, 'translation', '名前の対訳.tsv')

KIND = {
    'ITEMS.TXT': '品物', '2DEvents.txt': '建物・主人', 'NPCdata.txt': '人', 'npcnames.txt': '人の名',
    'npctopic.txt': '話題', 'MapStats.txt': '地名', 'MONSTERS.TXT': '怪物', 'Spells.txt': '呪文',
    'SKILLDES.TXT': '技能', 'Class.txt': '職業', 'stats.txt': '能力', 'Awards.txt': '表彰',
    'STDITEMS.TXT': '付加名', 'SPCITEMS.TXT': '付加名', 'npcprof.txt': '職業(NPC)', 'GLOBAL.TXT': '画面',
}


def main():
    src = {}
    for name in ('p01_ui', 'p02_names'):
        for line in open(os.path.join(PK, name + '.tsv'), encoding='utf-8'):
            key, en, ref = line.rstrip('\n').split('\t')
            src[key] = en
    pairs = collections.defaultdict(set)
    terms = []
    for name in ('p01_ui', 'p02_names'):
        p = os.path.join(PK, 'out', name + '.tsv')
        if not os.path.exists(p):
            continue
        for line in open(p, encoding='utf-8'):
            line = line.rstrip('\n')
            if line.startswith('#TERM'):
                t = line[5:].strip().split('\t')
                if len(t) == 2:
                    terms.append((t[0], t[1]))
                continue
            if '\t' not in line:
                continue
            key, ja = line.split('\t', 1)
            if ja == 'KEEP' or key not in src:
                continue
            en = B.unesc(src[key]).strip()
            fn = key.split('|')[0]
            if fn == 'GLOBAL.TXT' and len(en) > 30:
                continue
            if fn == 'SPCITEMS.TXT' and key.endswith(':0'):
                continue
            pairs[(en, ja.strip())].add(KIND.get(fn, fn))
    for en, ja in terms:
        pairs[(en, ja)].add('用語')
    with open(OUT, 'w', encoding='utf-8', newline='\n') as f:
        for (en, ja), kinds in sorted(pairs.items(), key=lambda x: x[0][0].lower()):
            f.write('%s\t%s\t%s\n' % (en, ja, '・'.join(sorted(kinds))))
    print('%d 組 → %s' % (len(pairs), OUT))
    by_en = collections.defaultdict(set)
    for (en, ja), kinds in pairs.items():
        if '画面' not in kinds:
            by_en[en].add(ja)
    dup = {en: v for en, v in by_en.items() if len(v) > 1}
    if dup:
        print('同じ英語に違う訳: %d' % len(dup))
        for en in sorted(dup):
            print('  %s → %s' % (en, ' / '.join(sorted(dup[en]))))


if __name__ == '__main__':
    main()
