# -*- coding: utf-8 -*-
"""ScummVM の mm.dat の中の Xeen の定数（CONSTANTS_7、英語）を読み書きする。

読み込みの順と型は engines/mm/xeen/resources.cpp の loadData() から機械的に取る
（file.syncString / syncStrings / syncStrings2D / syncNumbers* / syncBytes2D）。

python tools/constants.py export <出力 TSV>
    英語の文を「鍵<TAB>英文」で書き出す（鍵は名前、配列は 名前[番号]）。
    英文の中の制御文字は \\n \\t \\v \\f \\r \\xNN の形にする。
python tools/constants.py build <訳の TSV> <出力 CONSTANTS> [<出力 CONSTKEYS>]
    訳の TSV（鍵<TAB>訳）で文を置き換えた CONSTANTS を作る（Shift-JIS）。訳のない鍵は英文のまま。
"""
import sys, os, re, struct, zipfile, io

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
SRC = os.path.join(ROOT, 'build', 'scummvm-src')
MMDAT = os.path.join(SRC, 'dists', 'engine-data', 'mm.dat')
RES_CPP = os.path.join(SRC, 'engines', 'mm', 'xeen', 'resources.cpp')
EN_ID = 7


def schema():
    """loadData の file.syncXxx(...) を順に (型, 名前, 数の並び) にする。"""
    src = open(RES_CPP, encoding='utf-8').read()
    body = src[src.index('void Resources::loadData()'):]
    body = body[:body.index('ResFile keys')]
    out = []
    for m in re.finditer(r'file\.(sync[A-Za-z0-9]+)\(([^;]*)\);', body):
        kind, args = m.group(1), m.group(2)
        parts = [a.strip() for a in args.split(',')]
        name = re.sub(r'^\(.*?\)', '', parts[0]).strip()
        name = re.sub(r'^&', '', name)
        name = re.sub(r'(\[0\])+$', '', name)
        dims = [int(x) for x in parts[1:]]
        out.append((kind, name, dims))
    return out


def read_en(name='CONSTANTS'):
    z = zipfile.ZipFile(MMDAT)
    return z.read('xeen/%s_%d' % (name, EN_ID))


def prod(d):
    n = 1
    for x in d:
        n *= x
    return n


def walk(data):
    """(鍵, 型, 値) の並び。値は文字列なら bytes、それ以外は bytes の塊のまま。"""
    pos = 0
    items = []

    def rstr():
        nonlocal pos
        e = data.index(b'\0', pos)
        s = data[pos:e]
        pos = e + 1
        return s

    for kind, name, dims in schema():
        if kind == 'syncString':
            items.append((name, 'str', rstr()))
            continue
        tag = data[pos:pos + 4]
        d4 = dims + [0] * (4 - len(dims))
        expect = struct.pack('<I', ((d4[0] << 24) | (d4[1] << 16) | (d4[2] << 8) | d4[3]) & 0xFFFFFFFF)  # MKTAG
        assert tag == expect, (name, tag, expect, pos)
        pos += 4
        n = prod(dims)
        if kind in ('syncStrings', 'syncStrings2D'):
            items.append((name, 'tag', tag))
            for i in range(n):
                items.append(('%s[%d]' % (name, i), 'str', rstr()))
        elif kind.startswith('syncNumbers'):
            items.append((name, 'raw', tag + data[pos:pos + 4 * n]))
            pos += 4 * n
        elif kind == 'syncBytes2D':
            items.append((name, 'raw', tag + data[pos:pos + n]))
            pos += n
        else:
            raise ValueError(kind)
    assert pos == len(data), (pos, len(data))
    return items


def esc(b):
    out = []
    for c in b:
        if c == 10:
            out.append('\\n')
        elif c == 9:
            out.append('\\t')
        elif c == 11:
            out.append('\\v')
        elif c == 12:
            out.append('\\f')
        elif c == 13:
            out.append('\\r')
        elif c == 0x5C:
            out.append('\\\\')
        elif c < 0x20 or c >= 0x7F:
            out.append('\\x%02X' % c)
        else:
            out.append(chr(c))
    return ''.join(out)


def unesc(s):
    """esc の逆。訳文（Unicode）は Shift-JIS にする。"""
    out = bytearray()
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            if n == 'x':
                out.append(int(s[i + 2:i + 4], 16))
                i += 4
                continue
            out += {'n': b'\n', 't': b'\t', 'v': b'\v', 'f': b'\f', 'r': b'\r', '\\': b'\\'}[n]
            i += 2
            continue
        out += c.encode('cp932')
        i += 1
    return bytes(out)


def load_tsv(path):
    d = {}
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        k, v = line.split('\t', 1)
        d[k] = v
    return d


def build(trans):
    out = bytearray()
    for key, typ, val in walk(read_en()):
        if typ == 'str':
            if key in trans:
                out += unesc(trans[key]) + b'\0'
            else:
                out += val + b'\0'
        else:
            out += val
    return bytes(out)


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'export':
        with open(sys.argv[2], 'w', encoding='utf-8', newline='\n') as f:
            n = 0
            for key, typ, val in walk(read_en()):
                if typ == 'str':
                    f.write('%s\t%s\n' % (key, esc(val)))
                    n += 1
        print('文の数', n)
    elif cmd == 'build':
        trans = load_tsv(sys.argv[2])
        open(sys.argv[3], 'wb').write(build(trans))
        if len(sys.argv) > 4:
            open(sys.argv[4], 'wb').write(read_en('CONSTKEYS'))
