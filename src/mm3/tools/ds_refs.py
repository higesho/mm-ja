# DS の文字列ごとの参照を調べる → translation/ds_refs.tsv
#   鍵、元の長さ、コードの即値の参照の数、番地の表の中の位置（, 区切り）、途中への参照
# 番地の表: DS の中で、文字列の先頭を指す語が 3 つ以上続く所
import os, sys, struct
sys.path.insert(0, os.path.dirname(__file__))
from extract import ds_strings, code_imms, DSB, ROOT, OVL
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
mem = open(os.path.join(W, "build", "mem.bin"), "rb").read()
exe = open(os.path.join(W, "..", "MM3.EXE"), "rb").read()
ds = mem[DSB:DSB + 0x10000]
strs = ds_strings(ds)
starts = {o for o, _ in strs}
# 文字列でない短いもの（"s" など）も表の先として数えるため、0 の直後の位置も先頭とみなす
heads = set(starts)
for k in range(1, 0x8880):
    if ds[k - 1] == 0 and ds[k] != 0:
        heads.add(k)
imms = code_imms(mem[ROOT[0]:ROOT[1]], 0)
for v, n in code_imms(exe[OVL + 0x10:], 0).items():
    imms[v] = imms.get(v, 0) + n
isptr = [0] * 0x8880          # 2 = 文字列の先頭を指す、1 = 空の文字列（0 のバイト）を指す
for k in range(0, 0x8880 - 1):
    v = struct.unpack_from("<H", ds, k)[0]
    if 0x1000 <= v < 0x8880:
        isptr[k] = 2 if v in heads else (1 if ds[v] == 0 else 0)
# 文字列の中身の所は表ではない
for o, s in strs:
    for q in range(max(0, o - 1), o + len(s) + 1):
        if q < 0x8880:
            isptr[q] = 0
ptrloc = {}
for k in range(0, 0x8880 - 6):
    # k から 2 バイトおきに続き、文字列の先頭を指すものが 3 つ以上
    run = 0
    j = k
    while j < 0x8880 - 1 and isptr[j]:
        run += isptr[j] == 2; j += 2
    if run >= 3 and not (k >= 2 and isptr[k - 2]):
        for q in range(k, j, 2):
            v = struct.unpack_from("<H", ds, q)[0]
            ptrloc.setdefault(v, []).append(q)
rows = []
for off, s in strs:
    mids = [str(i) for i in range(1, len(s)) if imms.get(off + i)]
    rows.append("D.%04X\t%d\t%d\t%s\t%s" % (off, len(s), imms.get(off, 0),
                ",".join("%04X" % q for q in sorted(set(ptrloc.get(off, [])))), ",".join(mids)))
open(os.path.join(W, "translation", "ds_refs.tsv"), "w", newline="\n").write("\n".join(rows) + "\n")
print(len(rows), "件、表から指されるもの", sum(1 for r in rows if r.split("\t")[3]),
      "、表からだけ指されるもの", sum(1 for r in rows if r.split("\t")[3] and r.split("\t")[2] == "0"))
