# -*- coding: utf-8 -*-
"""訳から日本語化の書庫 xeen_ja.dat（zip）を組み立てる。

python tools/build_ja.py [出力]（既定 build/ja/xeen_ja.dat）

訳の集め方は tools/gather.py（作業の出力 → 用語集 → 手直し）。訳のない文は英文のまま。
訳文の書き方: 制御の印は英文と同じ \\n \\t123 \\v123 \\f12 \\xNN。英文の前後の空白は訳に引き継ぐ。

書庫の中身
- xeen/<番号>, dark/<番号>, intro/<番号>: 訳した文のファイル（番号は CC の中の番号を 16 進 4 桁の小文字で）
- CONSTANTS_21, CONSTKEYS_21: 画面の部品の文（ScummVM の mm.dat と同じ形）
- monnames/xeen.mon, monnames/dark.mon: 怪物の名前（0 区切り）
- font_ja.bin
- font_ja12.bin: 東雲フォント 12 ドット（tools/build_font12.py）
- gfx/<絵のファイル名>/imageNN.bmp: 絵の中の英文を日本語に描き替えたもの（tools/make_endings.py）
"""
import sys, os, re, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import constants as C
from gather import gather_cc, gather_constants, gather_monsters
from common import ROOT

PREFIX = {'X': 'xeen', 'D': 'dark', 'I': 'intro'}


def carry_spaces(en, ja):
    """英文の前後の空白を訳に引き継ぐ。訳が自分で付けていればそのまま。"""
    lead = re.match(r'^ *', en).group(0)
    trail = re.search(r' *$', en).group(0)
    if lead and not ja.startswith(' '):
        ja = lead + ja
    if trail and not ja.endswith(' '):
        ja = ja + trail
    return ja


def text_of(en, ja):
    if ja is None or ja == 'KEEP':
        return C.unesc(en)
    return C.unesc(carry_spaces(en, ja))


def main():
    outp = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'ja', 'xeen_ja.dat')
    rows, trans, src = gather_cc()

    files = {}
    changed = set()
    for r in rows:
        k, en = r[0], r[1]
        arc, fid, i = k.split(':')
        t = text_of(en, trans.get(k))
        if t == C.unesc(en):
            # 英語のまま: 原作の文を入れず、印 0x7F だけを書く（ScummVM が元の CC から写す）
            t = b'\x7f' if t else b''
        else:
            changed.add((arc, fid))
        files.setdefault((arc, fid), []).append(t)

    z = zipfile.ZipFile(outp, 'w', zipfile.ZIP_DEFLATED)
    n = 0
    for (arc, fid), strs in sorted(files.items()):
        if (arc, fid) not in changed:
            continue
        z.writestr('%s/%s' % (PREFIX[arc], fid.lower()), b'\0'.join(strs) + b'\0')
        n += 1

    crows, ctrans = gather_constants()
    cdict = {}
    for r in crows:
        k, en = r[0], (r[1] if len(r) > 1 else '')
        if k in ctrans and ctrans[k] != 'KEEP':
            cdict[k] = carry_spaces(en, ctrans[k])
    z.writestr('CONSTANTS_21', C.build(cdict))
    z.writestr('CONSTKEYS_21', C.read_en('CONSTKEYS'))

    mrows, mtrans = gather_monsters()
    groups = {}
    for r in mrows:
        k, en = r[0], (r[1] if len(r) > 1 else '')
        _, fname, i = k.split(':')
        groups.setdefault(fname, []).append(text_of(en, mtrans.get(k)))
    for fname, names in groups.items():
        z.writestr('monnames/%s' % fname, b'\0'.join(names) + b'\0')

    z.write(os.path.join(ROOT, 'build', 'ja', 'font_ja.bin'), 'font_ja.bin')
    # 東雲フォント 12 ドット（tools/build_font12.py）。ScummVM の F11 で美咲と切り替える
    f12 = os.path.join(ROOT, 'build', 'ja', 'font_ja12.bin')
    if os.path.exists(f12):
        z.write(f12, 'font_ja12.bin')
    # 絵の差し替え（tools/make_endings.py が作る gfx/<絵のファイル名>/imageNN.bmp）
    gfx = os.path.join(ROOT, 'build', 'ja', 'gfx')
    for base, dirs, fs in os.walk(gfx):
        for f in sorted(fs):
            p = os.path.join(base, f)
            z.write(p, os.path.relpath(p, os.path.join(ROOT, 'build', 'ja')).replace(os.sep, '/'))
    z.close()
    done = sum(1 for r in rows if r[0] in trans)
    print('文 %d / %d、訳したファイル %d、画面の部品 %d / %d、怪物 %d / %d → %s %d バイト' % (
        done, len(rows), n, len(cdict), len(crows), len(mtrans), len(mrows), outp, os.path.getsize(outp)))


if __name__ == '__main__':
    main()
