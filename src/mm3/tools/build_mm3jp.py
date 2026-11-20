# Might and Magic III 用の常駐プログラム MM3JP.COM を作る（試作）
#
# 仕組み
#   - INT 21h を横取りする。MM3.EXE（自己解凍のあと）の起動処理が AH=4Ah を呼んだとき（戻り先 IP=0x00B4）、
#     呼び出し元 CS の 0x00A8 からを照合し、合えば DS（CS+0x186F）の文字列を訳に書き換える
#   - INT 10h を横取りする。画面ドライバ（MM3.CC の項目 130、VGA 用）がモード 13h を設定したとき、呼び出し元 CS の
#     文字列を描く処理（0x15B6）などを照合し、3か所を常駐部への jmp far に書き換える
#       0x1B08 次の字を読む: 日本語なら 1〜2 バイトを読み、字の番号を CURJ に置いて 0x7F（目印）を返す
#       0x1B42 1字を描く:   0x7F なら美咲フォントの字（8×8）を描く
#       0x165A 折り返し:     行の頭から前向きに字を区切り、空白・日本語の字の境目（禁則を守る）で折り返す
#   - 0x7F の幅はフォントの幅の表（フォントの区画の 0x107F と 0x10FF）を 8 にして測らせる
#
# 文字の符号
#   0x00〜0x7F 元のまま（英数字と書式の記号）
#   0x80〜(0x80+L-1) をリードにして + 2 バイト目（0x21〜0xFF の 0x25 以外の 222 種）: 2 バイトの字
#   残りの 0x80〜0xFF（0xA0 を除く）: 1 バイトの字（よく使う字から順に）。L は字の数から最小に決める
#
# CC の差し替え
#   - mm3.cc を開いたハンドルを覚える。目次（0x1172 バイト）を読んだ直後に、差し替える項目の 8 バイト（暗号のまま）を
#     照合して書き換える（位置 = 0x400000 + MM3JP.DAT の中の位置、大きさ = 圧縮した大きさ）
#   - そのハンドルで 0x400000 より先へ seek したら MM3JP.DAT へ回し、続く read も MM3JP.DAT から読む
import os
import struct
import sys

from keystone import Ks, KS_ARCH_X86, KS_MODE_16

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

SIG4A = bytes.fromhex("a190002bd88ec0b44a57cd215fd3e7fa")   # 本体 CS:0x00A8〜
GAME_DS_ADD = 0x186F
DRV_SIG = {0x15B6: bytes.fromhex("558bec1e0656572ec606670e002e803e"),
           0x1B08: bytes.fromhex("2ec5362c0b2eff062c0bac247fc3"),
           0x1B42: bytes.fromhex("2e8e06f8092e8b3e120a"),
           0x165A: bytes.fromhex("8bf1ac3c20751390")}
DRV_RET = 0x1B15          # ドライバの中の ret（c3）
# 英語のまま残す DS の文字列: {位置: (訳を移す部分の始まり, その部分を指す番地の表の位置の並び)}
# Where Are We?（自動地図）が "007%s is not"（DS:0x5B19）を目印に MM3 を探すため。
# D.5AEA の 46 バイト目からが「%s is not in any condition to perform actions!」で、DS:0x52D2 の表から指される
KEEP_EN = {0x5AEA: (46, [0x52D2])}
# 怪物の名前の並び（目印 + 0xFC0 から 0x39C バイト）: Where Are We? が 0 区切りの英字として読むので、英語のまま残し、
# 訳は空いた所へ置いて番地の表（DS:0x5632〜）を向け替える
KEEP_EN_BLOCK = range(0x6AD9, 0x6AD9 + 0x39C)
TRAILS = [c for c in range(0x21, 0x100) if c != 0x25]
NOSTART = "、。，．・：；？！ー）」』】〕〉》…‥ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ々〜～"
NOEND = "（「『【〔〈《"
ANOSTART = b"!?,.):;"
ANOEND = b"("

# ---- 常駐部の変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("OLD21", 4), ("OLD10", 4), ("GAMECS", 2), ("GAMEDS", 2), ("DRV", 2), ("CURJ", 2),
                   ("SAVEAH", 2), ("RETPTR", 4), ("C1B47", 4), ("J16A6", 4), ("J167F", 4),
                   ("WPREV", 2), ("WPP", 2), ("WBEST", 2), ("WPKIND", 1), ("WFOUND", 1),
                   ("CCH", 8), ("CCV", 4), ("JPH", 2)]:
    V[name] = _p
    _p += size
