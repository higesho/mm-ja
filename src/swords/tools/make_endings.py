# -*- coding: utf-8 -*-
"""全滅の画面（lose.int）とクリアの画面（win.int）の絵に描かれた英文を、日本語に描き替える。

python -I tools/make_endings.py
  → build/ja/gfx/<lose.int|win.int>/image00.bmp・image01.bmp（左右の半分、160×200、8 ビット、色は scr.pal）
     ScummVM は SpriteResource を読むとき gfx/<ファイル名>/imageNN.bmp があればそのコマの代わりに使う
     （build_ja.py が xeen_ja.dat に入れる）。確かめる用に test/sprites/<名前>_ja.png も書く

英文の字（色番号 240〜254 と、その下の影 186・31）を消して周りの色で埋め、
PixelMplus12 Bold で、原作と同じ作り（上が黄色・下へ橙、下に 2 段の影）の字を描く。
"""
import os, sys
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cc import CC
import sprite

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
GAME_CC = os.path.join(ROOT, '..', 'SWRD.CC')
FONT = os.path.join(ROOT, '..', '..', 'Ultima 8', 'jp_work', 'font', 'PixelMplus-20130602',
                    'PixelMplus-20130602', 'PixelMplus12-Bold.ttf')
OUT = os.path.join(ROOT, 'build', 'ja', 'gfx')

# 絵ごとの訳（行ごと）
TEXTS = {
    'lose.int': ['そなたらの敗北により、闇がハヴェックを覆う。',
                 'やがてジーン全土も闇に沈み、希望は永遠に消え去る。'],
    'win.int': ['ハヴェックは解放された。正しく治めるがよい。',
                'ハヴェックの領主たちに栄光あれ！'],
}
TEXT_COLORS = set(range(240, 255))
SHADOW = (186, 31)                       # 字の 1 段下・2 段下の影
# 字の上から下への色（原作の字の行ごとの色にならう）
GRADIENT = [245, 245, 246, 246, 246, 247, 247, 248, 248, 249, 250, 251, 251]


def load(name, cc, pal):
    data = cc.get(name)
    canvas = bytearray(320 * 200)
    for i, (o1, o2) in enumerate(sprite.frames(data)):
        half = bytearray(160 * 200)
        sprite.draw_cell(data, o1, half, 160, 200)
        if o2:
            sprite.draw_cell(data, o2, half, 160, 200)
        for y in range(200):
            canvas[y * 320 + i * 160:y * 320 + i * 160 + 160] = half[y * 160:y * 160 + 160]
    return np.frombuffer(bytes(canvas), dtype=np.uint8).reshape(200, 320).copy()


def text_lines(idx):
    """英文の各行の上端と下端（字の色がある行のまとまり）。"""
    # 英文は絵の下の方だけ（全滅の画面の髑髏の光も同じ色なので、上は見ない）
    rows = [y for y in range(120, 200) if np.isin(idx[y], list(TEXT_COLORS)).sum() >= 3]
    groups = []
    for y in rows:
        if groups and y <= groups[-1][1] + 2:
            groups[-1][1] = y
        else:
            groups.append([y, y])
    return groups


def erase(idx, pal_rgb, top):
    text = np.isin(idx, list(TEXT_COLORS))
    text[:top] = False
    # 影: 字の 1〜3 段下にある 186・31
    shadow = np.zeros_like(text)
    for dy in (1, 2, 3):
        below = np.zeros_like(text)
        below[dy:] = text[:-dy]
        shadow |= below & np.isin(idx, SHADOW)
    mask = (text | shadow).astype(np.uint8)
    mask = cv2.dilate(mask, np.ones((3, 3), np.uint8))
    rgb = pal_rgb[idx]
    filled = cv2.inpaint(rgb, mask * 255, 3, cv2.INPAINT_TELEA)
    # 埋めた所を、絵の中で字以外に使われている色の中から一番近い色に戻す
    used = sorted(set(np.unique(idx[mask == 0]).tolist()) - TEXT_COLORS)
    cand = pal_rgb[used].astype(np.int32)
    out = idx.copy()
    ys, xs = np.nonzero(mask)
    for y, x in zip(ys, xs):
        d = ((cand - filled[y, x].astype(np.int32)) ** 2).sum(1)
        out[y, x] = used[int(d.argmin())]
    return out


def draw_text(idx, lines, tops, font):
    for line, top in zip(lines, tops):
        w = int(font.getlength(line))
        im = Image.new('1', (w + 4, 20), 0)
        ImageDraw.Draw(im).text((0, 0), line, font=font, fill=1)
        g = np.array(im, dtype=bool)
        ys = np.nonzero(g.any(1))[0]
        g = g[ys[0]:ys[-1] + 1]
        h = g.shape[0]
        x0 = (320 - w) // 2
        # 影（1 段下と 2 段下）
        for dy, c in ((2, SHADOW[1]), (1, SHADOW[0])):
            for y, x in zip(*np.nonzero(g)):
                yy, xx = top + y + dy, x0 + x
                if 0 <= yy < 200 and 0 <= xx < 320:
                    idx[yy, xx] = c
        for y, x in zip(*np.nonzero(g)):
            yy, xx = top + y, x0 + x
            if 0 <= yy < 200 and 0 <= xx < 320:
                idx[yy, xx] = GRADIENT[min(len(GRADIENT) - 1, y * len(GRADIENT) // h)]
    return idx


def main():
    cc = CC(GAME_CC)
    pal = sprite.palette(cc.get('scr.pal'))
    pal_rgb = np.array(pal, dtype=np.uint8).reshape(256, 3)
    font = ImageFont.truetype(FONT, 12)
    for name, lines in TEXTS.items():
        idx = load(name, cc, pal)
        groups = text_lines(idx)
        assert len(groups) == len(lines), (name, groups)
        idx = erase(idx, pal_rgb, groups[0][0] - 2)
        # 原作の各行の上端にそろえて描く（字の高さは原作とほぼ同じ 11〜12 ドット）
        idx = draw_text(idx, lines, [g[0] for g in groups], font)
        d = os.path.join(OUT, name)
        os.makedirs(d, exist_ok=True)
        for i in range(2):
            im = Image.fromarray(idx[:, i * 160:i * 160 + 160].copy(), 'P')
            im.putpalette(pal)
            im.save(os.path.join(d, 'image%02d.bmp' % i))
        full = Image.fromarray(idx, 'P')
        full.putpalette(pal)
        os.makedirs(os.path.join(ROOT, 'test', 'sprites'), exist_ok=True)
        full.convert('RGB').resize((960, 600), Image.NEAREST).save(
            os.path.join(ROOT, 'test', 'sprites', name.replace('.', '_') + '_ja.png'))
        print(name, '英文の行', groups, '→', d)


main()
