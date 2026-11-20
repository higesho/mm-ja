"""Xeen の CC 書庫を読む・作る道具。

python tools/cc.py list <cc>            一覧（番号・位置・大きさ・推定した名前）
python tools/cc.py dump <cc> <出力先>    全部を復号して書き出す（名前が分かれば名前で）
"""
import sys, os, struct


def name_to_id(name):
    name = name.upper()
    if len(name) == 4:
        try:
            return int(name, 16)
        except ValueError:
            pass
    b = name.encode('latin-1')
    total = b[0]
    for c in b[1:]:
        total = ((total & 0x7F) << 9 | (total & 0xFF80) >> 7) & 0xFFFF
        total = (total + c) & 0xFFFF
    return total


def read_index(data):
    count = struct.unpack_from('<H', data, 0)[0]
    raw = bytearray(data[2:2 + count * 8])
    seed = 0xAC
    for i in range(len(raw)):
        v = raw[i]
        raw[i] = ((((v << 2) | (v >> 6)) & 0xFF) + seed) & 0xFF
        seed = (seed + 0x67) & 0xFF
    ents = []
    for i in range(count):
        e = raw[i * 8:i * 8 + 8]
        fid = e[0] | e[1] << 8
        off = e[2] | e[3] << 8 | e[4] << 16
        size = e[5] | e[6] << 8
        ents.append((fid, off, size))
    return ents


def encode_index(ents):
    raw = bytearray()
    for fid, off, size in ents:
        raw += struct.pack('<HI', fid, off)[:5] + struct.pack('<H', size) + b'\0'
    seed = 0xAC
    for i in range(len(raw)):
        v = (raw[i] - seed) & 0xFF
        raw[i] = ((v >> 2) | (v << 6)) & 0xFF
        seed = (seed + 0x67) & 0xFF
    return struct.pack('<H', len(ents)) + bytes(raw)


class CC:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self.index = read_index(self.data)
        self.byid = {e[0]: e for e in self.index}

    def get(self, key):
        fid = key if isinstance(key, int) else name_to_id(key)
        e = self.byid.get(fid)
        if e is None:
            return None
        _, off, size = e
        return bytes(b ^ 0x35 for b in self.data[off:off + size])


def known_names():
    """ScummVM のソースから分かる名前の型で候補を作る。"""
    names = []
    for side in ('0', 'x'):
        for n in range(1000):
            names.append('maze%s%03d.evt' % (side, n))
            names.append('aaze%s%03d.txt' % (side, n))
            names.append('maze%s%03d.dat' % (side, n))
            names.append('maze%s%03d.mob' % (side, n))
            names.append('xeen%s%03d.txt' % (side, n))
            names.append('dark%s%03d.txt' % (side, n))
    for n in range(1000):
        names.append('aaze2%03d.txt' % n)
    for p in ('xeen', 'dark'):
        for n in range(10000):
            names.append('%s%04d.txt' % (p, n))
        names.append('%smirr.txt' % p)
    return names


if __name__ == '__main__':
    cmd, path = sys.argv[1], sys.argv[2]
    cc = CC(path)
    extra = []
    if len(sys.argv) > 4:
        extra = open(sys.argv[4], encoding='utf-8').read().split()
    names = {}
    for n in known_names() + extra:
        fid = name_to_id(n)
        if fid in cc.byid:
            names.setdefault(fid, n)
    if cmd == 'list':
        for fid, off, size in cc.index:
            print('%04X %8d %6d %s' % (fid, off, size, names.get(fid, '')))
    elif cmd == 'dump':
        out = sys.argv[3]
        os.makedirs(out, exist_ok=True)
        for fid, off, size in cc.index:
            nm = names.get(fid, '%04X.bin' % fid)
            open(os.path.join(out, nm), 'wb').write(cc.get(fid))
