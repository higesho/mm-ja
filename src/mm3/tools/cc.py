"""MM3.CC の読み書き（World of Xeen と同じ形式）"""
import struct, sys, os

def name_hash(name):
    t = 0
    for ch in name.upper():
        t = ((t << 9) | (t >> 7)) & 0xFFFF
        t = (t + ord(ch)) & 0xFFFF
    return t

def read_index(d):
    n = struct.unpack('<H', d[:2])[0]
    raw = d[2:2 + n * 8]; out = bytearray(); k = 0xAC
    for b in raw:
        out.append(((((b << 2) | (b >> 6)) & 0xFF) + k) & 0xFF); k = (k + 0x67) & 0xFF
    ents = []
    for i in range(n):
        e = out[i*8:i*8+8]
        h = e[0] | e[1] << 8
        off = e[2] | e[3] << 8 | e[4] << 16
        sz = e[5] | e[6] << 8
        ents.append((h, off, sz, e[7]))
    return ents

def load(path):
    d = open(path, 'rb').read()
    res = {}
    for h, off, sz, f in read_index(d):
        res[h] = d[off:off+sz]
    return res

if __name__ == '__main__':
    src, outdir = sys.argv[1], sys.argv[2]
    d = open(src, 'rb').read()
    for i, (h, off, sz, f) in enumerate(read_index(d)):
        data = d[off:off+sz]
        open(os.path.join(outdir, '%03d_%04X.bin' % (i, h)), 'wb').write(data)
