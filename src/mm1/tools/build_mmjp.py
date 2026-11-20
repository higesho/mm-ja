# Might and Magic 1 用の常駐プログラム MMJP.COM を作る（試作）
#
# 仕組み
#   - INT 21h を横取りする。MM.EXE の起動処理が AH=4Ah を呼んだとき（戻り先 IP=0xEFC6）、呼び出し元 CS の
#     puts（0x0BCC）の中身を照合し、合えば puts の入口を常駐部への jmp far に書き換え、DS の文字列を訳に置き換える
#   - puts の横取り: 文字列を1マスずつ元の puts に渡す。日本語の字は、字形表の SLOT 番（2ビット形式 DS:0x48FC と
#     1ビット形式 DS:0x4D0C の両方）に一時的に写して描き、描いたら元に戻す
#
# 文字の符号（1バイト = 1マス。ゲームの桁の計算がそのまま使える）
#   0x00 終わり / 0x0D 改行 / 0x20〜0x7F 英数字（ゲームの字）
#   0xA0〜0xFF       よく使う字 96 字（1バイトで1字）
#   リード＋トレイル  2字の組を2マスに描く（組の片方は英数字でもよい）
#                    リード 0x02〜0x0C,0x0E〜0x1F,0x80〜0x9F（61種）、トレイル 0x01〜0xFF の 0x0D 以外（254種）
#   0x01 b1 b2       長い訳の印: 常駐部の中の訳（番号 (b1-1)*255+(b2-1)）を描く
#
# 使い方: python build_mmjp.py <MM.EXE> <訳のファイル> <出力 MMJP.COM>
#   訳のファイル: 「E.<DS の位置（16進）><TAB>訳」。\n は改行。# で始まる行は注釈
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from keystone import Ks, KS_ARCH_X86, KS_MODE_16  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")

EXE_DS = 0x107B0                 # 読み込み像の中の DS の位置
PUTS = 0x0BCC                    # puts の入口（CS）
PUTS_CONT = 0x0BD3               # 入口の4命令（push bx/dx/bp, mov bx,[0xB8]）の次
PUTS_SIG = bytes.fromhex("5352558b1eb800021e0e018b871801a3")
RETF_GADGET = 0x09E9             # CS の中の 0xCB（retf）のバイト。元の puts の near ret をここに戻して far で帰る
STARTUP_RET = 0xEFC6             # 起動処理の int 21h（AH=4Ah）の次
VAR_STR = 0x3BD4                 # puts が描く文字列の番地
VAR_COL, VAR_ROW = 0x10F, 0x111  # カーソル（語）
CBUF = 0x1EB8                    # cout の1文字の置き場（DS）
SLOT = 0x5F                      # 字形を一時的に写す番号
EXP_TAB = 0x48FC                 # 2ビット形式の字形表（0x20〜0x60、16 バイト/字）
BIT_TAB = 0x4D0C                 # 1ビット形式の字形表（8 バイト/字）
MARK = 0x01
# 追加の文字列（訳のファイルの鍵 X.名前）: 名前 → (宿り先の文字列の DS の位置, 命令の即値の CS の位置, 元の即値)
#   英語で使い回している文字列を、日本語では別の訳にしたいときに使う
EXTRA = {"COND_GOOD": (0x26E4, 0x696C, 0x268C)}   # 状態の GOOD（英語は性格の GOOD を使い回す）。宿り先は ERADICATED
# 英語のままメモリに残す文字列: DS の位置 → それを出す命令の即値の CS の位置
#   Where Are We?（DOSBox のメモリを読む自動マッピングの道具）は、"NO SPELL POINTS\0SPELL FAILED\0" を目印に MM1 を探す
KEEP_EN = {0x3B99: 0xDA3A,      # nosppts: NO SPELL POINTS
           0x3BA9: 0xDA05}      # goz34: SPELL FAILED
MONBUF2 = 0x1928                 # 遭遇の一覧（0x3573）が怪物の名前を 15 バイト（後ろの空白ごと）写して出す置き場
MONBUF = 0x38C9                  # pmonname が怪物の名前を写して空白2つで切る置き場（ここから来た文字列は日本語の名前に差し替える）
# 本体のコード（CS）の書き換え: (位置, 元のバイト, 新しいバイト)。英語の複数形の S を足す所を飛ばす
CODE_FIX = [(0xB448, 0x72, 0xEB),    # inopsh: TAKES n POINT(S) OF DAMAGE! の S
            (0xC127, 0x74, 0xEB),    # rolldmg: ... FOR n POINT(S) OF DAMAGE! の S
            (0xACF4, 0x00, 0x07)]    # invron: 反転の英語ラベル ROUND #（DS:0x31C4、7 字）を描かず、回数の数字だけ反転する
