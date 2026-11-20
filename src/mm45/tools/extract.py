# -*- coding: utf-8 -*-
"""XEEN.CC・DARK.CC・INTRO.CC から訳す文を抜き出す。

python tools/extract.py
  → translation/cc_en.tsv   鍵<TAB>英文<TAB>使われ方<TAB>ファイル（推定した名前）
     鍵は「書庫:番号:何番目」（書庫は X=XEEN.CC、D=DARK.CC、I=INTRO.CC。番号は CC の中の番号＝名前のハッシュ）
  → translation/cc_files.tsv  文のファイルの一覧（書庫:番号、推定した名前、種類、文の数、大きさ）
  → translation/monsters_en.tsv  怪物の名前（鍵 M:xeen.mon:番号 など）

英文の中の制御文字は constants.py と同じく \\n \\t \\v \\f \\r \\xNN の形。
文のファイルは「0 で終わる文字列が並んだもの」（地図の文 aaze*.txt、地名、呪文名、酒場のうわさ、冒険の記録など）。
地図の台本（maze*.evt）を読み、地図の文がどの命令で使われるか（会話・看板・答えなど）を「使われ方」に書く。
"""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cc import CC, name_to_id
from constants import esc

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
GAME = os.path.join(ROOT, '..')
OUT = os.path.join(ROOT, 'translation')

ARCHIVES = [('X', 'XEEN.CC'), ('D', 'DARK.CC'), ('I', 'INTRO.CC')]
CTRL_OK = set(range(1, 13)) | {0}

# 名前の分かっているもの（ScummVM のソースから）
FIXED_NAMES = ['tavern.bin', 'spldesc.bin', 'qnotes.bin', 'special.bin', 'award.bin', 'spells.xen',
               'mae.xen', 'mae.cld', 'spells.cld', 'mapnames.cld', 'xeenmirr.txt', 'darkmirr.txt',
               'xeen.mon', 'dark.mon']


def map_names():
    """地図番号ごとの名前の型。"""
    out = {}
    for m in range(256):
        c = 'x' if m >= 100 else '0'
        out['aaze%s%03d.txt' % (c, m)] = ('map', m)
        out['aaze2%03d.txt' % m] = ('large', m)
        out['xeen%s%03d.txt' % (c, m)] = ('mapname', m)
        out['dark%s%03d.txt' % (c, m)] = ('mapname', m)
    return out


def is_strlist(d):
    if not d or len(d) < 2:
        return False
    if any(not (32 <= b < 127 or b in CTRL_OK) for b in d):
        return False
    return sum(1 for b in d if 65 <= b <= 122) > len(d) * 0.3


def save_archive(cc):
    """セーブ書庫（0x2A0C などをつないだもの）の中のファイル: 番号 → 中身。地図の台本はここにある。"""
    data = b''.join(cc.get(r) or b'' for r in (0x2A0C, 0x2A1C, 0x2A2C, 0x2A3C, 0x284C, 0x2A5C))
    if not data:
        return {}
    from cc import read_index
    return {fid: data[off:off + size] for fid, off, size in read_index(data)}


def parse_events(d):
    """地図の台本: (位置, 命令, 引数) の並び。"""
    ev = []
    pos = 0
    while pos < len(d):
        ln = d[pos]
        if ln < 5 or pos + 1 + ln > len(d):
            break
        x, y, dr, line, op = d[pos + 1:pos + 6]
        params = list(d[pos + 6:pos + 1 + ln])
        ev.append(((x, y, dr, line), op, params))
        pos += 1 + ln
    return ev


