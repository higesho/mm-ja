# -*- coding: utf-8 -*-
"""訳す文を抜き出して translation/src/<組>.tsv（鍵<TAB>英文）を作る。

鍵: <組>:<行番号>:<欄>[:<行の識別>]  ※行番号は 0 始まり（見出し行を含む）
会話（RUDE の NPC*.RUDE）は組 rude、鍵は rude:<NPC番号>:<行>:<欄>
文の中の改行は \\n、タブは \\t と書く。
"""
import os
import re
import sys
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import table
import spec

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXT = os.path.join(ROOT, 'extract')
SRC = os.path.join(ROOT, 'translation', 'src')


def src_path(p):
    top = p.split('/')[0]
    return os.path.join(EXT, top, p)


def esc(b):
    s = b.decode('cp1252', 'replace')
    return s.replace('\\', '\\\\').replace('\r\n', '\\n').replace('\n', '\\n').replace('\t', '\\t')


def worth(b):
    s = b.strip()
    if not s or s.lower() in (b'n/a', b'blank', b'none'):
        return False
    return re.search(rb'[A-Za-z]{2,}', s) is not None


def units_of(group, path, fmt, cols, keycol, header):
    data = open(src_path(path), 'rb').read()
    out = []
    if fmt == 'lines':
        lines = data.split(b'\r\n')
        for i, l in enumerate(lines):
            v = l
            if len(v) >= 2 and v[:1] == b'"' and v[-1:] == b'"':
                v = v[1:-1].replace(b'""', b'"')
            if worth(v):
                out.append(('%s:%d' % (group, i), v))
        return out
    rows = table.parse(data, b'\t' if fmt == 'tsv' else b',')
    for ri, row in enumerate(rows):
        if header and ri == 0:
            continue
        for c in cols:
            if c < len(row) and worth(row[c][2]):
                rid = ''
                if keycol is not None and keycol < len(row):
                    rid = ':' + re.sub(r'[^0-9A-Za-z]', '', row[keycol][2].decode('latin-1'))[:20]
                out.append(('%s:%d:%d%s' % (group, ri, c, rid), row[c][2]))
    return out


def all_units():
    groups = {}
    for (group, path, fmt, cols, keycol, header) in spec.DATA:
        groups[group] = units_of(group, path, fmt, cols, keycol, header)
    pv = []
    for v in spec.PCVOICES:
        for sx in 'MF':
            pv += units_of('pcvoice', 'DATA/PCVOICES/%s%s.CSV' % (v.upper(), sx), 'csv', [3], None, False)
    # 鍵に声の名を入れる
    groups['pcvoice'] = []
    for v in spec.PCVOICES:
        for sx in 'MF':
            for k, t in units_of('pcvoice', 'DATA/PCVOICES/%s%s.CSV' % (v.upper(), sx), 'csv', [3], None, False):
                groups['pcvoice'].append((k.replace('pcvoice:', 'pcvoice:%s%s:' % (v, sx)), t))
    rude = []
    files = sorted(glob.glob(os.path.join(EXT, 'RUDE', 'RUDE', 'NPC[0-9]*.RUDE')),
                   key=lambda f: int(re.search(r'NPC(\d+)', f).group(1)))
    for fn in files:
        n = int(re.search(r'NPC(\d+)', fn).group(1))
        for k, t in units_of('rude', 'RUDE/NPC%d.RUDE' % n, 'csv', [3, 4], None, False):
            rude.append((k.replace('rude:', 'rude:%d:' % n), t))
    groups['rude'] = rude
    # 表示時の辞書で訳す名前（データの中では鍵として使われるので、ファイルは書き換えない）
    for g, path, col in (('dict_monster', 'DATA/MONSTERS.TXT', 1), ('dict_spell', 'DATA/SPELL.TXT', 1)):
        seen = set()
        out = []
        for k, t in units_of(g, path, 'tsv', [col], None, True):
            if t not in seen:
                seen.add(t)
                out.append((k, t))
        groups[g] = out
    return groups


def main():
    os.makedirs(SRC, exist_ok=True)
    groups = all_units()
    total = 0
    for g, us in groups.items():
        with open(os.path.join(SRC, g + '.tsv'), 'w', encoding='utf-8', newline='\n') as f:
            for k, t in us:
                f.write('%s\t%s\n' % (k, esc(t)))
        n = sum(len(t) for _, t in us)
        uniq = len(set(t for _, t in us))
        total += n
        print('%-10s %5d 件 (異なり %5d) %8d 字' % (g, len(us), uniq, n))
    print('合計 %d 字' % total)


if __name__ == '__main__':
    main()
