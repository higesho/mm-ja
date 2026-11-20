"""東雲 BDF（JIS 番号）→ DLL に入れる C の表 src/jfont.h を作る。

区点 94×94 を並べ、1 字は 1 行 16 ビット（左詰め）× 高さ。12・14・16 の 3 種。
字のない区点は全部 0 で、別に「ある字」の表（1 区点 1 ビット）を付ける。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, '..', 'font')
OUT = os.path.join(HERE, '..', 'src', 'jfont.h')
SIZES = [12, 14, 16]


def load_bdf(path, size):
    g = {}
    lines = open(path, encoding='latin1').read().split('\n')
    i = 0
    while i < len(lines):
        l = lines[i]
        if l.startswith('ENCODING'):
            code = int(l.split()[1])
            bbx = None
            while not lines[i].startswith('BBX'):
                i += 1
            bbx = list(map(int, lines[i].split()[1:]))
            while lines[i] != 'BITMAP':
                i += 1
            i += 1
            rows = []
            while lines[i] != 'ENDCHAR':
                rows.append(int(lines[i], 16))
                i += 1
            w, h, ox, oy = bbx
            nb = (w + 7) // 8 * 8
            bm = [0] * size
            # 字の枠の下端 = 基線 - 2（FONTBOUNDINGBOX と同じ）。全部同じ枠なので上から並べる
            top = size - h - (oy + 2)
            for r, v in enumerate(rows):
                y = top + r
                if 0 <= y < size:
                    bm[y] = (v << (16 - nb)) & 0xffff if nb <= 16 else v >> (nb - 16)
            ku, ten = (code >> 8) - 0x20, (code & 0xff) - 0x20
            if 1 <= ku <= 94 and 1 <= ten <= 94:
                g[(ku - 1) * 94 + (ten - 1)] = bm
        i += 1
    return g


def main():
    out = ['/* mkjfont.py が作る。東雲フォント 0.9.11p1（パブリックドメイン） */',
           '#pragma once']
    have = [0] * (94 * 94)
    for s in SIZES:
        g = load_bdf(os.path.join(FONT, f'shnmk{s}.bdf'), s)
        for k in g:
            have[k] = 1
        vals = []
        for k in range(94 * 94):
            vals.extend(g.get(k, [0] * s))
        out.append(f'static const unsigned short jfont{s}[{94 * 94 * s}] = {{')
        for i in range(0, len(vals), 24):
            out.append(','.join(str(v) for v in vals[i:i + 24]) + ',')
        out.append('};')
        print(f'{s}px: {len(g)} 字')
    bits = bytearray((94 * 94 + 7) // 8)
    for k, v in enumerate(have):
        if v:
            bits[k >> 3] |= 1 << (k & 7)
    out.append(f'static const unsigned char jfont_have[{len(bits)}] = {{')
    for i in range(0, len(bits), 32):
        out.append(','.join(str(v) for v in bits[i:i + 32]) + ',')
    out.append('};')
    open(OUT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')


if __name__ == '__main__':
    main()
