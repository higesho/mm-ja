# -*- coding: utf-8 -*-
"""訳す仕事を組（バッチ）に分けて translation/work/<組>_in.tsv を作る。

同じ英文は一度だけ訳す（最初に出た鍵を代表にする）。既に訳がある英文（translation/ja と dict にあるもの）は除く。
各行: 代表の鍵<TAB>英文。会話（rude）は NPC ごとに「#NPC 番号 名前」の行を挟む（文脈のため）。

python tools/make_work.py names      名前の組（N1: 人名・地名・店・本の題・怪物・呪文、N2: 品物名と付加語）
python tools/make_work.py bulk [字数]  残り全部を字数ごとに分ける（既定 22000）
"""
import os
import re
import sys
import glob

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'translation', 'src')
WORK = os.path.join(ROOT, 'translation', 'work')

ORDER = ['gametext', 'statdesc', 'skill', 'spell', 'concat', 'item', 'book', 'journal', 'scripttext',
         'pcvoice', 'blurb', 'rude', 'npcname', 'mapstats', 'shops', 'dict_monster', 'dict_spell']


def load_src():
    units = []  # (group, key, en)
    for g in ORDER:
        for line in open(os.path.join(SRC, g + '.tsv'), encoding='utf-8'):
            k, en = line.rstrip('\n').split('\t', 1)
            units.append((g, k, en))
    return units


def done_english():
    """訳のある英文の集合"""
    src = {}
    for g, k, en in load_src():
        src[k] = en
    done = set()
    for fn in glob.glob(os.path.join(ROOT, 'translation', 'ja', '*.tsv')):
        for line in open(fn, encoding='utf-8'):
            if '\t' in line and not line.startswith('#'):
                k, v = line.rstrip('\n').split('\t', 1)
                if k in src and v.strip():
                    done.add(src[k])
    for fn in glob.glob(os.path.join(WORK, '*_out.tsv')):
        for line in open(fn, encoding='utf-8'):
            if '\t' in line and not line.startswith('#'):
                k, v = line.rstrip('\n').split('\t', 1)
                if k in src and v.strip():
                    done.add(src[k])
    return done


def npc_names():
    names = {}
    for line in open(os.path.join(SRC, 'npcname.tsv'), encoding='utf-8'):
        k, en = line.rstrip('\n').split('\t', 1)
        m = re.match(r'npcname:\d+:1:(\d+)', k)
        if m:
            names[int(m.group(1))] = en
    return names


def write_batch(name, rows):
    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, name + '_in.tsv')
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        for r in rows:
            f.write(r + '\n')
    n = sum(len(r.split('\t', 1)[1]) for r in rows if '\t' in r and not r.startswith('#'))
    print('%-24s %5d 行 %7d 字' % (name, len([r for r in rows if not r.startswith('#')]), n))


def main():
    mode = sys.argv[1]
    units = load_src()
    done = done_english()
    seen = set(done)
    names = npc_names()

    def take(pred):
        rows = []
        for g, k, en in units:
            if en in seen or not pred(g, k, en):
                continue
            seen.add(en)
            rows.append((g, k, en))
        return rows

    if mode == 'names':
        n1 = take(lambda g, k, en: g in ('npcname', 'mapstats', 'shops', 'dict_monster', 'dict_spell')
                  or (g == 'book' and re.match(r'book:\d+:1:', k))
                  or (g == 'gametext' and 214 <= int(k.split(':')[1]) <= 221))
        n2 = take(lambda g, k, en: (g == 'item' and re.match(r'item:\d+:1:', k)) or (g == 'concat' and re.match(r'concat:\d+:1:', k)))
        write_batch('N1_names', ['%s\t%s' % (k, en) for g, k, en in n1])
        write_batch('N2_items', ['%s\t%s' % (k, en) for g, k, en in n2])
        return

    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 22000
    rest = take(lambda g, k, en: True)
    batches = []
    cur, size, curg = [], 0, None
    lastnpc = None
    for g, k, en in rest:
        if cur and (size >= limit or (g != curg and size >= limit * 0.5)):
            batches.append(cur)
            cur, size, lastnpc = [], 0, None
        curg = g
        if g == 'rude':
            npc = int(k.split(':')[1])
            if npc != lastnpc:
                cur.append('#NPC %d %s' % (npc, names.get(npc, '?')))
                lastnpc = npc
        cur.append('%s\t%s' % (k, en))
        size += len(en)
    if cur:
        batches.append(cur)
    for i, b in enumerate(batches, 1):
        g = b[0].split(':')[0] if not b[0].startswith('#') else 'rude'
        write_batch('B%02d_%s' % (i, g), b)


if __name__ == '__main__':
    main()
