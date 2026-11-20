# -*- coding: utf-8 -*-
"""美咲ゴシック（BDF、Unicode）から ScummVM の日本語表示用の font_ja.bin を作る。

font_ja.bin: JIS X 0208 の 94 区 × 94 点、1 字 8 バイト（1 行 1 バイト、上位ビットが左）。
字の位置は Shift-JIS の符号から区点を出して引く（engines/mm/xeen/font.cpp の sjisToCell）。

python tools/build_font.py <BDF> <出力>
"""
import sys


def load_bdf(path):
    glyphs = {}
    asc = 7
    cur = None
    bitmap = None
    for line in open(path, encoding='latin-1'):
        w = line.split()
        if not w:
            continue
        if w[0] == 'FONT_ASCENT':
            asc = int(w[1])
        elif w[0] == 'ENCODING':
            cur = {'enc': int(w[1])}
        elif w[0] == 'BBX' and cur is not None:
            cur['bbx'] = tuple(int(x) for x in w[1:5])
        elif w[0] == 'BITMAP':
            bitmap = []
        elif w[0] == 'ENDCHAR':
            cur['rows'] = bitmap
            glyphs[cur['enc']] = cur
            cur = None
            bitmap = None
        elif bitmap is not None:
            bitmap.append(int(w[0], 16))
    return glyphs, asc


def cell_rows(g, asc):
    """8×8 の行（上位ビットが左）にする。基線は上から asc 行目。"""
    bw, bh, bx, by = g['bbx']
    out = [0] * 8
    top = asc - (by + bh)
    nbytes = (bw + 7) // 8
    for i, v in enumerate(g['rows']):
        y = top + i
        if 0 <= y < 8:
            # 行の値は左詰め（nbytes バイト）
            bits = v >> (nbytes * 8 - 8) if nbytes > 1 else v
            out[y] = (bits >> bx) & 0xFF if bx >= 0 else (bits << -bx) & 0xFF
    return out


def main():
    bdf, outp = sys.argv[1], sys.argv[2]
    glyphs, asc = load_bdf(bdf)
    data = bytearray(94 * 94 * 8)
    have = 0
    top_used = [0] * 8
    for row in range(94):
        for col in range(94):
            # 区点 → Shift-JIS
            ku, ten = row + 1, col + 1
            hi = (ku + 1) // 2 + (0x80 if ku <= 62 else 0xC0)
            if ku % 2:
                lo = ten + 0x3F + (1 if ten >= 64 else 0)
            else:
                lo = ten + 0x9E
            try:
                ch = bytes([hi, lo]).decode('cp932')
            except UnicodeDecodeError:
                continue
            g = glyphs.get(ord(ch))
            if not g:
                continue
            rows = cell_rows(g, asc)
            for y in range(8):
                if rows[y]:
                    top_used[y] += 1
            data[(row * 94 + col) * 8:(row * 94 + col) * 8 + 8] = bytes(rows)
            have += 1
    open(outp, 'wb').write(data)
    print('字の数', have, '行ごとの使用', top_used)


if __name__ == '__main__':
    main()
