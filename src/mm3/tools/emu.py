"""MM3.EXE を unicorn で模擬実行し、自分で解いた後のメモリ像を取り出す。
使い方: python tools/emu.py ../MM3.EXE build/mem.bin [命令数の上限]
PSP は 0x0FF0、読み込み像は 0x1000 から。"""
import struct, sys, os
from unicorn import *
from unicorn.x86_const import *

PSP = 0x0FF0
LOAD = 0x1000
STOPFILE = os.environ.get('STOPFILE', '#').upper()
GAME = os.path.dirname(os.path.abspath(sys.argv[1]))

d = open(sys.argv[1], 'rb').read()
(magic, cblp, cp, crlc, hdrp, minalloc, maxalloc, ss, sp, csum, ip, cs, lfarlc, ovno) = struct.unpack('<14H', d[:28])
size = cp * 512 - (512 - cblp if cblp else 0)
img = bytearray(d[hdrp * 16:size])
for i in range(crlc):
    o, s = struct.unpack('<HH', d[lfarlc + i * 4:lfarlc + i * 4 + 4])
    p = s * 16 + o
    v = struct.unpack('<H', img[p:p + 2])[0]
    img[p:p + 2] = struct.pack('<H', (v + LOAD) & 0xFFFF)

mu = Uc(UC_ARCH_X86, UC_MODE_16)
mu.mem_map(0, 0x110000)
mu.mem_write(LOAD * 16, bytes(img))
psp = bytearray(256)
psp[0:2] = b'\xcd\x20'
psp[2:4] = struct.pack('<H', 0x9FFF)
psp[0x2C:0x2E] = struct.pack('<H', 0x0F00)
psp[0x80] = 0; psp[0x81] = 13
mu.mem_write(PSP * 16, bytes(psp))
env = b'COMSPEC=C:\\COMMAND.COM\x00PATH=Z:\\\x00\x00\x01\x00C:\\MM3.EXE\x00'
mu.mem_write(0x0F00 * 16, env)
# 割り込みベクタ: すべて F000:xxxx の iret へ
for n in range(256):
    mu.mem_write(n * 4, struct.pack('<HH', n * 4, 0xF000))
    mu.mem_write(0xF0000 + n * 4, b'\xcf\x90\x90\x90')

mu.reg_write(UC_X86_REG_CS, LOAD + cs); mu.reg_write(UC_X86_REG_IP, ip)
mu.reg_write(UC_X86_REG_SS, LOAD + ss); mu.reg_write(UC_X86_REG_SP, sp)
mu.reg_write(UC_X86_REG_DS, PSP); mu.reg_write(UC_X86_REG_ES, PSP)

files = {}
nexth = [5]
memtop = [0x9FFF]
log = []
stop = {'why': None}

def rd_str(seg, off):
    s = b''
    a = seg * 16 + off
    while True:
        c = mu.mem_read(a, 1)[0]
        if c == 0: break
        s += bytes([c]); a += 1
    return s.decode('latin1')

def setcf(cf):
    fl = mu.reg_read(UC_X86_REG_EFLAGS)
    mu.reg_write(UC_X86_REG_EFLAGS, (fl | 1) if cf else (fl & ~1))

