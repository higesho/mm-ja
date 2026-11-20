# -*- coding: utf-8 -*-
"""訳を集める（組み立てと検査で共通）。

- CC の文: translation/work/out/cc_*.tsv → 用語集で埋める → translation/ja/*.tsv（手直し、最後に勝つ）
- 画面の部品の文: translation/work/out/con_*.tsv → 名前の表は用語集で埋める → translation/ja_constants/*.tsv
- 怪物の名前: 用語集の「怪物」→ translation/ja_monsters.tsv
同じ英文は、訳のある鍵から同じ訳を写す（CC の文の中だけ）。
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

GLOSSARY_CC_KIND = {'mapname': '地名', 'spells.xen': '呪文', 'mae.xen': '材質'}


def fill_core(en, ja_core):
    """英文の前後の制御・空白を残して中身だけ置き換える。"""
    pre, core, post = split_affix(en)
    return pre + ja_core + post


_HARMONIZE = None


def harmonize(d):
    """translation/そろえ.tsv の置き換えを訳に当てる。"""
    global _HARMONIZE
    if _HARMONIZE is None:
        _HARMONIZE = []
        p = os.path.join(TR, 'そろえ.tsv')
        if os.path.exists(p):
            for r in read_tsv(p):
                if len(r) >= 2:
                    src_ = r[0][3:] if r[0].startswith('re:') else re.escape(r[0])
                    _HARMONIZE.append((re.compile(src_), r[1]))
    for k, v in d.items():
        if v and v != 'KEEP':
            for rx, to in _HARMONIZE:
                v = rx.sub(to, v)
            d[k] = v
    return d


def gather_cc():
    rows = read_tsv(os.path.join(TR, 'cc_en.tsv'))
    by_kind, by_en = load_glossary()
    out = load_trans(os.path.join(TR, 'work', 'out', 'cc_*.tsv'))
    src = {k: 'work' for k in out}
    # 用語集
    for r in rows:
        k, en = r[0], r[1]
        note = r[2] if len(r) > 2 else ''
        fname = r[3] if len(r) > 3 else ''
        if k in out:
            continue
        kind = None
        if note.startswith('地名'):
            kind = '地名'
        elif fname in GLOSSARY_CC_KIND:
            kind = GLOSSARY_CC_KIND[fname]
        elif note == '名前':
            kind = '人名'
        elif note == '物の名前（誰が〜の見出し）':
            kind = '物'
        if kind:
            pre, core, post = split_affix(en)
            ja = by_kind.get((kind, en)) or by_en.get(en) or by_kind.get((kind, core)) or by_en.get(core)
            if ja is not None:
                out[k] = ja if (kind, en) in by_kind or en in by_en else fill_core(en, ja)
                src[k] = 'glossary'
        if '答え' in note and k not in out:
            out[k] = 'KEEP'
            src[k] = 'answer'
    fixes = load_trans(os.path.join(TR, 'ja', '*.tsv'))
    for k, v in fixes.items():
        out[k] = v
        src[k] = 'fix'
    # 同じ英文に同じ訳
    by_text = {}
    for r in rows:
        if r[0] in out and out[r[0]] != 'KEEP':
            by_text.setdefault(r[1], out[r[0]])
    for r in rows:
        if r[0] not in out and r[1] in by_text:
            out[r[0]] = by_text[r[1]]
            src[r[0]] = 'same'
    return rows, harmonize(out), src


def gather_constants():
    rows = read_tsv(os.path.join(TR, 'constants_en.tsv'))
    by_kind, by_en = load_glossary()
    out = load_trans(os.path.join(TR, 'work', 'out', 'con_*.tsv'))
    for r in rows:
        k = r[0]
        en = r[1] if len(r) > 1 else ''
        b = const_base(k)
        if k in out or b not in CONST_GLOSSARY or not en:
            continue
        kind = CONST_GLOSSARY[b]
        pre, core, post = split_affix(en)
        # SKILL_NAMES の後ろの \t100 なども残す
        ja = by_kind.get((kind, core)) or by_en.get(core)
        if ja is None and core.strip():
            ja = by_kind.get((kind, core.strip())) or by_en.get(core.strip())
        if ja is not None:
            out[k] = pre + ja + post
    out.update(load_trans(os.path.join(TR, 'ja_constants', '*.tsv')))
    return rows, harmonize(out)


def gather_monsters():
    rows = read_tsv(os.path.join(TR, 'monsters_en.tsv'))
    by_kind, by_en = load_glossary()
    out = {}
    for r in rows:
        k, en = r[0], (r[1] if len(r) > 1 else '')
        ja = by_kind.get(('怪物', en)) or by_en.get(en)
        if ja:
            out[k] = ja
    p = os.path.join(TR, 'ja_monsters.tsv')
    if os.path.exists(p):
        out.update(load_trans(p))
    return rows, out
