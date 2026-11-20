"""訳（translation/ja*.tsv）から DLL が読む jp/mm8jp.dat を作る。

ja*.tsv: 番号<TAB>訳（改行は \\n）。番号は extract.py と同じ。
同じ英文には同じ訳を使えるよう、translation/en.tsv の英文が同じものへ訳を写す（番号の訳がないとき）。

dat の形:
  "MM8JPDAT", u32 ファイル数
  ファイルごとに: 名前 64, u32 件数, 件ごとに u32 番号, u32 原文の欄の CRC32, u32 長さ, 訳のバイト
  txt の番号は 行<<8 | 欄、STR は番号。件は番号の順。
"""
import os, sys, re, glob, struct, zlib, unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extract

HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, '..', 'translation')
OUT = os.path.join(HERE, '..', '..', 'jp', 'mm8jp.dat')

# cp932 に無い字・使わない字の置き換え
FIX = {'©': '(C)', '®': '(R)', '™': '(TM)', '〜': '～', '−': '－', '—': '―', '–': '－', '‐': '－', '¢': '￠', '£': '￡', '¬': '￢', '‖': '∥',
       '"': '”', '…': '…', '･': '・', '　': '　'}


def unesc(s):
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            out.append({'n': '\n', 't': '\t', '\\': '\\'}.get(c, '\\' + c))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def load_tsv(path):
    d = {}
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#') or '\t' not in line:
            continue
        k, v = line.split('\t', 1)
        d[k] = unesc(v)
    return d


def font_have():
    """東雲フォントにある区点（JIS）"""
    have = set()
    for l in open(os.path.join(HERE, '..', 'font', 'shnmk14.bdf'), encoding='latin1'):
        if l.startswith('ENCODING'):
            have.add(int(l.split()[1]))
    return have


HAVE = None


def encode(s, key, errs):
    global HAVE
    if HAVE is None:
        HAVE = font_have()
    t = ''.join(FIX.get(c, c) for c in s)
    # 半角カナは全角に
    t = ''.join(unicodedata.normalize('NFKC', c) if '｡' <= c <= 'ﾟ' else c for c in t)
    try:
        b = t.encode('cp932')
    except UnicodeEncodeError as e:
        errs.append(f'{key}: 符号にできない字 {t[e.start:e.end]!r}')
        b = t.encode('cp932', errors='replace')
    # 2 バイトの字がフォントにあるか
    i = 0
    while i < len(b):
        c = b[i]
        if (0x81 <= c <= 0x9f or 0xe0 <= c <= 0xfc) and i + 1 < len(b):
            # DLL と同じ計算で区点を出し、フォントにあるか見る
            a, t2 = c, b[i + 1]
            ku = (a - (0x81 if a < 0xa0 else 0xc1)) * 2 + 1
            if t2 >= 0x9f:
                ku += 1; ten = t2 - 0x9f + 1
            else:
                ten = t2 - 0x40 + 1 - (1 if t2 >= 0x80 else 0)
            if ((ku + 0x20) << 8 | (ten + 0x20)) not in HAVE:
                errs.append(f'{key}: フォントにない字 {b[i:i + 2].decode("cp932", errors="replace")!r}')
            i += 2
        elif c >= 0x80:
            errs.append(f'{key}: 1 バイトの高位の字 {bytes([c])!r}')
            i += 1
        else:
            i += 1
    return b


def fmt_specs(b):
    return re.findall(rb'%[-+0#]*\d*(?:\.\d+)?l?[sdiuxXc]', b)


def build(verbose=True):
    src = extract.extract()                     # [(番号, 原文の文)]
    en = dict(src)
    ja = {}
    # 作業の出力 → ja*.tsv（手直し。後から読むほうが勝つ）の順
    for p in sorted(glob.glob(os.path.join(TR, 'work', '*_out.tsv'))) + sorted(glob.glob(os.path.join(TR, 'ja*.tsv'))):
        ja.update(load_tsv(p))
    ja = {k: v for k, v in ja.items() if v != 'KEEP'}
    # 同じ英文 → 同じ訳
    by_en = {}
    for k, v in src:
        if k in ja:
            by_en.setdefault(v, ja[k])
    files = {}
    errs, warns = [], []
    n_direct = n_copy = 0
    for k, v in src:
        if k in ja:
            t = ja[k]; n_direct += 1
        elif v in by_en:
            t = by_en[v]; n_copy += 1
        else:
            continue
        m = re.fullmatch(r'(.+?):(\d+):(\d+)', k)
        if k.startswith('@'):
            name, addr = k.split('#')
            key = int(addr, 16)
            raw = v
            quoted = False
            b = encode(t, k, errs)
            if name == '@inline' and len(b) > 31:
                errs.append(f'{k}: カード名が 31 バイトを超える ({len(b)})')
            files.setdefault(name, []).append((key, zlib.crc32(raw) & 0xffffffff, b))
            continue
        if m:
            name, row, col = m.group(1), int(m.group(2)), int(m.group(3))
            key = (row << 8) | col
            rows = extract.split_rows(open(extract.find_raw(name), 'rb').read())
            raw = rows[row].split(b'\t')[col]
            quoted = raw.startswith(b'"')
        else:
            name, idx = k.split('#')
            key = int(idx)
            raw = open(extract.find_raw(name), 'rb').read().split(b'\0')[key]
            quoted = False
        t = re.sub(r'%32(?!の)', '%32の', t)      # 所有格の印（彼／彼女 + の）
        b = encode(t, k, errs)
        if b'\t' in b or b'\r' in b:
            errs.append(f'{k}: タブか \\r が入っています')
        if fmt_specs(b) != fmt_specs(v):
            errs.append(f'{k}: 書式が違う {fmt_specs(v)} → {fmt_specs(b)}')
        # \f の色指定（\f + 5 桁）は数を合わせる
        if b.count(b'\x0c') != v.count(b'\x0c'):
            warns.append(f'{k}: 色の指定の数が違う')
        if name.lower().endswith('.str') and len(b) >= 800:
            errs.append(f'{k}: STR の 1 文が 800 バイト以上')
        if quoted:
            b = b'"' + b + b'"'
        files.setdefault(name, []).append((key, zlib.crc32(raw) & 0xffffffff, b))
    out = bytearray(b'MM8JPDAT')
    out += struct.pack('<I', len(files))
    for name in sorted(files):
        ents = sorted(files[name])
        out += name.encode('ascii').ljust(64, b'\0')
        out += struct.pack('<I', len(ents))
        for key, crc, b in ents:
            out += struct.pack('<III', key, crc, len(b)) + b
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'wb').write(out)
    if verbose:
        print(f'訳 {n_direct} 件、同じ英文から写した {n_copy} 件、全 {len(src)} 件中。{len(out)} バイト')
        for e in errs[:50]:
            print('誤り', e)
        for w in warns[:20]:
            print('注意', w)
    return errs


if __name__ == '__main__':
    errs = build()
    sys.exit(1 if errs else 0)