LEADS = list(range(0x02, 0x0D)) + list(range(0x0E, 0x20)) + list(range(0x80, 0xA0))
TRAILS = [c for c in range(0x01, 0x100) if c not in (0x0D, 0x20)]   # 0x20 は名前の切り方（空白2つ）とぶつかるので外す
PUTC_BUF = 0x38D9                # 0xC5AD（1文字を位置に描く）の置き場。ここから来た字は日本語として読まない（ROUND # の反転など）
ITEM_TAB, ITEM_N, ITEM_SZ, ITEM_W = 0x917A, 255, 24, 14   # 品物: 名前 14 桁＋データ 10 バイト
MON_TAB, MON_N, MON_SZ, MON_W = 0xA962, 195, 32, 15        # 怪物: 名前 15 桁＋データ 17 バイト
SINGLES = list(range(0xA0, 0x100))
NT = len(TRAILS)

# ---- 常駐部の変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("OLD21", 4), ("FARP", 4), ("GAMECS", 2), ("GAMEDS", 2), ("DONE", 1), ("RETIP", 2),
                   ("SAVEPTR", 2), ("SAVE16", 16), ("SAVE8", 8)]:
    V[name] = _p
    _p += size
CODE = (_p + 15) & ~15

FAR_JMP = lambda a: f".byte 0x2e,0xff,0x2e,{a & 0xff},{a >> 8}"