def text_uses(events):
    """地図の文の番号 → 使われ方の集合。"""
    uses = {}

    def add(i, what):
        uses.setdefault(i, set()).add(what)
    for _, op, p in events:
        p0 = p[0] if p else None
        if op == 0x01:
            add(p0, '表示')
        elif op in (0x02, 0x03):
            add(p0, '扉の文')
        elif op in (0x04, 0x27):
            add(p0, '看板')
        elif op == 0x05:
            add(p0, '名前')
            if len(p) > 1:
                add(p[1], '会話')
        elif op in (0x15, 0x37):
            # ConfirmWord: p0 は入力の種類（0 は鏡）。p2 が 0 なら p0 番の文が答え、p3 は問いの見出し
            if len(p) > 3:
                if p[2]:
                    add(p[2], '答え')
                elif p0:
                    add(p0, '答え')
                if p[3]:
                    add(p[3], '問い')
        elif op == 0x20:
            if len(p) > 1:
                add(p[1], '物の名前（誰が〜の見出し）')
        elif op in (0x29, 0x35):
            add(p0, '表示')
        elif op == 0x25:
            add(p0, '表示（%s は名前）')
        elif op == 0x31:
            if len(p) > 1:
                add(p[1], '表示（下2行）')
    return uses


def main():
    os.makedirs(OUT, exist_ok=True)
    mnames = map_names()
    rows = []
    files = []
    mons = []
    for tag, fn in ARCHIVES:
        cc = CC(os.path.join(GAME, fn))
        # 名前の推定
        guess = {}
        for n in FIXED_NAMES:
            guess.setdefault(name_to_id(n), n)
        for n in mnames:
            guess.setdefault(name_to_id(n), n)
        # 地図の台本
        evuses = {}
        sav = save_archive(cc)
        for m in range(256):
            c = 'x' if m >= 100 else '0'
            d = sav.get(name_to_id('maze%s%03d.evt' % (c, m)))
            if d:
                evuses[m] = text_uses(parse_events(d))
        for fid, off, size in cc.index:
            d = cc.get(fid)
            name = guess.get(fid, '')
            if name in ('xeen.mon', 'dark.mon') and d:
                # 怪物の名前（1件の大きさは ScummVM の MonsterStruct から）
                continue
            if name.endswith('mirr.txt'):
                continue            # 鏡の行き先（打って答える言葉）は英語のまま
            if not is_strlist(d):
                continue
            kind, m = mnames.get(name, ('other', None))
            if name and kind == 'other':
                kind = name
            strs = d.split(b'\0')
            if strs and strs[-1] == b'':
                strs = strs[:-1]
            uses = evuses.get(m, {}) if kind == 'map' else {}
            files.append((tag, fid, name, kind, len(strs), len(d)))
            for i, s in enumerate(strs):
                note = ''
                if kind == 'map':
                    note = '・'.join(sorted(uses.get(i, [])))
                elif kind == 'mapname':
                    note = '地名（32バイトまで）'
                elif kind == 'large':
                    note = '長い文'
                rows.append(('%s:%04X:%d' % (tag, fid, i), esc(s), note, name))
    with open(os.path.join(OUT, 'cc_en.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for r in rows:
            f.write('\t'.join(r) + '\n')
    with open(os.path.join(OUT, 'cc_files.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for tag, fid, name, kind, n, size in files:
            f.write('%s:%04X\t%s\t%s\t%d\t%d\n' % (tag, fid, name, kind, n, size))
    # 怪物の名前（DARK.CC の xeen.mon・dark.mon。1 件 60 バイトで、先頭 16 バイトが名前）
    dcc = CC(os.path.join(GAME, 'DARK.CC'))
    with open(os.path.join(OUT, 'monsters_en.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for fname in ('xeen.mon', 'dark.mon'):
            d = dcc.get(fname)
            for i in range(len(d) // 60):
                nm = d[i * 60:i * 60 + 16].split(b'\0')[0]
                f.write('M:%s:%d\t%s\n' % (fname, i, esc(nm)))
    uniq = len(set(r[1] for r in rows))
    print('文のファイル', len(files), '文', len(rows), '重複を除いて', uniq,
          '英文の大きさ（重複を除く）', sum(len(s) for s in set(r[1] for r in rows)))


if __name__ == '__main__':
    main()
