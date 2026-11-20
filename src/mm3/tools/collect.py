# 訳を集めて検査する
#   python tools/collect.py                 全部の組を集めて translation/ja.tsv を作り、translation/work/check.txt に検査結果
#   python tools/collect.py --only <組>     その組だけ検査して画面に出す（組の名前は ds_ui1 など。.tsv は付けても付けなくてもよい）
# 訳のファイル: translation/work/out/<組>.tsv（鍵<TAB>訳、KEEP、#TERM 英語<TAB>訳）
# 手直し: translation/ja_fix.txt（鍵<TAB>訳。最後に上書き）
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
from textfmt import from_text, tokens  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
ONE = set("ぁあぃいぅうぇえぉおかがきぎくぐけげこごさざしじすずせぜそぞただちぢっつづてでとどなにぬねのはばぱひびぴふぶぷへべぺほぼぽまみむめもゃやゅゆょよらりるれろゎわゐゑをん、。「」！？ー・…")
ANSWERS = ["RATS", "SEADOG", "PRIMARY", "SUBLEVEL", "YOUTH", "TEARS", "BLINK", "EYES", "WARP", "CREATORS",
           "CIRCLE", "WEEDS", "JVCIII", "FREEMAN", "DOOMED", "REDHOT", "BLASTOFF"]
PRINTF = re.compile(r"%[-+ 0#]*[0-9]*(?:\.[0-9]+)?[lh]?[a-zA-Z]")


def printf_specs(t):
    """%の書式の並び。%.0s（引数を読むだけで何も出さない）は %s とも %c とも合うものとして扱う"""
    return ["%s" if x in ("%.0s", "%c") else x for x in PRINTF.findall(t)]


def est_bytes(t):
    n = 0
    for ch in from_text(t):
        if ord(ch) < 0x80:
            n += 1
        elif ch in ONE:
            n += 1
        else:
            n += 2
    return n


def load_font():
    sys.path.insert(0, HERE)
    from build_mm3jp import load_bdf, BDF
    return load_bdf(BDF)


def load_keep_cc():
    keep = {}
    f = os.path.join(TR, "keep_cc.tsv")
    if os.path.exists(f):
        for l in open(f, encoding="utf-8"):
            p = l.rstrip("\n").split("\t")
            if len(p) == 3:
                keep[p[0]] = (p[1], p[2])
    return keep


KEEP_CC = load_keep_cc()
# 答えの語（看板は除く）。文の中にこの語が出たら、訳に英語を添える
ANSWER_WORDS = ["Smello", "Joabary", "Nortic", "Epsilon"]   # 答えになる固有名詞（ふつうの語は除く）


def check_group(name, font, out_lines):
    src = os.path.join(TR, "work", name + ".tsv")
    dst = os.path.join(TR, "work", "out", name + ".tsv")
    en = [l.rstrip("\n").split("\t") for l in open(src, encoding="utf-8") if l.strip()]
    if not os.path.exists(dst):
        out_lines.append(f"[{name}] 訳がまだない")
        return {}, []
    ja = {}
    terms = []
    for l in open(dst, encoding="utf-8-sig"):
        l = l.rstrip("\n").rstrip("\r")
        if not l.strip():
            continue
        if l.startswith("#TERM"):
            terms.append(l[5:].strip())
            continue
        if l.startswith("#"):
            continue
        if "\t" not in l:
            out_lines.append(f"[{name}] タブのない行: {l[:60]}")
            continue
        k, t = l.split("\t", 1)
        ja[k.strip()] = t
    probs = []
    for k, lim, t in en:
        lim = int(lim)
        if k not in ja:
            probs.append(f"{k} 訳がない")
            continue
        j = ja[k]
        if k in KEEP_CC:
            ja[k] = "KEEP"
            continue
        if j == "KEEP":
            continue
        raw_en = re.sub(r"\{[^}]*\}", "", t).replace("\\n", " ").strip()
        if re.fullmatch(r"[A-Z0-9 ']{2,}", raw_en) and k.startswith("C"):
            probs.append(f"{k} 答えの行は KEEP にする: {t}")
        try:
            from_text(j)
        except ValueError as e:
            probs.append(f"{k} {e}: {j}")
            continue
        if tokens(t) != tokens(j):
            probs.append(f"{k} 書式の印が違う: 英 {' '.join(tokens(t))} / 訳 {' '.join(tokens(j))}")
        if printf_specs(t) != printf_specs(j):
            probs.append(f"{k} %の書式が違う: 英 {PRINTF.findall(t)} / 訳 {PRINTF.findall(j)}")
        if re.search(r"(?<!\\)[{}]", re.sub(r"\{[^{}]*\}", "", j)):
            probs.append(f"{k} {{ }} が残っている: {j}")
        b = est_bytes(j)
        if b > lim:
            probs.append(f"{k} 長い（約 {b} > 上限 {lim}）: {j}")
        for a in ANSWERS:
            if re.search(r"\b%s\b" % a, t) and a not in j:
                probs.append(f"{k} 答え {a} が訳にない: {j}")
        for a in ANSWER_WORDS:
            if a.upper() in ANSWERS:
                continue
            if re.search(r"\b%s\b" % re.escape(a), t, re.I) and a.lower() not in j.lower():
                probs.append(f"{k} 答えの語 {a} を英語で添える: {j}")
        miss =sorted(set(ch for ch in from_text(j) if ord(ch) >= 0x80 and ord(ch) not in font))
        if miss:
            probs.append(f"{k} フォントにない字 {''.join(miss)}: {j}")
    extra = [k for k in ja if k not in {e[0] for e in en}]
    if extra:
        probs.append(f"知らない鍵: {' '.join(extra[:10])}")
    out_lines.append(f"[{name}] {len(ja)}/{len(en)} 行、問題 {len(probs)}")
    out_lines += ["  " + p for p in probs]
    return ja, terms


def main():
    font = load_font()
    names = sorted(f[:-4] for f in os.listdir(os.path.join(TR, "work")) if f.endswith(".tsv"))
    if len(sys.argv) > 2 and sys.argv[1] == "--only":
        n = sys.argv[2].replace(".tsv", "")
        lines = []
        check_group(n, font, lines)
        print("\n".join(lines))
        return
    lines = []
    allja = {}
    allterms = []
    for n in names:
        ja, terms = check_group(n, font, lines)
        allja.update(ja)
        allterms += [f"{n}\t{t}" for t in terms]
    fix = os.path.join(TR, "ja_fix.txt")
    if os.path.exists(fix):
        for l in open(fix, encoding="utf-8"):
            l = l.rstrip("\n")
            if l and not l.startswith("#") and "\t" in l:
                k, t = l.split("\t", 1)
                allja[k] = t
    open(os.path.join(TR, "ja.tsv"), "w", encoding="utf-8", newline="\n").write(
        "".join(f"{k}\t{v}\n" for k, v in sorted(allja.items())))
    open(os.path.join(TR, "work", "check.txt"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    open(os.path.join(TR, "work", "terms.txt"), "w", encoding="utf-8").write("\n".join(allterms) + "\n")
    print("\n".join(l for l in lines if l.startswith("[")))
    print(f"訳 {len(allja)} 件 → translation/ja.tsv、検査 → translation/work/check.txt")


if __name__ == "__main__":
    main()
