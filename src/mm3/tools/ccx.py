"""MM3.CC の全項目を解凍して ccx/ に出す（名前の分かるものは名前で）。圧縮されていない項目はそのまま。"""
import sys, os, re
sys.path.insert(0, os.path.dirname(__file__))
from cc import read_index, name_hash
import lzhuf

cc = open(sys.argv[1], 'rb').read()
mem = open(sys.argv[2], 'rb').read()
out = sys.argv[3]
ents = read_index(cc)
names = set(m.group().decode() for m in re.finditer(rb'[A-Za-z0-9_%]{1,12}\.[A-Za-z0-9]{1,3}(?=\x00)', mem))
full = set()
for n in names:
    if '%' in n:
        for k in range(0, 100):
            for v in ([k] if n.count('%') == 1 else []):
                try: full.add(n % v)
                except TypeError: pass
    else:
        full.add(n.lower())
hmap = {}
for n in full:
    hmap.setdefault(name_hash(n), []).append(n)
rows = []
for i, (h, off, sz, f) in enumerate(ents):
    raw = cc[off:off + sz]
    nm = hmap.get(h, ['%04X' % h])
    nm = sorted(nm, key=len)[0]
    try:
        size = (raw[2] << 8) | raw[3]
        data = lzhuf.decode(raw) if size > 0 and i > 1 else raw
        kind = 'lz'
    except Exception as e:
        data = raw; kind = 'raw'
    open(os.path.join(out, '%03d_%s' % (i, nm)), 'wb').write(data)
    rows.append('%03d\t%04X\t%s\t%d\t%d\t%s' % (i, h, nm, sz, len(data), kind))
open(os.path.join(out, '_index.tsv'), 'w').write('\n'.join(rows) + '\n')
