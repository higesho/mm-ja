# 手分けして訳すための作業ファイルを translation/work/ に作る
#   ds_1, ds_2:   本体の文字列（鍵 / 幅 / 途中への参照 / 場面 / 英文）
#   ev_1〜ev_6:   出来事の文（鍵 / 幅 / 英文）。場所ごとにまとめて分ける
#   str:          STR.DAT の行（鍵 / 幅 / 英文）
#   names:        品物・怪物の名前（鍵 / 幅 / 英文）
# 自動で KEEP にするもの（ファイル名など）は作業ファイルに入れない（collect.py が KEEP にする）
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
WORK = os.path.join(TR, "work")

AUTO_KEEP_RE = re.compile(r"(\.16|\.dat|\.DAT|\.DRV|\.ch|\.DTA)$|\\r|^R60|<<NMSG>>|^Version |^xxx$|_FILE_INFO|^\(27FKd$"
                          r"|^NNENW$|^DAE$|^9CB$|^WAFE|^Preamble$|^Tandy$")
CREDITS = {"D.1bdc", "D.1bec", "D.1bf9", "D.1c47", "D.1c58", "D.1c67", "D.1c75", "D.1c84"}


def read_tsv(name):
    rows = []
    for line in open(os.path.join(TR, name), encoding="utf-8"):
        rows.append(line.rstrip("\n").split("\t"))
    return rows


def auto_keep(key, en):
    if key.startswith("D."):
        return bool(AUTO_KEEP_RE.search(en.strip())) or key in CREDITS
    if key.startswith("V."):
        return len(en.replace("\\n", "").strip()) <= 1
    if key.startswith("S."):
        return en.strip() == "" or key in ("S.302", "S.303", "S.304", "S.305")
    return en.strip() == ""


def split_by_size(groups, n):
    """groups: [(名前, [行…])]。ほぼ同じ大きさの n 組に分ける（groups の順を保つ）"""
    total = sum(len(r[-1]) for _, rows in groups for r in rows)
    out = [[] for _ in range(n)]
    acc = 0
    for name, rows in groups:
        k = min(n - 1, acc * n // total)
        out[k] += rows
        acc += sum(len(r[-1]) for r in rows)
    return out


def write(name, rows, header):
    os.makedirs(os.path.join(WORK, "out"), exist_ok=True)
    with open(os.path.join(WORK, name + ".tsv"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# " + header + "\n")
        for r in rows:
            f.write("\t".join(r) + "\n")
    print(name, len(rows), sum(len(r[-1]) for r in rows))


def main():
    ds = [r for r in read_tsv("en_ds.tsv") if not auto_keep(r[0], r[5])]
    ds = [[r[0], r[1], r[3], r[4], r[5]] for r in ds]
    half = split_by_size([(r[0], [r]) for r in ds], 2)
    for i, rows in enumerate(half):
        write(f"ds_{i + 1}", rows, "鍵\t幅\t途中への参照\t場面\t英文")
    ev = [r for r in read_tsv("en_events.tsv") if not auto_keep(r[0], r[2])]
    groups = {}
    for r in ev:
        groups.setdefault(r[0][:5], []).append(r)
    for i, rows in enumerate(split_by_size(list(groups.items()), 6)):
        write(f"ev_{i + 1}", rows, "鍵\t幅\t英文")
    st = []
    for r in read_tsv("en_str.tsv"):
        if auto_keep(r[0], r[2]):
            continue
        n = len(r[2])
        st.append([r[0], str(n if n < 30 else 38), r[2]])
    write("str", st, "鍵\t幅\t英文")
    names = [r for r in read_tsv("en_items.tsv") + read_tsv("en_monsters.tsv") if not auto_keep(r[0], r[2])]
    write("names", names, "鍵\t幅\t英文")


if __name__ == "__main__":
    main()
