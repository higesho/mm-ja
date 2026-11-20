# 文字列と参照元の一覧を作る
#   本体 MM.EXE: DS の中の文字列。参照は CS のコードの即値・変位と、DS の中の語（表）
#   オーバーレイ *.OVR: データ部（DS:0xC940〜）の文字列。参照はオーバーレイのコード部の即値・変位
# 出力: translation/en_exe.tsv, translation/en_ovr.tsv
#   列: 鍵 <TAB> 長さ <TAB> 先頭への参照の数 <TAB> 途中への参照（+位置,…） <TAB> 英文（0x0D は \n）
#   鍵: E.<DS の位置>（本体）、<ファイル名>.<DS の位置>（オーバーレイ）
import glob
import os
import re
import struct
import sys
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
GAME = os.path.join(HERE, "..", "..")
OUT = os.path.join(HERE, "..", "translation")
EXE_DS = 0x107B0
OVR_DS = 0xC940
STR_RE = re.compile(rb"[\x20-\x7e\x0d]{2,}\x00")


def find_strings(data, base, lo=0, hi=None):
    out = []
    for m in STR_RE.finditer(data, lo, hi if hi is not None else len(data)):
        s = m.group()[:-1]
        if sum(c >= 0x41 and c <= 0x5a for c in s) < 2 and not re.search(rb"[A-Z][A-Z]", s):
            continue            # 英字の少ないものはデータとみなす
        out.append((base + m.start(), s))
    return out


def operands(code, addr):
    """コードの即値・変位を集める（線形にたどる。読めない所は1バイト進める）。
    戻り値: (値, 命令の番地, 命令名, 文字列の番地か)。文字列の番地とみなすのは、puts の文字列変数 [0x3BD4] に
    即値を入れる命令と、レジスタに即値を入れてすぐ [0x3BD4] に入れる命令"""
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.detail = True
    vals = []
    pos = 0
    prev = None
    while pos < len(code):
        ins = next(md.disasm(code[pos:pos + 15], addr + pos), None)
        if ins is None:
            pos += 1
            prev = None
            continue
        if ins.mnemonic.startswith(("j", "call", "loop")):
            pos += ins.size
            prev = None
            continue
        sp = ins.mnemonic == "mov" and ins.op_str.startswith("word ptr [0x3bd4], 0x")
        if (prev is not None and ins.mnemonic == "mov" and ins.op_str.startswith("word ptr [0x3bd4], ")
                and ins.op_str.split(", ")[1] == prev[1]):
            vals[prev[0]] = vals[prev[0]][:3] + (True,)
        prev = None
        for op in ins.operands:
            if op.type == 2:         # 即値
                vals.append((op.imm & 0xFFFF, ins.address, ins.mnemonic, sp))
                if ins.mnemonic == "mov" and ins.operands[0].type == 1:
                    prev = (len(vals) - 1, ins.op_str.split(",")[0])
            elif op.type == 3 and op.mem.disp:
                vals.append((op.mem.disp & 0xFFFF, ins.address, ins.mnemonic, False))
        pos += ins.size
    return vals


def table_words(data, base, strings):
    """データの中の、文字列を指す語が2つ以上続く所（表）の語。並びの境目はどこでもよい。
    続きの中では文字列の途中を指す語も含める（先頭を指す語が2つ以上あるときだけ）"""
    import bisect
    starts = {a for a, _ in strings}
    spans = sorted((a, a + len(s)) for a, s in strings)
    keys = [a for a, _ in spans]

    def inside(v):
        i = bisect.bisect_right(keys, v) - 1
        return i >= 0 and spans[i][0] <= v <= spans[i][1]
    out = []
    for al in (0, 1):
        run = []
        for i in range(al, len(data) - 1, 2):
            v = struct.unpack_from("<H", data, i)[0]
            if inside(base + i) or inside(base + i + 1):     # 文字列の本文（終わりの 0 も）は表ではない
                v = -1
            if inside(v):
                run.append(v)
                continue
            if sum(x in starts for x in run) >= 2:
                out += run
            run = []
        if sum(x in starts for x in run) >= 2:
            out += run
    return out


def refs_for(strings, vals, words=()):
    """vals: operands() の戻り値。words: 表の語。
    戻り値: head（先頭への参照の数）, inner（途中への参照: 文字列の番地として使われるものだけ）, strhead（先頭を文字列の番地として使う数）"""
    starts = {a: s for a, s in strings}
    spans = sorted((a, a + len(s)) for a, s in strings)
    import bisect
    keys = [a for a, _ in spans]
    head = {a: 0 for a in starts}
    strhead = {a: 0 for a in starts}
    inner = {a: set() for a in starts}
    for v, sp, tw in [(x[0], x[3], False) for x in vals] + [(w, True, True) for w in words]:
        i = bisect.bisect_right(keys, v) - 1
        if i < 0:
            continue
        a, e = spans[i]
        if v == a:
            head[a] += 1
            strhead[a] += sp
        elif a < v < e and sp and not tw:
            inner[a].add(v - a)
    return head, inner, strhead