RES = r'''
int21:
    cmp ah, 0x3f
    je i_3f
    cmp ah, 0x4a
    je i_4a
    cmp ah, 0x4c
    jne chain
    mov byte ptr cs:[{DONE}], 0
chain:
    {jmp_old}

; オーバーレイのデータ部の読み込み（DS:0xC940 へ）: 読んだ後に中身のハッシュで照合して置き換える
i_3f:
    cmp byte ptr cs:[{DONE}], 1
    jne chain
    cmp dx, {OVR_DS}
    jne chain
    push ax
    mov ax, ds
    cmp ax, word ptr cs:[{GAMEDS}]
    pop ax
    jne chain
    pushf
    {call_old}
    jc r_out
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    cld
    mov cx, ax
    push ds
    pop es
    mov di, {OVR_DS}
    push cx
    call hash
    pop cx
    push cs
    pop ds
    mov si, {OVTAB}
o_lp:
    mov ax, word ptr [si]
    or ax, ax
    je o_end
    cmp ax, cx
    jne o_nx
    cmp bx, word ptr [si+2]
    jne o_nx
    cmp dx, word ptr [si+4]
    jne o_nx
    mov si, word ptr [si+6]
    call apply
    jmp o_end
o_nx:
    add si, 8
    jmp o_lp
o_end:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
r_out:
    retf 2

; ES:DI から CX バイトのハッシュ → BX, DX
hash:
    xor bx, bx
    xor dx, dx
    jcxz h_ret
h_lp:
    mov al, byte ptr es:[di]
    xor ah, ah
    rol bx, 1
    add bx, ax
    add dx, ax
    rol dx, 1
    rol dx, 1
    rol dx, 1
    inc di
    loop h_lp
h_ret:
    ret

; DS:SI の置き換えの並び（位置, 長さ, 中身 … 0xFFFF）を ES に書く
apply:
    lodsw
    cmp ax, 0xffff
    je a_ret
    mov di, ax
    lodsw
    mov cx, ax
    test ch, 0x80
    jnz a_copy
    rep movsb
    jmp apply
a_copy:
    and ch, 0x7f
    lodsw
    push ds
    push si
    push es
    pop ds
    mov si, ax
    rep movsb
    pop si
    pop ds
    jmp apply
a_ret:
    ret

; 怪物の名前: ES:SI（pmonname か遭遇の一覧の置き場）の英語の名前を、pmonname と同じに切って（0、空白2つ、
; 最後の空白、15 バイトのどれか）ハッシュで表を引き、見つかれば ES:SI を常駐部の中の日本語の名前に変える。AX BX CX DX DI を使う
monname:
    mov di, si
    xor cx, cx
mn_len:
    mov al, byte ptr es:[di]
    or al, al
    je mn_hash
    cmp al, 0x20
    jne mn_next
    cmp cx, 14
    jae mn_hash
    cmp byte ptr es:[di+1], 0x20
    je mn_hash
mn_next:
    inc di
    inc cx
    cmp cx, 15
    jb mn_len
mn_hash:
    mov di, si
    call hash
    push ds
    push cs
    pop ds
    mov di, {MONTAB}
    mov cx, {MONN}
mn_lp:
    jcxz mn_no
    cmp bx, word ptr [di]
    jne mn_nx
    cmp dx, word ptr [di+2]
    jne mn_nx
    mov si, word ptr [di+4]
    pop ds
    push cs
    pop es
    ret
mn_nx:
    add di, 6
    dec cx
    jmp mn_lp
mn_no:
    pop ds
    ret

i_4a:
    cmp byte ptr cs:[{DONE}], 0
    jne chain
    push bp
    mov bp, sp
    cmp word ptr [bp+2], {STARTUP_RET}
    jne i_out
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov es, word ptr [bp+4]
    push cs
    pop ds
    cld
    mov di, {PUTS}
    mov cx, {SIGLEN}
    call hash
    cmp bx, {SIGH1}
    jne i_pop
    cmp dx, {SIGH2}
    jne i_pop
    mov word ptr [{GAMECS}], es
    mov word ptr [{FARP}+2], es
    mov word ptr [{FARP}], {PUTS_CONT}
    mov ax, es
    add ax, {DSPARA}
    mov word ptr [{GAMEDS}], ax
    mov byte ptr es:[{PUTS}], 0xea
    mov word ptr es:[{PUTS}+1], {HOOK}
    mov word ptr es:[{PUTS}+3], cs
    push ax
    mov si, {CPATCHES}
    call apply
    pop ax
    mov es, ax
    mov si, {PATCHES}
    call apply
    mov byte ptr [{DONE}], 1
i_pop:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
i_out:
    pop bp
    jmp chain

; ---- puts の横取り（ゲームの jmp far から来る。スタックの上は near の戻り先、DS はゲームの DS）----
puts_hook:
    pop word ptr cs:[{RETIP}]
    push word ptr cs:[{GAMECS}]
    push word ptr cs:[{RETIP}]
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push bp
    push es
    mov ax, word ptr [{VAR_STR}]
    mov word ptr cs:[{SAVEPTR}], ax
    mov si, ax
    push ds
    pop es
    cmp ax, {MONBUF}
    je ph_mon
    cmp ax, {MONBUF2}
    jne ph_notmon
ph_mon:
    call monname
    jmp ph_loop
ph_notmon:
    cmp ax, {PUTC_BUF}
    jne ph_mark
    mov al, byte ptr [si]
    call putc
    jmp ph_done
ph_mark:
    cmp byte ptr es:[si], {MARK}
    jne ph_loop
    mov al, byte ptr es:[si+1]
    dec al
    mov ah, 255
    mul ah
    mov bl, byte ptr es:[si+2]
    dec bl
    xor bh, bh
    add ax, bx
    shl ax, 1
    mov bx, ax
    mov si, word ptr cs:[bx+{STRTAB}]
    push cs
    pop es
ph_loop:
    mov al, byte ptr es:[si]
    inc si
    or al, al
    je ph_done
    cmp al, 0x0d
    jne ph_1
    mov word ptr [{VAR_COL}], 0
    inc word ptr [{VAR_ROW}]
    jmp ph_loop
ph_1:
    cmp al, 0x20
    jb ph_lead
    cmp al, 0x80
    jb ph_ascii
    cmp al, 0xa0
    jb ph_lead
    sub al, 0xa0
    xor ah, ah
    call putg
    jmp ph_loop
ph_ascii:
    call putc
    jmp ph_loop
ph_lead:
    mov bl, al
    xor bh, bh
    mov bl, byte ptr cs:[bx+{LEADIX}]
    mov al, byte ptr es:[si]
    inc si
    or al, al
    je ph_done
    mov cl, al
    xor ch, ch
    mov di, cx
    mov cl, byte ptr cs:[di+{TRAILIX}]
    mov ax, {NT}
    mul bx
    add ax, cx
    shl ax, 1
    shl ax, 1
    mov bx, ax
    push word ptr cs:[bx+{PAIRS}+2]
    mov ax, word ptr cs:[bx+{PAIRS}]
    call putg
    pop ax
    call putg
    jmp ph_loop
ph_done:
    mov ax, word ptr cs:[{SAVEPTR}]
    mov word ptr [{VAR_STR}], ax
    pop es
    pop bp
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    retf

; AX = 字（0x8000 以上なら下位が英数字、それ以外は字形の番号）
putg:
    test ah, 0x80
    jz pg_jp
    jmp putc
pg_jp:
    push si
    push di
    push cx
    push bx
    push es
    shl ax, 1
    shl ax, 1
    shl ax, 1
    add ax, {GLYPHS}
    mov bx, ax
    push ds
    pop es
    push cs
    pop ds
    ; 元の字形を退避（DS はいま CS、ES はゲームの DS）
    mov cx, 8
    xor di, di
pg_save:
    mov ax, word ptr es:[di+{EXPS}]
    mov word ptr [di+{SAVE16}], ax
    add di, 2
    loop pg_save
    mov ax, word ptr es:[{BITS}]
    mov word ptr [{SAVE8}], ax
    mov ax, word ptr es:[{BITS}+2]
    mov word ptr [{SAVE8}+2], ax
    mov ax, word ptr es:[{BITS}+4]
    mov word ptr [{SAVE8}+4], ax
    mov ax, word ptr es:[{BITS}+6]
    mov word ptr [{SAVE8}+6], ax
    ; 日本語の字形を写す
    xor di, di
    mov cx, 8
pg_put:
    mov al, byte ptr [bx]
    mov byte ptr es:[di+{BITS}], al
    push bx
    mov bl, al
    shr bl, 1
    shr bl, 1
    shr bl, 1
    shr bl, 1
    xor bh, bh
    mov ah, byte ptr [bx+{EXP}]
    mov bl, al
    and bl, 0x0f
    mov al, byte ptr [bx+{EXP}]
    pop bx
    push di
    shl di, 1
    mov byte ptr es:[di+{EXPS}], ah
    mov byte ptr es:[di+{EXPS}+1], al
    pop di
    inc bx
    inc di
    loop pg_put
    push es
    pop ds
    mov al, {SLOT}
    call putc
    ; 元に戻す（DS はゲームの DS）
    push cs
    pop es
    mov cx, 8
    xor di, di
pg_rest:
    mov ax, word ptr es:[di+{SAVE16}]
    mov word ptr [di+{EXPS}], ax
    add di, 2
    loop pg_rest
    mov ax, word ptr es:[{SAVE8}]
    mov word ptr [{BITS}], ax
    mov ax, word ptr es:[{SAVE8}+2]
    mov word ptr [{BITS}+2], ax
    mov ax, word ptr es:[{SAVE8}+4]
    mov word ptr [{BITS}+4], ax
    mov ax, word ptr es:[{SAVE8}+6]
    mov word ptr [{BITS}+6], ax
    pop es
    pop bx
    pop cx
    pop di
    pop si
    ret

; AL = 1マスの字。元の puts に1文字の文字列として渡す
putc:
    push si
    push di
    push cx
    mov byte ptr [{CBUF}], al
    mov byte ptr [{CBUF}+1], 0
    mov word ptr [{VAR_STR}], {CBUF}
    push cs
    .byte 0x68,{BACK_LO},{BACK_HI}
    .byte 0x68,{RETF_LO},{RETF_HI}
    push bx
    push dx
    push bp
    mov bx, word ptr [0xb8]
    {jmp_puts}
pc_back:
    pop cx
    pop di
    pop si
    ret
'''

