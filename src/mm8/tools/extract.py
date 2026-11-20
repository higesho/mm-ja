"""訳す文を抜き出す。

txt 表: 行は \\r\\n、欄はタブで切る（ゲームと同じ）。欄の中の改行は \\n。
欄の頭が " なら前後の 1 字ずつは引用符（ゲームは頭の " と最後の字を外す）。
STR: NUL で区切った文の並び。

出力 translation/en.tsv: 番号<TAB>英文（改行は \\n、タブはない）
番号は txt なら「ファイル:行:列」、STR なら「ファイル#番号」。
"""
import os, sys, glob, re, json

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, '..', 'raw', 'EnglishT')
OUT = os.path.join(HERE, '..', 'translation', 'en.tsv')

# ファイル: (見出しの行数, 訳す列)
COLS = {
    '2DEvents.txt': (2, [5, 6, 7]),
    'Autonote.txt': (1, [1]),
    'Awards.txt': (1, [1]),
    'Global.txt': (2, [1]),
    'ITEMS.txt': (2, [2, 10, 16]),
    'MONSTERS.txt': (2, [1]),
    'NPCDATA.txt': (2, [1]),
    'NPCNEWS.txt': (1, [1]),
    'Quest.txt': (1, [1]),
    'quests.txt': (1, [1]),
    'Skilldes.txt': (1, [1, 2, 3, 4, 5]),
    'Spells.txt': (2, [2, 4, 5, 6, 7, 8, 9]),
    'class.txt': (1, [1]),
    'history.txt': (1, [1, 3]),
    'mapstats.txt': (3, [1]),
    'npcgreet.txt': (1, [1, 2]),
    'npctext.txt': (1, [1]),
    'npctopic.txt': (1, [1]),
    'placemon.txt': (1, [1]),
    'roster.txt': (2, [1]),
    'scroll.txt': (1, [1]),
    'stats.txt': (1, [1]),
    'trans.txt': (1, [1]),
    'MERCHANT.TXT': (1, [1, 2, 3, 4]),
    'SPCITEMS.TXT': (4, [0, 1]),
    'STDITEMS.TXT': (4, [1]),
    'DECLIST.TXT': (2, [2]),       # 装飾物の名前（見ると状態表示行に出る）
}


def split_rows(data):
    """ゲームと同じ切り方: \\r で切り、行頭の \\n を外す"""
    return data.split(b'\r\n')


def cell_text(raw):
    """欄の生のバイト → 画面に出る文（引用符を外す）"""
    if raw.startswith(b'"'):
        raw = raw[1:-1]
    return raw


def find_raw(name):
    for f in os.listdir(RAW):
        if f.lower() == name.lower():
            return os.path.join(RAW, f)
    raise FileNotFoundError(name)


def is_text(s):
    s = s.strip()
    if not s:
        return False
    if re.fullmatch(rb'[-+0-9., %dx]*', s):
        return False
    if s in (b'n/a', b'null', b'0', b'pending', b'dec03'):
        return False
    return True


IMG = os.path.join(HERE, '..', 'ana', 'img.bin')    # MM8-Rel.exe を読み込んだ形（0x400000 から）
EXE_PTR = [0x40b236 + 1, 0x40b726 + 1, 0x40eb43 + 1,  # mov ecx, 文 の文のところ（アルコメイジ）
           0x433144 + 1,                                # push 文（時刻の表示の書式）
           0x41de1d, 0x41de43, 0x41de77, 0x41deb3, 0x41def7, 0x41df43,  # 呪文の残り時間（Duration: と単位）
           0x48e893]                                    # 射撃のダメージがないときの N/A
CARD_BASE, CARD_SIZE, CARD_N = 0x4f2218, 0x6c, 102   # アルコメイジのカード（+0x10 に名前 32 バイト）


def exe_str(img, va):
    o = va - 0x400000
    return img[o:img.index(bytes([0]), o)]


def extract_exe():
    """exe の中の文。番号 @ptr#番地（命令の中の文の番地を差し替える）、@inline#番地（その場に書く、31 バイトまで）"""
    import struct
    img = open(IMG, 'rb').read()
    out = []
    for a in EXE_PTR:
        va = struct.unpack_from('<I', img, a - 0x400000)[0]
        out.append((f'@ptr#{a:x}', exe_str(img, va)))
    for n in range(CARD_N):
        va = CARD_BASE + n * CARD_SIZE + 0x10
        out.append((f'@inline#{va:x}', exe_str(img, va)))
    return out


def esc(b):
    s = b.decode('cp1252', errors='replace')
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('\t', '\\t')


def extract():
    out = []
    for name, (head, cols) in COLS.items():
        rows = split_rows(open(find_raw(name), 'rb').read())
        for r, row in enumerate(rows):
            if r < head:
                continue
            cells = row.split(b'\t')
            for c in cols:
                if c < len(cells) and is_text(cell_text(cells[c])):
                    out.append((f'{name}:{r}:{c}', cell_text(cells[c])))
    out += extract_exe()
    for f in sorted(os.listdir(RAW)):
        if f.lower().endswith('.str'):
            parts = open(os.path.join(RAW, f), 'rb').read().split(b'\0')
            for i, p in enumerate(parts):
                if is_text(p):
                    out.append((f'{f}#{i}', p))
    return out


if __name__ == '__main__':
    out = extract()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='\n') as fp:
        for k, v in out:
            fp.write(f'{k}\t{esc(v)}\n')
    tot = sum(len(v) for k, v in out)
    uniq = {}
    for k, v in out:
        uniq.setdefault(v, k)
    print(f'{len(out)} 件 {tot} バイト（重複を除くと {len(uniq)} 件 {sum(len(v) for v in uniq)} バイト）')
    per = {}
    for k, v in out:
        f = re.split(r'[:#]', k)[0]
        per.setdefault(f, [0, 0])
        per[f][0] += 1
        per[f][1] += len(v)
    for f, (n, b) in sorted(per.items(), key=lambda x: -x[1][1])[:40]:
        print(f'  {f:16s} {n:6d} {b:8d}')
