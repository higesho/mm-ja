"""用語の割れを調べる。英文に固有名詞（names.tsv の人・地図・店の名前、用語集の表）が出るのに、
訳にその訳語が無い行を数える。使い方: python tools/check_terms.py [詳しく出す語]"""
import os, sys, re, glob, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import unesc
import collect

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')


def terms():
    t = {}
    # 名前の一覧のうち、人・地図・店（固有名詞）
    en = collect.en_map()
    out, _ = collect.read_out()
    for k, s in en.items():
        f = k.split(':')[0]
        col = k.split(':')[-1]
        if (f in ('Npcdata.txt', 'MAPSTATS.TXT') or (f == '2DEvents.txt' and col in ('5', '6'))) and k in out and out[k] != 'KEEP':
            if len(s) >= 4 and s[0].isupper():
                t.setdefault(s, unesc(out[k]))
    # 用語集の表（| 英語 | 日本語 |、/ で並んだものは組にする）
    for line in open(os.path.join(TR, '用語集.md'), encoding='utf-8'):
        m = re.match(r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', line)
        if not m or m.group(1) in ('英語', '---'):
            continue
        es = [x.strip() for x in re.sub(r'（.*?）|\(.*?\)', '', m.group(1)).split('/')]
        js = [x.strip() for x in re.sub(r'（.*?）', '', m.group(2)).split('/')]
        if len(es) == len(js):
            for e, j in zip(es, js):
                if '→' not in e and len(e) >= 4:
                    t[e] = j
    return t


def main():
    t = terms()
    en = collect.en_map()
    tr = {}
    for line in open(os.path.join(TR, 'ja', 'all.tsv'), encoding='utf-8'):
        k, _, v = line.rstrip('\n').partition('\t')
        tr[k] = unesc(v)
    miss = collections.Counter()
    alt = collections.defaultdict(collections.Counter)
    show = sys.argv[1] if len(sys.argv) > 1 else None
    for k, s in en.items():
        if k not in tr:
            continue
        j = tr[k]
        for e, jj in t.items():
            if re.search(r'\b' + re.escape(e) + r'\b', s) and jj not in j:
                miss[e] += 1
                if show == e:
                    print(k, '|', s[:100].replace('\n', ' '), '|', j[:100].replace('\n', ' '))
    for e, n in miss.most_common(80):
        print(n, e, '→', t[e])


if __name__ == '__main__':
    main()