DATA = (_p + 15) & ~15


def JMPF(a):
    return f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"


RES = r'''
int21:
    cmp ah, 0x3f
    je i3f
    cmp ah, 0x42
    je i42
    cmp ah, 0x3d
    je i3d
    cmp ah, 0x3e
    je i3e
    cmp ah, 0x4a
    je i4a
c21:
    {JMPF_OLD21}

i3d:
    push si
    push cx
    push ax
    push di
    mov si, dx
f_l:
    cmp byte ptr [si], 0
    je f_e
    inc si
    jmp f_l
f_e:
    sub si, 6
    cmp si, dx
    jb notcc
    mov cx, 6
    mov di, {CCNAME}
cmp_l:
    mov al, byte ptr [si]
    cmp al, 0x61
    jb up1
    cmp al, 0x7a
    ja up1
    sub al, 0x20
up1:
    cmp al, byte ptr cs:[di]
    jne notcc
    inc si
    inc di
    loop cmp_l
    pop di
    pop ax
    pop cx
    pop si
    pushf
    {CALLF_OLD21}
    jc ret_f
    push bx
    push si
    mov si, {CCH}
    mov bx, 4
reg_l:
    cmp word ptr cs:[si], 0xffff
    je reg_s
    add si, 2
    dec bx
    jnz reg_l
    jmp reg_x
reg_s:
    mov word ptr cs:[si], ax
    mov bx, si
    sub bx, {CCH}
    shr bx, 1
    mov byte ptr cs:[bx+{CCV}], 0
reg_x:
    pop si
    pop bx
    clc
ret_f:
    retf 2
notcc:
    pop di
    pop ax
    pop cx
    pop si
    jmp c21

findh:
    push cx
    mov si, {CCH}
    mov cx, 4
fh_l:
    cmp word ptr cs:[si], bx
    je fh_y
    add si, 2
    loop fh_l
    pop cx
    stc
    ret
fh_y:
    sub si, {CCH}
    shr si, 1
    pop cx
    clc
    ret

i3e:
    push si
    call findh
    jc i3e_x
    shl si, 1
    mov word ptr cs:[si+{CCH}], 0xffff
    push cx
    mov si, {CCH}
    mov cx, 4
c_l:
    cmp word ptr cs:[si], 0xffff
    jne c_any
    add si, 2
    loop c_l
    cmp word ptr cs:[{JPH}], 0xffff
    je c_any
    push ax
    push bx
    mov bx, word ptr cs:[{JPH}]
    mov ah, 0x3e
    pushf
    {CALLF_OLD21}
    mov word ptr cs:[{JPH}], 0xffff
    pop bx
    pop ax
c_any:
    pop cx
i3e_x:
    pop si
    jmp c21

i42:
    cmp al, 0
    jne c21
    push si
    call findh
    jc i42_n
    cmp cx, 0x40
    jae i42_v
    mov byte ptr cs:[si+{CCV}], 0
i42_n:
    pop si
    jmp c21
i42_v:
    mov byte ptr cs:[si+{CCV}], 1
    call openjp
    jc i42_e
    push bx
    push cx
    mov bx, word ptr cs:[{JPH}]
    sub cx, 0x40
    mov ax, 0x4200
    pushf
    {CALLF_OLD21}
    pop cx
    pop bx
    jc i42_e
    add dx, 0x40
    clc
i42_e:
    pop si
    retf 2

i3f:
    push si
    call findh
    jc i3f_n
    cmp byte ptr cs:[si+{CCV}], 0
    jne i3f_v
    pop si
    pushf
    {CALLF_OLD21}
    jc i3f_r
    cmp ax, {IDXLEN}
    jne i3f_c
    cmp cx, {IDXLEN}
    jne i3f_c
    call patchidx
i3f_c:
    clc
i3f_r:
    retf 2
i3f_v:
    pop si
    push bx
    mov bx, word ptr cs:[{JPH}]
    pushf
    {CALLF_OLD21}
    pop bx
    retf 2
i3f_n:
    pop si
    jmp c21

patchidx:
    push ax
    push cx
    push si
    push di
    push es
    push ds
    push ds
    pop es
    push cs
    pop ds
    cld
    mov si, {IDXTAB}
pi_l:
    mov ax, word ptr [si]
    cmp ax, 0xffff
    je pi_x
    mov di, ax
    shl di, 3
    add di, dx
    add di, 2
    push si
    push di
    add si, 2
    mov cx, 8
    repe cmpsb
    pop di
    pop si
    jne pi_n
    push si
    add si, 10
    mov cx, 8
    rep movsb
    pop si
pi_n:
    add si, 18
    jmp pi_l
pi_x:
    pop ds
    pop es
    pop di
    pop si
    pop cx
    pop ax
    ret

openjp:
    cmp word ptr cs:[{JPH}], 0xffff
    jne oj_ok
    push ax
    push dx
    push ds
    push cs
    pop ds
    mov dx, {JPNAME}
    mov ax, 0x3d00
    pushf
    {CALLF_OLD21}
    jc oj_f
    mov word ptr cs:[{JPH}], ax
    pop ds
    pop dx
    pop ax
oj_ok:
    clc
    ret
oj_f:
    pop ds
    pop dx
    pop ax
    stc
    ret
i4a:
    push bp
    mov bp, sp
    cmp word ptr [bp+2], 0x00B4
    jne i4a_x
    push ax
    push cx
    push si
    push di
    push ds
    push es
    mov ds, word ptr [bp+4]
    mov si, 0x00A8
    push cs
    pop es
    mov di, {SIG4A}
    mov cx, 16
    cld
    repe cmpsb
    jne i4a_y
    mov word ptr cs:[{CCH}], 0xffff
    mov word ptr cs:[{CCH}+2], 0xffff
    mov word ptr cs:[{CCH}+4], 0xffff
    mov word ptr cs:[{CCH}+6], 0xffff
    mov word ptr cs:[{JPH}], 0xffff
    mov ax, ds
    mov word ptr cs:[{GAMECS}], ax
    add ax, {GAME_DS_ADD}
    mov word ptr cs:[{GAMEDS}], ax
    mov es, ax
    mov si, {DSPATCH}
    push cs
    pop ds
ad_l:
    lodsw
    cmp ax, 0xffff
    je i4a_y
    mov di, ax
    lodsw
    mov cx, ax
    rep movsb
    jmp ad_l
i4a_y:
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop ax
i4a_x:
    pop bp
    jmp c21

int10:
    cmp ax, 0x0013
    je i10
c10:
    {JMPF_OLD10}
i10:
    push bp
    mov bp, sp
    push ax
    push cx
    push si
    push di
    push ds
    push es
    mov ds, word ptr [bp+4]
    cld
    push cs
    pop es
    mov si, 0x15B6
    mov di, {SIGW}
    mov cx, 16
    repe cmpsb
    jne i10_x
    mov si, 0x1B08
    mov di, {SIGG}
    mov cx, 14
    repe cmpsb
    jne i10_x
    mov si, 0x1B42
    mov di, {SIGD}
    mov cx, 10
    repe cmpsb
    jne i10_x
    mov si, 0x165A
    mov di, {SIGB}
    mov cx, 8
    repe cmpsb
    jne i10_x
    mov ax, ds
    mov word ptr cs:[{DRV}], ax
    mov word ptr cs:[{RETPTR}+2], ax
    mov word ptr cs:[{C1B47}+2], ax
    mov word ptr cs:[{J16A6}+2], ax
    mov word ptr cs:[{J167F}+2], ax
    mov byte ptr [0x1B08], 0xEA
    mov word ptr [0x1B09], {L_getc}
    mov word ptr [0x1B0B], cs
    mov byte ptr [0x1B42], 0xEA
    mov word ptr [0x1B43], {L_drawc}
    mov word ptr [0x1B45], cs
    mov byte ptr [0x165A], 0xEA
    mov word ptr [0x165B], {L_wrap}
    mov word ptr [0x165D], cs
i10_x:
    pop es
    pop ds
    pop di
    pop si
    pop cx
    pop ax
    pop bp
    jmp c10

getc:
    push es
    mov es, word ptr cs:[{DRV}]
    lds si, dword ptr es:[0xb2c]
    lodsb
    cmp al, 0x80
    jae gj
    inc word ptr es:[0xb2c]
    pop es
    {JMPF_RETPTR}
gj:
    mov byte ptr cs:[{SAVEAH}], ah
    mov ah, 0
    inc word ptr es:[0xb2c]
    cmp al, {LEADEND}
    jae gs1
    mov ah, al
    lodsb
    inc word ptr es:[0xb2c]
gs1:
    mov word ptr cs:[{CURJ}], ax
    push ds
    mov ds, word ptr es:[0x9fe]
    mov byte ptr [0x107f], 8
    mov byte ptr [0x10ff], 8
    pop ds
    mov ah, byte ptr cs:[{SAVEAH}]
    mov al, 0x7f
    pop es
    {JMPF_RETPTR}

drawc:
    cmp al, 0x7f
    je dj
    mov es, word ptr cs:[{DRV}]
    mov es, word ptr es:[0x9f8]
    {JMPF_C1B47}
dj:
    push ds
    push si
    push di
    push bx
    push cx
    push dx
    push bp
    push ax
    mov ds, word ptr cs:[{DRV}]
    mov es, word ptr [0x9f8]
    mov di, word ptr [0xa12]
    shl di, 1
    mov di, word ptr [di+0x69c]
    add di, word ptr [0xa10]
    mov ax, word ptr cs:[{CURJ}]
    or ah, ah
    jnz ga_p
    mov bl, al
    sub bl, 0x80
    mov bh, 0
    shl bx, 1
    mov ax, word ptr cs:[bx+{GIDX}]
    jmp ga_h
ga_p:
    mov bl, ah
    sub bl, 0x80
    mov bh, 0
    shl bx, 1
    mov bx, word ptr cs:[bx+{GIDX}]
    sub al, 0x21
    cmp al, 4
    jb ga_t
    dec al
ga_t:
    mov ah, 0
    add ax, bx
ga_h:
    mov cl, 3
    shl ax, cl
    add ax, {GLYPHS}
    mov si, ax
    mov dl, byte ptr [0xb76]
    mov bp, 8
dr_r:
    mov al, byte ptr cs:[si]
    inc si
    mov cx, 8
dr_p:
    shl al, 1
    jnc dr_s
    mov byte ptr es:[di], dl
dr_s:
    inc di
    loop dr_p
    add di, 312
    dec bp
    jnz dr_r
    add word ptr [0xa10], 8
    pop ax
    pop bp
    pop dx
    pop cx
    pop bx
    pop di
    pop si
    pop ds
    {JMPF_RETPTR}

wrap:
    push es
    mov si, dx
    mov word ptr cs:[{WPREV}], 0xffff
    mov word ptr cs:[{WPP}], 0xffff
    mov byte ptr cs:[{WFOUND}], 0
w_l:
    cmp si, cx
    ja w_end
    mov di, si
    call wclass
    cmp al, 0
    je w_l
    cmp al, 1
    jne w_nb
    mov word ptr cs:[{WBEST}], di
    mov byte ptr cs:[{WFOUND}], 1
    jmp w_next
w_nb:
    cmp word ptr cs:[{WPREV}], 0xffff
    je w_next
    mov ah, byte ptr cs:[{WPKIND}]
    cmp al, 4
    je w_next
    cmp al, 6
    je w_next
    cmp ah, 5
    je w_next
    cmp ah, 7
    je w_next
    cmp al, 3
    jb w_a
    cmp al, 5
    jbe w_ok
w_a:
    cmp ah, 3
    jb w_next
    cmp ah, 5
    ja w_next
w_ok:
    mov bx, word ptr cs:[{WPREV}]
    mov word ptr cs:[{WBEST}], bx
    mov byte ptr cs:[{WFOUND}], 1
w_next:
    mov bx, word ptr cs:[{WPREV}]
    mov word ptr cs:[{WPP}], bx
    mov word ptr cs:[{WPREV}], di
    mov byte ptr cs:[{WPKIND}], al
    jmp w_l
w_end:
    cmp byte ptr cs:[{WFOUND}], 0
    je w_none
    mov cx, word ptr cs:[{WBEST}]
    pop es
    {JMPF_J16A6}
w_none:
    mov cx, word ptr cs:[{WPP}]
    cmp cx, 0xffff
    jne w_n2
    mov cx, word ptr cs:[{WPREV}]
w_n2:
    pop es
    {JMPF_J167F}

wclass:
    lodsb
    cmp al, 0x0c
    jne wc1
    lodsb
    cmp al, 0x64
    je wc0
    inc si
wc0:
    mov al, 0
    ret
wc1:
    cmp al, 0x08
    jne wc2
    cmp byte ptr [si], 0x20
    jne wc0
    inc si
    jmp wc0
wc2:
    cmp al, 0x20
    jb wc0
    jne wc3
    mov al, 1
    ret
wc3:
    cmp al, 0x80
    jae wcj
    cmp al, 0x2d
    je wcb
    cmp al, 0x2f
    je wcb
    push di
    push cx
    push es
    push cs
    pop es
    mov di, {ANOST}
    mov cx, {ANOST_N}
    repne scasb
    je wca6
    mov di, {ANOEND}
    mov cx, {ANOEND_N}
    repne scasb
    je wca7
    mov al, 2
    jmp wcx
wca6:
    mov al, 6
    jmp wcx
wca7:
    mov al, 7
    jmp wcx
wcb:
    mov al, 1
    ret
wcj:
    push di
    push cx
    push es
    push cs
    pop es
    mov ah, 0
    cmp al, {LEADEND}
    jae wcj1
    mov ah, al
    lodsb
wcj1:
    mov di, {NOST}
    mov cx, {NOST_N}
    repne scasw
    je wcj4
    mov di, {NOEND}
    mov cx, {NOEND_N}
    repne scasw
    je wcj5
    mov al, 3
    jmp wcx
wcj4:
    mov al, 4
    jmp wcx
wcj5:
    mov al, 5
wcx:
    pop es
    pop cx
    pop di
    ret
'''

