# -*- coding: utf-8 -*-
"""Xeen の絵（SpriteResource の形式）を読む道具。ScummVM の engines/mm/shared/xeen/sprites.cpp の drawSprite を写したもの。

python tools/sprite.py <CC> <ファイル名> <パレットのファイル名> <出力フォルダ>
  → 各コマを PNG（見る用）に書き出す。frame 番号ごとに、背景と前景の 2 つのセルを重ねた 1 枚
"""
import sys, os, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PATTERN_STEPS = [0, 1, 1, 1, 2, 2, 3, 3, 0, -1, -1, -1, -2, -2, -3, -3]


def frames(data):
    count = struct.unpack_from('<H', data, 0)[0]
    return [struct.unpack_from('<HH', data, 2 + i * 4) for i in range(count)]


def draw_cell(data, offset, canvas, w, h, ox=0, oy=0):
    """セルを canvas（w×h の色番号の bytearray、-1 は透明の扱いはしない）に描く。描いた範囲を返す。"""
    p = offset
    xoff, width, yoff, height = struct.unpack_from('<HHHH', data, p)
    p += 8
    y = oy + yoff
    yctr = height
    while yctr > 0:
        ln = data[p]; p += 1
        if ln == 0:
            n = data[p]; p += 1
            y += n + 1
            yctr -= n + 1
            continue
        start = p
        x0 = data[p]; p += 1
        line = {}
        lx = x0
        bc = 1
        while bc < ln:
            op = data[p]; p += 1; bc += 1
            cnt = op & 0x1F
            cmd = (op & 0xE0) >> 5
            if cmd in (0, 1):
                for _ in range(op + 1):
                    line[lx] = data[p]; p += 1; bc += 1; lx += 1
            elif cmd == 2:
                c = data[p]; p += 1; bc += 1
                for _ in range(cnt + 3):
                    line[lx] = c; lx += 1
            elif cmd == 3:
                back = struct.unpack_from('<H', data, p)[0]; p += 2; bc += 2
                q = p - back
                for i in range(cnt + 4):
                    line[lx] = data[q + i]; lx += 1
            elif cmd == 4:
                a, b = data[p], data[p + 1]; p += 2; bc += 2
                for _ in range(cnt + 2):
                    line[lx] = a; lx += 1
                    line[lx] = b; lx += 1
            elif cmd == 5:
                lx += cnt + 1
            else:
                l2 = op & 0x07
                c2 = (op >> 2) & 0x0E
                c = data[p]; p += 1; bc += 1
                for i in range(l2 + 3):
                    line[lx] = c & 0xFF; lx += 1
                    c += PATTERN_STEPS[c2 + (i % 2)]
        assert bc == ln and p == start + ln
        for x, c in line.items():
            xx = ox + xoff + x
            if 0 <= xx < w and 0 <= y < h:
                canvas[y * w + xx] = c
        y += 1
        yctr -= 1
    return xoff, yoff, width, height


def palette(data):
    return [min(255, v * 255 // 63) for v in data[:768]]


def main():
    from PIL import Image
    from cc import CC
    cc_path, name, palname, outdir = sys.argv[1:5]
    cc = CC(cc_path)
    data = cc.get(name)
    pal = palette(cc.get(palname))
    os.makedirs(outdir, exist_ok=True)
    for i, (o1, o2) in enumerate(frames(data)):
        canvas = bytearray(320 * 200)
        r1 = draw_cell(data, o1, canvas, 320, 200)
        if o2:
            draw_cell(data, o2, canvas, 320, 200)
        im = Image.frombytes('P', (320, 200), bytes(canvas))
        im.putpalette(pal)
        im.save(os.path.join(outdir, '%s_%02d.png' % (name.replace('.', '_'), i)))
        print(i, '位置・大きさ', r1, 'セル2' if o2 else '')


if __name__ == '__main__':
    main()
