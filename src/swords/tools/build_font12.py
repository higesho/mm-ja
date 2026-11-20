# -*- coding: utf-8 -*-
"""東雲フォント 12 ドット（BDF、JIS X 0208）から ScummVM の日本語表示用の font_ja12.bin を作る。

font_ja12.bin: JIS X 0208 の 94 区 × 94 点、1 字 24 バイト（1 行 2 バイト × 12 行、上位ビットが左）。
並びは font_ja.bin（美咲 8×8）と同じで、区点の番号で引く。
ScummVM は画面を 3 倍に広げ、美咲のマス（8×8）を東雲の字（1 ドットを 2×2）で描き直す（engines/mm/xeen/screen.cpp）。

python tools/build_font12.py <shnmk12.bdf> <出力>
東雲フォントはパブリックドメイン。
"""
import sys


def main():
    bdf, outp = sys.argv[1], sys.argv[2]
    data = bytearray(94 * 94 * 24)
    have = 0
    enc = None
    bbx = None
    rows = None
    for line in open(bdf, encoding='latin-1'):
        w = line.split()
        if not w:
            continue
        if w[0] == 'ENCODING':
            enc = int(w[1])
        elif w[0] == 'BBX':
            bbx = tuple(int(x) for x in w[1:5])
        elif w[0] == 'BITMAP':
            rows = []
        elif w[0] == 'ENDCHAR':
            ku, ten = (enc >> 8) - 0x20, (enc & 0xFF) - 0x20
            if 1 <= ku <= 94 and 1 <= ten <= 94:
                bw, bh, bx, by = bbx
                # FONTBOUNDINGBOX は 12 12 0 -2。字の箱がずれていれば合わせる
                top = (12 - 2) - (by + bh)
                cell = ((ku - 1) * 94 + (ten - 1)) * 24
                for i, v in enumerate(rows):
                    y = top + i
                    if not 0 <= y < 12:
                        continue
                    nbytes = (bw + 7) // 8
                    v <<= (16 - nbytes * 8)
                    v = (v >> bx) if bx >= 0 else (v << -bx)
                    v &= 0xFFF0
                    data[cell + y * 2] = v >> 8
                    data[cell + y * 2 + 1] = v & 0xFF
                have += 1
            rows = None
        elif rows is not None:
            rows.append(int(w[0], 16))
    open(outp, 'wb').write(data)
    print('字の数', have, '→', outp, len(data), 'バイト')


if __name__ == '__main__':
    main()
