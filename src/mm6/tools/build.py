"""訳（translation/ja/*.tsv）から mm6jp_text.bin と mm6jp_font.bin を作り、ゲームのフォルダへ置く。

  python build.py            作ってゲームのフォルダへ写す（ddraw.dll は試験版 dll/out/test/ddraw.dll）
  python build.py --check    検査だけ

訳の TSV（UTF-8）: 1 行 1 件、タブ区切り
  key <TAB> en <TAB> ja
  key は表なら 行:列（0 始まり）、文字列集（.str）なら 番号
  en は原文（\\t \\n \\r \\\\ でエスケープ）。組み立て時に元のファイルの欄と照らし合わせる
  ja が空の行は飛ばす
ファイル名は 元のファイル名.tsv（例 GLOBAL.TXT.tsv）
"""
import os, sys, struct, zlib, glob, re

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.abspath(os.path.join(HERE, '..'))
GAME = os.path.abspath(os.path.join(WORK, '..'))
EXTRACT = os.path.join(WORK, 'extract', 'icons')
JA = os.path.join(WORK, 'translation', 'ja')
FONTDIR = os.path.join(WORK, 'font')
OUT = os.path.join(WORK, 'out')


def unesc(s):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == '\\' and i + 1 < len(s):
            n = s[i + 1]
            out.append({'t': '\t', 'n': '\n', 'r': '\r', '\\': '\\'}.get(n, '\\' + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def esc(s):
    return s.replace('\\', '\\\\').replace('\t', '\\t').replace('\n', '\\n').replace('\r', '\\r')


def is_str_file(name):
    return name.lower().endswith('.str')


def split_table(data):
    """表を行・欄に分ける。欄は TAB、行は CR（続く LF も含む）。LF だけは欄の中身（ゲームと同じ）"""
    rows, row, cs, i, n = [], [], 0, 0, len(data)
    while True:
        end = i >= n
        if end or data[i] in (9, 13):
            row.append(data[cs:i])
            if end:
                rows.append(row)
                break
            if data[i] == 13:
                if i + 1 < n and data[i + 1] == 10:
                    i += 1
                rows.append(row)
                row = []
            i += 1
            cs = i
            continue
        i += 1
    return rows


def split_strs(data):
    return data.split(b'\0')


def load_orig(name):
    return open(os.path.join(EXTRACT, name), 'rb').read()


def to_euc(s, where):
    try:
        return s.encode('euc_jp')
    except UnicodeEncodeError as e:
        bad = s[e.start:e.end]
        raise SystemExit('%s: EUC-JP にない字 %r（U+%04X）' % (where, bad, ord(bad[0])))


def read_ja():
    """{ファイル名: [(key, en, ja)]}"""
    out = {}
    for p in sorted(glob.glob(os.path.join(JA, '*.tsv'))):
        name = os.path.basename(p)[:-4]
        ents = []
        for ln, line in enumerate(open(p, encoding='utf-8'), 1):
            line = line.rstrip('\r\n')
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 3 or not parts[2].strip():
                continue
            ents.append((parts[0], unesc(parts[1]), unesc(parts[2]), '%s:%d' % (os.path.basename(p), ln)))
        out[name] = ents
    return out


def build_text(ja):
    files = []
    chars = set()
    problems = 0
    for name, ents in sorted(ja.items()):
        orig = load_orig(name)
        typ = 2 if is_str_file(name) else 3 if name.lower().endswith('.bin') else 1
        recs = []
        if typ == 1:
            rows = split_table(orig)
        elif typ == 2:
            strs = split_strs(orig)
        for key, en, jt, where in ents:
            if typ == 1:
                r, c = map(int, key.split(':'))
                cell = rows[r][c] if r < len(rows) and c < len(rows[r]) else None
                k = (r << 8) | c
            elif typ == 3:
                # バイナリの表: 鍵はその欄（32 バイト、NUL 終わり）の位置
                k = int(key)
                cell = orig[k:k + 32].split(b'\0')[0]
                if len(jt.encode('euc_jp', errors='replace')) > 31:
                    print('%s: 31 バイトを超える' % where)
                    problems += 1
                    continue
            else:
                r = int(key)
                cell = strs[r] if r < len(strs) else None
                k = r
            if cell is None:
                print('%s: 元の欄がない %s' % (where, key))
                problems += 1
                continue
            cell_s = cell.decode('cp1252', errors='replace')
            core = cell_s[1:-1] if cell_s.startswith('"') and typ == 1 else cell_s
            if en != core and en != cell_s:
                print('%s: 原文が違う %s\n  元: %r\n  訳表: %r' % (where, key, cell_s[:80], en[:80]))
                problems += 1
                continue
            for ch in jt:
                if ord(ch) > 0x7F:
                    chars.add(ch)
            if typ == 1 and ('\t' in jt or '\r' in jt):
                print('%s: 表の欄にタブ・CR は入れられない' % where)
                problems += 1
                continue
            body = to_euc(jt, where)
            if typ == 1 and cell_s.startswith('"'):
                body = b'"' + body + b'"'
            recs.append((k, zlib.crc32(cell) & 0xFFFFFFFF, body))
        recs.sort()
        files.append((name.lower(), typ, recs))
    out = bytearray(b'MJT1' + struct.pack('<I', len(files)))
    for name, typ, recs in files:
        nb = name.encode('ascii')
        out += bytes([len(nb)]) + nb + bytes([typ]) + struct.pack('<I', len(recs))
        for k, crc, body in recs:
            out += struct.pack('<IIH', k, crc, len(body)) + body
    return bytes(out), chars, problems


# ---- フォント ----
FONTS = [(10, 'PixelMplus10-Regular.ttf'), (12, 'PixelMplus12-Regular.ttf')]


def render_glyphs(chars):
    from PIL import Image, ImageDraw, ImageFont
    codes = sorted(set((ch.encode('euc_jp')[0] << 8) | ch.encode('euc_jp')[1] for ch in chars
                       if len(ch.encode('euc_jp')) == 2) | {0xA2A3})
    out = bytearray(b'MJF1' + struct.pack('<II', len(FONTS), len(codes)))
    for s, _ in FONTS:
        out += struct.pack('<I', s)
    for c in codes:
        out += struct.pack('<H', c)
    if len(out) & 1:
        out += b'\0'
    for s, fn in FONTS:
        font = ImageFont.truetype(os.path.join(FONTDIR, fn), s)
        asc, desc = font.getmetrics()
        for c in codes:
            ch = bytes([c >> 8, c & 255]).decode('euc_jp')
            im = Image.new('1', (s * 2, s * 2), 0)
            d = ImageDraw.Draw(im)
            d.fontmode = '1'
            d.text((0, 0), ch, font=font, fill=1)
            px = im.load()
            if ch not in '　' and not any(px[x, y] for x in range(s) for y in range(s)):
                print('フォント %s に字がない: %s（%04X）' % (fn, ch, c))
            for y in range(s):
                bits = 0
                for x in range(s):
                    if px[x, y]:
                        bits |= 0x8000 >> x
                out += struct.pack('<H', bits)
    return bytes(out), len(codes)


def main():
    check = '--check' in sys.argv
    ja = read_ja()
    text, chars, problems = build_text(ja)
    print('訳: %d ファイル, %d 件, 字 %d 種, 問題 %d' % (len(ja), sum(len(v) for v in ja.values()), len(chars), problems))
    if check:
        return
    font, n = render_glyphs(chars)
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, 'mm6jp_text.bin'), 'wb').write(text)
    open(os.path.join(OUT, 'mm6jp_font.bin'), 'wb').write(font)
    print('フォント: %d 字 %d バイト / 訳 %d バイト' % (n, len(font), len(text)))
    if '--install' in sys.argv or True:
        import shutil
        for f in ['mm6jp_text.bin', 'mm6jp_font.bin']:
            shutil.copy(os.path.join(OUT, f), os.path.join(GAME, f))
        dll = os.path.join(WORK, 'dll', 'out', 'test', 'ddraw.dll')   # 試験版（build.bat test）
        if os.path.exists(dll):
            shutil.copy(dll, os.path.join(GAME, 'ddraw.dll'))
        print('ゲームのフォルダへ置いた')


if __name__ == '__main__':
    main()