INIT = r'''
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov ax, 0x3510
    int 0x21
    mov word ptr [{OLD10}], bx
    mov word ptr [{OLD10}+2], es
    mov word ptr [{CCH}], 0xffff
    mov word ptr [{CCH}+2], 0xffff
    mov word ptr [{CCH}+4], 0xffff
    mov word ptr [{CCH}+6], 0xffff
    mov word ptr [{JPH}], 0xffff
    mov word ptr [{RETPTR}], {DRV_RET}
    mov word ptr [{C1B47}], 0x1B47
    mov word ptr [{J16A6}], 0x16A6
    mov word ptr [{J167F}], 0x167F
    mov ax, 0x2521
    mov dx, {L_int21}
    int 0x21
    mov ax, 0x2510
    mov dx, {L_int10}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov es, word ptr [0x2c]
    mov ah, 0x49
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''


def fix16(code, addr):
    """keystone が 16ビットコードに混ぜる 32ビット形式の命令を、同じ長さの 16ビット形式に直す"""
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    b = bytearray(code)
    md = Cs(CS_ARCH_X86, CS_MODE_16)
    pos = 0
    while pos < len(b):
        ins = next(md.disasm(bytes(b[pos:]), addr + pos), None)
        if ins is None:
            break
        x = bytes(b[pos:pos + ins.size])
        if x[0] == 0x66:
            if x[1] in (0xe9, 0xe8) and len(x) == 6:
                rel = struct.unpack_from('<i', x, 2)[0] + 3
                b[pos:pos + 6] = bytes([x[1]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] == 0x0f and 0x80 <= x[2] <= 0x8f and len(x) == 7:
                rel = struct.unpack_from('<i', x, 3)[0] + 3
                b[pos:pos + 7] = bytes([0x0f, x[2]]) + struct.pack('<H', rel & 0xFFFF) + b'\x90\x90\x90'
            elif x[1] in (0xca, 0xc2) and len(x) == 4:
                b[pos:pos + 4] = x[1:] + b'\x90'
            elif x[1] in (0xc3, 0xcb) and len(x) == 2:
                b[pos:pos + 2] = x[1:] + b'\x90'
            else:
                raise RuntimeError(f'直せない 32ビット命令: {x.hex()} at {addr + pos:#x}')
        pos += ins.size
    return bytes(b)


def asm(src, addr, kw):
    k = dict(kw)
    k.update(V)
    for n in ("OLD21", "OLD10", "RETPTR", "C1B47", "J16A6", "J167F"):
        k["JMPF_" + n] = JMPF(V[n])
    k["CALLF_OLD21"] = f".byte 0x2e,0xff,0x1e,{V['OLD21'] & 0xff},{V['OLD21'] >> 8}"
    src = "\n".join(line.split(";")[0] for line in src.format(**k).splitlines())
    if not src.strip():
        return b""
    enc, _ = Ks(KS_ARCH_X86, KS_MODE_16).asm(src, addr)
    return fix16(bytes(enc), addr)


def load_bdf(path):
    glyphs = {}
    cur = rows = bbx = None
    asc = 7
    for line in open(path, encoding="latin1"):
        t = line.split()
        if not t:
            continue
        if t[0] == "FONT_ASCENT":
            asc = int(t[1])
        elif t[0] == "ENCODING":
            cur = int(t[1])
        elif t[0] == "BBX":
            bbx = list(map(int, t[1:5]))
        elif t[0] == "BITMAP":
            rows = []
        elif t[0] == "ENDCHAR":
            w, h, xo, yo = bbx
            g = [0] * 8
            top = asc - (yo + h)
            for i, r in enumerate(rows):
                y = top + i
                if 0 <= y < 8:
                    g[y] = (int(r[:2], 16) >> xo) & 0xFF
            glyphs[cur] = bytes(g)
            rows = None
        elif rows is not None:
            rows.append(t[0])
    return glyphs


def is_jp(ch):
    return ord(ch) >= 0x80


class Encoder:
    """訳文を符号に直す。リード L 個（2 バイトの字）と、残りの 1 バイトの字（よく使う字から）"""

    def __init__(self, texts, font):
        freq = {}
        for t in texts:
            for ch in t:
                if is_jp(ch):
                    freq[ch] = freq.get(ch, 0) + 1
        order = sorted(freq, key=lambda c: (-freq[c], c))
        self.missing = [c for c in order if ord(c) not in font]
        n = len(order)
        L = 0
        while (127 - L) + L * len(TRAILS) < n:
            L += 1
        self.L = L
        self.leadend = 0x80 + L
        singles = [c for c in range(0x80 + L, 0x100) if c != 0xA0]
        ns = min(len(singles), n)
        self.code = {}
        gidx = [0] * 128
        gl = bytearray()
        for i, ch in enumerate(order[:ns]):
            self.code[ch] = bytes([singles[i]])
            gidx[singles[i] - 0x80] = i
            gl += font.get(ord(ch), bytes(8))
        rest = order[ns:]
        for k in range(L):
            gidx[k] = ns + k * len(TRAILS)
        for i, ch in enumerate(rest):
            self.code[ch] = bytes([0x80 + i // len(TRAILS), TRAILS[i % len(TRAILS)]])
            gl += font.get(ord(ch), bytes(8))
        self.gidx = gidx
        self.glyphs = bytes(gl)
        self.nchars = n
        self.nsingle = ns

    def encode(self, t):
        out = bytearray()
        for ch in t:
            if is_jp(ch):
                out += self.code[ch]
            else:
                out.append(ord(ch))
        return bytes(out)

    def codes_of(self, chars):
        out = []
        for ch in chars:
            if ch in self.code:
                c = self.code[ch]
                out.append(c[0] if len(c) == 1 else (c[0] << 8) | c[1])
        return out


def cc_index_bytes(entry_no, h, off, size, flag):
    """目次の 1 項目（8 バイト）を暗号にする"""
    plain = bytes([h & 0xFF, h >> 8, off & 0xFF, (off >> 8) & 0xFF, (off >> 16) & 0xFF, size & 0xFF, size >> 8, flag])
    out = bytearray()
    for k, b in enumerate(plain):
        key = (0xAC + 0x67 * (entry_no * 8 + k)) & 0xFF
        v = (b - key) & 0xFF
        out.append(((v >> 2) | (v << 6)) & 0xFF)
    return bytes(out)


VBASE = 0x400000


def layout_ds(ds_items, enc):
    """DS の訳の置き方を決める。ds_items: [(位置, 元の長さ, 訳, 表の中の位置の並び, 即値の参照の数, 途中への参照あり)]
    収まるものはその場に。収まらず、番地の表からだけ指されるものは、空いた所へ移して表を書き換える。
    空いた所 = その場に置いた訳の後ろ（元の 0 の手前まで）と、移した文字列の元の場所。途中への参照があるものの後ろは使わない。
    戻り値: (書き換えの並び（位置, 長さ, バイト列 … 0xFFFF で終わり）, 入らなかったもの, 移した数)"""
    patches = []
    free = []
    moves = []
    over = []
    mem = open(os.path.join(HERE, "..", "build", "mem.bin"), "rb").read()
    ods = mem[0x286F0:0x286F0 + 0x10000]
    for off, olen, t, ptrs, imm, mids in ds_items:
        b = enc.encode(t) + b"\0"
        if off in KEEP_EN:
            # 英語のまま残し、途中から始まる文の訳だけを空いた所へ移して、番地の表を向け替える
            cut, locs = KEEP_EN[off]
            assert b[:cut] == ods[off:off + cut], hex(off)
            moves.append((off + cut, 0, b[cut:], locs))
            continue
        if off in KEEP_EN_BLOCK:
            assert ptrs, hex(off)
            moves.append((off, olen, b, ptrs))
            continue
        if len(b) <= olen + 1:
            patches.append((off, b))
            if not mids and off + len(b) < off + olen:
                free.append([off + len(b), off + olen])
        elif ptrs and imm == 0:
            moves.append((off, olen, b, ptrs))
            if not mids:
                free.append([off, off + olen])
        else:
            over.append((off, len(b) - 1, olen))
    moved = 0
    for off, olen, b, ptrs in sorted(moves, key=lambda m: -len(m[2])):
        best = None
        for fr in free:
            if fr[1] - fr[0] >= len(b) and (best is None or fr[1] - fr[0] < best[1] - best[0]):
                best = fr
        if best is None:
            over.append((off, len(b) - 1, olen))
            continue
        new = best[0]
        best[0] += len(b)
        patches.append((new, b))
        for loc in ptrs:
            patches.append((loc, struct.pack("<H", new)))
        moved += 1
    # 重なりの検査
    spans = sorted((a, a + len(x)) for a, x in patches)
    for (a1, e1), (a2, e2) in zip(spans, spans[1:]):
        assert e1 <= a2, ("DS の書き換えが重なる", hex(a1), hex(a2))
    # 元の DS と同じバイトは書かない（英語の部分を配布物に入れないため、差分だけにする）
    dsp = bytearray()
    for a, x in patches:
        k = 0
        while k < len(x):
            if x[k] == ods[a + k]:
                k += 1
                continue
            e = k
            same = 0
            while e < len(x) and same < 4:
                same = same + 1 if x[e] == ods[a + e] else 0
                e += 1
            e -= same
            dsp += struct.pack("<HH", a + k, e - k) + x[k:e]
            k = e
    dsp += b"\xff\xff"
    return bytes(dsp), over, moved


def build(ds_items, cc_texts, out_com, out_dat, ccpath):
    """ds_items: [(DS の位置, 元の長さ, 訳の文字列)]、cc_texts: {項目の番号: 訳の文字列の並び（0 区切りにする）}"""
    sys.path.insert(0, HERE)
    import lzhuf
    from cc import read_index
    font = load_bdf(BDF)
    alltexts = [it[2] for it in ds_items] + [NOSTART + NOEND]
    for strs in cc_texts.values():
        alltexts += strs
    enc = Encoder(alltexts, font)
    # CC の差し替え: 訳を符号にして 0 区切りで並べ、圧縮して DAT に入れる
    ccraw = open(ccpath, "rb").read()
    ents = read_index(ccraw)
    n_ent = struct.unpack_from("<H", ccraw, 0)[0]
    encidx = ccraw[2:2 + n_ent * 8]
    dat = bytearray()
    idxtab = bytearray()
    for no in sorted(cc_texts):
        body = b"".join(enc.encode(t) + b"\0" for t in cc_texts[no])
        comp = lzhuf.encode(body)
        assert lzhuf.decode(comp) == body
        assert lzhuf.inplace_ok(comp), f"項目 {no}: その場の解凍で追い越す"
        h, off, size, flag = ents[no]
        new = cc_index_bytes(no, h, VBASE + len(dat), len(comp), flag)
        idxtab += struct.pack("<H", no) + encidx[no * 8:no * 8 + 8] + new
        dat += comp
        if len(dat) & 1:
            dat += b"\0"
    idxtab += b"\xff\xff"
    blobs = []
    p = DATA
    lay = {}

    def put(name, blob):
        nonlocal p
        lay[name] = p
        blobs.append((p, blob))
        p += len(blob)
        if p & 1:
            blobs.append((p, b"\0"))
            p += 1
    put("SIG4A", SIG4A)
    put("SIGW", DRV_SIG[0x15B6])
    put("SIGG", DRV_SIG[0x1B08])
    put("SIGD", DRV_SIG[0x1B42])
    put("SIGB", DRV_SIG[0x165A])
    put("CCNAME", b"MM3.CC")
    put("JPNAME", b"MM3JP.DAT\0")
    put("IDXTAB", bytes(idxtab))
    dsp, over, nreloc = layout_ds(ds_items, enc)
    put("DSPATCH", bytes(dsp))
    put("ANOST", ANOSTART)
    put("ANOEND", ANOEND)
    nost = enc.codes_of(NOSTART)
    noend = enc.codes_of(NOEND)
    put("NOST", b"".join(struct.pack("<H", c) for c in nost) or b"\0\0")
    put("NOEND", b"".join(struct.pack("<H", c) for c in noend) or b"\0\0")
    put("GIDX", b"".join(struct.pack("<H", x) for x in enc.gidx))
    put("GLYPHS", enc.glyphs)
    code_at = (p + 15) & ~15
    kw = dict(lay, GAME_DS_ADD=GAME_DS_ADD, DRV_RET=DRV_RET, LEADEND=enc.leadend, IDXLEN=2 + n_ent * 8,
              ANOST_N=len(ANOSTART), ANOEND_N=len(ANOEND), NOST_N=max(1, len(nost)), NOEND_N=max(1, len(noend)))
    labels = ["int21", "int10", "getc", "drawc", "wrap"]
    dummy = {"L_" + n: 0x1234 for n in labels}

    def label(name):
        return code_at + len(asm(RES[:RES.index("\n" + name + ":")], code_at, {**kw, **dummy}))
    lab = {"L_" + n: label(n) for n in labels}
    res = asm(RES, code_at, {**kw, **lab})
    resident_end = code_at + len(res)
    msg = f"MM3JP: Might and Magic III Japanese ({enc.nchars} chars)\r\n$".encode()
    ikw = dict(lab, MSG=0x9000, PARAS=(resident_end + 15) // 16, DRV_RET=DRV_RET)
    init = asm(INIT, resident_end, ikw)
    ikw["MSG"] = resident_end + len(init)
    init = asm(INIT, resident_end, ikw)
    img = bytearray(resident_end + len(init) + len(msg) - 0x100)
    img[0:3] = b"\xe9" + struct.pack("<H", (resident_end - 0x103) & 0xFFFF)
    for a, blob in blobs:
        img[a - 0x100:a - 0x100 + len(blob)] = blob
    img[code_at - 0x100:resident_end - 0x100] = res
    img[resident_end - 0x100:] = init + msg
    open(out_com, "wb").write(img)
    open(out_dat, "wb").write(dat)
    print(f"書き出し: {out_com}  {len(img)} バイト（常駐 {resident_end - 0x100}）、{out_dat} {len(dat)} バイト")
    print(f"字 {enc.nchars}（1 バイト {enc.nsingle}、リード {enc.L}）、DS {len(ds_items) - len(over)} 件、CC {len(cc_texts)} 項目")
    if over:
        print("元より長い DS の訳（入れていない）:", " ".join(f"{o:#x}({a}>{b})" for o, a, b in over))
    if enc.missing:
        print("フォントにない字:", "".join(enc.missing))
    return enc


def load_translations():
    """translation/ja.tsv と英文から、DS の訳と CC の文のファイルを組み立てる"""
    from textfmt import from_text
    tr = os.path.join(HERE, "..", "translation")
    ja = {}
    for l in open(os.path.join(tr, "ja.tsv"), encoding="utf-8"):
        k, t = l.rstrip("\n").split("\t", 1)
        ja[k] = t
    keep_cc = set(l.split("\t")[0] for l in open(os.path.join(tr, "keep_cc.tsv"), encoding="utf-8") if l.strip())
    refs = {}
    for l in open(os.path.join(tr, "ds_refs.tsv"), encoding="utf-8"):
        k, n, imm, ptrs, mids = l.rstrip("\n").split("\t")
        refs[k] = (int(n), int(imm), [int(x, 16) for x in ptrs.split(",") if x], bool(mids))
    from make_work import ds_keep
    ds_items = []
    for l in open(os.path.join(tr, "en_ds.tsv"), encoding="utf-8"):
        k, _, _, _, en_t = l.rstrip("\n").split("\t")
        t = ja.get(k)
        if not t or t == "KEEP" or ds_keep(int(k[2:], 16), en_t):
            continue
        n, imm, ptrs, mids = refs[k]
        ds_items.append((int(k[2:], 16), n, from_text(t), ptrs, imm, mids))
    files = {}
    for l in open(os.path.join(tr, "en_cc.tsv"), encoding="utf-8"):
        k, n, t = l.rstrip("\n").split("\t")
        no = int(k[1:4])
        j = ja.get(k)
        use = j if j and j != "KEEP" and k not in keep_cc else None
        if use:
            use = use.replace("-- More --", "-- つづく --")
        files.setdefault(no, []).append((from_text(use) if use else from_text(t), bool(use)))
    cc_texts = {no: [s for s, _ in v] for no, v in files.items() if any(u for _, u in v)}
    return ds_items, cc_texts


if __name__ == "__main__":
    ds_items, cc_texts = load_translations()
    build(ds_items, cc_texts,
          os.path.join(HERE, "..", "build", "MM3JP.COM"), os.path.join(HERE, "..", "build", "MM3JP.DAT"),
          os.path.join(HERE, "..", "..", "MM3.CC"))
