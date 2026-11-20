# 訳を集めて検査し、translation/ja.txt を作る
#   python tools/collect.py                 全部の組を集めて ja.txt を書き、注意を translation/work/check.txt に書く
#   python tools/collect.py --only ev_1.tsv その組だけ検査して注意を画面に出す（ja.txt は書かない）
# 訳: translation/work/out/<組>.tsv（鍵<TAB>訳、KEEP、#TERM 英語<TAB>訳）。手直し: translation/ja_fix.txt（最後に上書き）
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from jpcommon import BAD_HALF, align, fit_spaces, is_jp, layout, load_bdf, norm_ascii, unesc  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
WORK = os.path.join(TR, "work")


def read_work(path):
    rows = {}
    order = []
    for line in open(path, encoding="utf-8"):
        if line.startswith("#"):
            continue
        t = line.rstrip("\n").split("\t")
        rows[t[0]] = t
        order.append(t[0])
    return rows, order


def read_out(path):
    tr = {}
    terms = []
    dup = []
    for line in open(path, encoding="utf-8-sig"):
        line = line.rstrip("\n").rstrip("\r")
        if not line.strip():
            continue
        if line.startswith("#TERM"):
            terms.append(line[5:].strip())
            continue
        if line.startswith("#"):
            continue
        if "\t" not in line:
            dup.append(f"タブがない行: {line[:40]}")
            continue
        k, v = line.split("\t", 1)
        if k in tr:
            dup.append(f"{k}: 2回ある")
        tr[k] = v
    return tr, terms, dup


GLYPHS = None


def check_chars(key, ja, en):
    global GLYPHS
    if GLYPHS is None:
        GLYPHS = load_bdf()
    notes = []
    for tag in ("{c}", "{l}", "{r}"):
        if ja.startswith(tag):
            ja = ja[3:]
    for ch in ja:
        if ch in BAD_HALF and ch not in en and ch != "|":
            notes.append(f"使えない半角の字「{ch}」")
        elif is_jp(ch) and ord(ch) not in GLYPHS:
            notes.append(f"フォントにない字「{ch}」")
    return notes


def prep(key, ja, en):
    """訳を組み立て前の形にする（全角英数→半角、\\n、寄せ、前後の空白）"""
    ja = norm_ascii(unesc(ja))
    en = unesc(en)
    return ja, en


def check_one(pkg, key, row, ja):
    notes = []
    if ja == "KEEP":
        return notes
    if pkg.startswith("ds"):
        width, inner, en = int(row[1]), [int(x) for x in row[2].split(",") if x], unesc(row[4])
        ja, _ = prep(key, ja, row[4])
        notes += check_chars(key, ja, en)
        parts = ja.split("|")
        if len(parts) - 1 != len(inner):
            notes.append(f"| の数が {len(parts) - 1}（途中への参照は {len(inner)} 個）")
            return notes
        bounds = [0] + inner + [width]
        for i, p in enumerate(parts):
            seg_en = en[bounds[i]:bounds[i + 1]]
            if len(parts) == 1:
                p, ok = align(p, width)
                p = p if ok else fit_spaces(p, en)
            w = bounds[i + 1] - bounds[i]
            if len(p) > w:
                notes.append(f"長い（{len(p)} > {w} マス）: {p}" if len(parts) == 1 else
                             f"{i + 1} 番目の部分が長い（{len(p)} > {w} マス）: {p}（英文 {seg_en!r}）")
    elif pkg.startswith("ev"):
        width, en = int(row[1]), unesc(row[2])
        ja, _ = prep(key, ja, row[2])
        notes += check_chars(key, ja, en)
        if "|" in ja:
            notes.append("| は使えない")
        lines, ln = layout(ja, width)
        notes += ln
        nen = en.count("\n") + 1
        if len(lines) > max(nen, 1):
            notes.append(f"行が多い（{len(lines)} 行 > 英文 {nen} 行、幅 {width}）: " + " / ".join(lines))
    elif pkg == "str":
        width, en = int(row[1]), unesc(row[2])
        ja, _ = prep(key, ja, row[2])
        notes += check_chars(key, ja, en)
        if "\n" in ja or "|" in ja:
            notes.append("改行や | は使えない")
        if len(ja) > width:
            notes.append(f"長い（{len(ja)} > {width} マス）: {ja}")
    elif pkg == "names":
        width, en = int(row[1]), row[2]
        ja, _ = prep(key, ja, row[2])
        notes += check_chars(key, ja, en)
        if len(ja) > width:
            notes.append(f"長い（{len(ja)} > {width} マス）: {ja}")
        if "  " in ja or "\n" in ja or "|" in ja:
            notes.append("空白2つ・改行・| は使えない")
    return notes


