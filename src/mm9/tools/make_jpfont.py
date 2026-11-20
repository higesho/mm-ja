# -*- coding: utf-8 -*-
"""日本語の字の表（アトラス）と符号表を作る。

符号: 1バイト目 0x80〜0xBF、2バイト目 0xC0〜0xFF。番号 i → (0x80 + i//64, 0xC0 + i%64)
字の順: JIS X 0208 の 1〜8 区（記号・英数・かな・ギリシア・キリル）、16〜47 区（第1水準）、
        その後に translation/extra_chars.txt の字（第2水準など、訳に出てくるもの）

出力:
  build/charmap.tsv                    字<TAB>符号（16進4桁）
  build/jpdata/art/fonts/jp/*.pcx      各フォントの字の表（64 列）
  build/jpdata/art/fonts/jp/jpfont.txt DLL が読む設定
  build/jpdata/art/fonts/jp/charmap.bin 番号→UTF-16（4096×2 バイト。GDI 経路用）

python tools/make_jpfont.py [preview]
"""
import os
import sys
from PIL import Image

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FONTDIR = os.path.join(ROOT, 'font')
OUT = os.path.join(ROOT, 'build', 'jpdata', 'art', 'fonts', 'jp')
KEY = (0, 255, 255)
COLS = 64
MAXCH = 4096

# ゲームのフォント（128 の名）: 行の高さ, 東雲の大きさ, 塗り, 縁（None = なし）, 送り幅, 上の余白
FONTS = [
    # name,              H,  bdf, fill,            outline,          W,  top
    ('MAINTEXTE128',     18, 14, (56, 26, 5),      None,             15, 2),
    ('MAINTEXTGREEN128', 18, 14, (0, 56, 0),       None,             15, 2),
    ('MAINTEXTRED128',   18, 14, (108, 0, 3),      None,             15, 2),
    ('MAINTEXTSPECIAL128', 18, 14, (0, 39, 92),    None,             15, 2),
    ('MAINTEXTLIGHT128', 18, 14, (244, 222, 181),  (71, 50, 30),     16, 1),
    ('MAINTEXTD128',     15, 12, (56, 26, 5),      (219, 197, 149),  14, 0),
    ('SMALLFONT128',     15, 12, (56, 26, 5),      None,             13, 2),
    ('SMALLFONTGREEN128', 15, 12, (0, 56, 0),      None,             13, 2),
    ('SMALLFONTRED128',  15, 12, (108, 0, 3),      None,             13, 2),
    ('SMALLFONTSPECIAL128', 15, 12, (120, 184, 230), None,           13, 2),
    ('SMALLFONTTAN128',  15, 12, (244, 222, 181),  (105, 80, 53),    14, 0),
    ('RUDEFONT',         15, 12, (56, 26, 5),      None,             13, 2),
    ('RUDERED',          15, 12, (137, 10, 10),    None,             13, 2),
    ('A8PTFONT',         13, 12, (255, 255, 255),  (0, 0, 0),        13, 0),
    ('A9PTFONT',         13, 12, (255, 255, 255),  (0, 0, 0),        13, 0),
    ('A10PTFONT',        16, 12, (255, 255, 255),  (0, 0, 0),        14, 1),
    ('A12PTFONT',        16, 12, (255, 255, 255),  (0, 0, 0),        14, 1),
    ('A14PTFONT',        20, 16, (255, 255, 255),  (0, 0, 0),        18, 1),
    ('A18PTFONT',        24, 16, (255, 255, 255),  (0, 0, 0),        18, 3),
]


def read_bdf(path):
    """JIS 番号 → (幅, 高さ, 行のリスト[int])"""
    glyphs = {}
    enc = None
    bbx = None
    rows = None
    for line in open(path, encoding='latin-1'):
        line = line.strip()
        if line.startswith('ENCODING'):
            enc = int(line.split()[1])
        elif line.startswith('BBX'):
            bbx = [int(v) for v in line.split()[1:]]
        elif line == 'BITMAP':
            rows = []
        elif line == 'ENDCHAR':
            if enc is not None and rows is not None:
                glyphs[enc] = (bbx[0], bbx[1], rows)
            enc, rows = None, None
        elif rows is not None:
            rows.append(int(line, 16) << (0 if len(line) * 4 >= bbx[0] else 0))
            rows[-1] = (rows[-1], len(line) * 4)
    return glyphs


def jis_to_char(code):
    b = bytes([(code >> 8) | 0x80, (code & 0xFF) | 0x80])
    try:
        return b.decode('euc_jp')
    except UnicodeDecodeError:
        return None


