"""試験版の strdump（ゲーム自身が読んで作った、マップの文字列の表）を、訳から求めた期待値と照合する。

  1. 試験版を入れ、mm6jp.ini に [Debug] Test=1 TailFill=1 を書いて起動
  2. mm6t の send('strdump') → ゲームのフォルダに mm6jp_strdump.txt が出来て終わる
  3. python tools/check_strdump.py

ついでに、ゲームの限度（大きさ 0x2000 未満、500 本まで、1 本 800 バイトまで）も見る。
"""
import os, struct, sys, zlib
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..'))
GAME = os.path.abspath(os.path.join(WORK, '..'))


def load_bin():
    d = open(os.path.join(WORK, 'out', 'mm6jp_text.bin'), 'rb').read()
    nf = struct.unpack_from('<I', d, 4)[0]
    p = 8
    files = {}
    for _ in range(nf):
        nl = d[p]; p += 1
        name = d[p:p + nl].decode(); p += nl
        typ = d[p]; p += 1
        n = struct.unpack_from('<I', d, p)[0]; p += 4
        ents = {}
        for _k in range(n):
            key, crc, ln = struct.unpack_from('<IIH', d, p)
            ents[key] = (crc, d[p + 10:p + 10 + ln]); p += 10 + ln
        files[name.lower()] = (typ, ents)
    return files


def merge_strs(ents, s):
    """dll/lodtext.c の merge_strs と同じ"""
    out = bytearray(); i = 0; idx = 0; n = len(s)
    while i < n:
        st = i
        while i < n and s[i]: i += 1
        e = ents.get(idx)
        out += e[1] if e and (not e[0] or e[0] == zlib.crc32(s[st:i])) else s[st:i]
        if i < n: out.append(0); i += 1
        idx += 1
    return bytes(out)


def game_view(m):
    """ゲームの 0x439870 と同じ: NUL ごとに 1 本。先頭が " なら先頭と末尾の 1 字を落とす"""
    parts = m.split(b'\0')
    strs = parts[:-1]          # 最後の NUL のあとは数えない
    out = []
    for s in strs:
        if s[:1] == b'"': s = s[1:-1]
        out.append(s)
    return out


def main():
    files = load_bin()
    src = {f.lower(): os.path.join(WORK, 'extract', 'icons', f) for f in os.listdir(os.path.join(WORK, 'extract', 'icons'))}
    dump = {}
    cur = None
    for line in open(os.path.join(GAME, 'mm6jp_strdump.txt'), 'rb').read().split(b'\r\n'):
        if line.startswith(b'F '):
            _, name, size, cnt = line.split()
            cur = dump[name.decode()] = {'size': int(size), 'cnt': int(cnt), 's': {}}
        elif line:
            k, _, hx = line.partition(b' ')
            cur['s'][int(k)] = bytes.fromhex(hx.decode())
    bad = 0; nfile = 0; nstr = 0
    for name, (typ, ents) in sorted(files.items()):
        if typ != 2 or name in ('intro.str', 'win.str', 'lose.str'): continue
        m = merge_strs(ents, open(src[name], 'rb').read())
        exp = game_view(m)
        nfile += 1
        probs = []
        if len(m) >= 0x2000: probs.append('大きさ %d が 0x2000 以上' % len(m))
        if len(exp) > 500: probs.append('%d 本（500 本まで）' % len(exp))
        if max(len(x) for x in exp) > 800: probs.append('800 バイトを超える文がある')
        if m[-1:] != b'\0': probs.append('末尾が NUL でない')
        for i, x in enumerate(m.split(b'\0')[:-1]):
            if x[:1] == b'"' and x[-1:] != b'"': probs.append('%d: " で始まり " で終わらない' % i)
        g = dump.get(name)
        if not g: probs.append('書き出しにない')
        else:
            if g['size'] != len(m): probs.append('大きさ ゲーム %d / 期待 %d' % (g['size'], len(m)))
            if g['cnt'] != len(exp): probs.append('本数 ゲーム %d / 期待 %d' % (g['cnt'], len(exp)))
            for i, x in enumerate(exp):
                nstr += 1
                if g['s'].get(i) != x:
                    probs.append('%d: ゲーム %r / 期待 %r' % (i, g['s'].get(i, b'').decode('euc_jp', 'replace'), x.decode('euc_jp', 'replace')))
                if b'#' * 4 in g['s'].get(i, b''): probs.append('%d: 後ろのごみを読んでいる' % i)
        if probs:
            bad += 1
            print(name); [print('   ', p) for p in probs[:6]]
    print('マップの文字列集 %d 本・文字列 %d 本を照合、問題のあるファイル %d 本' % (nfile, nstr, bad))
    # 物語・勝ち・負けの文（NUL を改行にして 1 本の文として出す）
    for name in ('intro.str', 'win.str', 'lose.str'):
        typ, ents = files[name]
        s = open(src[name], 'rb').read()
        m = merge_strs(ents, s)
        print('%s: 元 %d → 訳後 %d バイト、末尾 %r' % (name, len(s), len(m), m[-2:]))
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