def check_pkg(pkg):
    rows, order = read_work(os.path.join(WORK, pkg + ".tsv"))
    outp = os.path.join(WORK, "out", pkg + ".tsv")
    if not os.path.exists(outp):
        return {}, [], [f"{pkg}: 訳のファイルがない"]
    tr, terms, dup = read_out(outp)
    notes = [f"{pkg}: {d}" for d in dup]
    for k in tr:
        if k not in rows:
            notes.append(f"{pkg}: {k}: 作業ファイルにない鍵")
    missing = [k for k in order if k not in tr]
    if missing:
        notes.append(f"{pkg}: 訳のない鍵 {len(missing)} 件: " + " ".join(missing[:10]) + (" …" if len(missing) > 10 else ""))
    for k in order:
        if k in tr:
            for n in check_one(pkg, k, rows[k], tr[k]):
                notes.append(f"{pkg}: {k}: {n}")
    return tr, terms, notes


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        pkg = os.path.basename(sys.argv[2]).replace(".tsv", "")
        tr, terms, notes = check_pkg(pkg)
        for n in notes:
            print(n)
        print(f"{pkg}: 訳 {len(tr)} 件、注意 {len(notes)} 件")
        return
    allt = {}
    allterms = []
    allnotes = []
    for p in sorted(glob.glob(os.path.join(WORK, "*.tsv"))):
        pkg = os.path.basename(p)[:-4]
        tr, terms, notes = check_pkg(pkg)
        allt.update(tr)
        allterms += terms
        allnotes += notes
    tf = os.path.join(TR, "term_fix.txt")
    if os.path.exists(tf):
        pairs = []
        for line in open(tf, encoding="utf-8"):
            line = line.rstrip("\n")
            if line and not line.startswith("#") and "\t" in line:
                pairs.append(line.split("\t", 1))
        for k in allt:
            for a, b in pairs:
                if a in allt[k]:
                    allt[k] = allt[k].replace(a, b)
    fix = os.path.join(TR, "ja_fix.txt")
    if os.path.exists(fix):
        for line in open(fix, encoding="utf-8"):
            line = line.rstrip("\n")
            if line and not line.startswith("#") and "\t" in line:
                k, v = line.split("\t", 1)
                allt[k] = v
    with open(os.path.join(TR, "ja.txt"), "w", encoding="utf-8", newline="\n") as f:
        for k in sorted(allt):
            if allt[k] != "KEEP":
                f.write(f"{k}\t{allt[k]}\n")
    with open(os.path.join(WORK, "check.txt"), "w", encoding="utf-8", newline="\n") as f:
        for n in allnotes:
            f.write(n + "\n")
    with open(os.path.join(WORK, "new_terms.txt"), "w", encoding="utf-8", newline="\n") as f:
        for t in allterms:
            f.write(t + "\n")
    print(f"訳 {len(allt)} 件（KEEP {sum(v == 'KEEP' for v in allt.values())}）、注意 {len(allnotes)} 件、新しい語 {len(allterms)}")


if __name__ == "__main__":
    main()
