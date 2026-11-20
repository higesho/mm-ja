# MM3 の英文を抜き出す
#   DS の文字列 → translation/en_ds.tsv（鍵 D.<位置>、長さ、先頭への参照、途中への参照、英文）
#   CC の文のファイル → translation/en_cc.tsv（鍵 C<項目>.<番号>、長さ、英文）
# 英文の書き方は tools/textfmt.py（書式の記号は {c} {y:010} などの印にする）
import os
import re
import struct
import sys
import glob

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from capstone.x86 import X86_OP_IMM, X86_OP_MEM

sys.path.insert(0, os.path.dirname(__file__))
from textfmt import to_text  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
W = os.path.join(HERE, "..")
DSB = 0x286F0
ROOT = (0x10000, 0x27D10)
OVL = 0x286D0
CC_TEXT = list(range(2, 11)) + list(range(319, 383))


def ds_strings(ds):
    ok = set(range(0x20, 0x7F)) | set(range(1, 14))
    out = []
    i = 0
    while i < len(ds):
        if ds[i] in ok:
            j = i
            while j < len(ds) and ds[j] in ok:
                j += 1
            if j < len(ds) and ds[j] == 0 and j - i >= 2:
                s = ds[i:j]
                if sum(chr(c).isalpha() for c in s) >= 2:
                    out.append((i, s))
            i = j + 1
        else:
            i += 1
    return out


def code_imms(code, base):
    """コードの即値（16 ビット）を集める: 値 → 個数"""
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    md.detail = True
    imms = {}
    pos = 0
    while pos < len(code):
        got = False
        for ins in md.disasm(code[pos:], base + pos):
            got = True
            pos = ins.address - base + ins.size
            if ins.mnemonic in ("mov", "push"):
                for op in ins.operands:
                    if op.type == X86_OP_IMM and op.size == 2:
                        v = op.imm & 0xFFFF
                        imms[v] = imms.get(v, 0) + 1
        if not got:
            pos += 1
    return imms


def main():
    mem = open(os.path.join(W, "build", "mem.bin"), "rb").read()
    exe = open(os.path.join(W, "..", "MM3.EXE"), "rb").read()
    ds = mem[DSB:DSB + 0x10000]
    strs = ds_strings(ds)
    imms = code_imms(mem[ROOT[0]:ROOT[1]], 0)
    for v, n in code_imms(exe[OVL + 0x10:], 0).items():
        imms[v] = imms.get(v, 0) + n
    # DS の中の語（表）
    words = {}
    for k in range(0, len(ds) - 1, 2):
        v = struct.unpack_from("<H", ds, k)[0]
        words[v] = words.get(v, 0) + 1
    rows = []
    for off, s in strs:
        head = imms.get(off, 0) + words.get(off, 0)
        mids = [k for k in range(1, len(s)) if imms.get(off + k)]
        rows.append("D.%04X\t%d\t%d\t%s\t%s" % (off, len(s), head, ",".join(map(str, mids)), to_text(s)))
    os.makedirs(os.path.join(W, "translation"), exist_ok=True)
    open(os.path.join(W, "translation", "en_ds.tsv"), "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")
    print("DS:", len(rows), "件", sum(len(s) for _, s in strs), "バイト、途中への参照あり",
          sum(1 for r in rows if r.split("\t")[3]))
    rows = []
    tot = 0
    for no in CC_TEXT:
        f = glob.glob(os.path.join(W, "ccx", "%03d_*" % no))[0]
        d = open(f, "rb").read()
        parts = d.split(b"\0")
        assert parts[-1] == b"", f
        for k, s in enumerate(parts[:-1]):
            rows.append("C%03d.%03d\t%d\t%s" % (no, k, len(s), to_text(s)))
            tot += len(s)
    open(os.path.join(W, "translation", "en_cc.tsv"), "w", encoding="utf-8", newline="\n").write("\n".join(rows) + "\n")
    print("CC:", len(rows), "件", tot, "バイト")


if __name__ == "__main__":
    main()
