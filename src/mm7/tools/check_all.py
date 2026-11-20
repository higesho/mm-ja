"""訳の機械検査（全件）。結果は translation/check_report.tsv（種類<TAB>鍵<TAB>英文<TAB>訳）。
- fmt: printf の差し込み（%s %d %lu %u %02d など）の並びが英文と違う
- code: %01〜%34 の組が英文と違う
- quote: 半角の " がある
- char: 東雲に無い字・半角カタカナ
- eng: 訳に英単語（小文字 4 字以上）が残っている
- width: 1 行の短い言葉で、訳の幅（点）が英文の 1.4 倍＋20 点を超える
- nl: 英文に段落の区切りがあるのに訳に改行が無い
- same: 訳が英文と同じ（KEEP でないのに英語のまま）"""
import os, sys, re, struct, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import unesc
import collect, build

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')
FNT = os.path.join(HERE, '..', 'orig', 'fnt', 'Lucida.fnt')

FMT = re.compile(r'%[-+ 0#]*\d*(?:\.\d+)?(?:l|h)?[sdufxXc]|%%')
CODE = re.compile(r'%(?:0[0-9]|[1-3][0-9])(?![0-9])')


def lucida_width():
    t = open(FNT, 'rb').read()
    met = [struct.unpack_from('<iii', t, 32 + 12 * i) for i in range(256)]
    def w(s):
        n = 0
        for ch in s:
            b = ch.encode('cp932', 'replace')
            if len(b) == 2:
                n += 13
            else:
                m = met[b[0]]
                n += m[0] + m[1] + m[2]
        return n
    return w


def fmts(s):
    # %01 などの 2 桁の会話コードは除く
    s2 = CODE.sub('', s)
    return [m.group() for m in FMT.finditer(s2)]


def main():
    en = collect.en_map()
    tr = {}
    for line in open(os.path.join(TR, 'ja', 'all.tsv'), encoding='utf-8'):
        k, _, v = line.rstrip('\n').partition('\t')
        tr[k] = unesc(v)
    width = lucida_width()
    rep = []
    for k, s in en.items():
        if k not in tr:
            continue
        j = tr[k]
        f = k.split(':')[0]
        def add(kind):
            rep.append((kind, k, s, j))
        if fmts(s) != fmts(j):
            add('fmt')
        if sorted(CODE.findall(s)) != sorted(CODE.findall(j)):
            add('code')
        if '"' in j:
            add('quote')
        if not build.check(k, j) if False else any(_bad(ch) for ch in j):
            add('char')
        if re.search(r'[a-z]{4,}', CODE.sub('', FMT.sub('', j))) and not f.upper().endswith('.STR'):
            add('eng')
        if '\n' not in s and len(s) <= 40 and width(j) > width(s) * 1.4 + 20:
            add('width')
        if '\n\n' in s and '\n' not in j:
            add('nl')
        if j == s and re.search('[A-Za-z]{3,}', s):
            add('same')
    with open(os.path.join(TR, 'check_report.tsv'), 'w', encoding='utf-8', newline='\n') as o:
        for kind, k, s, j in rep:
            o.write('\t'.join([kind, k, s.replace('\n', '\\n'), j.replace('\n', '\\n')]) + '\n')
    c = collections.Counter(r[0] for r in rep)
    print(dict(c))


def _bad(ch):
    try:
        b = ch.encode('cp932')
    except UnicodeEncodeError:
        return True
    if len(b) == 1:
        return b[0] >= 0x80
    return not (0x81 <= b[0] <= 0x84 or 0x88 <= b[0] <= 0x9F or 0xE0 <= b[0] <= 0xEA)


if __name__ == '__main__':
    main()
