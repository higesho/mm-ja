"""MM6/7 の LOD 書庫を読む・書く。"""
import struct, zlib, sys, os

class Lod:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        d = self.data
        assert d[:4] == b'LOD\0'
        self.header = d[:0x100]
        self.dirname = d[0x100:0x110]
        self.diroff, self.dirsize, self.dirunk, self.count = struct.unpack_from('<IIIi', d, 0x110)
        self.dirtail = d[0x110:0x120]
        self.files = []
        base = self.diroff
        for i in range(self.count):
            e = base + i * 0x20
            name = d[e:e+16].split(b'\0')[0].decode('latin1')
            off, size, unk, num = struct.unpack_from('<IIII', d, e + 16)
            self.files.append((name, base + off, size, d[e:e+16], unk, num))

    def names(self):
        return [f[0] for f in self.files]

    def raw(self, name):
        for f in self.files:
            if f[0].lower() == name.lower():
                return self.data[f[1]:f[1]+f[2]]
        raise KeyError(name)

    def text(self, name):
        """圧縮ファイル（0x30 バイトの見出し＋zlib）を解く。見出し 0x14=圧縮後の大きさ、0x28=元の大きさ。"""
        r = self.raw(name)
        psize, = struct.unpack_from('<I', r, 0x14)
        usize, = struct.unpack_from('<I', r, 0x28)
        body = r[0x30:0x30+psize]
        if usize:
            return zlib.decompress(body)
        return body

if __name__ == '__main__':
    l = Lod(sys.argv[1])
    for f in l.files:
        print(f[0], f[2], f[4], f[5])
