"""MM8 の LOD 書庫を読む・書く。

形: 0x100 の頭、0x100 に目録の組（名16・位置・大きさ・?・件数）、
各件は 0x4C（名64・位置（組の頭から）・大きさ・?）。
"""
import struct, sys, os, zlib

ENT = 0x4C


def read_lod(path):
    data = open(path, 'rb').read()
    dname = data[0x100:0x110].split(b'\0')[0]
    doff, dsize, dunk, cnt = struct.unpack_from('<IIII', data, 0x110)
    items = []
    for i in range(cnt):
        p = doff + i * ENT
        name = data[p:p + 64].split(b'\0')[0].decode('latin-1')
        off, size, unk = struct.unpack_from('<III', data, p + 64)
        items.append((name, doff + off, size, unk))
    return data, items


def unpack(raw):
    """圧縮された中身を開く。形が分からなければそのまま。"""
    # 文の類: [u32 圧縮後][u32 元] zlib
    if len(raw) >= 8:
        a, b = struct.unpack_from('<II', raw, 0)
        if a == len(raw) - 8 and raw[8:9] == b'\x78':
            return zlib.decompress(raw[8:])
    # 機械語の頭つき（MM8 の "mvii" など）は後で
    return raw


if __name__ == '__main__':
    data, items = read_lod(sys.argv[1])
    for name, off, size, unk in items:
        print(f'{name:40s} {off:08x} {size:8d} {unk:x}  {data[off:off+16].hex()}')