def rebase(strings, head, inner, strhead):
    """先頭が文字列として使われず、途中から使われるもの（前にデータの字が付いている）は、そこを先頭にする"""
    out = []
    for a, s in strings:
        k = min(inner[a]) if inner[a] else 0
        if strhead[a] == 0 and k > 0:
            out.append((a + k, s[k:]))
        else:
            out.append((a, s))
    return out


def load_fix():
    fix = {}
    path = os.path.join(OUT, "extract_fix.txt")
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            t = line.split("#")[0].split()
            if len(t) == 3 and t[0] == "rebase":
                fix[t[1]] = int(t[2])
    return fix


def apply_fix(strings, prefix, fix):
    out = []
    for a, s in strings:
        k = fix.get(f"{prefix}.{a:04x}", 0)
        out.append((a + k, s[k:]))
    return out


def esc(s):
    return s.decode("latin1").replace("\r", "\\n")


def main():
    d = open(os.path.join(GAME, "MM.EXE"), "rb").read()
    hdr = struct.unpack_from("<H", d, 8)[0] * 16
    img = d[hdr:]
    code, ds = img[:EXE_DS], img[EXE_DS:]
    strings = find_strings(ds, 0, 0, 0x5000)        # 0x48FC 以降は字形表
    strings += find_strings(ds, 0, 0x5000)
    strings = [x for x in strings if not (0x48FC <= x[0] < 0x4F0C) and not (0x917A <= x[0] < 0xC1C2)]   # 字形表と、品物・怪物の表
    vals = operands(code, 0)
    words = table_words(ds, 0, strings)
    strings = rebase(strings, *refs_for(strings, vals, words))
    fix = load_fix()
    strings = apply_fix(strings, "E", fix)
    head, inner, _ = refs_for(strings, vals, words)
    # 場面: 文字列を使う命令がある関数の名前（MM.RSM の記号表）
    import bisect
    sys.path.insert(0, HERE)
    from rsm import load as rsm_load
    syms = sorted((a, n) for t, a, n in rsm_load(os.path.join(GAME, "MM.RSM")))
    skeys = [a for a, _ in syms]
    users = {}
    starts = {a for a, _ in strings}
    for v, at, _, _ in vals:
        if v in starts:
            i = bisect.bisect_right(skeys, at) - 1
            if i >= 0:
                users.setdefault(v, set()).add(syms[i][1].rstrip("_"))
    with open(os.path.join(OUT, "en_exe.tsv"), "w", encoding="utf-8") as f:
        for a, s in strings:
            f.write(f"E.{a:04x}\t{len(s)}\t{head[a]}\t{','.join('+%d' % x for x in sorted(inner[a]))}\t{esc(s)}"
                    f"\t{','.join(sorted(users.get(a, ())))}\n")
    print("本体", len(strings), "件", sum(len(s) for _, s in strings), "バイト、途中への参照あり",
          sum(1 for a in inner if inner[a]), "件、参照なし", sum(1 for a in head if head[a] == 0 and not inner[a]))
    # 品物・怪物の名前の表（決まった幅、0 で終わらない）: 鍵 I.番号 / M.番号、列は幅と英文（右の空白は除く）
    with open(os.path.join(OUT, "en_tables.tsv"), "w", encoding="utf-8") as f:
        for kind, tab, cnt, size, w in (("I", 0x917A, 255, 24, 14), ("M", 0xA962, 195, 32, 15)):
            for i in range(cnt):
                name = ds[tab + i * size:tab + i * size + w]
                f.write(f"{kind}.{i + 1:03d}\t{w}\t{name.decode('latin1').rstrip()}\n")
    print("表: 品物 255 件、怪物 195 件")
    n = tot = ni = 0
    with open(os.path.join(OUT, "en_ovr.tsv"), "w", encoding="utf-8") as f:
        for path in sorted(glob.glob(os.path.join(GAME, "*.OVR"))):
            name = os.path.basename(path)[:-4]
            o = open(path, "rb").read()
            magic, caddr, csize, daddr, dsize, _, entry = struct.unpack_from("<7H", o, 0)
            assert magic == 0xF2 and daddr == OVR_DS
            ocode = o[14:14 + csize]
            odata = o[14 + csize:14 + csize + dsize]
            strs = find_strings(odata, OVR_DS)
            vals = operands(ocode, caddr)
            words = table_words(odata, OVR_DS, strs)
            strs = rebase(strs, *refs_for(strs, vals, words))
            strs = apply_fix(strs, name, fix)
            h, inn, _ = refs_for(strs, vals, words)
            for a, s in strs:
                f.write(f"{name}.{a:04x}\t{len(s)}\t{h[a]}\t{','.join('+%d' % x for x in sorted(inn[a]))}\t{esc(s)}\n")
            n += len(strs)
            tot += sum(len(s) for _, s in strs)
            ni += sum(1 for a in inn if inn[a])
    print("OVR", n, "件", tot, "バイト、途中への参照あり", ni, "件")


if __name__ == "__main__":
    main()
