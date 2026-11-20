"""translation/src から、手分けして訳す組（work/pNN_*.tsv）を作る。訳は work/out/ に同じ名前で置かれる。

  python packets.py make      組を作る（大きさを表示）
  python packets.py collect   work/out/ を集めて translation/ja/<ファイル>.tsv に書き、検査する
"""
import os, sys, re, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B

WORK = B.WORK
SRC = os.path.join(WORK, 'translation', 'src')
PK = os.path.join(WORK, 'translation', 'work')
OUTD = os.path.join(PK, 'out')
JA = B.JA


def load_src(name):
    out = []
    for line in open(os.path.join(SRC, name + '.tsv'), encoding='utf-8'):
        k, en, ref = line.rstrip('\n').split('\t')
        out.append((name, k, en, ref))
    return out


def col_of(k):
    return int(k.split(':')[1]) if ':' in k else None


def sel(name, cols=None, part=None, nparts=1):
    ents = load_src(name)
    if cols is not None:
        ents = [e for e in ents if col_of(e[1]) in cols]
    if nparts > 1:
        # 字数でほぼ等分（行の途中で切らない）
        total = sum(len(e[2]) for e in ents)
        acc, out = 0, []
        for e in ents:
            idx = min(nparts - 1, acc * nparts // max(total, 1))
            if idx == part:
                out.append(e)
            acc += len(e[2])
        ents = out
    return ents


def plan():
    strs = sorted(f[:-4] for f in os.listdir(SRC) if f.lower().endswith('.str.tsv'))
    return [
        ('p01_ui', sel('GLOBAL.TXT') + sel('stats.txt', [0]) + sel('Class.txt', [0]) + sel('SKILLDES.TXT', [0, 2, 3, 4])
         + sel('Spells.txt', [2, 4, 9, 10, 11]) + sel('MapStats.txt') + sel('Awards.txt') + sel('MONSTERS.TXT')
         + sel('STDITEMS.TXT') + sel('SPCITEMS.TXT') + sel('npcprof.txt', [1])),
        ('p02_names', sel('ITEMS.TXT', [2, 10]) + sel('2DEvents.txt') + sel('NPCdata.txt') + sel('npcnames.txt')
         + sel('npctopic.txt')),
        ('p03_npctext_a', sel('npctext.txt', None, 0, 2)),
        ('p04_npctext_b', sel('npctext.txt', None, 1, 2)),
        ('p05_proftext_a', sel('PROFTEXT.txt', None, 0, 2)),
        ('p06_proftext_b', sel('PROFTEXT.txt', None, 1, 2)),
        ('p07_news', sel('NPCNews.txt') + sel('Quests.txt') + sel('Autonote.txt') + sel('Trans.txt')),
        ('p08_itemdesc_a', sel('ITEMS.TXT', [15], 0, 2)),
        ('p09_itemdesc_b', sel('ITEMS.TXT', [15], 1, 2)),
        ('p10_rules', sel('Spells.txt', [8]) + sel('SKILLDES.TXT', [1]) + sel('Class.txt', [1]) + sel('stats.txt', [1])
         + sel('npcprof.txt', [5, 6, 7])),
        ('p11_talk', sel('npcbtb.txt') + sel('Merchant.txt') + sel('Scroll.txt')),
        ('p12_maps', sum((load_src(s) for s in strs), [])),
    ]


def make():
    os.makedirs(OUTD, exist_ok=True)
    seen = set()
    for name, ents in plan():
        with open(os.path.join(PK, name + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
            for fn, k, en, ref in ents:
                f.write('%s|%s\t%s\t%s\n' % (fn, k, en, ref))
                seen.add((fn, k))
        print('%-16s %5d 件 %7d 字' % (name, len(ents), sum(len(e[2]) for e in ents)))
    # 漏れがないか
    allk = set()
    for p in glob.glob(os.path.join(SRC, '*.tsv')):
        for e in load_src(os.path.basename(p)[:-4]):
            allk.add((e[0], e[1]))
    print('組に入っていない件:', len(allk - seen))


def collect():
    """work/out/*.tsv → translation/ja/<ファイル>.tsv（en を src から付ける）"""
    src = {}
    for p in glob.glob(os.path.join(SRC, '*.tsv')):
        for e in load_src(os.path.basename(p)[:-4]):
            src[(e[0], e[1])] = e[2]
    ja = {}
    terms = []
    problems = 0
    for p in sorted(glob.glob(os.path.join(OUTD, '*.tsv'))):
        for ln, line in enumerate(open(p, encoding='utf-8'), 1):
            line = line.rstrip('\r\n')
            if not line:
                continue
            if line.startswith('#TERM'):
                terms.append(line[5:].strip())
                continue
            if '\t' not in line or '|' not in line.split('\t')[0]:
                print('%s:%d 形が違う: %s' % (os.path.basename(p), ln, line[:60]))
                problems += 1
                continue
            key, tr = line.split('\t', 1)
            fn, k = key.split('|', 1)
            if (fn, k) not in src:
                print('%s:%d 知らない鍵 %s' % (os.path.basename(p), ln, key))
                problems += 1
                continue
            if tr.strip() == 'KEEP':
                continue
            en = src[(fn, k)]
            problems += check(fn, k, en, tr, os.path.basename(p), ln)
            ja.setdefault(fn, {})[k] = (en, tr)
    os.makedirs(JA, exist_ok=True)
    for fn, d in ja.items():
        def sk(k):
            return [int(x) for x in k.split(':')]
        with open(os.path.join(JA, fn + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
            for k in sorted(d, key=sk):
                f.write('%s\t%s\t%s\n' % (k, d[k][0], d[k][1]))
    n = sum(len(d) for d in ja.values())
    print('集めた: %d ファイル %d 件 / 原文 %d 件, 問題 %d' % (len(ja), n, len(src), problems))
    if terms:
        open(os.path.join(PK, 'terms.txt'), 'w', encoding='utf-8').write('\n'.join(terms) + '\n')
        print('新しい用語: %d（work/terms.txt）' % len(terms))


PF = re.compile(r'%(?:\d{2}(?![a-z])|[-+#0]*\d*(?:\.\d+)?(?:l|h)?[sdiucxXf%])')


def check(fn, k, en, tr, pf, ln):
    """差し込みの記号の数・順番、使えない字"""
    bad = 0
    e = PF.findall(B.unesc(en))
    t = PF.findall(B.unesc(tr))
    npc = [x for x in e if re.match(r'%\d{2}$', x)]
    prf = [x for x in e if not re.match(r'%\d{2}$', x)]
    tnpc = [x for x in t if re.match(r'%\d{2}$', x)]
    tprf = [x for x in t if not re.match(r'%\d{2}$', x)]
    if prf != tprf:
        print('%s:%d %s|%s printf の記号が違う %s → %s' % (pf, ln, fn, k, prf, tprf))
        bad += 1
    if [x for x in tnpc if x not in npc]:
        print('%s:%d %s|%s 英文にない NPC の記号 %s → %s' % (pf, ln, fn, k, npc, tnpc))
        bad += 1
    if '%01' in npc and '%01' not in tnpc:
        print('%s:%d %s|%s %%01（名前）が消えている' % (pf, ln, fn, k))
        bad += 1
    try:
        B.unesc(tr).encode('euc_jp')
    except UnicodeEncodeError as ex:
        ch = B.unesc(tr)[ex.start]
        print('%s:%d %s|%s 使えない字 %r' % (pf, ln, fn, k, ch))
        bad += 1
    if re.search('[｡-ﾟ]', tr):
        print('%s:%d %s|%s 半角カナ' % (pf, ln, fn, k))
        bad += 1
    if B.unesc(en).count('\n') != B.unesc(tr).count('\n') and not fn.lower().endswith('.str'):
        pass
    return bad


if __name__ == '__main__':
    {'make': make, 'collect': collect}[sys.argv[1]]()
