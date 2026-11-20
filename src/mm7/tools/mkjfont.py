"""東雲 BDF（JIS 番号）→ C の表 jfont.h。区点 94×94 を Shift_JIS から引けるように並べる。
1 字は 1 行 16 ビット（左詰め）× 高さ。禁則の表も作る。"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, '..', 'font')

def load_bdf(path, size):
    g = {}
    lines = open(path, encoding='latin1').read().split('\n')
    i = 0
    fbb = None
    while i < len(lines):
        l = lines[i]
        if l.startswith('FONTBOUNDINGBOX'):
            fbb = list(map(int, l.split()[1:]))
        if l.startswith('STARTCHAR'):
            enc = None; bbx = None; bm = []
            while not lines[i].startswith('ENDCHAR'):
                t = lines[i]
                if t.startswith('ENCODING'): enc = int(t.split()[1])
                elif t.startswith('BBX'): bbx = list(map(int, t.split()[1:]))
                elif t.startswith('BITMAP'):
                    i += 1
                    while not lines[i].startswith('ENDCHAR'):
                        bm.append(int(lines[i], 16)); i += 1
                    break
                i += 1
            w, h, ox, oy = bbx
            nbits = ((w + 7) // 8) * 8
            rows = [0] * size
            # 字の枠の下端 = fbb の oy（例 -2）。上からの位置に直す
            top = (fbb[1] + fbb[3]) - (h + oy)
            for r, v in enumerate(bm):
                y = top + r
                if 0 <= y < size:
                    rows[y] = (v << (16 - nbits)) >> ox & 0xFFFF if ox >= 0 else (v << (16 - nbits)) & 0xFFFF
            g[enc] = rows
        i += 1
    return g

def emit(name, g, size, out):
    out.append(f'static const unsigned short {name}[94*94][{size}] = {{')
    n = 0
    for ku in range(94):
        for ten in range(94):
            code = ((ku + 0x21) << 8) | (ten + 0x21)
            rows = g.get(code)
            if rows: n += 1
            out.append('{' + ','.join(str(x) for x in (rows or [0]*size)) + '},')
    out.append('};')
    return n

def sjis_list(s):
    r = []
    for ch in s:
        b = ch.encode('cp932')
        if len(b) == 2: r.append(b[0] << 8 | b[1])
    return r

NOSTART = '、。，．・：；？！゛゜ヽヾゝゞ々ー）］｝」』〉》】〕’”…‥ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ〜～'
NOEND = '（［｛「『〈《【〔‘“'

def main():
    out = ['/* mkjfont.py で作った。東雲フォント 0.9.11p1（パブリックドメイン）から */']
    for size in (12, 14, 16):
        g = load_bdf(os.path.join(FONT, f'shnmk{size}.bdf'), size)
        n = emit(f'jf{size}', g, size, out)
        print(size, n, 'glyphs')
    out.append('static const unsigned short nostart[] = {' + ','.join(map(str, sjis_list(NOSTART))) + ',0};')
    out.append('static const unsigned short noend[] = {' + ','.join(map(str, sjis_list(NOEND))) + ',0};')
    open(os.path.join(HERE, '..', 'dll', 'jfont.h'), 'w').write('\n'.join(out) + '\n')

if __name__ == '__main__':
    main()
