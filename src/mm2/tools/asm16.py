"""keystone で 16 ビットのコードを組み立てる（32 ビット形式の命令を直す）。
メモリの番地は数で書く（ラベルを番地に使うと 67 の前置きが付く）。遠い jmp/call は far_jmp()/far_call() を使う。"""
import struct
from keystone import Ks, KS_ARCH_X86, KS_MODE_16
from capstone import Cs, CS_ARCH_X86, CS_MODE_16


def fix16(code, addr):
    b = bytearray(code)
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    pos = 0
    while pos < len(b):
        ins = next(md.disasm(bytes(b[pos:]), addr + pos), None)
        if ins is None:
            break
        x = bytes(b[pos:pos + ins.size])
        if x[0] in (0x66, 0x67):
            if x[0] == 0x66 and x[1] in (0xe9, 0xe8) and len(x) == 6:
                rel = struct.unpack_from('<i', x, 2)[0] + 3
                b[pos:pos + 6] = bytes([x[1]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[0] == 0x66 and x[1] == 0x0f and 0x80 <= x[2] <= 0x8f and len(x) == 7:
                rel = struct.unpack_from('<i', x, 3)[0] + 3
                b[pos:pos + 7] = bytes([0x0f, x[2]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[0] == 0x66 and x[1] in (0xca, 0xc2) and len(x) == 4:
                b[pos:pos + 4] = x[1:] + b'\x90'
            elif x[0] == 0x66 and x[1] in (0xc3, 0xcb) and len(x) == 2:
                b[pos:pos + 2] = x[1:] + b'\x90'
            else:
                raise RuntimeError(f'直せない 32ビット命令: {x.hex()} at {addr + pos:#x} ({ins.mnemonic} {ins.op_str})')
        pos += ins.size
    return bytes(b)


def far_jmp(a, seg='2e'):
    return f".byte 0x{seg},0xff,0x2e,{a & 0xff},{a >> 8}"


def far_call(a, seg='2e'):
    return f".byte 0x{seg},0xff,0x1e,{a & 0xff},{a >> 8}"


def asm(src, addr, **kw):
    src = "\n".join(line.split(";")[0] for line in src.format(**kw).splitlines())
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src, addr)
    return fix16(bytes(enc), addr)
