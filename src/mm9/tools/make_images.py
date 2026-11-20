# -*- coding: utf-8 -*-
"""LOCALART の画像の英語を日本語にする。

文字の形（消す所）は、同じ場所の別の版（背景・選べない状態・光るアニメの各コマ）の差から取り、
OpenCV で塗り直してから、日本語を似た装飾（金銅色＋暗い縁取り）で描く。
出力: build/jpdata/localart/...（data\\localart\\... に置くと元の画像より優先される）
python tools/make_images.py [menu] [preview]
"""
import os
import sys
import math
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'extract', 'LOCALART', 'LOCALART')
OUT = os.path.join(ROOT, 'build', 'jpdata', 'localart')
VIEW = os.path.join(ROOT, 'view', 'img')
FONT = 'C:/Windows/Fonts/NotoSerifJP-VF.ttf'


def font(size, weight=b'Bold'):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(weight)
    return f


def load(rel):
    return Image.open(os.path.join(SRC, *rel.split('/'))).convert('RGB')


def save(img, rel, preview=True):
    """元の PCX と同じパレット・同じ書式で保存する（変えていない画素は元のまま。
    こうすると元のファイルとの差分が小さくなり、配布物に元の絵が入らない）"""
    dst = os.path.join(OUT, *rel.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    srcpath = os.path.join(SRC, *rel.split('/'))
    orig = Image.open(srcpath)
    rgb = img.convert('RGB')
    if orig.mode == 'P':
        pal = np.array(orig.getpalette()[:768], dtype=np.int32).reshape(-1, 3)
        idx = np.asarray(orig).copy()
        o_rgb = pal[idx]
        n_rgb = np.asarray(rgb).astype(np.int32)
        ch = np.any(o_rgb != n_rgb, axis=2)
        if ch.any():
            px = n_rgb[ch]
            # 透明色（パレット 0 と同じ色）以外で近い色を選ぶ
            d = ((px[:, None, :] - pal[None, :, :]) ** 2).sum(2)
            idx[ch] = d.argmin(1)
        out = Image.fromarray(idx.astype(np.uint8), 'P')
        out.putpalette(orig.getpalette())
    else:
        out = rgb
    import io
    b = io.BytesIO()
    out.save(b, format='PCX')
    data = bytearray(b.getvalue())
    head = open(srcpath, 'rb').read(128)
    data[:128] = head  # 見出し（解像度の欄など）は元のまま
    open(dst, 'wb').write(bytes(data))
    if preview:
        os.makedirs(VIEW, exist_ok=True)
        out.convert('RGB').save(os.path.join(VIEW, os.path.basename(rel).replace('.PCX', '.png')))


def diff_mask(a, b, th=40):
    d = np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16)).sum(axis=2)
    return (d > th).astype(np.uint8) * 255


def inpaint(img, mask, grow=2, radius=5):
    m = cv2.dilate(mask, np.ones((3, 3), np.uint8), iterations=grow)
    arr = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    out = cv2.inpaint(arr, m, radius, cv2.INPAINT_TELEA)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def redo_frame(orig_frame, bg_crop, under, lab, th=45):
    """アニメの1コマ: 元のコマの、背景と大きく違う所（英字とその光）だけを塗り直して日本語を載せる。
    ほかの画素は元のコマのまま"""
    o = np.asarray(orig_frame).astype(int)
    b = np.asarray(bg_crop).astype(int)
    m = (np.abs(o - b).sum(2) > th).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=2)
    # 塗り直す所は、文字を消した背景（under）の色に、元のコマとの明るさの差を足して近づける
    u = np.asarray(under).astype(int)
    out = o.copy()
    out[m > 0] = u[m > 0]
    img = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    img = Image.fromarray(cv2.cvtColor(cv2.inpaint(cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR),
                                                   (cv2.dilate(m, np.ones((3, 3), np.uint8)) - m) * 255, 2, cv2.INPAINT_TELEA), cv2.COLOR_BGR2RGB))
    return paste(img, lab, (0, 0))


