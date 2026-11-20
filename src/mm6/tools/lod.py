"""MM6 の LOD 書庫を読む・書き出す。

使い方:
  python lod.py list  data/icons.lod
  python lod.py x     data/icons.lod  出力先  [名前の絞り込み(正規表現)]

書庫の作り:
  0x000 "LOD\\0" + 版 "MMVI" ...（0x100 バイトの頭）
  0x100 目録 32 バイト: 名前[16], 位置, 大きさ, ?, 個数
  目録の位置から 32 バイトずつ: 名前[16], 位置(目録の位置から), 大きさ, ?, ?
"""
import struct, sys, os, re, zlib


def read_lod(path):
    data = open(path, 'rb').read()
    dname = data[0x100:0x110].split(b'\0')[0]
    doff, dsize, dunk, count = struct.unpack_from('<IIII', data, 0x110)
    files = []
    for i in range(count):
        p = doff + i * 32
        name = data[p:p + 16].split(b'\0')[0].decode('latin-1')
        off, size, u1, u2 = struct.unpack_from('<IIII', data, p + 16)
        files.append((name, doff + off, size, u1, u2))
    return data, dname, doff, files


def unpack_entry(name, raw):
    """icons.lod の文書や .fnt などの圧縮を解く。分からなければそのまま返す。"""
    # icons.lod の項目は 0x30 バイトの頭: 名前[16], ?, 圧縮後の大きさ(0x14), ..., 元の大きさ(0x28)
    if len(raw) >= 0x30:
        csize = struct.unpack_from('<I', raw, 0x14)[0]
        usize = struct.unpack_from('<I', raw, 0x28)[0]
        if csize == len(raw) - 0x30:
            if usize == 0:
                return raw[0x30:]
            try:
                d = zlib.decompress(raw[0x30:])
                if len(d) == usize:
                    return d
            except zlib.error:
                pass
    if len(raw) >= 8:
        csize, usize = struct.unpack_from('<II', raw, 0)
        if csize == len(raw) - 8 and usize >= csize:
            try:
                return zlib.decompress(raw[8:])
            except zlib.error:
                pass
    return raw


def main():
    cmd, path = sys.argv[1], sys.argv[2]
    data, dname, doff, files = read_lod(path)
    if cmd == 'list':
        print(dname, hex(doff), len(files))
        for f in files:
            print('%-16s %8x %8d %8x %8x' % f)
    elif cmd == 'x':
        out = sys.argv[3]
        args=[a for a in sys.argv[4:] if a!='-u']
        pat = re.compile(args[0], re.I) if args else None
        os.makedirs(out, exist_ok=True)
        for name, off, size, u1, u2 in files:
            if pat and not pat.search(name):
                continue
            raw = data[off:off + size]
            if '-u' in sys.argv:
                raw = unpack_entry(name, raw)
            open(os.path.join(out, name), 'wb').write(raw)


if __name__ == '__main__':
    main()
