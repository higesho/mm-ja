# MM.RSM（Aztec C の記号表）を読む: 記録 = 02 種類 番地(2) 名前 00
import sys, re
def load(path=r'L:/Games/GOG/TocaRaceDriver3/Might and Magic 1/MM.RSM'):
    d = open(path, 'rb').read()
    out = []
    for m in re.finditer(rb'\x02(.)(..)([\x21-\x7e]+)\x00', d, re.S):
        out.append((m.group(1)[0], int.from_bytes(m.group(2), 'little'), m.group(3).decode()))
    return out
if __name__ == '__main__':
    for t, a, n in load():
        print('%02x %04x %s' % (t, a, n))