def keep_outside(orig_frame, new_frame, bg_crop, th=12):
    """新しいコマのうち、元のコマが背景と同じ所（文字の光の外）は元のコマの画素に戻す。
    こうすると差分が文字の周りだけになる"""
    o = np.asarray(orig_frame).astype(int)
    b = np.asarray(bg_crop).astype(int)
    n = np.asarray(new_frame).astype(int)
    same_bg = np.abs(o - b).sum(2) <= th
    unchanged_new = np.abs(n - b).sum(2) <= th
    keep = same_bg & unchanged_new
    out = n.copy()
    out[keep] = o[keep]
    return Image.fromarray(out.astype(np.uint8))


def label(size, lines, fsize, glow=0.0, faded=False, align='center', top=None):
    """透明な画像に装飾した文字を描く（RGBA）"""
    W, H = size
    f = font(fsize)
    spacing = int(fsize * 0.05)
    boxes = [f.getbbox(t) for t in lines]
    lh = [b[3] - b[1] for b in boxes]
    total = sum(lh) + spacing * (len(lines) - 1)
    y = (H - total) // 2 if top is None else top
    # 文字の形（白黒）
    mask = Image.new('L', size, 0)
    d = ImageDraw.Draw(mask)
    pos = []
    for t, b, h in zip(lines, boxes, lh):
        w = b[2] - b[0]
        x = (W - w) // 2 if align == 'center' else 4
        d.text((x - b[0], y - b[1]), t, font=f, fill=255)
        pos.append((x, y, w, h))
        y += h + spacing
    # 塗り: 上が明るい金、下が銅
    grad = Image.new('RGB', size)
    gp = grad.load()
    ys = [p[1] for p in pos]
    for yy in range(H):
        # 行ごとのグラデーション
        t = 0.5
        for (x0, y0, w0, h0) in pos:
            if y0 - 2 <= yy <= y0 + h0 + 2:
                t = (yy - y0) / max(1, h0)
        t = min(1, max(0, t))
        c = (int(250 - 70 * t), int(222 - 110 * t), int(150 - 105 * t))
        for xx in range(W):
            gp[xx, yy] = c
    out = Image.new('RGBA', size, (0, 0, 0, 0))
    # 光（アニメのコマ）
    if glow > 0:
        g = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(6))
        g = g.point(lambda v: int(min(255, v * 1.6 * glow)))
        out = Image.composite(Image.new('RGBA', size, (255, 240, 190, 255)), out, g)
    # 影と縁
    sh = mask.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    shadow = Image.new('RGBA', size, (40, 20, 5, 255))
    out = Image.composite(shadow, out, sh.point(lambda v: int(v * 0.9)))
    edge = mask.filter(ImageFilter.MaxFilter(3))
    out = Image.composite(Image.new('RGBA', size, (70, 35, 10, 255)), out, edge)
    fill = grad.convert('RGBA')
    out = Image.composite(fill, out, mask)
    if faded:
        a = out.getchannel('A').point(lambda v: int(v * 0.45))
        out.putalpha(a)
    return out


def paste(bg, lab, xy):
    bg = bg.convert('RGBA')
    bg.alpha_composite(lab, xy)
    return bg.convert('RGB')


MAIN = [  # (ファイル, 位置, 日本語の行)
    ('STARTGAMEANIM.PCX', (36, 30), ['冒険を', '始める']),
    ('LOADGAMEANIM.PCX', (36, 142), ['続きから']),
    ('OPTIONSBUTTON.PCX', (36, 252), ['設定']),
    ('VIEWINTROBUTTON.PCX', (36, 362), ['序章を', '見る']),
    ('CREDITSBUTTON.PCX', (36, 472), ['制作者']),
    ('QUITBUTTON.PCX', (554, 449), ['終了']),
]
PAUSE = [
    ('PAUSEMENUSAVE.PCX', (36, 50), ['記録する']),
    ('PAUSEMENULOAD.PCX', (36, 186), ['読み込む']),
    ('PAUSEMENUOPTIONS.PCX', (36, 300), ['設定']),
    ('PAUSEMENUMAINMENU.PCX', (36, 426), ['メイン', 'メニュー']),
    ('PAUSEMENURESUMEGAME.PCX', (554, 454), ['ゲームに', '戻る']),
]


