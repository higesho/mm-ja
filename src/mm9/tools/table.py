# -*- coding: utf-8 -*-
"""CSV / TSV を「欄の位置」を保ったまま読む・書き換える。

parse(data, delim) → 行のリスト。各行は欄のリスト、欄は (start, end, value)。
  start/end は元のバイト列での欄の範囲（引用符を含む）。value は引用を解いた bytes。
replace(data, edits) → edits = {(start, end): 新しい value(bytes)} を当てた bytes。
  新しい値は、区切り・引用符・改行を含むなら引用符で囲む。元が引用されていれば囲む。
"""


def parse(data, delim=b','):
    d = delim[0]
    rows = []
    row = []
    i = 0
    n = len(data)
    while i < n:
        start = i
        if data[i] == 0x22:  # "
            i += 1
            buf = bytearray()
            while i < n:
                if data[i] == 0x22:
                    if i + 1 < n and data[i + 1] == 0x22:
                        buf.append(0x22)
                        i += 2
                        continue
                    i += 1
                    break
                buf.append(data[i])
                i += 1
            # 閉じ引用符の後ろに余計な字があれば欄の終わりまで足す
            while i < n and data[i] not in (d, 0x0d, 0x0a):
                buf.append(data[i])
                i += 1
            row.append((start, i, bytes(buf)))
        else:
            while i < n and data[i] not in (d, 0x0d, 0x0a):
                i += 1
            row.append((start, i, data[start:i]))
        if i < n and data[i] == d:
            i += 1
            if i == n or data[i] in (0x0d, 0x0a):
                row.append((i, i, b''))
            continue
        # 行の終わり
        if i < n and data[i] == 0x0d:
            i += 1
        if i < n and data[i] == 0x0a:
            i += 1
        rows.append(row)
        row = []
    if row:
        rows.append(row)
    return rows


def quote(value, was_quoted, delim=b','):
    need = was_quoted or any(c in value for c in (delim[0], 0x22, 0x0d, 0x0a))
    if not need:
        return value
    return b'"' + value.replace(b'"', b'""') + b'"'


def replace(data, edits, delim=b','):
    out = bytearray()
    pos = 0
    for (s, e) in sorted(edits):
        out += data[pos:s]
        was_quoted = e > s and data[s] == 0x22
        out += quote(edits[(s, e)], was_quoted, delim)
        pos = e
    out += data[pos:]
    return bytes(out)
