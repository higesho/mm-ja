# 入力と比べる文字列を地図のイベント（MM3.CUR の mazeNN.evt）から拾う → translation/keep_cc.tsv
#   命令 0x15（言葉の照合）の引数 1 と 3（答え。0 でないとき）
#   町（地図 1〜5）の命令 02・03（扉の看板。鏡の行き先の入力と比べる）
import os, sys, re
sys.path.insert(0, os.path.dirname(__file__))
from cc import read_index, name_hash
W = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
cur = open(os.path.join(W, "..", "MM3.CUR"), "rb").read()
cc = open(os.path.join(W, "..", "MM3.CC"), "rb").read()
ents = read_index(cur); hs = {e[0]: i for i, e in enumerate(ents)}
cents = read_index(cc); chs = {e[0]: i for i, e in enumerate(cents)}
en = {}
for l in open(os.path.join(W, "translation", "en_cc.tsv"), encoding="utf-8"):
    k, n, t = l.rstrip("\n").split("\t"); en[k] = t
keep = {}
for m in range(1, 100):
    h = name_hash("maze%02u.evt" % m)
    if h not in hs:
        continue
    tno = chs.get(name_hash("text%02u.maz" % m))
    e = ents[hs[h]]; d = cur[e[1]:e[1] + e[2]]
    p = 0
    while p < len(d):
        L = d[p]; r = d[p + 1:p + 1 + L]; p += 1 + L
        if len(r) < 6:
            continue
        op, prm = r[4], r[5:]
        cand = []
        if op == 0x15 and len(prm) >= 4 and prm[0]:
            cand = [(prm[0], "答え"), (prm[2], "答え")]
        if op in (2, 3) and m <= 5:
            cand = [(prm[0], "看板")]
        for q, why in cand:
            k = "C%03d.%03d" % (tno, q)
            if q and k in en and "{" not in en[k] and len(en[k]) <= 30:
                keep[k] = why
rows = [f"{k}\t{why}\t{en[k]}" for k, why in sorted(keep.items())]
open(os.path.join(W, "translation", "keep_cc.tsv"), "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")
print(len(rows), "件")
