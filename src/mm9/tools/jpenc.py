# -*- coding: utf-8 -*-
"""日本語の文を MM9 用の自前の2バイト符号にする（ASCII はそのまま）。"""
import os

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
_MAP = None

# 全角に直してから引く字（半角のままだと英字フォントの字になる記号は対象外）
_ALIAS = {'～': '〜', '－': '−', '—': '―', '∥': '‖', '￠': '¢', '￡': '£', '￢': '¬'}


def charmap():
    global _MAP
    if _MAP is None:
        _MAP = {}
        for line in open(os.path.join(ROOT, 'build', 'charmap.tsv'), encoding='utf-8'):
            ch, code = line.rstrip('\n').split('\t')
            _MAP[ch] = int(code, 16)
    return _MAP


class EncodeError(Exception):
    pass


def encode(text, missing=None):
    """文字列 → bytes。表に無い字は missing（集合）に足すか、例外にする"""
    m = charmap()
    out = bytearray()
    for ch in text:
        o = ord(ch)
        if o < 0x80:
            out.append(o)
            continue
        ch = _ALIAS.get(ch, ch)
        code = m.get(ch)
        if code is None:
            if missing is not None:
                missing.add(ch)
                out += b'?'
                continue
            raise EncodeError('表に無い字: %r（%s）' % (ch, text[:40]))
        out.append(code >> 8)
        out.append(code & 0xFF)
    return bytes(out)


def decode(data):
    inv = {v: k for k, v in charmap().items()}
    out = []
    i = 0
    while i < len(data):
        c = data[i]
        if 0x80 <= c < 0xC0 and i + 1 < len(data) and data[i + 1] >= 0xC0:
            out.append(inv.get((c << 8) | data[i + 1], '?'))
            i += 2
        else:
            out.append(chr(c))
            i += 1
    return ''.join(out)
