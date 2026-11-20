# イベント・STR.DAT・品物・怪物の文を抜き出す
#   translation/en_events.tsv: 鍵 V.<i|o><場所 2桁>.<番号 3桁> / 幅（英文の1行の最大） / 英文（@ は \n にする）
#   translation/en_str.tsv:    鍵 S.<行 3桁> / 幅 / 英文（1行）
#   translation/en_items.tsv:  鍵 I.<番号 3桁> / 12 / 英文
#   translation/en_monsters.tsv: 鍵 M.<番号 3桁> / 14 / 英文
#   translation/events_meta.tsv: 鍵 V.<i|o><場所> / 文の表の位置 / 文の表の長さ / 全体の長さ
import os, struct, sys
sys.path.insert(0, os.path.dirname(__file__))
import lzw

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, '..', '..')
OUT = os.path.join(HERE, '..', 'translation')
EVBUF = 2300


def esc(s):
    return s.replace(chr(92), chr(92) * 2).replace(chr(10), chr(92) + 'n')


def events():
    """戻り値: [(io, loc, blob, anchor)]。anchor は文の表の前の 0xFF の位置"""
    out = []
    for io in 'IO':
        d = open(os.path.join(GAME, f'EVENTS{io}.DAT'), 'rb').read()
        offs = struct.unpack_from('<71I', d, 0)
        for loc, o in enumerate(offs):
            if not o:
                continue
            blob = lzw.unpack(d[o:])
            # 3 バイトずつの組の終わり（00 00 00）の後ろの語が、0xFF を指すところ（城は先頭の語）
            wpos = None
            w0 = struct.unpack_from('<H', blob, 0)[0]
            if blob[2] == 0xFF and w0 < len(blob) and blob[w0] == 0xFF:
                wpos = 0
            else:
                i = 0
                while i + 5 <= len(blob):
                    if blob[i:i + 3] == b'\0\0\0':
                        a = i + 3 + struct.unpack_from('<H', blob, i + 3)[0]
                        if i + 5 < a < len(blob) and blob[a] == 0xFF:
                            wpos = i + 3
                            break
                    i += 3
            anchor = wpos + struct.unpack_from('<H', blob, wpos)[0]
            assert blob[anchor] == 0xFF, (io, loc)
            out.append((io.lower(), loc, blob, anchor))
    return out


def main():
    n = 0
    with open(os.path.join(OUT, 'en_events.tsv'), 'w', encoding='utf-8', newline='\n') as f, \
         open(os.path.join(OUT, 'events_meta.tsv'), 'w', encoding='utf-8', newline='\n') as fm:
        for io, loc, blob, anchor in events():
            tab = blob[anchor + 1:]
            parts = tab.split(b'\xff')
            if parts and parts[-1] == b'':
                parts = parts[:-1]
            fm.write(f'V.{io}{loc:02d}\t{anchor}\t{len(tab)}\t{len(blob)}\t{len(parts)}\n')
            for k, p in enumerate(parts):
                t = p.decode('latin1')
                lines = t.split('@')
                w = max(len(x) for x in lines)
                f.write(f'V.{io}{loc:02d}.{k:03d}\t{w}\t{esc(t.replace("@", chr(10)))}\n')
                n += 1
    print('events', n)
    x = lzw.unpack(open(os.path.join(GAME, 'STR.DAT'), 'rb').read())
    t = bytes(10 if b == 1 else (b + 0x1C) & 255 for b in x).decode('latin1')
    lines = t.split('\n')
    with open(os.path.join(OUT, 'en_str.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for i, l in enumerate(lines):
            f.write(f'S.{i:03d}\t{len(l)}\t{esc(l)}\n')
    print('str', len(lines))
    d = open(os.path.join(GAME, 'ITEMS.DAT'), 'rb').read()
    with open(os.path.join(OUT, 'en_items.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for i in range(1, len(d) // 20):
            f.write(f'I.{i:03d}\t12\t{d[i * 20:i * 20 + 12].decode("latin1").rstrip()}\n')
    m = lzw.unpack(open(os.path.join(GAME, 'MONSTERS.DAT'), 'rb').read())
    with open(os.path.join(OUT, 'en_monsters.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for i in range(len(m) // 26):
            nm = bytes(c & 0x7F for c in m[i * 26:i * 26 + 14]).decode('latin1').rstrip()
            f.write(f'M.{i:03d}\t14\t{nm}\n')


if __name__ == '__main__':
    main()
