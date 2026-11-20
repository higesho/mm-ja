# 訳の手分け用のファイルを作る: translation/work/*.tsv
#   exe_NN.tsv  本体の文字列（並び順のまま、約 110 件ずつ）: 鍵 幅 途中への参照 場面 英文
#   ovr_NN.tsv  オーバーレイ（ファイルごとにまとめて、約 3,500 バイトずつ）: 鍵 幅 途中への参照 場面(ファイル名) 英文
#   tbl_items.tsv / tbl_monsters.tsv  品物・怪物の名前: 鍵 幅 英文
# 訳した結果は translation/work/out/<同じ名前> に「鍵<TAB>訳」で置く（tools/collect.py が集める）
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
WORK = os.path.join(TR, "work")


def rows(fn):
    return [line.rstrip("\n").split("\t") for line in open(os.path.join(TR, fn), encoding="utf-8")]


def write(name, lines):
    with open(os.path.join(WORK, name), "w", encoding="utf-8") as f:
        f.write("".join(lines))
    return name


def main():
    os.makedirs(os.path.join(WORK, "out"), exist_ok=True)
    made = []
    exe = rows("en_exe.tsv")
    n = 0
    for i in range(0, len(exe), 116):
        n += 1
        made.append((write(f"exe_{n:02d}.tsv", [f"{t[0]}\t{t[1]}\t{t[3]}\t{t[5]}\t{t[4]}\n" for t in exe[i:i + 116]]),
                     len(exe[i:i + 116]), sum(int(t[1]) for t in exe[i:i + 116])))
    ovr = rows("en_ovr.tsv")
    groups, cur, size = [], [], 0
    last = None
    for t in ovr:
        f = t[0].split(".")[0]
        if f != last and size >= 3400:
            groups.append(cur)
            cur, size = [], 0
        cur.append(t)
        size += int(t[1])
        last = f
    if cur:
        groups.append(cur)
    for k, g in enumerate(groups, 1):
        made.append((write(f"ovr_{k:02d}.tsv", [f"{t[0]}\t{t[1]}\t{t[3]}\t{t[0].split('.')[0]}\t{t[4]}\n" for t in g]),
                     len(g), sum(int(t[1]) for t in g)))
    tbl = rows("en_tables.tsv")
    for kind, name in (("I", "tbl_items.tsv"), ("M", "tbl_monsters.tsv")):
        sel = [t for t in tbl if t[0].startswith(kind + ".")]
        made.append((write(name, [f"{t[0]}\t{14 if kind == 'M' else t[1]}\t{t[2]}\n" for t in sel]), len(sel),
                     sum(len(t[2]) for t in sel)))
    for name, cnt, b in made:
        print(f"{name}\t{cnt} 件\t{b} バイト")


if __name__ == "__main__":
    main()
