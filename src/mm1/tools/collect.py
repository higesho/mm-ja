# 手分けした訳を集めて検査し、translation/ja.txt を作る
#   入力: translation/work/*.tsv（英文）と translation/work/out/*.tsv（訳: 鍵<TAB>訳 / 鍵<TAB>KEEP / #TERM 英語<TAB>訳）
#         translation/ja_fix.txt（手直し: 鍵<TAB>訳。あれば最後に上書き）
#   出力: translation/ja.txt、translation/work/new_terms.txt、translation/work/check.txt（注意の一覧）
#   そのあと build_mmjp.py で組み立てて、幅・折り返し・禁則などの注意も check.txt に足す
# 使い方: python collect.py [--nobuild]
#         python collect.py --only <組の名前>   その組（work/out/<名前>）だけを検査して注意を表示する（ファイルは書かない）
import glob
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")
WORK = os.path.join(TR, "work")

ASCII_OK = set(" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ_")
ICONS = set("`[\\]^")
# 打って答える言葉: 英文にこの語があれば、訳に (語) を添える
# LOVE, CRYSTAL, CURRENT, I BE ME も答えだが、ふつうの語として多く出るので、謎の手がかりの所だけ手で添える
ANSWERS = ["LORD IRONFIST", "IRONFIST", "LARA", "OG"]
KEEP_ALWAYS = {"AREAE3.ca7d", "AREAE3.ca85", "AREAE3.ca8b", "AREAE3.ca94", "AREAE3.ca9c", "AREAE3.caa2", "AREAE3.caa7"}


def load_glossary():
    """用語集の表から、英語と日本語の組（/ で並んだものは順に対応させる）"""
    pairs = []
    sec = ""
    for line in open(os.path.join(TR, "用語集.md"), encoding="utf-8"):
        if line.startswith("## "):
            sec = line[3:].strip()
        if sec not in ("世界・土地", "人"):          # 固有名詞の表だけ調べる
            continue
        if not line.startswith("|") or line.startswith("|---") or "英語" in line:
            continue
        cols = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cols) < 2:
            continue
        en = [re.sub(r"（.*?）|\(.*?\)", "", x).strip() for x in cols[0].split(" / ")]
        ja = [re.sub(r"（.*?）", "", x).strip() for x in cols[1].split(" / ")]
        if len(en) == len(ja):
            for e, j in zip(en, ja):
                for e1, j1 in zip(e.split(", "), j.split("、")) if e.count(", ") == j.count("、") else [(e, j)]:
                    if e1 and j1 and len(e1) >= 3:
                        pairs.append((e1.upper(), j1))
    return pairs


