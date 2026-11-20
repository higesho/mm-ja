"""英文を translation/en/<ファイル>.tsv に抜き出す（キー<TAB>英文、改行は \\n と書く）。STR はまとめて STR.tsv。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tables

HERE = os.path.dirname(os.path.abspath(__file__))
EN = os.path.join(HERE, '..', 'translation', 'en')


def esc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def unesc(s):
    out = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\'}.get(n, '\\' + n))
            i += 2
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def main():
    os.makedirs(EN, exist_ok=True)
    groups = {}
    for name in tables.all_files():
        data = open(os.path.join(tables.ORIG, name), 'rb').read()
        base = 'STR' if name.upper().endswith('.STR') else name
        groups.setdefault(base, []).extend(tables.units(name, data))
    for base, us in groups.items():
        with open(os.path.join(EN, base + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
            for k, s in us:
                f.write(k + '\t' + esc(s) + '\n')
    print(sum(len(v) for v in groups.values()), '件')


if __name__ == '__main__':
    main()
