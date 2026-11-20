# -*- coding: utf-8 -*-
"""訳の検査。

python tools/check.py                全部を検査して translation/work/check.txt に書く
python tools/check.py --only cc_03   その組の出力（translation/work/out/cc_03.tsv）だけを検査して画面に出す

誤り（直すこと）: 使えない字、制御の印の違い、埋め込み（%s など）の違い、地名が 32 バイトを超える
注意（できれば直す）: 改行の数の違い、短い見出しが英文より幅広い、看板が長い、自分の改行の直後が行頭禁則の字
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from gather import gather_cc, gather_constants, gather_monsters
from cc import CC

NO_START = set('、。，．・：；？！゛゜ヽヾゝゞ々ー‐～’”）〕］｝〉》」』】°′″℃％ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ')

_font = None


def en_width(s):
    """英文（エスケープした形）の幅（ドット）。元のフォントの幅の表で数える。"""
    global _font
    if _font is None:
        _font = CC(os.path.join(ROOT, '..', 'SWRD.CC')).get('fnt')
    s = re.sub(r'\\x0[4]\d{3}|\\x07\d{3}|\\[tv]\d{3}|\\f(\d\d|d)|\\x[0-9A-F]{2}|\\[nr]', '', s)
    w = 0
    for ch in s:
        c = ord(ch)
        if c == 32:
            w += 4
        elif 32 < c < 128:
            w += _font[0x1000 + c]
        else:
            w += 8
    return w


def ja_width(s):
    s = re.sub(r'\\x0[4]\d{3}|\\x07\d{3}|\\[tv]\d{3}|\\f(\d\d|d)|\\x[0-9A-F]{2}|\\[nr]', '', s)
    w = 0
    for ch in s:
        c = ord(ch)
        if c == 32:
            w += 4
        elif c < 128:
            w += en_width(ch)
        else:
            w += 8
    return w


def bad_chars(s):
    out = []
    for ch in s:
        if ord(ch) < 128:
            continue
        if 0xFF61 <= ord(ch) <= 0xFF9F:
            out.append(ch)
            continue
        try:
            b = ch.encode('cp932')
        except UnicodeEncodeError:
            out.append(ch)
            continue
        if len(b) != 2 or b[0] == 0x87 or b[0] in (0xED, 0xEE) or b[0] >= 0xFA:
            out.append(ch)
    return out


def norm_fmt(tokens):
    return ['%s' if t == '%.0s' else t for t in tokens]


def check_one(k, en, ja, note, errs, warns):
    if ja is None or ja == 'KEEP':
        return
    if '\t' in ja:
        errs.append((k, 'タブが入っている', ja))
    bc = bad_chars(ja)
    if bc:
        errs.append((k, '使えない字 %s' % ''.join(sorted(set(bc))), ja))
    try:
        from constants import unesc
        unesc(ja)
    except Exception as e:
        errs.append((k, '印の書き方の誤り %s' % e, ja))
    ce = [t for t in ctrl_tokens(en) if t != '\\n']
    cj = [t for t in ctrl_tokens(ja) if t != '\\n']
    if ce != cj:
        errs.append((k, '制御の印が違う 英%s 訳%s' % (' '.join(ce), ' '.join(cj)), ja))
    if norm_fmt(fmt_tokens(en)) != norm_fmt(fmt_tokens(ja)):
        errs.append((k, '埋め込みが違う 英%s 訳%s' % (' '.join(fmt_tokens(en)), ' '.join(fmt_tokens(ja))), ja))
    if en.count('\\n') != ja.count('\\n'):
        warns.append((k, '改行の数が違う 英%d 訳%d' % (en.count('\\n'), ja.count('\\n')), ja))
    for part in ja.split('\\n')[1:]:
        p = re.sub(r'^(\\[tv]\d{3}|\\f(\d\d|d)|\\x[0-9A-F]{2})*', '', part)
        if p and p[0] in NO_START:
            warns.append((k, '改行の直後が行頭禁則の字', ja))
            break
    if note.startswith('地名') and len(ja.encode('cp932', 'replace')) > 32:
        errs.append((k, '地名が 32 バイトを超える', ja))
    if note in ('看板', '扉の文') and ja_width(ja) > 12 * 8:
        warns.append((k, '看板・扉の文が全角 12 字より長い', ja))


def main():
    only = None
    if len(sys.argv) > 2 and sys.argv[1] == '--only':
        only = sys.argv[2].replace('.tsv', '')
    errs, warns = [], []

    rows, trans, src = gather_cc()
    if only:
        keys = set(load_trans(os.path.join(TR, 'work', 'out', only + '.tsv')))
        work = set(r[0] for r in read_tsv(os.path.join(TR, 'work', only + '.tsv')))
        missing = work - keys
        for k in sorted(missing):
            errs.append((k, 'まだ訳がない', ''))
        for k in sorted(keys - work):
            errs.append((k, '組に無い鍵', ''))
    for r in rows:
        k, en = r[0], r[1]
        note = r[2] if len(r) > 2 else ''
        if only and not only.startswith('cc'):
            break
        if only and k not in keys:
            continue
        check_one(k, en, trans.get(k), note, errs, warns)
        ja = trans.get(k)
        if len(r) > 3 and r[3] == 'special.bin' and ja and ja != 'KEEP' and en.strip().count('   ') != ja.strip().count('   '):
            errs.append((k, '字幕の区切り（空白3つ）の数が違う 英%d 訳%d' % (en.strip().count('   '), ja.strip().count('   ')), ja))

    crows, ctrans = gather_constants()
    if not only or only.startswith('con'):
        ckeys = None
        if only:
            ckeys = set(load_trans(os.path.join(TR, 'work', 'out', only + '.tsv')))
            work = set(r[0] for r in read_tsv(os.path.join(TR, 'work', only + '.tsv')))
            for k in sorted(work - ckeys):
                errs.append((k, 'まだ訳がない', ''))
        for r in crows:
            k, en = r[0], (r[1] if len(r) > 1 else '')
            if ckeys is not None and k not in ckeys:
                continue
            ja = ctrans.get(k)
            check_one(k, en, ja, '', errs, warns)
            if ja and ja != 'KEEP' and '\\n' not in en and len(en) < 40 and ja_width(ja) > en_width(en) + 8:
                warns.append((k, '短い見出しが英文より幅広い 英%dドット 訳%dドット' % (en_width(en), ja_width(ja)), ja))

    if not only:
        mrows, mtrans = gather_monsters()
        for r in mrows:
            ja = mtrans.get(r[0])
            if ja and ja_width(ja) > 64:
                warns.append((r[0], '怪物の名前が全角 8 字より長い', ja))
            if ja and bad_chars(ja):
                errs.append((r[0], '使えない字', ja))

    lines = ['誤り %d 件、注意 %d 件' % (len(errs), len(warns)), '']
    lines += ['[誤り] %s\t%s\t%s' % e for e in errs]
    lines += ['[注意] %s\t%s\t%s' % w for w in warns]
    if not only:
        done = sum(1 for r in rows if r[0] in trans)
        lines.insert(1, 'CC の文 %d / %d に訳あり（うち KEEP %d）、画面の部品 %d / %d' % (
            done, len(rows), sum(1 for v in trans.values() if v == 'KEEP'),
            len(ctrans), len(crows)))
        with open(os.path.join(TR, 'work', 'check.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('\n'.join(lines) + '\n')
        print('\n'.join(lines[:3]))
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        print('\n'.join(lines))
    return 1 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