def main():
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    src = {}            # 鍵 → (幅, 途中への参照, 英文, 組の名前)
    order = []
    for path in sorted(glob.glob(os.path.join(WORK, "*.tsv"))):
        if only and os.path.basename(path) != only:
            continue
        name = os.path.basename(path)
        for line in open(path, encoding="utf-8"):
            t = line.rstrip("\n").split("\t")
            if name.startswith("tbl_"):
                src[t[0]] = (int(t[1]), "", t[2], name)
            else:
                src[t[0]] = (int(t[1]), t[2], t[4], name)
            order.append(t[0])
    ja, terms, notes = {}, [], []
    for path in sorted(glob.glob(os.path.join(WORK, "out", "*.tsv"))):
        name = os.path.basename(path)
        if only and name != only:
            continue
        for n, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.rstrip("\n").lstrip("﻿")
            if not line.strip():
                continue
            if line.startswith("#TERM"):
                terms.append(line[5:].strip())
                continue
            if line.startswith("#"):
                continue
            if "\t" not in line:
                notes.append(f"{name}:{n}: タブがない行")
                continue
            k, v = line.split("\t", 1)
            if k not in src:
                notes.append(f"{name}:{n}: 知らない鍵 {k}")
                continue
            ja[k] = v.rstrip()
    fix = os.path.join(TR, "ja_fix.txt")
    if os.path.exists(fix) and not only:
        for line in open(fix, encoding="utf-8"):
            line = line.rstrip("\n")
            if line and not line.startswith("#") and "\t" in line:
                k, v = line.split("\t", 1)
                ja[k] = v
    for k in KEEP_ALWAYS:
        if k in ja:
            ja[k] = "KEEP"
    missing = [k for k in order if k not in ja]
    gloss = load_glossary()
    out = []
    for k in order:
        if k not in ja:
            continue
        v = ja[k]
        w, inner, en, grp = src[k]
        if v == "KEEP":
            continue
        body = re.sub(r"^\{[clr]\}", "", v)
        bad = sorted({c for c in body.replace("\\n", "") if ord(c) < 0x80 and c not in ASCII_OK and c != "|"
                      and not (c in ICONS and c in en)})
        if bad:
            notes.append(f"{k}: 使えない半角の字 {''.join(bad)}: {v}")
        n_in = len([x for x in inner.split(",") if x])
        if body.count("|") != n_in:
            notes.append(f"{k}: | の数 {body.count('|')} が途中への参照 {inner or 'なし'} と合わない")
        for a in ([] if grp.startswith("tbl_") else ANSWERS):
            if re.search(r"(?<![A-Z])" + re.escape(a) + r"(?![A-Z])", en) and f"({a})" not in v and a not in v:
                if not (a == "IRONFIST" and "(LORD IRONFIST)" in v):
                    notes.append(f"{k}: 答えの言葉 {a} が訳に添えられていない")
                break
        for e, j in gloss:
            if re.search(r"(?<![A-Z])" + re.escape(e) + r"(?![A-Z])", en) and j not in v and len(j) >= 2:
                notes.append(f"{k}: 用語「{e}」→「{j}」が訳にない")
        # 幅（1字＝1マス）
        if grp.startswith("tbl_"):
            if len(v) > 14 or "  " in v:
                notes.append(f"{k}: 名前は 14 マス以内、空白2つは不可（{len(v)} マス）: {v}")
        elif "\\n" not in en and "\\n" not in body and "|" not in body and len(en) < 40:
            lead = len(en) - len(en.lstrip(" ")) if not body.startswith(" ") else 0
            trail = len(en) - len(en.rstrip(" ")) if not body.endswith(" ") else 0
            if lead + len(body) + trail > len(en):
                notes.append(f"{k}: 1行の文は英文の幅 {len(en)} マス以内（いま {lead + len(body) + trail}）: {v}")
        elif "|" in body:
            bounds = [0] + [int(x) for x in inner.split(",") if x]
            for i, part in enumerate(body.split("|")[:-1]):
                if i + 1 < len(bounds) and len(part) > bounds[i + 1] - bounds[i]:
                    notes.append(f"{k}: | の前の部分 {i + 1} が {bounds[i + 1] - bounds[i]} マスを超える: {v}")
        for line in body.split("\\n")[1:]:
            if line[:1] in "、。，．・：；？！ー～…」』）ぁぃぅぇぉっゃゅょァィゥェォッャュョ" and line:
                notes.append(f"{k}: 改行の直後が行頭禁則の字「{line[0]}」")
        out.append(f"{k}\t{v}\n")
    # 追加の文字列（X.名前、ja_fix.txt にだけ書く）はそのまま渡す
    out += [f"{k}\t{v}\n" for k, v in ja.items() if k.startswith("X.")]
    if only:
        print(f"{only}: 訳 {len(out)} 件、KEEP {sum(1 for k in order if ja.get(k) == 'KEEP')} 件、まだ {len(missing)} 件")
        if missing:
            print("まだ訳のない鍵:", " ".join(missing))
        print("\n".join(notes) if notes else "注意なし")
        return
    with open(os.path.join(TR, "ja.txt"), "w", encoding="utf-8") as f:
        f.write("# tools/collect.py が work/out と ja_fix.txt から作る。直接は直さない\n")
        f.write("".join(out))
    with open(os.path.join(WORK, "new_terms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(terms) + "\n")
    print(f"訳 {len(out)} 件（KEEP {sum(1 for k in order if ja.get(k) == 'KEEP')}）、まだ {len(missing)} 件、新しい用語 {len(terms)}")
    if "--nobuild" not in sys.argv and out:
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_mmjp.py"), os.path.join(HERE, "..", ".."),
                            os.path.join(TR, "ja.txt"), os.path.join(HERE, "..", "build", "MMJP.COM")],
                           capture_output=True, text=True, encoding="utf-8")
        print(r.stdout.strip())
        if r.returncode:
            print(r.stderr.strip()[-2000:])
        notes.append("--- 組み立て ---")
        notes += r.stdout.strip().splitlines() + ([r.stderr.strip()[-2000:]] if r.returncode else [])
    with open(os.path.join(WORK, "check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(notes) + "\n")
        if missing:
            f.write("--- まだ訳のない鍵 ---\n" + " ".join(missing) + "\n")
    print(f"注意 {len([x for x in notes if not x.startswith('---')])} 件 → translation/work/check.txt")


if __name__ == "__main__":
    main()
