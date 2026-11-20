# -*- coding: utf-8 -*-
"""訳を当てたデータを作る。

translation/ja/*.tsv（鍵<TAB>訳）を読み、元のファイルの該当欄を訳（自前の符号）に置き換えて
build/jpdata/<REZ 内の道筋> に書く。訳の無い欄は英語のまま。
python tools/build_jp.py [install]   install で jp_work/game/data にも写す
"""
import os
import re
import sys
import glob
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import table
import spec
import jpenc
from extract import src_path, units_of

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
JA = os.path.join(ROOT, 'translation', 'ja')
OUT = os.path.join(ROOT, 'build', 'jpdata')
GAME_DATA = os.path.join(ROOT, 'game', 'data')


def unesc(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\'}.get(c, '\\' + c))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def load_ja():
    ja = {}
    for fn in sorted(glob.glob(os.path.join(JA, '*.tsv'))):
        for ln, line in enumerate(open(fn, encoding='utf-8'), 1):
            line = line.rstrip('\n')
            if not line or line.startswith('#'):
                continue
            if '\t' not in line:
                print('書式の誤り %s:%d' % (os.path.basename(fn), ln))
                continue
            k, v = line.split('\t', 1)
            if v.strip():
                ja[k] = v
    return ja


MIXSPACE = re.compile(r'(?<=[^\x00-\x7f]) +(?=[\x21-\x7e])|(?<=[\x21-\x7e]) +(?=[^\x00-\x7f])')


def tidy(s):
    """日本語と英数字の間の空白を除く（ゲームの折り返しは空白で切るので、文の途中で行が割れる）。
    行頭・行末の空白はそのまま"""
    lead = len(s) - len(s.lstrip(' '))
    trail = len(s) - len(s.rstrip(' '))
    core = s[lead:len(s) - trail] if trail else s[lead:]
    core = MIXSPACE.sub('', core)
    return ' ' * lead + core + ' ' * trail


def encode_field(text, orig):
    nl = b'\r\n' if b'\r\n' in orig else b'\n'
    b = jpenc.encode(tidy(unesc(text)), MISSING)
    return b.replace(b'\n', nl) if nl == b'\r\n' else b


MISSING = set()


def build_file(path, fmt, keyprefix, cols, keycol, header, ja, used):
    data = open(src_path(path), 'rb').read()
    if fmt == 'lines':
        lines = data.split(b'\r\n')
        changed = False
        for i, l in enumerate(lines):
            k = '%s:%d' % (keyprefix, i)
            if k in ja:
                v = encode_field(ja[k], l)
                quoted = len(l) >= 2 and l[:1] == b'"' and l[-1:] == b'"'
                lines[i] = table.quote(v, quoted)
                used.add(k)
                changed = True
        return b'\r\n'.join(lines) if changed else None
    delim = b'\t' if fmt == 'tsv' else b','
    rows = table.parse(data, delim)
    edits = {}
    for ri, row in enumerate(rows):
        if header and ri == 0:
            continue
        for c in cols:
            if c >= len(row):
                continue
            rid = ''
            if keycol is not None and keycol < len(row):
                rid = ':' + re.sub(r'[^0-9A-Za-z]', '', row[keycol][2].decode('latin-1'))[:20]
            k = '%s:%d:%d%s' % (keyprefix, ri, c, rid)
            if k in ja:
                s, e, v = row[c]
                edits[(s, e)] = encode_field(ja[k], v)
                used.add(k)
    return table.replace(data, edits, delim) if edits else None


def write(path, data):
    dst = os.path.join(OUT, *path.split('/'))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(data)


def main():
    ja = load_ja()
    used = set()
    n = 0
    for (group, path, fmt, cols, keycol, header) in spec.DATA:
        d = build_file(path, fmt, group, cols, keycol, header, ja, used)
        if d is not None:
            write(path, d)
            n += 1
    for v in spec.PCVOICES:
        for sx in 'MF':
            path = 'DATA/PCVOICES/%s%s.CSV' % (v.upper(), sx)
            d = build_file(path, 'csv', 'pcvoice:%s%s' % (v, sx), [3], None, False, ja, used)
            if d is not None:
                write(path, d)
                n += 1
    for fn in glob.glob(os.path.join(ROOT, 'extract', 'RUDE', 'RUDE', 'NPC[0-9]*.RUDE')):
        num = int(re.search(r'NPC(\d+)', fn).group(1))
        path = 'RUDE/NPC%d.RUDE' % num
        d = build_file(path, 'csv', 'rude:%d' % num, [3, 4], None, False, ja, used)
        if d is not None:
            write(path, d)
            n += 1
    # 表示時の辞書（translation/dict/*.tsv: 英語<TAB>訳）
    dic = {}
    for fn in sorted(glob.glob(os.path.join(ROOT, 'translation', 'dict', '*.tsv'))):
        for line in open(fn, encoding='utf-8'):
            line = line.rstrip('\n')
            if not line or line.startswith('#') or '\t' not in line:
                continue
            en, j = line.split('\t', 1)
            if j.strip():
                dic[unesc(en)] = jpenc.encode(unesc(j), MISSING)
    os.makedirs(os.path.join(OUT, 'jp'), exist_ok=True)
    with open(os.path.join(OUT, 'jp', 'dict.txt'), 'wb') as f:
        for en, j in dic.items():
            f.write(en.encode('cp1252') + b'\t' + j + b'\r\n')
    # 禁則の字
    NOSTART = '、。，．・：；？！ー－～…‥」』）］｝〕〉》】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々'
    NOEND = '「『（［｛〔〈《【'
    m = jpenc.charmap()
    with open(os.path.join(OUT, 'jp', 'kinsoku.txt'), 'w') as f:
        for ch in NOSTART:
            if ch in m:
                f.write('S %04X\n' % m[ch])
        for ch in NOEND:
            if ch in m:
                f.write('E %04X\n' % m[ch])
    print('辞書 %d 語' % len(dic))
    unused = set(ja) - used
    print('訳 %d 件を当てた（ファイル %d）。使われなかった鍵 %d' % (len(used), n, len(unused)))
    for k in sorted(unused)[:20]:
        print('  未使用', k)
    if MISSING:
        print('字の表に無い字:', ''.join(sorted(MISSING)))
        open(os.path.join(ROOT, 'translation', 'extra_chars.txt'), 'a', encoding='utf-8').write(''.join(sorted(MISSING)))
    if 'install' in sys.argv:
        for dirpath, _, files in os.walk(OUT):
            for f in files:
                s = os.path.join(dirpath, f)
                rel = os.path.relpath(s, OUT)
                d = os.path.join(GAME_DATA, rel)
                os.makedirs(os.path.dirname(d), exist_ok=True)
                if os.path.exists(d):
                    os.remove(d)  # ハードリンク先を壊さないよう、消してから書く
                shutil.copyfile(s, d)
        print('game/data に写した')


if __name__ == '__main__':
    main()