def hook_int(uc, intno, user):
    ax = uc.reg_read(UC_X86_REG_AX); ah = ax >> 8; al = ax & 0xFF
    bx = uc.reg_read(UC_X86_REG_BX); cx = uc.reg_read(UC_X86_REG_CX); dx = uc.reg_read(UC_X86_REG_DX)
    ds = uc.reg_read(UC_X86_REG_DS); es = uc.reg_read(UC_X86_REG_ES)
    sp_ = uc.reg_read(UC_X86_REG_SP); ss_ = uc.reg_read(UC_X86_REG_SS)
    rip, rcs = uc.reg_read(UC_X86_REG_IP), uc.reg_read(UC_X86_REG_CS)
    vo, vs = struct.unpack('<HH', uc.mem_read(intno * 4, 4))
    if vs != 0xF000:
        # プログラムが置いた割り込み処理へ飛ぶ
        fl = uc.reg_read(UC_X86_REG_EFLAGS)
        sp_ -= 6
        uc.mem_write(ss_ * 16 + sp_, struct.pack('<HHH', rip, rcs, fl & 0xFFFF))
        uc.reg_write(UC_X86_REG_SP, sp_)
        uc.reg_write(UC_X86_REG_CS, vs); uc.reg_write(UC_X86_REG_IP, vo)
        log.append('INT %02X -> %04X:%04X' % (intno, vs, vo))
        return
    log.append('INT %02X AX=%04X BX=%04X CX=%04X DX=%04X DS=%04X from %04X:%04X' % (intno, ax, bx, cx, dx, ds, rcs, rip))
    if intno != 0x21:
        if intno == 0x10 and ah == 0x0F: uc.reg_write(UC_X86_REG_AX, 0x5003)
        if intno == 0x11: uc.reg_write(UC_X86_REG_AX, 0x0026)
        if intno == 0x12: uc.reg_write(UC_X86_REG_AX, 640)
        return
    cf = False
    if ah == 0x30: uc.reg_write(UC_X86_REG_AX, 0x0005)
    elif ah == 0x4A:
        if es == PSP: memtop[0] = PSP + bx
        log.append('  resize %04X to %04X' % (es, bx))
    elif ah == 0x48:
        seg = memtop[0] + 1
        if seg + bx > 0x9FFF: cf = True; uc.reg_write(UC_X86_REG_AX, 8); uc.reg_write(UC_X86_REG_BX, 0x9FFF - seg)
        else: uc.reg_write(UC_X86_REG_AX, seg); memtop[0] = seg + bx
        log.append('  alloc %04X -> %s' % (bx, 'fail' if cf else '%04X' % seg))
    elif ah == 0x35:
        o, s = struct.unpack('<HH', uc.mem_read(al * 4, 4))
        uc.reg_write(UC_X86_REG_ES, s); uc.reg_write(UC_X86_REG_BX, o)
    elif ah == 0x25:
        uc.mem_write(al * 4, struct.pack('<HH', dx, ds))
    elif ah in (0x3D, 0x3C):
        name = rd_str(ds, dx)
        log.append('  open ' + name)
        p = os.path.join(GAME, name.split('\\')[-1])
        if os.path.exists(p) and ah == 0x3D:
            h = nexth[0]; nexth[0] += 1
            files[h] = [open(p, 'rb').read(), 0, name]
            uc.reg_write(UC_X86_REG_AX, h)
        else:
            cf = True; uc.reg_write(UC_X86_REG_AX, 2)
        if name.upper().endswith(STOPFILE):
            stop['why'] = 'open ' + name; uc.emu_stop()
    elif ah == 0x3F:
        if bx in files:
            f = files[bx]; data = f[0][f[1]:f[1] + cx]
            log.append('  read %s @%X len %X -> %04X:%04X' % (f[2], f[1], len(data), ds, dx))
            if f[1] == int(os.environ.get('STACKAT', '-1'), 16):
                stk = struct.unpack('<64H', uc.mem_read(ss_ * 16 + sp_, 128))
                log.append('  stack ' + ' '.join('%04X' % w for w in stk) + ' BP=%04X SS=%04X SP=%04X' % (uc.reg_read(UC_X86_REG_BP), ss_, sp_))
            f[1] += len(data)
            uc.mem_write(ds * 16 + dx, data); uc.reg_write(UC_X86_REG_AX, len(data))
        else:
            uc.reg_write(UC_X86_REG_AX, 0)
    elif ah == 0x42:
        if bx in files:
            f = files[bx]; off = (cx << 16) | dx
            if al == 0: f[1] = off
            elif al == 1: f[1] += off
            else: f[1] = len(f[0]) + off
            uc.reg_write(UC_X86_REG_AX, f[1] & 0xFFFF); uc.reg_write(UC_X86_REG_DX, f[1] >> 16)
    elif ah == 0x3E: files.pop(bx, None)
    elif ah == 0x44: uc.reg_write(UC_X86_REG_DX, 0x80 if bx < 3 else 0)
    elif ah == 0x19: uc.reg_write(UC_X86_REG_AX, (ax & 0xFF00) | 2)
    elif ah == 0x47: uc.mem_write(ds * 16 + uc.reg_read(UC_X86_REG_SI), b'\x00')
    elif ah == 0x36: uc.reg_write(UC_X86_REG_AX, 64); uc.reg_write(UC_X86_REG_BX, 0x7000); uc.reg_write(UC_X86_REG_CX, 512); uc.reg_write(UC_X86_REG_DX, 0x7FFF)
    elif ah == 0x4C or ah == 0x00:
        stop['why'] = 'exit %d' % al; uc.emu_stop()
    setcf(cf)

tick = [0]
def hook_in(uc, port, size, user):
    tick[0] += 1
    if port == 0x3DA: return 0x09 if (tick[0] // 3) % 2 else 0
    if port == 0x60: return 0x9C
    return 0
def hook_out(uc, port, size, value, user):
    pass
mu.hook_add(UC_HOOK_INTR, hook_int)
mu.hook_add(UC_HOOK_INSN, hook_in, None, 1, 0, UC_X86_INS_IN)
mu.hook_add(UC_HOOK_INSN, hook_out, None, 1, 0, UC_X86_INS_OUT)
limit = int(sys.argv[3]) if len(sys.argv) > 3 else 200_000_000
try:
    mu.emu_start((LOAD + cs) * 16 + ip, 0, count=limit)
except UcError as e:
    stop['why'] = 'error %s at %04X:%04X' % (e, mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP))
print('screen:', ''.join(chr(int(l.split('AX=')[1][2:4],16)) for l in log if l.startswith('INT 10 AX=09')))
print('stop:', stop['why'], 'CS:IP=%04X:%04X DS=%04X' % (mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP), mu.reg_read(UC_X86_REG_DS)))
for l in (log if os.environ.get("ALLLOG") else log[-40:]): print(l)
open(sys.argv[2], 'wb').write(bytes(mu.mem_read(0, 0xA0000)))