def menu(folder, bgname, inactname, items):
    base = 'INTERFACESCREENS/%s/' % folder
    bg = load(base + bgname)
    inact = load(base + inactname)
    W, H = 209, 100
    # 消す所（文字の形）:
    #  左の列: 選べない状態 ≒ 背景を一様に淡くしたもの、なので一次式で当てはめて外れる所 ＝ 文字（両方の画像の文字）
    #  それを、アニメの各コマと背景の差（光の範囲）の中に限る。右（終了など）は橙色の所に限る
    bga = np.asarray(bg, dtype=np.float32)
    ina = np.asarray(inact, dtype=np.float32)
    left = bga[:, :250]
    X = np.concatenate([left.reshape(-1, 3), np.ones((left.shape[0] * left.shape[1], 1))], 1)
    res = np.zeros(left.shape[:2])
    for c in range(3):
        coef = np.linalg.lstsq(X, ina[..., c].reshape(-1), rcond=None)[0]
        res += np.abs((X @ coef).reshape(left.shape[:2]) - ina[..., c])
    letters = np.zeros((600, 800), bool)
    letters[:, :250] = res > 45
    orange = (bga[..., 0] - bga[..., 2]) > 40
    blob = np.zeros((600, 800), np.uint8)
    anims = {}
    for fn, (x, y), _ in items:
        a = load(base + fn)
        anims[fn] = a
        for k in range(10):
            fr = a.crop((k * W, 0, (k + 1) * W, H))
            blob[y:y + H, x:x + W] |= diff_mask(bg.crop((x, y, x + W, y + H)), fr, 60)
    blob = cv2.dilate(blob, np.ones((5, 5), np.uint8), iterations=2) > 0
    big = cv2.dilate(blob.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=6) > 0
    sel = (big & letters) | (blob & (letters | (~np.zeros_like(letters) & orange & (np.arange(800)[None, :] >= 250))))
    sel = sel & (letters | (np.arange(800)[None, :] >= 250))
    mask = sel.astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    clean = inpaint(bg, mask)
    mask_in = ((letters & big)[:, :250]).astype(np.uint8) * 255
    mask_in = cv2.morphologyEx(mask_in, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    clean_inact = inpaint(inact, mask_in)
    newbg = clean.copy()
    newin = clean_inact.copy()
    for fn, (x, y), lines in items:
        fs = 40 if len(lines) == 1 and len(lines[0]) <= 3 else 34
        if max(len(t) for t in lines) >= 4:
            fs = 32
        lab = label((W, H), lines, fs)
        newbg = paste(newbg, lab, (x, y))
        if x < 250:
            newin = paste(newin, label((W, H), lines, fs, faded=True), (x, y))
        # アニメ: 10 コマ、光が強まって弱まる
        frames = Image.new('RGB', (W * 10, H))
        under = clean.crop((x, y, x + W, y + H))
        bgc = bg.crop((x, y, x + W, y + H))
        oa = anims[fn]
        for k in range(10):
            g = 0.35 + 0.65 * math.sin(math.pi * (k + 0.5) / 10)
            fr = redo_frame(oa.crop((k * W, 0, (k + 1) * W, H)), bgc, under, label((W, H), lines, fs, glow=g))
            frames.paste(fr, (k * W, 0))
        save(frames, base + fn)
    save(newbg, base + bgname)
    save(newin, base + inactname)


def header_mask(a):
    r, g, b = a[..., 0].astype(int), a[..., 1].astype(int), a[..., 2].astype(int)
    cream = (r > 150) & (g > 120) & (b > 80) & (r - b > 25)
    blue = (b > r + 10) & (b > 80)
    return cream | blue


def draw_header(img, box, text, size=None, color=(236, 222, 182)):
    """赤い帯の見出し: 字を消して、クリーム色の日本語を真ん中に描く"""
    x, y, w, h = box
    a = np.asarray(img).copy()
    reg = a[y:y + h, x:x + w]
    m = header_mask(reg).astype(np.uint8) * 255
    full = np.zeros(a.shape[:2], np.uint8)
    full[y:y + h, x:x + w] = m
    img = inpaint(img, full, grow=1, radius=3)
    fs = size or 19
    f = font(fs, b'SemiBold')
    while f.getbbox(text)[2] - f.getbbox(text)[0] > w + 20 and fs > 10:
        fs -= 1
        f = font(fs, b'SemiBold')
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    lay = Image.new('L', img.size, 0)
    ImageDraw.Draw(lay).text((x + (w - tw) // 2 - bb[0], y + (h - th) // 2 - bb[1]), text, font=f, fill=255)
    out = img.convert('RGBA')
    sh = lay.filter(ImageFilter.MaxFilter(3))
    out = Image.composite(Image.new('RGBA', img.size, (25, 10, 0, 255)), out, sh)
    out = Image.composite(Image.new('RGBA', img.size, color + (255,)), out, lay)
    return out.convert('RGB')


HEADERS = {
    'INTERFACESCREENS/CHARACTERCREATION/CREATECHARACTERBG.PCX': [
        ((63, 104, 236, 27), '個人情報'), ((366, 103, 171, 38), '初期スキル'), ((146, 313, 112, 29), '能力値')],
    'INTERFACESCREENS/CHARACTERCREATION/CREATE4BG.PCX': [((322, 36, 182, 28), '一行のまとめ')],
    'INTERFACESCREENS/CHARACTERINFO/QUICKREF.PCX': [((322, 36, 182, 28), '一行のまとめ')],
    'INTERFACESCREENS/CHARACTERINFO/CHARACTERINVENTORYBG.PCX': [
        ((121, 103, 118, 30), '持ち物'), ((350, 103, 139, 26), '品物の詳細'), ((300, 274, 74, 29), '防御力', 15)],
    'INTERFACESCREENS/CHARACTERINFO/CHARACTERSKILLSBG.PCX': [
        ((102, 104, 114, 25), '防御'), ((365, 104, 95, 25), '武器'), ((111, 203, 96, 27), '魔法'),
        ((104, 318, 112, 29), '特技'), ((299, 274, 75, 29), '防御力', 15)],
    'INTERFACESCREENS/CHARACTERINFO/CHARACTERSPELLSBG.PCX': [((207, 103, 190, 42), '覚えた呪文')],
    'INTERFACESCREENS/CHARACTERINFO/CHARACTERSTATSBG.PCX': [
        ((103, 102, 112, 28), '能力値'), ((341, 101, 161, 45), '攻撃力'), ((92, 376, 202, 32), '魔法への耐性'),
        ((299, 274, 76, 29), '防御力', 15)],
    'INTERFACESCREENS/MAPSCREENS/MAPBG.PCX': [((263, 102, 154, 33), '地図')],
    'INTERFACESCREENS/MERCHANT/BANKBG.PCX': [((120, 82, 72, 27), '銀行'), ((591, 82, 117, 28), '持ち物')],
    'INTERFACESCREENS/MERCHANT/MERCHANTBG.PCX': [((98, 82, 115, 29), '商人'), ((591, 82, 117, 32), '持ち物')],
    'INTERFACESCREENS/NOTES/NOTESBG.PCX': [((297, 38, 70, 29), 'メモ')],
    'INTERFACESCREENS/TREASURE/TREASURE-BOOK.PCX': [((128, 32, 125, 30), '持ち物')],
}


def headers():
    for rel, items in HEADERS.items():
        img = load(rel)
        for it in items:
            box, text = it[0], it[1]
            img = draw_header(img, box, text, it[2] if len(it) > 2 else None)
        save(img, rel)


OPTIONS = [  # (ファイル, 位置, 高さ, 日本語の行)
    ('OPTIONSGAMEANIM.PCX', (36, 34), 100, ['ゲームの', '設定']),
    ('OPTIONSVIDEOANIM.PCX', (36, 135), 100, ['画面の', '設定']),
    ('OPTIONSSOUNDANIM.PCX', (36, 236), 100, ['音の', '設定']),
    ('OPTIONSCONTROLSANIM.PCX', (36, 337), 100, ['キー操作']),
    ('OPTIONSDONEANIM.PCX', (36, 502), 63, ['完了']),
    ('OPTIONSCANCELANIM.PCX', (36, 438), 63, ['やめる']),
]


def options():
    base = 'INTERFACESCREENS/OPTIONSSCREEN/'
    bg = load(base + 'OPTIONSBG.PCX')
    a = np.asarray(bg).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    copper = (r > 100) & (r - b > 45) & (r - g > 12)
    slate = (b >= r - 5) & (b > 70) & (np.abs(r - g) < 25) & (b - r < 40)
    blob = np.zeros(a.shape[:2], np.uint8)
    W = 209
    for fn, (x, y), H, _ in OPTIONS:
        if fn == 'OPTIONSCANCELANIM.PCX':
            continue  # 背景には描かれていない
        an = np.asarray(load(base + fn)).astype(int)
        for k in range(10):
            d = np.abs(an[:, k * W:(k + 1) * W] - a[y:y + H, x:x + W]).sum(2) > 60
            blob[y:y + H, x:x + W] |= d.astype(np.uint8)
    blob = cv2.dilate(blob, np.ones((5, 5), np.uint8), iterations=3) > 0
    m = (copper | slate) & blob
    m[:, :45] = False
    m[:, 250:] = False
    clean = inpaint(bg, m.astype(np.uint8) * 255, grow=1, radius=4)
    newbg = clean.copy()
    for fn, (x, y), H, lines in OPTIONS:
        fs = 32 if max(len(t) for t in lines) >= 4 else 36
        if H < 100:
            fs = 34
        if fn != 'OPTIONSCANCELANIM.PCX':
            newbg = paste(newbg, label((W, H), lines, fs), (x, y))
        frames = Image.new('RGB', (W * 10, H))
        under = clean.crop((x, y, x + W, y + H))
        bgc = bg.crop((x, y, x + W, y + H))
        oa = load(base + fn)
        for k in range(10):
            gl = 0.35 + 0.65 * math.sin(math.pi * (k + 0.5) / 10)
            fr = redo_frame(oa.crop((k * W, 0, (k + 1) * W, H)), bgc, under, label((W, H), lines, fs, glow=gl))
            frames.paste(fr, (k * W, 0))
        save(frames, base + fn)
    save(newbg, base + 'OPTIONSBG.PCX')


def draw_button(img, box, text, fs, whole=False, fill=(250, 236, 200), edge=(95, 55, 15)):
    """ボタンの字を消して日本語を描く（box の中を塗り直す）"""
    x0, y0, x1, y1 = box
    a = np.asarray(img).astype(np.int16)
    med = cv2.medianBlur(np.asarray(img), 9).astype(np.int16)
    dev = np.abs(a - med).sum(2) > 45
    m = np.zeros(dev.shape, np.uint8)
    m[y0:y1, x0:x1] = 255 if whole else dev[y0:y1, x0:x1] * 255
    m = cv2.dilate(m, np.ones((3, 3), np.uint8), iterations=1)
    img = inpaint(img, m, grow=1, radius=4)
    f = font(fs, b'Bold')
    bb = f.getbbox(text)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    W, H = img.size
    lay = Image.new('L', img.size, 0)
    ImageDraw.Draw(lay).text(((W - tw) // 2 - bb[0], (H - th) // 2 - bb[1]), text, font=f, fill=255)
    out = img.convert('RGBA')
    out = Image.composite(Image.new('RGBA', img.size, edge + (255,)), out, lay.filter(ImageFilter.MaxFilter(3)))
    out = Image.composite(Image.new('RGBA', img.size, fill + (255,)), out, lay)
    return out.convert('RGB')


BUTTONS = [
    # (ファイルの並び, 字の範囲, 日本語, 大きさ)
    (['COMMON/CANCEL BUTTON %s TRANS.PCX' % s for s in ('NORMAL', 'HIGH', 'DOWN')] +
     ['POPUP/POPUPCANCEL-%s.PCX' % s for s in ('NORMAL', 'HIGHLIGHT', 'PRESSED')], (16, 5, 100, 23), 'キャンセル', 15, True),
    (['CHARACTERINFO/CHARACTERSPELLALL-%s.PCX' % s for s in ('NORMAL', 'HIGHLIGHT', 'PRESSED')], (4, 5, 52, 27), '全部', 16),
    (['CHARACTERINFO/CHARACTERSPELLQUICK-%s.PCX' % s for s in ('NORMAL', 'HIGHLIGHT', 'PRESSED')], (4, 5, 108, 27), '即時呪文', 16),
]


def buttons():
    for it in BUTTONS:
        files, box, text, fs = it[:4]
        for fn in files:
            rel = 'INTERFACESCREENS/' + fn
            save(draw_button(load(rel), box, text, fs, len(it) > 4 and it[4]), rel)


def big_text(rel, box, lines, fs, th=50):
    """地図の上の大きな金銅色の字（Loading、Congratulations）を差し替える"""
    img = load(rel)
    a = np.asarray(img).astype(int)
    x0, y0, x1, y1 = box
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    m = ((r > 110) & (r - b > th)).astype(np.uint8)
    sel = np.zeros_like(m)
    sel[y0:y1, x0:x1] = m[y0:y1, x0:x1]
    sel = cv2.dilate(sel, np.ones((3, 3), np.uint8), iterations=2) * 255
    clean = inpaint(img, sel, grow=1, radius=5)
    W, H = x1 - x0, y1 - y0
    out = paste(clean, label((W, H), lines, fs), (x0, y0))
    save(out, rel)


CLASSES = {'ASSASSIN': '暗殺者', 'CRUSADER': '聖戦士', 'DRUID': 'ドルイド', 'FIGHTER': '戦士', 'GLADIATOR': '剣闘士',
           'HEALER': '癒し手', 'INITIATE': '入門者', 'LICH': 'リッチ', 'MAGE': '魔術師', 'MERCENARY': '傭兵',
           'PALADIN': 'パラディン', 'PRIEST': '司祭', 'RANGER': 'レンジャー', 'SCHOLAR': '学者'}


def paperdolls():
    """持ち物の画面の人形絵: 斜めの「The 〜」を消して、クラス名を縦書きで描く"""
    for cls, ja in CLASSES.items():
        for sx in 'MF':
            rel = 'INTERFACESCREENS/CHARACTERINFO/CHARACTERINVENTORYPD-%s%s.PCX' % (cls, sx)
            img = load(rel)
            a = np.asarray(img).astype(int)
            r, g, b = a[..., 0], a[..., 1], a[..., 2]
            brown = (r < 175) & (g < 115) & (b < 60) & (r - g > 25)
            reg = np.zeros(brown.shape, np.uint8)
            reg[28:136, 28:104] = brown[28:136, 28:104]
            # 人物（右から入り込む）に触れる塊は除く
            n, lab, st, _ = cv2.connectedComponentsWithStats(reg)
            keep = np.zeros_like(reg)
            for i in range(1, n):
                x, y, w, h, area = st[i]
                if x + w >= 104 or area < 3:
                    continue
                keep[lab == i] = 255
            keep = cv2.dilate(keep, np.ones((3, 3), np.uint8), iterations=2)
            clean = inpaint(img, keep, grow=0, radius=4)
            # 縦書き
            fs = 17 if len(ja) >= 5 else 19
            f = font(fs, b'Bold')
            lay = Image.new('L', img.size, 0)
            d = ImageDraw.Draw(lay)
            total = len(ja) * (fs + 1)
            y = 42 + max(0, (80 - total) // 2)
            for ch in ja:
                if ch == 'ー':
                    ch = '｜'
                bb = f.getbbox(ch)
                d.text((72 - (bb[2] - bb[0]) // 2 - bb[0], y - bb[1] + (fs - (bb[3] - bb[1])) // 2), ch, font=f, fill=255)
                y += fs + 1
            out = clean.convert('RGBA')
            out = Image.composite(Image.new('RGBA', img.size, (232, 200, 140, 255)), out, lay.filter(ImageFilter.MaxFilter(3)))
            out = Image.composite(Image.new('RGBA', img.size, (110, 45, 5, 255)), out, lay)
            save(out.convert('RGB'), rel)


def main():
    menu('MAINMENU', 'MAINMENUBG.PCX', 'MAINMENUINACTIVE.PCX', MAIN)
    menu('PAUSESCREEN', 'PAUSEMENU2D.PCX', 'PAUSEMENU-INACTIVE.PCX', PAUSE)
    headers()
    options()
    buttons()
    paperdolls()
    big_text('LOADSCREEN/LOADINGBG.PCX', (300, 380, 520, 462), ['読み込み中……'], 32)
    big_text('MISC/WINBG.PCX', (205, 125, 585, 215), ['おめでとう！'], 44, th=35)
    print('作成', OUT)


if __name__ == '__main__':
    main()
