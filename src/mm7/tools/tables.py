"""MM7 の txt 表（Excel 書き出しのタブ区切り）と STR を、元の形を崩さずに読み書きする。

表: 行の区切りは \\r\\n。欄は \\t 区切り。"..." で囲んだ欄の中には \\n（\\r なし）や "" が入る。
欄はそのままの文字列（囲みの " も含む）で持ち、訳を入れるときだけ作り直す。
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORIG = os.path.join(HERE, '..', 'orig', 'events')

# 訳す列（0 から数える）。見出しの行は抜かない（数字で始まる行などは問わず、中身があれば訳す）
# skip: 先頭から何行を見出しとして飛ばすか
SPEC = {
    '2DEvents.txt': dict(skip=2, cols=[5, 6, 7]),
    'AUTONOTE.TXT': dict(skip=1, cols=[1]),
    'AWARDS.TXT':   dict(skip=1, cols=[1]),
    'CLASS.TXT':    dict(skip=1, cols=[1]),
    'Global.txt':   dict(skip=2, cols=[1]),
    'HISTORY.TXT':  dict(skip=1, cols=[1, 3]),
    'ITEMS.TXT':    dict(skip=1, cols=[2, 10, 16]),
    'MAPSTATS.TXT': dict(skip=3, cols=[1]),
    'MERCHANT.TXT': dict(skip=1, cols=[1, 2, 3, 4]),
    'MONSTERS.TXT': dict(skip=4, cols=[1]),
    'NPCNAMES.TXT': dict(skip=1, cols=[0, 1]),
    'NPCNEWS.TXT':  dict(skip=1, cols=[1]),
    'NPCPROF.TXT':  dict(skip=4, cols=[1, 3, 4, 5, 6]),
    'NPCTEXT.TXT':  dict(skip=1, cols=[1]),
    'NPCTOPIC.TXT': dict(skip=1, cols=[1]),
    'Npcdata.txt':  dict(skip=2, cols=[1]),
    'npcgreet.txt': dict(skip=1, cols=[1, 2]),
    'PlaceMon.txt': dict(skip=1, cols=[1]),
    'POTION.TXT':   dict(skip=1, cols=[1, 2, 3]),
    'POTNOTES.TXT': dict(skip=1, cols=[1, 2, 3]),
    'QUESTS.TXT':   dict(skip=1, cols=[1]),
    'SCROLL.TXT':   dict(skip=1, cols=[1]),
    'SKILLDES.TXT': dict(skip=1, cols=[1, 2, 3, 4, 5]),
    'SPCITEMS.TXT': dict(skip=4, cols=[0, 1]),
    'SPELLS.TXT':   dict(skip=2, cols=[2, 4, 5, 6, 7, 8, 9]),
    'STATS.TXT':    dict(skip=1, cols=[1]),
    'STDITEMS.TXT': dict(skip=4, cols=[1]),
    'TRANS.TXT':    dict(skip=1, cols=[1]),
}


def parse(data):
    """bytes → 行のリスト。行は欄（bytes、囲みの " を含む生のまま）のリスト。最後の区切りの有無も返す。"""
    rows = []
    row = []
    i = 0
    n = len(data)
    start = 0
    while i <= n:
        if i < n and data[i:i+1] == b'"' and i == start:
            # 囲み欄: 閉じの " （"" でない）まで
            j = i + 1
            while j < n:
                if data[j:j+1] == b'"':
                    if data[j+1:j+2] == b'"':
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            continue
        if i == n or data[i:i+1] in (b'\t', b'\r', b'\n'):
            row.append(data[start:i])
            if i == n:
                rows.append(row)
                break
            if data[i:i+1] == b'\t':
                i += 1
            else:
                rows.append(row)
                row = []
                if data[i:i+2] == b'\r\n':
                    i += 2
                else:
                    i += 1
            start = i
            continue
        i += 1
    return rows


def unparse(rows):
    return b'\r\n'.join(b'\t'.join(r) for r in rows)


def cell_text(raw):
    """生の欄 → 中身の文字列（囲みを外し "" を " に）。cp1252 で読む"""
    s = raw.decode('cp1252')
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].replace('""', '"')
    return s


def make_cell(text, orig_raw):
    """訳 → 生の欄（Shift_JIS）。元が囲みなら囲む。改行や " を含むときも囲む"""
    b = text.encode('cp932')
    quoted = orig_raw[:1] == b'"' or b'\n' in b or b'\t' in b or b'"' in b
    if quoted:
        return b'"' + b.replace(b'"', b'""') + b'"'
    return b


def read_str(data):
    """STR: \\0 区切り"""
    parts = data.split(b'\0')
    return parts


def units(name, data):
    """訳す単位: (キー, 英文) を返す"""
    out = []
    if name.upper().endswith('.STR'):
        for i, p in enumerate(read_str(data)):
            s = p.decode('cp1252')
            if s.strip():
                out.append((f'{name}:{i}', s))
        return out
    spec = SPEC[name]
    rows = parse(data)
    for r, row in enumerate(rows):
        if r < spec['skip']:
            continue
        for c in spec['cols']:
            if c < len(row):
                s = cell_text(row[c])
                if s.strip() and any(ch.isalpha() for ch in s):
                    out.append((f'{name}:{r}:{c}', s))
    return out


def apply(name, data, tr):
    """tr: キー → 訳。訳のある欄だけ置き換えた bytes を返す"""
    if name.upper().endswith('.STR'):
        parts = read_str(data)
        for i in range(len(parts)):
            k = f'{name}:{i}'
            if k in tr:
                parts[i] = tr[k].encode('cp932')
        return b'\0'.join(parts)
    rows = parse(data)
    for r, row in enumerate(rows):
        for c in range(len(row)):
            k = f'{name}:{r}:{c}'
            if k in tr:
                row[c] = make_cell(tr[k], row[c])
    return unparse(rows)


def all_files():
    names = sorted(SPEC)
    for f in sorted(os.listdir(ORIG)):
        if f.upper().endswith('.STR'):
            names.append(f)
    return names


if __name__ == '__main__':
    # 確かめ: 読んで書き戻すと元と同じか
    total = 0
    for name in all_files():
        data = open(os.path.join(ORIG, name), 'rb').read()
        if not name.upper().endswith('.STR'):
            back = unparse(parse(data))
            assert back == data, name
        u = units(name, data)
        total += sum(len(s) for k, s in u)
        print(f'{name:14} {len(u):5} 件 {sum(len(s) for k, s in u):7} 字')
    print('合計', total)