INIT = r'''
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21}+2], es
    mov ax, 0x2521
    mov dx, {INT21}
    int 0x21
    mov ah, 9
    mov dx, {MSG}
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''


def fix16(code, addr):
    """keystone が 16ビットコードに混ぜる 32ビット形式の命令を、同じ長さの 16ビット形式に直す（U5 の jpenc.py と同じ）"""
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
    for n in ('BACK', 'RETF_GADGET'):
        if n in k:
            k[n.split('_')[0] + '_LO'], k[n.split('_')[0] + '_HI'] = k[n] & 0xFF, k[n] >> 8
    k.update(jmp_old=FAR_JMP(V["OLD21"]), jmp_puts=FAR_JMP(V["FARP"]),
             call_old=f".byte 0x2e,0xff,0x1e,{V['OLD21'] & 0xff},{V['OLD21'] >> 8}")
    src = "\n".join(line.split(";")[0] for line in src.format(**k).splitlines())
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
    return not (0x20 <= ord(ch) < 0x7F) and ch != "\r"


class Encoder:
    """訳文を符号に直す。よく使う字は1バイト、残りは2字の組（2バイトで2マス）"""

    def __init__(self, texts):
        freq = {}
        for t in texts:
            for ch in t:
                if is_jp(ch):
                    freq[ch] = freq.get(ch, 0) + 1
        top = sorted(freq, key=lambda c: (-freq[c], c))[:int(os.environ.get('MMJP_SINGLES', len(SINGLES)))]
        self.single = {ch: SINGLES[i] for i, ch in enumerate(top)}
        self.glyph_order = []        # 字形の番号 → 字
        self.glyph_ix = {}
        self.pairs = {}              # (a, b) → 組の番号
        self.pair_list = []
        for ch in top:                 # 1バイトの字は字形の番号＝符号−0xA0
            self.gix(ch)

    def gix(self, ch):
        if ch not in self.glyph_ix:
            self.glyph_ix[ch] = len(self.glyph_order)
            self.glyph_order.append(ch)
        return self.glyph_ix[ch]

    def segment(self, t):
        # 最短: 余分なマス（組に空白を足す）を最少に、次に組の数を最少に
        n = len(t)
        best = [None] * (n + 1)
        best[n] = ((0, 0), None)
        for i in range(n - 1, -1, -1):
            ch = t[i]
            nxt = t[i + 1] if i + 1 < n else None
            opts = []

            def add(cost, unit, j):
                c2 = best[j][0]
                opts.append(((cost[0] + c2[0], cost[1] + c2[1]), (unit, j)))
            if not is_jp(ch):
                add((0, 0), ("a", ch), i + 1)
                if nxt is not None and is_jp(nxt) and nxt not in self.single and ch != "\r":
                    add((0, 1), ("p", ch, nxt), i + 2)
            else:
                if ch in self.single:
                    add((0, 0), ("s", ch), i + 1)
                if nxt is not None and nxt != "\r":
                    add((0, 1), ("p", ch, nxt), i + 2)
                add((1, 1), ("p", ch, " "), i + 1)
            best[i] = min(opts, key=lambda o: o[0])
        units = []
        i = 0
        while i < n:
            unit, j = best[i][1]
            units.append(unit)
            i = j
        return units

    def code(self, ch):
        return 0x8000 | ord(ch) if not is_jp(ch) else self.gix(ch)

    def encode(self, t):
        out = bytearray()
        for u in self.segment(t):
            if u[0] == "a":
                out.append(0x0D if u[1] == "\r" else ord(u[1]))
            elif u[0] == "s":
                self.gix(u[1])
                out.append(self.single[u[1]])
            else:
                key = (u[1], u[2])
                for ch in key:
                    if is_jp(ch):
                        self.gix(ch)
                if key not in self.pairs:
                    self.pairs[key] = len(self.pair_list)
                    self.pair_list.append(key)
                n = self.pairs[key]
                out += bytes([LEADS[n // NT], TRAILS[n % NT]])
        return bytes(out)


COPY_MIN = 8                     # 元の英文と同じ英字の並びがこれ以上なら、書かずにメモリの元の英文から写す


def copy_ops(off, b, en):
    """訳のバイト列 b（DS:off に書く）のうち、元の英文 en と同じ半角の並び（COPY_MIN 字以上）は
    「写す」命令にする（配布物に原作の文を入れないため）。写す先は写す元より前（左へ動く）のときだけ。
    戻り値: [(位置, バイト列) か (位置, ("copy", 元の位置, 長さ))]。写す命令を先に並べる"""
    copies, writes = [], []
    i = start = 0
    while i < len(b):
        if 0x20 <= b[i] < 0x7F:
            j = i
            while j < len(b) and 0x20 <= b[j] < 0x7F:
                j += 1
            seg = b[i:j]
            k = en.find(seg) if len(seg.strip()) >= COPY_MIN else -1
            if k >= 0 and i <= k:
                if start < i:
                    writes.append((off + start, b[start:i]))
                copies.append((off + i, ("copy", off + k, len(seg))))
                start = j
            i = j
        else:
            i += 1
    if start < len(b):
        writes.append((off + start, b[start:]))
    return copies + writes


def norm(t):
    return t.replace("\\n", "\r")


WIDTH = 40                                   # 画面の桁数（puts は 40 マス目で自動的に改行する）
NO_HEAD = set("、。，．・：；？！ー～…‥」』）］｝〉》】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ")
NO_TAIL = set("「『（［｛〈《【")


def layout(t, start=0):
    """訳文を 40 マスで折り返す（1字＝1マス）。行頭禁則は追い出し、行末禁則は次の行へ送る。
    ちょうど 40 マスの行の後ろの改行は、ゲームの自動改行と重なって空行になるので除く。
    戻り値: (直した文, 注意の一覧)"""
    notes = []
    out = []
    col = start
    for li, line in enumerate(t.split("\r")):
        if li and line[:1] in NO_HEAD:
            notes.append(f"改行の直後が行頭禁則の字「{line[0]}」")
        cur = ""
        for ch in line:
            if col + len(cur) >= WIDTH:
                # 折り返す: 次の字が行頭禁則なら、前の行の末尾を送る（最大 2 字）。行末禁則の字も送る
                carry = ""
                k = 0
                while cur and k < 2 and (ch in NO_HEAD if not carry else carry[0] in NO_HEAD):
                    carry = cur[-1] + carry
                    cur = cur[:-1]
                    k += 1
                while cur and cur[-1] in NO_TAIL:
                    carry = cur[-1] + carry
                    cur = cur[:-1]
                out.append((cur, col + len(cur) >= WIDTH))
                col = 0
                cur = carry
            cur += ch
        out.append((cur, False))
        col = 0
    # ちょうど 40 マスの行は改行を書かない（自動改行に任せる）。それ以外は改行で区切る
    s = ""
    for i, (line, full) in enumerate(out):
        s += line
        if i + 1 < len(out):
            w = (start if i == 0 else 0) + len(line)
            if w < WIDTH:
                s += "\r"
    return s, notes


def read_translation(path):
    items = []
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#"):
            continue
        key, ja = line.split("\t", 1)
        items.append((key, ja))
    return items


def rol16(x, n):
    return ((x << n) | (x >> (16 - n))) & 0xFFFF


def h12(bs):
    h1 = h2 = 0
    for b in bs:
        h1 = (rol16(h1, 1) + b) & 0xFFFF
        h2 = rol16((h2 + b) & 0xFFFF, 3)
    return h1, h2


def read_inner():
    """抜き出しの一覧（en_exe.tsv / en_ovr.tsv）から、途中への参照の位置"""
    inner = {}
    for fn in ("en_exe.tsv", "en_ovr.tsv"):
        for line in open(os.path.join(HERE, "..", "translation", fn), encoding="utf-8"):
            t = line.rstrip("\n").split("\t")
            inner[t[0]] = [int(x) for x in t[3].split(",") if x]
    return inner


def main(game, trfile, out):
    d = open(os.path.join(game, "MM.EXE"), "rb").read()
    hdr = struct.unpack_from("<H", d, 8)[0] * 16
    img = d[hdr:]
    assert img[PUTS:PUTS + len(PUTS_SIG)] == PUTS_SIG, "puts の中身が違います"
    assert img[RETF_GADGET] == 0xCB
    sources = {"E": (img[EXE_DS:], 0)}        # 鍵の頭 → (データ, DS の位置の起点)
    ovinfo = {}
    for fn in sorted(os.listdir(game)):
        if fn.upper().endswith(".OVR"):
            o = open(os.path.join(game, fn), "rb").read()
            _, _, csize, daddr, dsize, _, _ = struct.unpack_from("<7H", o, 0)
            data = o[14 + csize:14 + csize + dsize]
            name = fn[:-4].upper()
            sources[name] = (data, daddr)
            ovinfo[name] = (dsize, *h12(data))
    inner_all = read_inner()
    items = read_translation(trfile)
    enc = Encoder([norm(ja) for _, ja in items])
    patches = {}                   # 鍵の頭 → [(DS の位置, バイト列)]
    longs = []
    warns = []
    warns_w = []                   # 桁あふれのおそれ
    warns_k = []                   # 禁則
    extras = {}                    # 追加の文字列（X.名前）: 名前 → 訳
    mon_jp = {}                    # 怪物の番号 → 日本語の名前（符号）
    moved = []                     # 英語のまま残し、訳を別の所に置く文字列: (DS の位置, 符号)
    hosts = {}                     # 宿り先にできる文字列: DS の位置 → [使った長さ, 英文の長さ＋0]
    for key, ja in items:
        kind, off = key.split(".")
        if kind == "X":
            extras[off] = ja
            continue
        if kind in ("I", "M"):
            # 品物の名前: 表の中の決まった幅をその場で書き換える（0 で終わらない）
            # 怪物の名前: 表は英語のまま残し（Where Are We? などがメモリから読むため）、画面に出すときに差し替える
            n = int(off)
            tab, cnt, size, w = (ITEM_TAB, ITEM_N, ITEM_SZ, ITEM_W) if kind == "I" else (MON_TAB, MON_N, MON_SZ, MON_W)
            assert 1 <= n <= cnt, key
            b = enc.encode(norm(ja))
            limit = w if kind == "I" else w - 1        # 怪物名は空白2つで切るので、最後の1マスは空ける
            assert len(b) <= limit and b"  " not in b and b"\r" not in b, f"{key}: 名前が {limit} マスに入りません: {ja}"
            if kind == "M":
                mon_jp[n] = b
            else:
                patches.setdefault("E", []).append((tab + (n - 1) * size, b + b" " * (w - len(b))))
            continue
        off = int(off, 16)
        data, base = sources[kind]
        en = data[off - base:data.index(b"\0", off - base)]
        en_len = len(en)
        align = None
        for tag in ("{c}", "{l}", "{r}"):
            if ja.startswith(tag):
                align, ja = tag[1], ja[3:]
        # 英文の前後の空白は訳に引き継ぐ（エディタが行末の空白を消しても困らないように）
        lead_sp = len(en) - len(en.lstrip(b" ")) if not ja.startswith(" ") else 0
        trail_sp = len(en) - len(en.rstrip(b" ")) if not ja.endswith(" ") else 0
        if en.strip(b" ") and align is None:
            ja = " " * lead_sp + ja + " " * trail_sp
        parts = [norm(x) for x in ja.split("|")]
        if len(parts) == 1 and align is None:
            parts[0], notes = layout(parts[0])
            for nt in notes:
                warns_k.append(f"{key}: {nt}")
            en_lines = en.split(b"\r")
            ja_lines = parts[0].split("\r")
            # 1行だけの英文（メニュー・見出しなど）は画面の位置が英文の幅で決まっているので、それより長い訳に注意
            if len(en_lines) == 1 and len(en) < WIDTH and len(ja_lines) == 1 and len(ja_lines[0]) > len(en):
                warns_w.append(f"{key}({len(ja_lines[0])}>{len(en)})")
        inner = inner_all.get(key, [])
        if len(parts) > 1:
            assert len(parts) - 1 == len(inner), f"{key}: | の数 {len(parts) - 1} が途中への参照 {inner} と合いません"
            bounds = [0] + inner
            b = bytearray()
            for i, part in enumerate(parts[:-1]):
                x = enc.encode(part)
                w = bounds[i + 1] - bounds[i]
                assert len(x) <= w, f"{key}: 区切り {i} の訳が {len(x)} バイトで {w} バイトに入りません"
                b += x + b" " * (w - len(x))
            b += enc.encode(parts[-1])
            b = bytes(b)
        else:
            b = enc.encode(parts[0])
            if inner:
                warns.append(key)
        if align is not None:
            assert len(b) <= en_len, f"{key}: {{{align}}} の訳が英文より長い"
            pad = en_len - len(b)
            l = {"l": 0, "r": pad, "c": pad // 2}[align]
            b = b" " * l + b + b" " * (pad - l)
        if kind == "E" and off in KEEP_EN:
            # 英文をメモリに残す（Where Are We? の目印）。訳は後で宿り先に置き、出す命令の即値を向け直す
            assert len(parts) == 1 and align is None, f"{key}: 英語を残す文字列には | や寄せを使えません"
            moved.append((off, b))
            continue
        if len(b) <= en_len:
            ops = copy_ops(off, b + b"\0", en)
            patches.setdefault(kind, []).extend(ops)
            if kind == "E" and not inner and len(ops) == 1 and not isinstance(ops[0][1], tuple):
                hosts[off] = [len(b) + 1, en_len + 1]
        else:
            assert len(parts) == 1, f"{key}: | で区切った訳は英文の長さに収めてください"
            assert en_len >= 3, f"{key}: 長い訳の印が入りません（英文 {en_len} バイト）"
            n = len(longs)
            longs.append(b)
            patches.setdefault(kind, []).append((off, bytes([MARK, n // 255 + 1, n % 255 + 1, 0])))
    extra_code = []
    # 追加の文字列: 宿り先の文字列（英文より短い訳）の 0 の後ろの空きに置き、命令の即値をそこへ向ける
    epos = {off: b for off, b in patches.get("E", [])}
    for name, (host, imm_at, old_ptr) in EXTRA.items():
        assert struct.unpack_from("<H", img, imm_at)[0] == old_ptr, f"{name}: 即値 {imm_at:#x} が違います"
        if name not in extras:
            continue
        data = img[EXE_DS:]
        room = data.index(b"\0", host) - host + 1          # 英文の長さ＋0
        used = len(epos[host]) if host in epos else room
        b = enc.encode(norm(extras[name])) + b"\0"
        assert used + len(b) <= room, f"{name}: 宿り先 E.{host:04x} の空きが足りません（空き {room - used}、要る {len(b)}）"
        patches["E"].append((host + used, b))
        extra_code.append((imm_at, struct.pack("<H", host + used)))
        hosts.pop(host, None)
    # 英語を残した文字列の訳: 空きのある宿り先に置き、その文字列を出す命令の即値を向け直す
    for off, b in moved:
        imm_at = KEEP_EN[off]
        assert struct.unpack_from("<H", img, imm_at)[0] == off, f"E.{off:04x}: 即値 {imm_at:#x} が違います"
        b = b + b"\0"
        host = next((h for h, (u, r) in sorted(hosts.items()) if r - u >= len(b)), None)
        assert host is not None, f"E.{off:04x}: 訳を置く空きが見つかりません"
        u, r = hosts[host]
        patches["E"].append((host + u, b))
        extra_code.append((imm_at, struct.pack("<H", host + u)))
        hosts[host][0] += len(b)
        print(f"英語を残す E.{off:04x}: 訳を E.{host:04x} の後ろ（DS:{host + u:04x}）に置く")
    # 怪物の名前の表: pmonname が空白2つで切った英語の名前のハッシュ → 日本語の名前
    montab = {}
    for n, b in sorted(mon_jp.items()):
        rec = img[EXE_DS + MON_TAB + (n - 1) * MON_SZ:][:MON_W]
        cut = MON_W
        for i in range(MON_W):
            if rec[i] == 0x20 and (i + 1 == MON_W or rec[i + 1] == 0x20):
                cut = i
                break
        hk = h12(rec[:cut])
        assert montab.get(hk, b) == b, f"M.{n:03d}: 同じ英語の名前に別の訳があります"
        montab[hk] = b
    assert len(enc.pair_list) <= len(LEADS) * NT
    font = load_bdf(BDF)
    missing = [c for c in enc.glyph_order if ord(c) not in font]
    gl = b"".join(font.get(ord(c), bytes(8)) for c in enc.glyph_order)
    pairs = b"".join(struct.pack("<HH", enc.code(a), enc.code(b)) for a, b in enc.pair_list)
    leadix = bytearray(256)
    for i, c in enumerate(LEADS):
        leadix[c] = i
    trailix = bytearray(256)
    for i, c in enumerate(TRAILS):
        trailix[c] = i
    exp = bytes(sum(3 << (2 * k) for k in range(4) if n >> k & 1) for n in range(16))
    def plist(ps):
        out = b""
        for off, b in ps:
            if isinstance(b, tuple):        # 写す: 位置, 0x8000|長さ, 元の位置
                out += struct.pack("<HHH", off, 0x8000 | b[2], b[1])
            else:
                out += struct.pack("<HH", off, len(b)) + b
        return out + b"\xff\xff"
    sigh = h12(PUTS_SIG)
    for at, old, new in CODE_FIX:
        assert img[at] == old, f"コードの書き換え {at:#x} の元のバイトが違います"
    CODE_PATCHES = [(at, bytes([new])) for at, old, new in CODE_FIX]
    CODE_PATCHES += extra_code

    kw = dict(PUTC_BUF=PUTC_BUF, SIGH1=sigh[0], SIGH2=sigh[1], OVR_DS=0xC940, STARTUP_RET=STARTUP_RET, PUTS=PUTS, PUTS_CONT=PUTS_CONT, SIGLEN=len(PUTS_SIG), DSPARA=EXE_DS >> 4,
              VAR_STR=VAR_STR, VAR_COL=VAR_COL, VAR_ROW=VAR_ROW, MARK=MARK, NT=NT, CBUF=CBUF, SLOT=SLOT,
              RETF_GADGET=RETF_GADGET, EXPS=EXP_TAB + (SLOT - 0x20) * 16, BITS=BIT_TAB + (SLOT - 0x20) * 8,
              MONBUF=MONBUF, MONBUF2=MONBUF2, MONN=len(montab))
    dummy = dict(MONTAB=0x9000, CPATCHES=0x9000, OVTAB=0x9000, SIG=0x9000, HOOK=0x9000, PATCHES=0x9000, STRTAB=0x9000, LEADIX=0x9000, TRAILIX=0x9000,
                 PAIRS=0x9000, GLYPHS=0x9000, EXP=0x9000, BACK=0x9000)
    res = asm(RES, CODE, {**kw, **dummy})
    p = CODE + len(res)
    lay = {}

    def put(name, blob):
        nonlocal p
        lay[name] = p
        blobs.append((p, blob))
        p += len(blob)
    blobs = []
    put("EXP", exp)
    put("LEADIX", bytes(leadix))
    put("TRAILIX", bytes(trailix))
    put("PATCHES", plist(patches.get("E", [])))
    put("CPATCHES", plist(CODE_PATCHES))
    # 怪物の名前: 日本語の名前（0 で終わる）を並べ、その後ろに表（h1, h2, 名前の位置）
    mpos = {}
    mbody = b""
    for hk, b in montab.items():
        mpos[hk] = p + len(mbody)
        mbody += b + b"\0"
    put("MONSTR", mbody)
    put("MONTAB", b"".join(struct.pack("<HHH", hk[0], hk[1], mpos[hk]) for hk in montab))
    # オーバーレイの表: データの大きさ, ハッシュ h1, h2, 置き換えの並び（同じ中身のものは1つにまとめる）
    ovl = {}
    for name, ps in patches.items():
        if name != "E":
            ovl.setdefault(ovinfo[name], []).extend(ps)
    ovpos = {}
    for k, ps in ovl.items():
        ovpos[k] = p
        put("OVP_%x_%x" % k[1:], plist(ps))
    put("OVTAB", b"".join(struct.pack("<4H", *k, ovpos[k]) for k in ovl) + b"\0\0")
    put("PAIRS", pairs)
    put("GLYPHS", gl)
    strtab = p
    p += 2 * len(longs)
    sptr, sbody = [], bytearray()
    for s in longs:
        sptr.append(p + len(sbody))
        sbody += s + b"\0"
    put("STRBODY", bytes(sbody))
    resident_end = p
    lay["STRTAB"] = strtab
    # ラベルの位置は、そのラベルより前だけを組み立てて求める
    def label(name):
        return CODE + len(asm(RES[:RES.index("\n" + name + ":")], CODE, {**kw, **dummy, **lay}))
    lay["HOOK"] = 0x9000
    lay["BACK"] = 0x9000
    lay["HOOK"] = label("puts_hook")
    lay["BACK"] = label("pc_back")
    res2 = asm(RES, CODE, {**kw, **dummy, **lay})
    assert len(res2) == len(res)
    msg = f"MMJP: test build ({len(enc.glyph_order)} chars, {len(enc.pair_list)} pairs)\r\n$".encode()
    ikw = dict(INT21=CODE, MSG=0x9000, PARAS=(resident_end + 15) // 16)
    init = asm(INIT, resident_end, ikw)
    ikw["MSG"] = resident_end + len(init)
    init = asm(INIT, resident_end, ikw)

    out_img = bytearray(b"\xe9" + struct.pack("<H", (resident_end - 0x103) & 0xFFFF))
    out_img += bytes(CODE - 0x100 - len(out_img))
    out_img += res2
    for a, blob in blobs:
        if a == lay["STRBODY"]:
            for x in sptr:
                out_img += struct.pack("<H", x)
        assert 0x100 + len(out_img) == a, (hex(a), hex(0x100 + len(out_img)))
        out_img += blob
    assert 0x100 + len(out_img) == resident_end
    out_img += init + msg
    open(out, "wb").write(out_img)
    print(f"書き出し: {out}  {len(out_img)} バイト（常駐 {resident_end - 0x100}）")
    print(f"字 {len(enc.glyph_order)}（1バイト {len(enc.single)}）、組 {len(enc.pair_list)}、"
          f"置き換え {sum(map(len, patches.values()))}（オーバーレイ {len(ovl)} 個）、長い訳 {len(longs)}")
    if warns:
        print("途中への参照があるのに | のない訳:", " ".join(warns))
    if warns_w:
        print("桁あふれのおそれ（英文より長い1行の訳）:", " ".join(warns_w))
    if warns_k:
        print("禁則:", " / ".join(warns_k))
    if missing:
        print("フォントにない字:", "".join(missing))


if __name__ == "__main__":
    main(*sys.argv[1:4])
