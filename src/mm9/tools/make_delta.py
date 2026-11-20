# -*- coding: utf-8 -*-
"""ゲームの REZ の中のファイルから、日本語化したファイル（build/jpdata）を作るための差分データを作る。

差分は「元のファイルの○バイト目から△バイト写す」（COPY）と「新しいバイト列を足す」（INSERT）の並び。
INSERT に入るのは訳・書き換えた画素・自作の字の表だけで、元のゲームのデータはほとんど入らない。

形式（リトルエンディアン）:
  "MM9JPDL1"  u32 ファイル数
  ファイルごと:
    u16+出力の相対パス（data\\ から、UTF-8）  u16+REZ の名（例 DATA.REZ。元が無いときは空）  u16+REZ の中の道筋
    u32 元の大きさ  u32 元の CRC32  u32 出力の大きさ  u32 出力の CRC32  u32 命令の数
    命令: u8 0 = COPY u32 位置 u32 長さ / u8 1 = INSERT u32 長さ バイト列
頭に "MM9JPDL1" を付けて書く（配布の zip で圧縮される）。

python tools/make_delta.py <出力 .dlt>
"""
import os
import sys
import struct
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rez

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
JP = os.path.join(ROOT, 'build', 'jpdata')
DATA = os.path.join(ROOT, '..', 'data')
K = 8

REZS = ['DATA.REZ', 'RUDE.REZ', 'SCRIPTS.REZ', 'LOCALART.REZ', 'ART.REZ']


def rez_index():
    idx = {}
    for r in REZS:
        fn = os.path.join(DATA, r)
        for e in rez.entries(fn):
            idx[rez.full(e).upper()] = (r, e)
    return idx


def read_entry(r, e):
    with open(os.path.join(DATA, r), 'rb') as f:
        f.seek(e['pos'])
        return f.read(e['size'])


def diff(src, dst):
    index = {}
    for i in range(0, len(src) - K + 1):
        index.setdefault(src[i:i + K], i)
    ops = []
    lit = bytearray()
    j, n, last = 0, len(dst), 0
    while j < n:
        best = None
        if j + K <= n:
            for cand in (last, index.get(dst[j:j + K])):
                if cand is None or cand + K > len(src) or src[cand:cand + K] != dst[j:j + K]:
                    continue
                L = K
                while j + L < n and cand + L < len(src) and src[cand + L] == dst[j + L]:
                    L += 1
                if best is None or L > best[1]:
                    best = (cand, L)
        if best:
            if lit:
                ops.append((1, bytes(lit)))
                lit = bytearray()
            ops.append((0, best[0], best[1]))
            j += best[1]
            last = best[0] + best[1]
        else:
            lit.append(dst[j])
            j += 1
    if lit:
        ops.append((1, bytes(lit)))
    return ops


def apply(src, ops):
    out = bytearray()
    for op in ops:
        out += src[op[1]:op[1] + op[2]] if op[0] == 0 else op[1]
    return bytes(out)


def s16(s):
    b = s.encode('utf-8')
    return struct.pack('<H', len(b)) + b


def main():
    outpath = sys.argv[1]
    idx = rez_index()
    files = []
    for dirpath, _, names in os.walk(JP):
        for nm in names:
            p = os.path.join(dirpath, nm)
            files.append(os.path.relpath(p, JP).replace('\\', '/'))
    files.sort()
    buf = bytearray(struct.pack('<I', len(files)))
    tot_lit = tot_cp = 0
    for rel in files:
        dst = open(os.path.join(JP, rel), 'rb').read()
        top = rel.split('/')[0].upper()
        key = rel.upper()
        if top == 'LOCALART' or top == 'ART':
            key = rel.upper()
        srcs = []
        if key in idx:
            srcs.append(idx[key])
        # メニューの光るアニメは背景の絵から作り直しているので、背景も元に含める
        for folder, bg in (('/MAINMENU/', 'MAINMENUBG.PCX'), ('/PAUSESCREEN/', 'PAUSEMENU2D.PCX'), ('/OPTIONSSCREEN/', 'OPTIONSBG.PCX')):
            if folder in key and 'ANIM' in key or (folder in key and key.endswith('BUTTON.PCX')):
                k2 = 'LOCALART/INTERFACESCREENS' + folder + bg
                if k2 in idx:
                    srcs.append(idx[k2])
        src = b''.join(read_entry(r, e) for r, e in srcs)
        ops = diff(src, dst) if src else [(1, dst)]
        assert apply(src, ops) == dst
        lit = sum(len(o[1]) for o in ops if o[0] == 1)
        tot_lit += lit
        tot_cp += len(dst) - lit
        buf += s16(rel) + struct.pack('<B', len(srcs))
        for r, e in srcs:
            buf += s16(r) + s16(rez.full(e))
        buf += struct.pack('<IIIII', len(src), zlib.crc32(src), len(dst), zlib.crc32(dst), len(ops))
        for op in ops:
            if op[0] == 0:
                buf += struct.pack('<BII', 0, op[1], op[2])
            else:
                buf += struct.pack('<BI', 1, len(op[1])) + op[1]
    open(outpath, 'wb').write(b'MM9JPDL1' + bytes(buf))
    print('ファイル %d、写す %d バイト、新しい %d バイト → %s（%d バイト）' % (len(files), tot_cp, tot_lit, outpath, 8 + len(buf)))


if __name__ == '__main__':
    main()
