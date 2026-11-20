# MM2 の DS の文字列と参照元の一覧を作る → translation/en_ds.tsv
#   DS = MM2.EXE のファイル 0x8630〜（実行時 DS:0）
#   参照: 本体のコード（ファイル 0x800〜0x8610）と各 *.OVL のコードの即値・変位（線形にたどる）、DS の中の表の語
#   列: 鍵 D.<DS の位置> / 長さ / 先頭への参照の数 / 途中への参照（+位置,…） / 参照する所（root, 2PLAY など） / 英文（\n は改行）
import bisect, glob, os, re, struct, sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, '..', '..')
OUT = os.path.join(HERE, '..', 'translation')
DS_FILE = 0x8630
ROOT = (0x800, 0x8610)
STR_RE = re.compile(rb'[\x0a\x0d\x20-\x7e]{1,}\x00')


def load():
    exe = open(os.path.join(GAME, 'MM2.EXE'), 'rb').read()
    ds = exe[DS_FILE:]
    mods = [('root', exe[ROOT[0]:ROOT[1]])]
    for p in sorted(glob.glob(os.path.join(GAME, '*.OVL'))):
        mods.append((os.path.basename(p)[:-4], open(p, 'rb').read()))
    return exe, ds, mods


def find_strings(ds):
    out = []
    for m in STR_RE.finditer(ds):
        s = m.group()[:-1]
        if len(re.findall(rb'[A-Za-z]', s)) < 2:
            continue
        out.append((m.start(), s))
    return out


def operands(code):
    """文字列の番地らしい即値: mov reg,imm16 のすぐ後に push reg（関数の引数）、mov word ptr [..], imm16、
    mov si/di/bx, imm16（文字列を読むレジスタ）。線形にたどる"""
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.detail = True
    vals = []
    pos = 0
    prev = None
    while pos < len(code):
        ins = next(md.disasm(code[pos:pos + 15], pos), None)
        if ins is None:
            pos += 1
            prev = None
            continue
        m, o = ins.mnemonic, ins.op_str
        if prev is not None and m == 'push' and o == prev[0]:
            vals.append((prev[1], prev[2], 'arg'))
        prev = None
        if m == 'mov' and len(ins.operands) == 2 and ins.operands[1].type == 2:
            dst = o.split(',')[0].strip()
            imm = ins.operands[1].imm & 0xFFFF
            if ins.operands[0].type == 1:
                if dst in ('ax', 'bx', 'cx', 'dx', 'si', 'di'):
                    prev = (dst, imm, ins.address)
                if dst in ('si', 'di', 'bx', 'dx', 'ax', 'cx'):
                    vals.append((imm, ins.address, 'reg'))
            elif ins.operands[0].type == 3 and o.startswith('word'):
                vals.append((imm, ins.address, 'mem'))
        pos += ins.size
    return vals


def table_words(ds, strings):
    starts = {a for a, _ in strings}
    spans = sorted((a, a + len(s)) for a, s in strings)
    keys = [a for a, _ in spans]

    def inside(v):
        i = bisect.bisect_right(keys, v) - 1
        return i >= 0 and spans[i][0] <= v <= spans[i][1]
    out = []
    for al in (0, 1):
        run = []
        for i in range(al, len(ds) - 1, 2):
            v = struct.unpack_from('<H', ds, i)[0]
            if inside(i) or inside(i + 1):
                v = -1
            if v in starts or (run and inside(v)):
                run.append(v)
                continue
            if sum(x in starts for x in run) >= 2:
                out += run
            run = []
        if sum(x in starts for x in run) >= 2:
            out += run
    return out


def main():
    exe, ds, mods = load()
    strings = find_strings(ds)
    starts = {a: s for a, s in strings}
    spans = sorted((a, a + len(s)) for a, s in strings)
    keys = [a for a, _ in spans]
    head = {a: 0 for a in starts}
    inner = {a: set() for a in starts}
    where = {a: set() for a in starts}
    allv = []
    for name, code in mods:
        for v, addr, kind in operands(code):
            allv.append((v, name, kind))
    for w in table_words(ds, strings):
        allv.append((w, 'table', 'table'))

    def tally(strings):
        spans = sorted((a, a + len(s)) for a, s in strings)
        keys = [a for a, _ in spans]
        head = {a: 0 for a, _ in strings}
        inner = {a: set() for a, _ in strings}
        where = {a: set() for a, _ in strings}
        for v, name, kind in allv:
            i = bisect.bisect_right(keys, v) - 1
            if i < 0:
                continue
            a, e = spans[i]
            if v == a:
                head[a] += 1
                where[a].add(name)
            elif a < v < e and a >= 0x400 and (kind in ('arg', 'mem') or (kind == 'table' and e - a <= 26)):
                inner[a].add(v - a)
                where[a].add(name + '*')
        return head, inner, where
    fix = {}
    norebase = set()
    for line in open(os.path.join(OUT, 'extract_fix.txt'), encoding='utf-8'):
        t = line.split('#')[0].split()
        if len(t) == 3 and t[0] == 'rebase':
            fix[int(t[1][2:], 16)] = int(t[2])
        if len(t) == 2 and t[0] == 'norebase':
            norebase.add(int(t[1][2:], 16))
    strings = [(a + fix.get(a, 0), s[fix.get(a, 0):]) for a, s in strings]
    head, inner, where = tally(strings)
    # 先頭が参照されず途中だけが参照されるもの（前にデータの字が付いている）は、そこを先頭にする
    strings = [(a + min(inner[a]), s[min(inner[a]):]) if head[a] == 0 and inner[a] and a not in norebase else (a, s)
               for a, s in strings]
    head, inner, where = tally(strings)
    os.makedirs(OUT, exist_ok=True)
    n = tot = 0
    with open(os.path.join(OUT, 'en_ds.tsv'), 'w', encoding='utf-8', newline='\n') as f:
        for a, s in strings:
            t = s.decode('latin1').replace(chr(10), chr(92) + 'n').replace(chr(13), chr(92) + 'r')
            f.write(f"D.{a:04x}\t{len(s)}\t{head[a]}\t{','.join('+%d' % k for k in sorted(inner[a]))}\t{','.join(sorted(where[a]))}\t{t}\n")
            n += 1
            tot += len(s)
    print(n, tot)


if __name__ == '__main__':
    main()
