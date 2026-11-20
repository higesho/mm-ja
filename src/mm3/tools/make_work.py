# 手分け用の作業ファイルを作る → translation/work/<組>.tsv（鍵<TAB>上限<TAB>英文）
# DS の訳さないもの（自動で KEEP）は translation/keep_auto.tsv に書く
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")

# 訳さない DS の範囲（絵のファイル名、入力と比べる語など）
KEEP_RANGES = [(0x0000, 0x11ED),      # 起動・文字画面の文・ファイル名
               (0x68A8, 0x6AD9),      # 怪物の絵の名前（bat, goblin …）
               (0x7845, 0x78A3),      # 入力と比べる語（home, seadog, freeman …）
               (0x7946, 0x7B1C),      # 物の絵の名前（ALTRCUP …）
               (0x7D8A, 0x7E89),      # 地形・建物の絵の名前（human, twn, mount …）
               (0x7BF8, 0x7C17),      # 品物の画面の絵の名前（items, buy, sell, detect, duplicat）
               (0x8880, 0x10000)]     # 実行時の置き場・C の実行時ライブラリ
KEEP_TEXT = ["Borland", "Null pointer", "print scanf", "COMSPEC"]
DS_GROUPS = [("ds_ui1", [(0x11ED, 0x4000)]),
             ("ds_ui2", [(0x4000, 0x5B59), (0x7900, 0x8880)]),
             ("ds_names", [(0x5B59, 0x7900)])]
CC_GROUPS = [("cc_misc", ["C002", "C003", "C006", "C008", "C010", "C382", "C004"]),
             ("cc_jester_tavern", ["C005", "C007"]),
             ("cc_corak", ["C009"])]
MAP_CHUNK = 15000


def ds_keep(off, t):
    if any(a <= off < b for a, b in KEEP_RANGES):
        return "範囲"
    raw = re.sub(r"\{[^}]*\}", "", t).replace("\\n", " ").strip()
    if re.fullmatch(r"[\w%?*]+\.[a-zA-Z0-9$?]{1,3}", raw):
        return "ファイル名"
    if not re.findall(r"[A-Za-z]{2,}", raw) or not re.search(r"[aeiouyAEIOUY]", raw):
        return "記号"
    if any(k in t for k in KEEP_TEXT):
        return "ライブラリ"
    return None


def main():
    os.makedirs(os.path.join(TR, "work", "out"), exist_ok=True)
    ds = [l.rstrip("\n").split("\t") for l in open(os.path.join(TR, "en_ds.tsv"), encoding="utf-8")]
    keep = []
    groups = {g: [] for g, _ in DS_GROUPS}
    for k, n, head, mids, t in ds:
        off = int(k[2:], 16)
        why = ds_keep(off, t)
        if why:
            keep.append(f"{k}\t{why}\t{t}")
            continue
        for g, rs in DS_GROUPS:
            if any(a <= off < b for a, b in rs):
                groups[g].append(f"{k}\t{n}\t{t}")
                break
    cc = [l.rstrip("\n").split("\t") for l in open(os.path.join(TR, "en_cc.tsv"), encoding="utf-8")]
    used = set()
    for g, files in CC_GROUPS:
        groups[g] = [f"{k}\t{max(int(n), 99)}\t{t}" for k, n, t in cc if k[:4] in files]
        used.update(files)
    rest = [(k, n, t) for k, n, t in cc if k[:4] not in used]
    i = 0
    cur, size = [], 0
    byfile = {}
    for k, n, t in rest:
        byfile.setdefault(k[:4], []).append((k, n, t))
    for f in sorted(byfile):
        fs = sum(int(n) for _, n, _ in byfile[f])
        if cur and size + fs > MAP_CHUNK:
            i += 1
            groups["cc_map%02d" % i] = cur
            cur, size = [], 0
        cur += [f"{k}\t{max(int(n), 99)}\t{t}" for k, n, t in byfile[f]]
        size += fs
    if cur:
        i += 1
        groups["cc_map%02d" % i] = cur
    for g, rows in groups.items():
        open(os.path.join(TR, "work", g + ".tsv"), "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")
        b = sum(int(r.split("\t")[1]) for r in rows)
        print(f"{g}: {len(rows)} 行")
    open(os.path.join(TR, "keep_auto.tsv"), "w", encoding="utf-8", newline="\n").write("\n".join(keep) + "\n")
    print("自動で KEEP:", len(keep))


if __name__ == "__main__":
    main()
