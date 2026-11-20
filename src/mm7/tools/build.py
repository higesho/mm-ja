"""translation/ja/*.tsv（キー<TAB>訳、改行は \n）を集めて、日本語の txt / STR を出力先に書く。
使い方: python tools/build.py [出力先（既定 ../MM7JP）]"""
import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tables

HERE = os.path.dirname(os.path.abspath(__file__))
JA = os.path.join(HERE, '..', 'translation', 'ja')

from extract import unesc

def load_ja():
    tr = {}
    for p in sorted(glob.glob(os.path.join(JA, '*.tsv'))):
        for ln, line in enumerate(open(p, encoding='utf-8'), 1):
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            k, _, v = line.partition('\t')
            tr[k] = unesc(v)
    return tr

def check(k, s):
    bad = []
    for ch in s:
        try:
            b = ch.encode('cp932')
        except UnicodeEncodeError:
            bad.append(ch); continue
        if len(b) == 1 and b[0] >= 0x80:
            bad.append(ch)        # 半角カタカナ
        elif len(b) == 2 and not (0x81 <= b[0] <= 0x84 or 0x88 <= b[0] <= 0x9F or 0xE0 <= b[0] <= 0xEA):
            bad.append(ch)        # JIS X 0208 の外（NEC 特殊文字など）は東雲に無い
    if bad:
        print('使えない字', k, ''.join(bad))
    return not bad

def main():
    """mm7jp.tsv（Shift_JIS、鍵<TAB>訳）を書く。--full なら組み立て済みの txt / STR も書く（確かめ用）"""
    from extract import esc
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    out = args[0] if args else os.path.join(HERE, '..', '..', 'MM7JP')
    os.makedirs(out, exist_ok=True)
    tr = load_ja()
    tr = {k: v for k, v in tr.items() if check(k, v)}
    with open(os.path.join(out, 'mm7jp.tsv'), 'wb') as f:
        f.write('# Might and Magic VII 日本語訳（鍵<TAB>訳）\n'.encode('cp932'))
        for k in sorted(tr, key=lambda k: (k.split(':')[0].upper(), [int(x) for x in k.split(':')[1:]])):
            f.write((k + '\t' + esc(tr[k]) + '\n').encode('cp932'))
    print(f'{len(tr)} 件 → {os.path.join(out, "mm7jp.tsv")}')
    if '--full' in sys.argv:
        full = os.path.join(HERE, '..', 'test', 'full')
        os.makedirs(full, exist_ok=True)
        for name in tables.all_files():
            if not any(k.split(':')[0] == name for k in tr):
                continue
            data = open(os.path.join(tables.ORIG, name), 'rb').read()
            open(os.path.join(full, name), 'wb').write(tables.apply(name, data, tr))
        print('組み立て済みの表 →', full)

if __name__ == '__main__':
    main()