def char_to_jis(ch):
    try:
        b = ch.encode('euc_jp')
    except UnicodeEncodeError:
        return None
    if len(b) != 2:
        return None
    return ((b[0] & 0x7F) << 8) | (b[1] & 0x7F)


def build_charset(base_glyphs):
    chars = []
    for ku in list(range(1, 9)) + list(range(16, 48)):
        for ten in range(1, 95):
            code = ((ku + 0x20) << 8) | (ten + 0x20)
            if code in base_glyphs:
                ch = jis_to_char(code)
                if ch and ch not in chars:
                    chars.append(ch)
    extra = os.path.join(ROOT, 'translation', 'extra_chars.txt')
    if os.path.exists(extra):
        for ch in open(extra, encoding='utf-8').read():
            if ch.strip() and ch not in chars and ord(ch) >= 0x80:
                chars.append(ch)
    if len(chars) > MAXCH:
        sys.exit('字が多すぎる: %d' % len(chars))
    return chars


def code_of(i):
    return (0x80 + i // COLS) << 8 | (0xC0 + i % COLS)


def glyph_mask(glyphs, ch):
    """字の点の集合（左上原点）と大きさ"""
    j = char_to_jis(ch)
    if j is None or j not in glyphs:
        return None
    w, h, rows = glyphs[j]
    pts = set()
    for y, (v, bits) in enumerate(rows):
        for x in range(w):
            if v & (1 << (bits - 1 - x)):
                pts.add((x, y))
    return w, h, pts


def render_font(spec, chars, bdfs):
    name, H, size, fill, outline, W, top = spec
    glyphs = bdfs[size]
    nrows = (len(chars) + COLS - 1) // COLS
    im = Image.new('RGB', (COLS * W, nrows * H), KEY)
    px = im.load()
    off = 1 if outline else 0
    for i, ch in enumerate(chars):
        g = glyph_mask(glyphs, ch)
        if not g:
            continue
        gw, gh, pts = g
        ox = (i % COLS) * W + off
        oy = (i // COLS) * H + top + off
        if outline:
            for (x, y) in pts:
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if (x + dx, y + dy) not in pts:
                            X, Y = ox + x + dx, oy + y + dy
                            if (i // COLS) * H <= Y < (i // COLS + 1) * H and (i % COLS) * W <= X < (i % COLS + 1) * W:
                                px[X, Y] = outline
        for (x, y) in pts:
            X, Y = ox + x, oy + y
            if Y < (i // COLS + 1) * H and X < (i % COLS + 1) * W:
                px[X, Y] = fill
    return im


def to_pcx(im, path):
    # 8 ビットのパレット形式で保存（透明色はパレット 0）
    colors = sorted(set(im.getdata()), key=lambda c: (c != KEY, c))
    pal = []
    for c in colors:
        pal += list(c)
    pal += [0] * (768 - len(pal))
    p = Image.new('P', im.size)
    p.putpalette(pal)
    idx = {c: i for i, c in enumerate(colors)}
    p.putdata([idx[c] for c in im.getdata()])
    p.save(path, format='PCX')


def main():
    os.makedirs(OUT, exist_ok=True)
    bdfs = {s: read_bdf(os.path.join(FONTDIR, 'shnmk%d.bdf' % s)) for s in (12, 14, 16)}
    chars = build_charset(bdfs[14])
    print('字の数', len(chars))
    with open(os.path.join(ROOT, 'build', 'charmap.tsv'), 'w', encoding='utf-8') as f:
        for i, ch in enumerate(chars):
            f.write('%s\t%04X\n' % (ch, code_of(i)))
    cm = bytearray(MAXCH * 2)
    for i, ch in enumerate(chars):
        cm[i * 2:i * 2 + 2] = ord(ch).to_bytes(2, 'little')
    open(os.path.join(OUT, 'charmap.bin'), 'wb').write(cm)
    cfg = ['# name width atlas']
    for spec in FONTS:
        im = render_font(spec, chars, bdfs)
        fn = spec[0].lower() + '.pcx'
        to_pcx(im, os.path.join(OUT, fn))
        cfg.append('%s %d %s' % (spec[0], spec[5], fn))
        if 'preview' in sys.argv:
            im.crop((0, 0, COLS * spec[5], spec[1] * 4)).save(os.path.join(ROOT, 'view', 'jp_' + fn.replace('.pcx', '.png')))
    open(os.path.join(OUT, 'jpfont.txt'), 'w').write('\n'.join(cfg) + '\n')
    print('作成', OUT)


if __name__ == '__main__':
    main()
