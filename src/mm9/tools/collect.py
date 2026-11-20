# -*- coding: utf-8 -*-
"""訳者の出力（translation/work/*_out*.tsv）を集めて検査し、translation/ja/<組>.tsv と辞書を作る。

- 同じ英文の鍵には、代表の鍵の訳をすべて当てる
- 検査: 書式（%s %d %%）の数と順番、半角の " 、字の表に無い字、KEEP、空
- 手直しは translation/ja_fix.tsv（鍵<TAB>訳）に書けば最後に上書きされる
- 辞書: dict_* の組と、短い訳（英文 40 字以下）を translation/dict/auto.tsv に（表示時の置き換え用）
- 名前の表: translation/glossary_names.tsv（人名・地名・店・本の題・怪物・呪文・品物）

python tools/collect.py
"""
import os
import re
import sys
import glob
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jpenc
from make_work import load_src

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TR = os.path.join(ROOT, 'translation')
WORK = os.path.join(TR, 'work')
JA = os.path.join(TR, 'ja')
DICT = os.path.join(TR, 'dict')

FMT = re.compile(r'%[-+#0]*\d*(?:\.\d+)?(?:l|h)?[sdiuxXfcp%]')


def fmts(s):
    return FMT.findall(s)


def load_unify():
    """translation/unify.tsv（正規表現<TAB>置き換え）: 組ごとに分かれた訳語をそろえる"""
    rules = []
    p = os.path.join(TR, 'unify.tsv')
    if os.path.exists(p):
        for line in open(p, encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if line and not line.startswith('#') and '\t' in line:
                a, b = line.split('\t', 1)
                rules.append((re.compile(a), b))
    return rules


def read_outputs():
    out = OrderedDict()
    for fn in sorted(glob.glob(os.path.join(WORK, '*_out*.tsv'))):
        for ln, line in enumerate(open(fn, encoding='utf-8-sig'), 1):
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            if '\t' not in line:
                print('書式の誤り %s:%d %r' % (os.path.basename(fn), ln, line[:60]))
                continue
            k, v = line.split('\t', 1)
            out[k.strip()] = v
    fix = os.path.join(TR, 'ja_fix.tsv')
    if os.path.exists(fix):
        for line in open(fix, encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if line and not line.startswith('#') and '\t' in line:
                k, v = line.split('\t', 1)
                out[k.strip()] = v
    return out


def main():
    units = load_src()
    src = {k: (g, en) for g, k, en in units}
    out = read_outputs()
    rules = load_unify()
    for k in list(out):
        v = out[k]
        for rx, rep in rules:
            v = rx.sub(rep, v)
        out[k] = v
    # 英文 → 訳（代表の鍵から）
    by_en = {}
    problems = []
    missing = set()
    for k, v in out.items():
        if k not in src:
            problems.append(('未知の鍵', k, v))
            continue
        g, en = src[k]
        v = v.strip('\r')
        if v == 'KEEP':
            by_en[en] = None
            continue
        if not v.strip():
            problems.append(('空', k, en))
            continue
        if fmts(en) != fmts(v):
            problems.append(('書式', k, '%s ⇔ %s' % (fmts(en), fmts(v))))
        if '"' in v:
            problems.append(('半角"', k, v[:60]))
        if '\t' in v:
            problems.append(('タブ', k, v[:60]))
        miss = set()
        jpenc.encode(v.replace('\\n', '\n'), miss)
        if miss:
            missing |= miss
            problems.append(('表に無い字 ' + ''.join(sorted(miss)), k, v[:60]))
        by_en[en] = v
    # 組ごとに書く
    os.makedirs(JA, exist_ok=True)
    os.makedirs(DICT, exist_ok=True)
    groups = OrderedDict()
    done = 0
    for g, k, en in units:
        if en in by_en and by_en[en] is not None:
            groups.setdefault(g, []).append((k, by_en[en]))
            done += 1
    for fn in glob.glob(os.path.join(JA, '*.tsv')):
        os.remove(fn)
    names = OrderedDict()
    auto = OrderedDict()
    for g, rows in groups.items():
        if g.startswith('dict_'):
            with open(os.path.join(DICT, g + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
                for k, v in rows:
                    en = src[k][1]
                    f.write('%s\t%s\n' % (en, v))
                    names[en] = v
            continue
        with open(os.path.join(JA, g + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
            for k, v in rows:
                f.write('%s\t%s\n' % (k, v))
        for k, v in rows:
            en = src[k][1]
            if g in ('npcname', 'mapstats', 'shops') or (g == 'item' and re.match(r'item:\d+:1:', k)) \
                    or (g == 'concat' and re.match(r'concat:\d+:1:', k)) or (g == 'book' and re.match(r'book:\d+:1:', k)) \
                    or (g == 'gametext' and 214 <= int(k.split(':')[1]) <= 221):
                names[en] = v
            if len(en) <= 40 and '\\n' not in en and not fmts(en):
                auto.setdefault(en, v)
    with open(os.path.join(DICT, 'auto.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for en, v in auto.items():
            f.write('%s\t%s\n' % (en, v))
    with open(os.path.join(TR, 'glossary_names.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for en, v in names.items():
            f.write('%s\t%s\n' % (en, v))
    # 用語（#TERM と *_terms.tsv）
    terms = OrderedDict()
    for fn in sorted(glob.glob(os.path.join(WORK, '*_terms*.tsv'))) + sorted(glob.glob(os.path.join(WORK, '*_out*.tsv'))):
        for line in open(fn, encoding='utf-8-sig'):
            line = line.rstrip('\r\n')
            if line.startswith('#TERM '):
                line = line[6:]
            elif fn.endswith('_out.tsv') or '_out' in os.path.basename(fn):
                continue
            if '\t' in line:
                a, b = line.split('\t', 1)
                terms.setdefault(a.strip(), b.strip())
    with open(os.path.join(TR, 'glossary_terms.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for a, b in terms.items():
            f.write('%s\t%s\n' % (a, b))
    total = len(units)
    print('訳のある鍵 %d / %d（英文の異なり %d 件を訳した）' % (done, total, len([v for v in by_en.values() if v])))
    print('辞書（短い訳）%d 語、名前の表 %d、用語 %d' % (len(auto), len(names), len(terms)))
    with open(os.path.join(TR, 'problems.txt'), 'w', encoding='utf-8') as f:
        for p in problems:
            f.write('%s\t%s\t%s\n' % p)
    print('問題 %d 件（translation/problems.txt）' % len(problems))
    if missing:
        print('表に無い字:', ''.join(sorted(missing)))
        ex = os.path.join(TR, 'extra_chars.txt')
        have = open(ex, encoding='utf-8').read() if os.path.exists(ex) else ''
        add = ''.join(c for c in sorted(missing) if c not in have)
        if add:
            open(ex, 'a', encoding='utf-8').write(add)
            print('extra_chars.txt に足した（tools/make_jpfont.py をやり直すこと）:', add)


if __name__ == '__main__':
    main()
