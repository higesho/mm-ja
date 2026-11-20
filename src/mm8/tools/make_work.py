"""手分けして訳すための作業ファイルを translation/work/ に作る。

同じ英文は 1 回だけ出す（build_dat.py が同じ英文に同じ訳を写す）。
組（phase）A: 名前・短い語（用語集のもとになる）、B: 長い文。
入力: work/<組>_in.tsv（番号<TAB>英文）、出力は訳す人が work/<組>_out.tsv（番号<TAB>訳）に書く。
"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, '..', 'translation', 'work')

# 組の決め方: (名前, 番号に合う正規表現, 1 組の英文の最大バイト数)
GROUPS = [
    ('A1_ui', r'^(Global\.txt|SPCITEMS\.TXT|STDITEMS\.TXT|MERCHANT\.TXT):|^Spells\.txt:\d+:[24]$|^Skilldes\.txt:', 40000),
    ('A2_names', r'^(NPCDATA\.txt|placemon\.txt|roster\.txt|mapstats\.txt|2DEvents\.txt):', 40000),
    ('A3_things', r'^(MONSTERS\.txt|npctopic\.txt):|^ITEMS\.txt:\d+:(2|10)$', 40000),
    ('B', r'.', 26000),
]


def disp(b):
    """表の欄の文 → 訳す人に見せる形（"" は " に、改行は \\n）"""
    s = b.decode('cp1252', errors='replace').replace('""', '"')
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def main():
    os.makedirs(WORK, exist_ok=True)
    src = extract.extract()
    seen = set()
    groups = {g[0]: [] for g in GROUPS}
    for k, v in src:
        if v in seen:
            continue
        seen.add(v)
        for name, pat, _ in GROUPS:
            if re.search(pat, k):
                groups[name].append((k, v))
                break
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, pat, lim in GROUPS:
        if only and name != only:
            continue
        items = groups[name]
        parts, cur, size = [], [], 0
        for k, v in items:
            if cur and size + len(v) > lim:
                parts.append(cur); cur, size = [], 0
            cur.append((k, v)); size += len(v)
        if cur:
            parts.append(cur)
        for i, part in enumerate(parts):
            fn = f'{name}{i + 1:02d}_in.tsv' if len(parts) > 1 else f'{name}_in.tsv'
            with open(os.path.join(WORK, fn), 'w', encoding='utf-8', newline='\n') as fp:
                for k, v in part:
                    fp.write(f'{k}\t{disp(v)}\n')
            print(f'{fn}: {len(part)} 件 {sum(len(v) for _, v in part)} バイト')


if __name__ == '__main__':
    main()
