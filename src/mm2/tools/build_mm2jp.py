# Might and Magic 2 用の常駐プログラム MM2JP.COM と、訳のデータ MM2JP.DAT を作る
#
# 仕組み
#   - MM2JP.COM は起動すると自分を上位メモリ（UMB）へ写して常駐する（通常のメモリはゲームが使い切るため）。UMB がなければ下に残る
#   - INT 21h を横取りする。MM2 が AH=3Dh でファイルを開くとき、PSP+0x10 の CS の 1字描く関数 putch（0x0D22）を照合し、
#     DS（CS:0x00CB の即値）の "Version" を確かめたら、putch の入口を常駐部への jmp far に書き換え、DS の文字列を訳に置き換え、
#     本体のコードを書き換える（CODE_FIX）
#   - putch の横取り: 日本語の符号なら、字形をフォント（窓の構造体 +0x0E の区画）の SLOT 番に一時的に写し、元の putch で描く
#   - 訳の大きな部分は MM2JP.DAT（MM2JP.COM と同じフォルダ）に置き、ゲームが読んだ直後に書き換える
#       出来事の文: 出来事のデータを DS:0x6052 に写して AH=49h で解放するとき（戻り先 CS:0x6095）、文の表を置き換える
#       STR.DAT・怪物: LZW の復号が終わって AH=3Eh で閉じるとき（戻り先 CS:0x2346）、復号先（SS:[BP-4] の区画）を置き換える
#       品物: items.dat を DS:0x6960 に読んで閉じるとき（戻り先 CS:0x69D6）、名前を置き換える
#       2PLAY.OVL: 読み込んだ後の次の INT 21h で、出来事の文を写す所の「and 0x7F」を「and 0xFF」に書き換える
#
# 文字の符号（1バイト = 1マス。ゲームの桁の計算がそのまま使える）
#   0x00〜0x7F        ゲームの字（英数字・記号・枠）
#   0x80〜0xFE        よく使う字（1バイトで1字）か、2字の組のリード
#   リード＋トレイル  2字の組（2バイトで2マス）。リードで空白を描いて進み、トレイルで1マス戻って2字を描く
#                    トレイルは TRAILS の値（改行・空白・@・- などゲームが特別に扱う字を除く）
#
# 使い方: python build_mm2jp.py <ゲームのフォルダ> <訳のファイル ja.txt> <出力のフォルダ>
#   訳のファイル: 「鍵<TAB>訳」。鍵は D.<DS の位置>、V.<i|o><場所>.<番号>、S.<行>、I.<番号>、M.<番号>
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))
from asm16 import asm, far_jmp, far_call  # noqa: E402
from jpcommon import align, fit_spaces, is_jp, layout, load_bdf, norm_ascii, unesc  # noqa: E402
import lzw  # noqa: E402
import extract_data  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
TR = os.path.join(HERE, "..", "translation")

DS_FILE = 0x8630                 # MM2.EXE の中の DS:0 の位置
PUTCH = 0x0D22                   # 1字描く関数（CS）
PUTCH_SIG = bytes.fromhex("558bec817e040001")   # push bp / mov bp,sp / cmp word [bp+4],0x100
PUTCH_CONT = 0x0D2A              # 入口の3命令の次（jne）
RET_GADGET = 0x0D20              # CS の中の 0xC3（ret）
RETF_GADGET = 0x34B5             # CS の中の add sp,2 / retf（引数を捨ててから far で戻る）
DS_IMM = 0x00CB                  # mov ax, <DS> の即値の位置（CS）
WIN = 0x4946                     # 今の窓の構造体へのポインタ（DS）: +4 桁, +5 行, +0x0E フォントの区画
AUTOADV = 0x4964                 # putch が描いた後に桁を進めるか（DS）
SLOT = 0x7F                      # 字形を一時的に写す番号
EV_FREE_IP = 0x6095              # 出来事のデータを解放する int 21h の次
EV_BUF = 0x6052                  # 出来事のデータの置き場（DS、2300 バイト）
EV_BUFLEN = 2300
EV_NAME = 0x04D0                 # "eventsi.dat" へのポインタ（DS）。+6 が i か o
EV_LOC = 0x0392                  # 今の場所の番号（DS）
DEC_CLOSE_IP = 0x2346            # LZW の復号の終わりの int 21h（AH=3Eh）の次。SS:[BP-4] が復号先の区画
ITEMS_CLOSE_IP = 0x69D6          # ファイルを閉じる関数の int 21h の次（品物の表を読んだ後）
ITEMS = 0x6960                   # 品物の表（DS）: 20 バイト × 256（名前 12）
CODE_FIX = [(0x3BB2, 0x7F, 0xFF)]   # 怪物の名前を写すとき最上位ビットを落とす（and al,0x7f）のをやめる
# オーバーレイの書き換え: (ファイル, 位置, 元, 新)。読み込んだ後に、前後 12 バイトの並びを探して書く
OVL_FIX = [("2PLAY.OVL", 0x1223, 0x7F, 0xFF),      # 出来事の文を写すとき and byte [bp-2],0x7f → 0xff
           ("2COMBAT.OVL", 0x0A1A, 0x76, 0xEB),    # 以下、英語の複数形の s を足す所を飛ばす（ダメージの Pt）
           ("2COMBAT.OVL", 0x0DCF, 0x76, 0xEB),    # time
           ("2COMBAT.OVL", 0x0E23, 0x76, 0xEB),    # time
           ("2COMBAT.OVL", 0x0E5A, 0x76, 0xEB),    # Pt
           ("2COMBAT.OVL", 0x2053, 0x74, 0xEB),    # 怪物の名前
           ("2COMBAT.OVL", 0x26B1, 0x74, 0xEB)]    # +n more 〈怪物〉
# 英語のまま残す DS の文字列: {DS の位置: (オーバーレイ, 参照の即値の位置)}。訳は他の文字列の空きに置き、即値をそこへ向ける。
# Where Are We?（自動地図）が "P-Prot Q-Quick\0"（DS:0x13C0）を目印に MM2 を探すため
KEEP_EN = {0x13B8: ("2COMBAT.OVL", 0x2CA4)}     # D-Delay P-Prot Q-Quick（2COMBAT の mov ax,0x13b8）
CUT3 = range(0x003E, 0x0072)     # 職業名: 名簿で頭の3マスだけ出る → 3マス目で組を切る
PAD_RANGE = range(0x4E3F, 0x5100)  # 歩き回る画面の欄・コマンド一覧: 英語の長さまで空白で埋める（前の字が残るため）
STR_SECTIONS = [0x0, 0x63C, 0xF5C, 0x1286, 0x1844]   # STR.DAT の区切りの位置（DS:0x52F4 の表）
SCRATCH_LEN = 4800
OPS_AT = 2400                      # 作業の場所: 0〜 元の文（SRCBUF）、2400〜 命令（OPSBUF）
NSECT = 5

SINGLE_CODES = list(range(0x80, 0xFF))           # 1バイトの字とリードに使う符号（127 個）
NLEADS = int(os.environ.get("MM2JP_LEADS", "40"))
LEADS = SINGLE_CODES[-NLEADS:]
SINGLES = SINGLE_CODES[:-NLEADS]
BAD_TRAIL = {0x00, 0x0A, 0x0D, 0x20, 0x2D, 0x40, 0x1C, 0x1D, 0x7F, 0xFF}
TRAILS = [c for c in range(0x21, 0xFF) if c not in BAD_TRAIL]
NT = len(TRAILS)

# ---- 常駐部の変数（0x103 から）----
V = {}
_p = 0x103
for name, size in [("OLD21", 4), ("JPC", 4), ("RETP", 4), ("RETFOFF", 2), ("GAMECS", 2), ("GAMEDS", 2),
                   ("DONE", 1), ("LEAD", 1), ("SLOTSEG", 2), ("SAVE8", 8), ("RESSEG", 2),
                   ("OVLP", 2), ("OVLSEG", 2), ("OVLOFF", 2), ("OVLLEN", 2), ("FH", 2), ("QK", 2), ("KEYA", 2),
                   ("DSTSEG", 2), ("E_KIND", 2), ("E_OFF", 4), ("E_LEN", 2), ("E_A", 2), ("E_B", 2), ("E_C", 2),
                   ("PATH", 80)]:
    V[name] = _p
    _p += size
CODE = (_p + 15) & ~15

RES = r'''
int21:
    cmp byte ptr cs:[{OVLP}], 1
    jne i_go
    cmp word ptr cs:[{OVLLEN}], 0
    je i_go
    call ovl_fix
i_go:
    cmp ah, 0x3d
    je i_3d
    cmp ah, 0x3f
    je i_3f
    cmp ah, 0x3e
    je i_3e
    cmp ah, 0x49
    je i_49
    cmp ah, 0x4c
    jne i_chain
    mov byte ptr cs:[{DONE}], 0
i_chain:
    {jmp_old}
i_3d:
    cmp byte ptr cs:[{DONE}], 0
    jne i_3d2
    call detect
i_3d2:
    call ovl_name
    jmp i_chain
i_3f:
    cmp byte ptr cs:[{OVLP}], 1
    jne i_chain
    cmp cx, 0x200
    jb i_chain
    mov word ptr cs:[{OVLSEG}], ds
    mov word ptr cs:[{OVLOFF}], dx
    mov word ptr cs:[{OVLLEN}], cx
    jmp i_chain
i_3e:
    mov byte ptr cs:[{OVLP}], 0
    cmp byte ptr cs:[{DONE}], 1
    jne i_chain
    push bp
    mov bp, sp
    push ax
    mov ax, word ptr [bp+4]
    cmp ax, word ptr cs:[{GAMECS}]
    jne i_3e_no
    mov ax, word ptr [bp+2]
    cmp ax, {DEC_CLOSE_IP}
    je i_3e_dec
    cmp ax, {ITEMS_CLOSE_IP}
    jne i_3e_no
    cmp cx, 0x1400
    jne i_3e_no
    cmp dx, {ITEMS}
    jne i_3e_no
    pop ax
    pop bp
    call items_patch
    jmp i_chain
i_3e_dec:
    pop ax
    pop bp
    call dec_patch
    jmp i_chain
i_3e_no:
    pop ax
    pop bp
    jmp i_chain
i_49:
    cmp byte ptr cs:[{DONE}], 1
    jne i_chain
    push bp
    mov bp, sp
    push ax
    mov ax, word ptr [bp+4]
    cmp ax, word ptr cs:[{GAMECS}]
    jne i_49_no
    mov ax, word ptr [bp+2]
    cmp ax, {EV_FREE_IP}
    jne i_49_no
    pop ax
    pop bp
    call ev_patch
    jmp i_chain
i_49_no:
    pop ax
    pop bp
    jmp i_chain

; ---- ゲームを見つけて書き換える ----
detect:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ah, 0x62
    pushf
    {call_old}
    add bx, 0x10
    mov es, bx
    mov di, {PUTCH}
    push cs
    pop ds
    mov si, {SIG}
    mov cx, {SIGLEN}
    cld
    repe cmpsb
    jne d_out
    mov ax, word ptr es:[{DS_IMM}]
    push es
    mov es, ax
    cmp word ptr es:[2], 0x6556
    pop es
    jne d_out
    mov word ptr cs:[{GAMEDS}], ax
    mov word ptr cs:[{GAMECS}], es
    mov word ptr cs:[{JPC_SEG}], es
    mov word ptr cs:[{RETP_SEG}], es
    mov byte ptr es:[{PUTCH}], 0xea
    mov word ptr es:[{PUTCH1}], {PH}
    mov word ptr es:[{PUTCH3}], cs
    mov byte ptr cs:[{DONE}], 1
    mov byte ptr cs:[{LEAD}], 0
    ; 本体のコードの書き換え: 表 CFTAB = (位置, 元, 新)… 0 で終わり
    mov si, {CFTAB}
d_cf:
    mov di, word ptr cs:[si]
    or di, di
    je d_ds
    mov al, byte ptr cs:[si+2]
    cmp byte ptr es:[di], al
    jne d_cf2
    mov al, byte ptr cs:[si+3]
    mov byte ptr es:[di], al
d_cf2:
    add si, 4
    jmp d_cf
    ; DS の書き換え: 表 DSTAB = (位置, 元の長さ, 命令…)… 位置 0 で終わり。元の文字列を SRCBUF に写してから命令を行う
d_ds:
    mov si, {DSTAB}
d_lp:
    mov di, word ptr cs:[si]
    or di, di
    je d_out
    mov cx, word ptr cs:[si+2]
    add si, 4
    push si
    push di
    mov si, di
    mov di, {SRCBUF}
    push cs
    pop es
    mov ds, word ptr cs:[{GAMEDS}]
    rep movsb
    pop di
    pop si
    push cs
    pop ds
    mov es, word ptr cs:[{GAMEDS}]
    call apply_ops
    jmp d_lp
d_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- オーバーレイ（*.OVL）を読んだら、表 OVLTAB の並びを探して1バイト書き換える ----
ovl_name:
    push ax
    push cx
    push si
    mov byte ptr cs:[{OVLP}], 0
    mov word ptr cs:[{OVLLEN}], 0
    mov si, dx
    mov cx, 16
on_lp:
    mov al, byte ptr [si]
    or al, al
    je on_out
    cmp al, 0x2e
    jne on_nx
    mov al, byte ptr [si+1]
    or al, 0x20
    cmp al, 0x6f
    jne on_nx
    mov al, byte ptr [si+2]
    or al, 0x20
    cmp al, 0x76
    jne on_nx
    mov al, byte ptr [si+3]
    or al, 0x20
    cmp al, 0x6c
    jne on_nx
    mov byte ptr cs:[{OVLP}], 1
    jmp on_out
on_nx:
    inc si
    loop on_lp
on_out:
    pop si
    pop cx
    pop ax
    ret

; OVLTAB: 件数, (並び 12 バイト, 書く位置, 新しい値)…
ovl_fix:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    push cs
    pop ds
    mov es, word ptr cs:[{OVLSEG}]
    mov bx, {OVLTAB2}
    mov dx, word ptr cs:[{OVLTAB}]
    cld
of_ent:
    or dx, dx
    je of_out
    mov di, word ptr cs:[{OVLOFF}]
    mov cx, word ptr cs:[{OVLLEN}]
    sub cx, 12
    jbe of_next
of_lp:
    push cx
    push di
    mov si, bx
    mov cx, 12
    repe cmpsb
    pop di
    pop cx
    je of_hit
    inc di
    loop of_lp
    jmp of_next
of_hit:
    mov al, byte ptr cs:[bx+12]
    xor ah, ah
    push di
    add di, ax
    mov al, byte ptr cs:[bx+13]
    mov byte ptr es:[di], al
    pop di
of_next:
    add bx, 14
    dec dx
    jmp of_ent
of_out:
    mov word ptr cs:[{OVLLEN}], 0
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- MM2JP.DAT ----
; ds:si, cx → dx（ハッシュ: dx を3ビット回して字と xor）
hash:
    xor dx, dx
    cld
h_lp:
    jcxz h_end
    lodsb
    rol dx, 1
    rol dx, 1
    rol dx, 1
    xor dl, al
    dec cx
    jmp h_lp
h_end:
    ret

dat_close:
    push ax
    push bx
    mov bx, word ptr cs:[{FH}]
    mov ah, 0x3e
    pushf
    {call_old}
    pop bx
    pop ax
    ret

; al=種類, ah=番号（al=0xFF なら KEYA と a の欄が同じもの）→ CF=0 で E_* に入れる（ファイルは開いたまま）
dat_find:
    push ax
    push bx
    push cx
    push dx
    push si
    push ds
    mov word ptr cs:[{QK}], ax
    push cs
    pop ds
    mov dx, {PATH}
    mov ax, 0x3d00
    pushf
    {call_old}
    jc df_fail
    mov word ptr cs:[{FH}], ax
    mov bx, ax
    mov dx, {SCRATCH}
    mov cx, 2048
    mov ah, 0x3f
    pushf
    {call_old}
    jc df_nf
    mov cx, word ptr cs:[{SCRATCH8}]
    mov si, {SCRATCH10}
df_lp:
    jcxz df_nf
    mov ax, word ptr cs:[si]
    cmp byte ptr cs:[{QK}], 0xff
    je df_h
    cmp ax, word ptr cs:[{QK}]
    je df_hit
    jmp df_next
df_h:
    ; 先頭のハッシュで探すのは STR の区切り 0（種類 2・番号 0）と怪物（種類 4・番号 0）だけ
    cmp ax, 2
    je df_h2
    cmp ax, 4
    jne df_next
df_h2:
    mov ax, word ptr cs:[si+8]
    cmp ax, word ptr cs:[{KEYA}]
    je df_hit
df_next:
    add si, 14
    dec cx
    jmp df_lp
df_hit:
    mov al, byte ptr cs:[si]
    xor ah, ah
    mov word ptr cs:[{E_KIND}], ax
    mov ax, word ptr cs:[si+2]
    mov word ptr cs:[{E_OFF}], ax
    mov ax, word ptr cs:[si+4]
    mov word ptr cs:[{E_OFF2}], ax
    mov ax, word ptr cs:[si+6]
    mov word ptr cs:[{E_LEN}], ax
    mov ax, word ptr cs:[si+8]
    mov word ptr cs:[{E_A}], ax
    mov ax, word ptr cs:[si+10]
    mov word ptr cs:[{E_B}], ax
    mov ax, word ptr cs:[si+12]
    mov word ptr cs:[{E_C}], ax
    clc
    jmp df_ret
df_nf:
    call dat_close
df_fail:
    stc
df_ret:
    pop ds
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; 命令（ds:si、ds=cs）を es:di に行う。0=終わり、1 長さ バイト列=書く、2 元の位置 長さ=SRCBUF から写す
apply_ops:
    cld
ao_lp:
    lodsb
    cmp al, 0
    je ao_end
    cmp al, 1
    je ao_lit
    lodsw
    mov dx, ax
    lodsw
    mov cx, ax
    push si
    mov si, {SRCBUF}
    add si, dx
    rep movsb
    pop si
    jmp ao_lp
ao_lit:
    lodsw
    mov cx, ax
    rep movsb
    jmp ao_lp
ao_end:
    ret

; ds:dx に E_LEN バイト読んで閉じる
dat_read:
    push ax
    push bx
    push cx
    push dx
    mov bx, word ptr cs:[{FH}]
    mov dx, word ptr cs:[{E_OFF}]
    mov cx, word ptr cs:[{E_OFF2}]
    mov ax, 0x4200
    pushf
    {call_old}
    pop dx
    push dx
    mov cx, word ptr cs:[{E_LEN}]
    mov ah, 0x3f
    pushf
    {call_old}
    call dat_close
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- 出来事の文（AH=49h、戻り先 CS:0x6095）----
ev_patch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ds, word ptr cs:[{GAMEDS}]
    mov bx, word ptr [{EV_NAME}]
    mov ah, byte ptr [{EV_LOC}]
    cmp byte ptr [bx+6], 0x6f
    jne ep1
    or ah, 0x80
ep1:
    mov al, 1
    call dat_find
    jc ep_out
    mov si, word ptr cs:[{E_A}]
    add si, {EV_TAB}
    mov cx, word ptr cs:[{E_B}]
    call hash
    cmp dx, word ptr cs:[{E_C}]
    jne ep_close
    ; 元の表を SRCBUF に写し、命令を OPSBUF に読んで、表の場所に書く
    mov si, word ptr cs:[{E_A}]
    add si, {EV_TAB}
    push si
    mov di, {SRCBUF}
    push cs
    pop es
    mov cx, word ptr cs:[{E_B}]
    cld
    rep movsb
    push cs
    pop ds
    mov dx, {OPSBUF}
    call dat_read
    pop di
    mov es, word ptr cs:[{GAMEDS}]
    mov si, {OPSBUF}
    call apply_ops
    jmp ep_out
ep_close:
    call dat_close
ep_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- LZW の復号の終わり（AH=3Eh、戻り先 CS:0x2346）: STR.DAT か怪物 ----
dec_patch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ax, word ptr ss:[bp-4]
    mov word ptr cs:[{DSTSEG}], ax
    mov ds, ax
    xor si, si
    mov cx, 64
    call hash
    mov word ptr cs:[{KEYA}], dx
    mov al, 0xff
    call dat_find
    jc dp_out
    ; 復号先の区画が STR.DAT・怪物の大きさに足りるかを、DOS の管理表（MCB）で確かめる
    ; （地図など小さな区画をハッシュの一致で取り違えて、後ろの管理表を壊さないように）
    mov ax, word ptr cs:[{DSTSEG}]
    dec ax
    mov es, ax
    cmp byte ptr es:[0], 0x4d
    je dp_mcb
    cmp byte ptr es:[0], 0x5a
    jne dp_skip
dp_mcb:
    mov ax, word ptr es:[3]
    cmp byte ptr cs:[{E_KIND}], 2
    jne dp_m4
    cmp ax, {STR_PARAS}
    jb dp_skip
    jmp dp_str
dp_m4:
    cmp byte ptr cs:[{E_KIND}], 4
    jne dp_skip
    cmp ax, {MON_PARAS}
    jae dp_mon
dp_skip:
    call dat_close
    jmp dp_out
dp_str:
    ; 区切りごと: 元の区切りを SRCBUF に写し、命令を OPSBUF に読んで書き、区切りの終わりまで 0x01 で埋める
    call dat_close
    xor ax, ax
ds_lp:
    push ax
    mov ah, al
    mov al, 2
    call dat_find
    jc ds_next
    mov ds, word ptr cs:[{DSTSEG}]
    mov si, word ptr cs:[{E_B}]
    mov di, {SRCBUF}
    push cs
    pop es
    mov cx, word ptr cs:[{E_C}]
    cld
    rep movsb
    push cs
    pop ds
    mov dx, {OPSBUF}
    call dat_read
    mov es, word ptr cs:[{DSTSEG}]
    mov di, word ptr cs:[{E_B}]
    mov si, {OPSBUF}
    call apply_ops
    mov cx, word ptr cs:[{E_B}]
    add cx, word ptr cs:[{E_C}]
    sub cx, di
    jbe ds_next
    mov al, 1
    rep stosb
ds_next:
    pop ax
    inc al
    cmp al, {NSECT}
    jb ds_lp
    jmp dp_out
dp_mon:
    push cs
    pop ds
    mov dx, {SCRATCH}
    call dat_read
    mov es, word ptr cs:[{DSTSEG}]
    xor di, di
    mov si, {SCRATCH}
    mov dx, word ptr cs:[{E_C}]
    cld
dm_lp:
    mov cx, 14
    rep movsb
    add di, 12
    dec dx
    jnz dm_lp
dp_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- 品物の名前（items.dat を読んで閉じるとき）----
items_patch:
    push ax
    push bx
    push cx
    push dx
    push si
    push di
    push ds
    push es
    mov ds, word ptr cs:[{GAMEDS}]
    mov si, {ITEM1}
    mov cx, 12
    call hash
    push dx
    mov ax, 3
    call dat_find
    pop dx
    jc ip_out
    cmp dx, word ptr cs:[{E_A}]
    jne ip_close
    push cs
    pop ds
    mov dx, {SCRATCH}
    call dat_read
    mov es, word ptr cs:[{GAMEDS}]
    mov di, {ITEM1}
    mov si, {SCRATCH}
    mov dx, word ptr cs:[{E_C}]
    cld
ii_lp:
    mov cx, 12
    rep movsb
    add di, 8
    dec dx
    jnz ii_lp
    jmp ip_out
ip_close:
    call dat_close
ip_out:
    pop es
    pop ds
    pop di
    pop si
    pop dx
    pop cx
    pop bx
    pop ax
    ret

; ---- putch の横取り（jmp far で来る。スタック: 近い戻り先, 字） ----
ph:
    push bp
    mov bp, sp
    mov ax, word ptr [bp+4]
    cmp byte ptr cs:[{LEAD}], 0
    jne ph_trail
    cmp ax, 0x80
    jb ph_orig
    cmp ax, 0xfe
    ja ph_orig
    mov bx, ax
    sub bx, 0x80
    shl bx, 1
    mov ax, word ptr cs:[bx+{SMAP}]
    cmp ax, 0xffff
    je ph_orig
    test ax, 0x8000
    jnz ph_lead
    call draw_g
    jmp ph_ret
ph_lead:
    and ax, 0x7fff
    inc ax
    mov byte ptr cs:[{LEAD}], al
    mov word ptr [bp+4], 0x20
    jmp ph_orig
ph_trail:
    xor cx, cx
    mov cl, byte ptr cs:[{LEAD}]
    mov byte ptr cs:[{LEAD}], 0
    cmp ax, 0xff
    ja ph_orig
    mov bx, ax
    mov al, byte ptr cs:[bx+{TIDX}]
    cmp al, 0xff
    je ph_orig
    xor ah, ah
    push ax
    mov ax, cx
    dec ax
    mov cx, {NT}
    mul cx
    pop cx
    add ax, cx
    cmp ax, {NPAIRS}
    jae ph_ret
    shl ax, 1
    shl ax, 1
    mov bx, ax
    mov ax, word ptr cs:[bx+{PAIRS}]
    mov cx, word ptr cs:[bx+{PAIRS2}]
    push cx
    mov bx, word ptr [{WIN}]
    cmp word ptr [{AUTOADV}], 0
    je ph_nob
    cmp byte ptr [bx+4], 0
    je ph_nob
    dec byte ptr [bx+4]
ph_nob:
    call draw_u
    pop ax
    call draw_u
ph_ret:
    pop bp
    {jmp_retp}
ph_orig:
    cmp word ptr [bp+4], 0x100
    {jmp_jpc}

; ax: 0x8000|英数字 か 字形の番号
draw_u:
    test ax, 0x8000
    jz draw_g
    and ax, 0xff
    jmp call_orig

; ax: 字形の番号。SLOT 番に写して元の putch で描き、元に戻す
draw_g:
    push si
    push di
    push es
    mov bx, word ptr [{WIN}]
    mov es, word ptr [bx+0x0e]
    mov word ptr cs:[{SLOTSEG}], es
    mov bx, {SLOT8}
    mov cx, word ptr es:[bx]
    mov word ptr cs:[{SAVE8}], cx
    mov cx, word ptr es:[bx+2]
    mov word ptr cs:[{SAVE8_2}], cx
    mov cx, word ptr es:[bx+4]
    mov word ptr cs:[{SAVE8_4}], cx
    mov cx, word ptr es:[bx+6]
    mov word ptr cs:[{SAVE8_6}], cx
    mov si, ax
    shl si, 1
    shl si, 1
    shl si, 1
    mov cx, word ptr cs:[si+{GLY}]
    mov word ptr es:[bx], cx
    mov cx, word ptr cs:[si+{GLY2}]
    mov word ptr es:[bx+2], cx
    mov cx, word ptr cs:[si+{GLY4}]
    mov word ptr es:[bx+4], cx
    mov cx, word ptr cs:[si+{GLY6}]
    mov word ptr es:[bx+6], cx
    pop es
    pop di
    pop si
    mov ax, {SLOT}
    call call_orig
    push es
    mov es, word ptr cs:[{SLOTSEG}]
    mov bx, {SLOT8}
    mov cx, word ptr cs:[{SAVE8}]
    mov word ptr es:[bx], cx
    mov cx, word ptr cs:[{SAVE8_2}]
    mov word ptr es:[bx+2], cx
    mov cx, word ptr cs:[{SAVE8_4}]
    mov word ptr es:[bx+4], cx
    mov cx, word ptr cs:[{SAVE8_6}]
    mov word ptr es:[bx+6], cx
    pop es
    ret

; ax: 字。元の putch を呼ぶ（near ret を CS の add sp,2 / retf に戻して、引数を捨てて far で帰ってくる）
call_orig:
    push cs
    call co_1
    ret
co_1:
    push ax
    push word ptr cs:[{RETFOFF}]
    push bp
    mov bp, sp
    cmp word ptr [bp+4], 0x100
    {jmp_jpc}
'''

# 常駐しない部分: MM2JP.DAT の場所を控え、UMB へ写して INT 21h をつなぐ
INSTALL = r'''
    ; 環境の後ろのプログラムの名前から MM2JP.DAT の場所を作る
    mov es, word ptr [0x2c]
    xor di, di
    mov cx, 0x7fff
    xor al, al
    cld
p_env:
    repne scasb
    cmp byte ptr es:[di], 0
    jne p_env
    add di, 3
    mov si, di
    mov di, {PATH}
    mov cx, 75
p_cp:
    mov al, byte ptr es:[si]
    mov byte ptr [di], al
    or al, al
    je p_end
    inc si
    inc di
    loop p_cp
p_end:
    cmp di, {PATH4}
    jb p_def
    mov byte ptr [di-3], 0x44
    mov byte ptr [di-2], 0x41
    mov byte ptr [di-1], 0x54
    jmp p_ok
p_def:
    mov word ptr [{PATH}], 0x4d4d
    mov word ptr [{PATH2}], 0x4a32
    mov word ptr [{PATH4}], 0x2e50
    mov word ptr [{PATH6}], 0x4144
    mov word ptr [{PATH8}], 0x0054
p_ok:
    push cs
    pop es
    mov ax, 0x3521
    int 0x21
    mov word ptr [{OLD21}], bx
    mov word ptr [{OLD21_2}], es
    ; 上位メモリを取る（取り方と UMB のつなぎを控えて、最後に戻す）
    mov ax, 0x5800
    int 0x21
    push ax
    mov ax, 0x5802
    int 0x21
    push ax
    mov ax, 0x5803
    mov bx, 1
    int 0x21
    mov ax, 0x5801
    mov bx, 0x40
    int 0x21
    mov ah, 0x48
    mov bx, {PARAS}
    int 0x21
    jc no_umb
    cmp ax, 0xa000
    jb no_umb_free
    mov word ptr [{RESSEG}], ax
    jmp got
no_umb_free:
    mov es, ax
    mov ah, 0x49
    int 0x21
no_umb:
    mov word ptr [{RESSEG}], 0
got:
    pop bx
    xor bh, bh
    mov ax, 0x5803
    int 0x21
    pop bx
    mov ax, 0x5801
    int 0x21
    mov ax, word ptr [{RESSEG}]
    or ax, ax
    je stay_low
    mov es, ax
    xor si, si
    xor di, di
    mov cx, {RESEND}
    cld
    rep movsb
    dec ax
    mov es, ax
    inc ax
    mov word ptr es:[1], ax
    mov word ptr es:[8], 0x4d4d
    mov word ptr es:[10], 0x4a32
    mov word ptr es:[12], 0x0050
    mov word ptr es:[14], 0
    push ds
    mov ds, ax
    mov word ptr ds:[{RESSEG}], ax
    mov dx, {INT21}
    mov ax, 0x2521
    int 0x21
    pop ds
    mov dx, {MSG_HI}
    mov ah, 9
    int 0x21
    mov ax, 0x4c00
    int 0x21
stay_low:
    mov dx, {INT21}
    mov ax, 0x2521
    int 0x21
    mov dx, {MSG_LO}
    mov ah, 9
    int 0x21
    mov dx, {PARAS}
    mov ax, 0x3100
    int 0x21
'''


# ---------------------------------------------------------------- 符号
class Encoder:
    """訳文を符号に直す。よく使う字は1バイト、残りは2字の組（2バイトで2マス）"""

    def __init__(self, texts):
        freq = {}
        for t in texts:
            for ch in t:
                if is_jp(ch):
                    freq[ch] = freq.get(ch, 0) + 1
        top = sorted(freq, key=lambda c: (-freq[c], c))[:int(os.environ.get("MM2JP_SINGLES", len(SINGLES)))]
        self.single = {ch: SINGLES[i] for i, ch in enumerate(top)}
        self.glyph_order = []
        self.glyph_ix = {}
        self.pairs = {}
        self.pair_list = []
        for ch in top:
            self.gix(ch)

    def gix(self, ch):
        if ch not in self.glyph_ix:
            self.glyph_ix[ch] = len(self.glyph_order)
            self.glyph_order.append(ch)
        return self.glyph_ix[ch]

    def segment(self, t, cuts=()):
        # 最短: 余分なマス（組に空白を足す）を最少に、次に組の数を最少に。cuts の位置（マス）を組がまたがない
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
                if nxt is not None and is_jp(nxt) and nxt not in self.single and ch not in "\n " and i + 1 not in cuts:
                    add((0, 1), ("p", ch, nxt), i + 2)
            else:
                if ch in self.single:
                    add((0, 0), ("s", ch), i + 1)
                if nxt is not None and nxt != "\n" and i + 1 not in cuts:
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

    def unit(self, ch):
        return 0x8000 | ord(ch) if not is_jp(ch) else self.gix(ch)

    def encode(self, t, cuts=()):
        out = bytearray()
        for u in self.segment(t, cuts):
            if u[0] == "a":
                out.append(ord(u[1]))
            elif u[0] == "s":
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
                if n // NT >= len(LEADS):
                    raise RuntimeError("組が多すぎます（MM2JP_LEADS を増やす）")
                out += bytes([LEADS[n // NT], TRAILS[n % NT]])
        return bytes(out)


COPY_MIN = 8                     # 元の英文と同じ半角の並びがこれ以上なら、書かずに元から写す（原作の文を配布物に入れない）


def make_ops(new, orig):
    """new を書く命令の列: 1 長さ バイト列（書く）、2 元の位置 長さ（orig から写す）、0（終わり）"""
    ops = bytearray()
    lit = bytearray()

    def flush():
        if lit:
            ops.extend(b"\x01" + struct.pack("<H", len(lit)) + lit)
            lit.clear()
    i = 0
    while i < len(new):
        best = (0, 0)
        if 0x20 <= new[i] < 0x7F:
            j = i
            while j < len(new) and 0x20 <= new[j] < 0x7F:
                j += 1
            for L in range(j - i, COPY_MIN - 1, -1):
                k = orig.find(new[i:i + L])
                if k >= 0:
                    best = (L, k)
                    break
        if best[0] >= COPY_MIN:
            flush()
            ops.extend(b"\x02" + struct.pack("<HH", best[1], best[0]))
            i += best[0]
        else:
            lit.append(new[i])
            i += 1
    flush()
    return bytes(ops) + b"\0"


def h16(bs):
    h = 0
    for b in bs:
        h = ((h << 3) | (h >> 13)) & 0xFFFF
        h ^= b
    return h


def read_translation(path):
    tr = {}
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "\t" not in line:
            continue
        key, ja = line.split("\t", 1)
        if ja != "KEEP":
            tr[key] = norm_ascii(unesc(ja))
    return tr


def read_tsv(name):
    return [line.rstrip("\n").split("\t") for line in open(os.path.join(TR, name), encoding="utf-8")]


# ---------------------------------------------------------------- 訳を組み立てる
def prepare(game, tr):
    """訳を画面の形にする。戻り値: 文の一覧（符号にする前）と、組み立ての材料"""
    notes = []
    exe = open(os.path.join(game, "MM2.EXE"), "rb").read()
    ds = exe[DS_FILE:]
    # 本体の文字列: (位置, [部分の文…], [部分の位置…], 英文)
    dsitems = []
    for r in read_tsv("en_ds.tsv"):
        key = r[0]
        if key not in tr:
            continue
        off = int(key[2:], 16)
        en = ds[off:ds.index(b"\0", off)].decode("latin1")
        inner = [int(x) for x in r[3].split(",") if x]
        ja = tr[key]
        parts = ja.split("|")
        if len(parts) != len(inner) + 1:
            notes.append(f"{key}: | の数が合わない（書かない）")
            continue
        if len(parts) == 1:
            t, ok = align(ja, len(en))
            parts = [t if ok else fit_spaces(ja, en)]
        dsitems.append((key, off, parts, [0] + inner, en))
    # 出来事の文
    evs = []
    widths = {r[0]: int(r[1]) for r in read_tsv("en_events.tsv")}
    for io, loc, blob, anchor in extract_data.events():
        tab = blob[anchor + 1:]
        parts = tab.split(b"\xff")
        ss = []
        for k, p in enumerate(parts[:-1] if parts and parts[-1] == b"" else parts):
            key = f"V.{io}{loc:02d}.{k:03d}"
            if key in tr:
                lines, ln = layout(tr[key], max(widths.get(key, 38), 1))
                ss.append("\n".join(lines))
            else:
                ss.append(p)
        evs.append((io, loc, blob, anchor, ss, parts[-1] == b""))
    # STR.DAT
    raw = lzw.unpack(open(os.path.join(game, "STR.DAT"), "rb").read())
    en_lines = bytes(10 if b == 1 else (b + 0x1C) & 255 for b in raw).decode("latin1").split("\n")
    st = []
    for i, l in enumerate(en_lines):
        k = f"S.{i:03d}"
        st.append(tr[k].replace("　", " ") if k in tr else l)
    # 品物・怪物
    items = []
    d = open(os.path.join(game, "ITEMS.DAT"), "rb").read()
    for i in range(1, 256):
        k = f"I.{i:03d}"
        items.append(tr.get(k, d[i * 20:i * 20 + 12].decode("latin1").rstrip()))
    mon = lzw.unpack(open(os.path.join(game, "MONSTERS.DAT"), "rb").read())
    mons = []
    for i in range(len(mon) // 26):
        k = f"M.{i:03d}"
        mons.append(tr.get(k, bytes(c & 0x7F for c in mon[i * 26:i * 26 + 14]).decode("latin1").rstrip()))
    return dict(exe=exe, ds=ds, dsitems=dsitems, evs=evs, raw=raw, st=st, items=items, mon=mon, mons=mons), notes


def build(game, trfile, outdir):
    tr = read_translation(trfile)
    P, notes = prepare(game, tr)
    texts = []
    for _, _, parts, _, _ in P["dsitems"]:
        texts += parts
    for ev in P["evs"]:
        texts += [s for s in ev[4] if isinstance(s, str)]
    texts += P["st"] + P["items"] + P["mons"]
    enc = Encoder(texts)

    # 本体の文字列
    dstab = bytearray()
    nds = 0
    moved = []        # 英語のまま残す文字列: (鍵, 位置, 訳の符号)
    hosts = []        # 訳の後ろに空きのある文字列: [空きの先頭, 空きの長さ, 鍵]
    for key, off, parts, starts, en in P["dsitems"]:
        bounds = starts + [len(en)]
        b = bytearray()
        ok = True
        cuts = (3,) if off in CUT3 else ()
        pad = len(parts) == 1 and chr(10) not in en and (off in PAD_RANGE or en.rstrip().endswith(("=", ":")))
        for i, p in enumerate(parts):
            e = enc.encode(p, cuts)
            w = bounds[i + 1] - bounds[i]
            if pad:
                e = e + b" " * max(0, w - len(e))
            if len(e) > w:
                notes.append(f"{key}: 長い（{len(e)} > {w}）: {p}")
                ok = False
                break
            if i + 1 < len(parts):
                e = e + b" " * (w - len(e))
            b += e
        if not ok:
            continue
        b += b"\0"
        orig = en.encode("latin1")
        if off in KEEP_EN:
            moved.append((key, off, bytes(b)))
            continue
        dstab += struct.pack("<HH", off, len(orig)) + make_ops(bytes(b), orig)
        nds += 1
        if len(parts) == 1 and not pad and off not in CUT3 and len(orig) + 1 - len(b) >= 8:
            hosts.append([off + len(b), len(orig) + 1 - len(b), key])
    # 英語のまま残す文字列の訳を、他の文字列の訳の後ろの空き（元の英文の残り）に置き、参照の即値を向け替える
    ovl_extra = []
    for key, off, b in moved:
        cand = [h for h in hosts if h[1] >= len(b)]
        assert cand, f"{key}: 訳を置く空きがない"
        h = min(cand, key=lambda h: h[1])
        at = h[0]
        dstab += struct.pack("<HH", at, len(b)) + make_ops(b, P["ds"][at:at + len(b)])
        h[0] += len(b)
        h[1] -= len(b)
        name, imm = KEEP_EN[off]
        notes.append(f"英語を残す {key}: 訳を {h[2]} の後ろ（DS:{at:04x}）に置き、{name} {imm:#x} の即値を向ける")
        ovl_extra.append((name, imm, off & 0xFF, at & 0xFF, 11))        # 下の桁: 並びは即値の手前まで
        ovl_extra.append((name, imm + 1, off >> 8, at >> 8, 0))        # 上の桁: 並びは即値から後ろ
        nds += 1
    dstab += b"\0\0"

    # MM2JP.DAT
    entries = []
    blobs = bytearray()

    def add(kind, ident, data, a, b, c):
        entries.append((kind, ident, len(blobs), len(data), a, b, c))
        blobs.extend(data)
    nev = 0
    for io, loc, blob, anchor, ss, trail in P["evs"]:
        if all(isinstance(s, bytes) for s in ss):
            continue
        new = bytearray()
        for s in ss:
            e = s if isinstance(s, bytes) else enc.encode(s).replace(b"\n", b"@")
            new += e + b"\xff"
        if not trail:
            new = new[:-1]
        orig = blob[anchor + 1:]
        if anchor + 1 + len(new) > EV_BUFLEN:
            notes.append(f"V.{io}{loc:02d}: 出来事の文が置き場に入らない（{anchor + 1 + len(new)} > {EV_BUFLEN}）")
            continue
        ops = make_ops(bytes(new), orig)
        assert len(orig) <= OPS_AT and len(ops) <= SCRATCH_LEN - OPS_AT
        add(1, loc | (0x80 if io == "o" else 0), ops, anchor, len(orig), h16(orig))
        nev += 1
    # STR.DAT: 区切りの位置を変えずに置く
    raw = P["raw"]
    bounds = STR_SECTIONS + [len(raw)]
    linestart = [0]
    for i, b in enumerate(raw):
        if b == 1:
            linestart.append(i + 1)
    for si in range(len(STR_SECTIONS)):
        a, e = bounds[si], bounds[si + 1]
        l0 = linestart.index(a)
        l1 = linestart.index(e) if e in linestart else len(linestart)
        seg = bytearray()
        for li in range(l0, l1):
            t = P["st"][li]
            b = enc.encode(t)
            seg += bytes((c - 0x1C) & 0xFF for c in b)
            if li + 1 < len(linestart):
                seg.append(1)
        if len(seg) > e - a:
            notes.append(f"STR の区切り {si}: 入らない（{len(seg)} > {e - a}）")
            seg = bytearray(raw[a:e])
        assert all(((c + 0x1C) & 0xFF) != 0x1D or c == 1 for c in seg)
        orig = raw[a:e]
        ops = make_ops(bytes(seg), orig)
        assert len(orig) <= OPS_AT and len(ops) <= SCRATCH_LEN - OPS_AT, (si, len(orig), len(ops))
        add(2, si, ops, h16(raw[:64]) if si == 0 else 0, a, e - a)
    # 品物
    d = open(os.path.join(game, "ITEMS.DAT"), "rb").read()
    data = bytearray()
    for i, t in enumerate(P["items"]):
        b = enc.encode(t)
        if len(b) > 12:
            notes.append(f"I.{i + 1:03d}: 長い: {t}")
            b = d[(i + 1) * 20:(i + 1) * 20 + 12]
        data += b + b" " * (12 - len(b))
    add(3, 0, bytes(data), h16(d[20:32]), 0, len(P["items"]))
    # 怪物
    data = bytearray()
    mon = P["mon"]
    for i, t in enumerate(P["mons"]):
        b = enc.encode(t)
        if len(b) > 14:
            notes.append(f"M.{i:03d}: 長い: {t}")
            b = bytes(c & 0x7F for c in mon[i * 26:i * 26 + 14])
        data += b + b" " * (14 - len(b))
    assert len(data) <= SCRATCH_LEN
    add(4, 0, bytes(data), h16(mon[:64]), 0, len(P["mons"]))
    hdr = b"MM2JPDAT" + struct.pack("<H", len(entries))
    dirsz = len(hdr) + 14 * len(entries)
    assert dirsz <= 2048
    dat = bytearray(hdr)
    for kind, ident, off, ln, a, b, c in entries:
        dat += struct.pack("<BBIHHHH", kind, ident, dirsz + off, ln, a, b, c)
    dat += blobs

    # 字形・組の表
    bdf = load_bdf()
    gly = bytearray()
    for ch in enc.glyph_order:
        g = bdf.get(ord(ch))
        if g is None:
            notes.append(f"字形がない「{ch}」")
            g = bytes(8)
        gly += g
    smap = [0xFFFF] * 127
    for ch, c in enc.single.items():
        smap[c - 0x80] = enc.glyph_ix[ch]
    for i, c in enumerate(LEADS):
        smap[c - 0x80] = 0x8000 | i
    tidx = bytes([TRAILS.index(c) if c in TRAILS else 0xFF for c in range(256)])
    pairs = bytearray()
    for a, b in enc.pair_list:
        pairs += struct.pack("<HH", enc.unit(a), enc.unit(b))
    cftab = bytearray()
    for off, old, new in CODE_FIX:
        cftab += struct.pack("<HBB", off, old, new)
    cftab += b"\0\0"

    img = P["exe"][0x800:]
    assert img[PUTCH:PUTCH + len(PUTCH_SIG)] == PUTCH_SIG
    assert img[RET_GADGET] == 0xC3 and img[RETF_GADGET:RETF_GADGET + 4] == bytes.fromhex("83c402cb")
    for off, old, new in CODE_FIX:
        assert img[off] == old, hex(off)
    fixes = [(name, off, old, new, 8) for name, off, old, new in OVL_FIX] + ovl_extra
    ovltab = bytearray(struct.pack("<H", len(fixes)))
    ovls = {n: open(os.path.join(game, n), "rb").read() for n in sorted(os.listdir(game)) if n.upper().endswith(".OVL")}
    for name, off, old, new, pos in fixes:
        data = ovls[name]
        assert data[off] == old, (name, hex(off))
        sig = data[off - pos:off - pos + 12]         # 並び 12 バイトの中の pos バイト目を書く
        assert sum(d.count(sig) for d in ovls.values()) == 1, (name, hex(off))
        ovltab += sig + bytes([pos, new])

    kw = dict(PUTCH=PUTCH, PUTCH1=PUTCH + 1, PUTCH3=PUTCH + 3, DS_IMM=DS_IMM, SIGLEN=len(PUTCH_SIG),
              WIN=WIN, AUTOADV=AUTOADV, SLOT=SLOT, SLOT8=SLOT * 8, NT=NT, NPAIRS=len(enc.pair_list),
              JPC_SEG=V["JPC"] + 2, RETP_SEG=V["RETP"] + 2, SAVE8_2=V["SAVE8"] + 2, SAVE8_4=V["SAVE8"] + 4,
              SAVE8_6=V["SAVE8"] + 6, OLD21_2=V["OLD21"] + 2, E_OFF2=V["E_OFF"] + 2,
              DEC_CLOSE_IP=DEC_CLOSE_IP, ITEMS_CLOSE_IP=ITEMS_CLOSE_IP, ITEMS=ITEMS, ITEM1=ITEMS + 20,
              EV_FREE_IP=EV_FREE_IP, EV_NAME=EV_NAME, EV_LOC=EV_LOC, EV_TAB=EV_BUF + 1,
              PATH2=V["PATH"] + 2, PATH4=V["PATH"] + 4, PATH6=V["PATH"] + 6, PATH8=V["PATH"] + 8,
              STR_PARAS=(len(P["raw"]) + 15) // 16, MON_PARAS=(len(P["mon"]) + 15) // 16)
    lay = dict(SIG=0, SMAP=0, TIDX=0, PAIRS=0, GLY=0, DSTAB=0, CFTAB=0, OVLTAB=0, SCRATCH=0, PH=0)

    def kwl():
        return dict(kw, **lay, SRCBUF=lay["SCRATCH"], OPSBUF=lay["SCRATCH"] + OPS_AT, OVLTAB2=lay["OVLTAB"] + 2, NSECT=NSECT, PAIRS2=lay["PAIRS"] + 2, GLY2=lay["GLY"] + 2, GLY4=lay["GLY"] + 4,
                    GLY6=lay["GLY"] + 6, SCRATCH8=lay["SCRATCH"] + 8, SCRATCH10=lay["SCRATCH"] + 10)
    for _ in range(3):
        code = asm_res(RES, CODE, kwl())
        p = (CODE + len(code) + 1) & ~1
        for name, size in [("SIG", len(PUTCH_SIG)), ("SMAP", 254), ("TIDX", 256), ("PAIRS", len(pairs)),
                           ("GLY", len(gly)), ("DSTAB", len(dstab)), ("CFTAB", len(cftab)),
                           ("OVLTAB", len(ovltab)), ("SCRATCH", SCRATCH_LEN)]:
            lay[name] = p
            p = (p + size + 1) & ~1
        resend = p
        ph = asm_res(RES.split("\nph:")[0] + "\nph:", CODE, kwl())
        lay["PH"] = CODE + len(ph)
    code = asm_res(RES, CODE, kwl())
    assert code[lay["PH"] - CODE:lay["PH"] - CODE + 3] == bytes.fromhex("5589e5"), code[lay["PH"] - CODE:][:4].hex()
    msg_hi = b"MM2JP: Japanese text resident (UMB).\r\n$"
    msg_lo = b"MM2JP: Japanese text resident (low memory).\r\n$"
    inst_at = (resend + 15) & ~15
    paras = (resend + 15) // 16 + 1
    k = kwl()
    k.update(PARAS=paras, RESEND=resend, INT21=CODE, MSG_HI=0, MSG_LO=0)
    for _ in range(2):
        inst = asm_res(INSTALL, inst_at, k)
        k["MSG_HI"] = inst_at + len(inst)
        k["MSG_LO"] = k["MSG_HI"] + len(msg_hi)
    inst = asm_res(INSTALL, inst_at, k)
    imgc = bytearray(inst_at + len(inst) + len(msg_hi) + len(msg_lo) - 0x100)

    def put(a, b):
        imgc[a - 0x100:a - 0x100 + len(b)] = b
    put(V["JPC"], struct.pack("<HH", PUTCH_CONT, 0))
    put(V["RETP"], struct.pack("<HH", RET_GADGET, 0))
    put(V["RETFOFF"], struct.pack("<H", RETF_GADGET))
    put(CODE, code)
    put(lay["SIG"], PUTCH_SIG)
    put(lay["SMAP"], struct.pack("<127H", *smap))
    put(lay["TIDX"], tidx)
    put(lay["PAIRS"], pairs)
    put(lay["GLY"], gly)
    put(lay["DSTAB"], dstab)
    put(lay["CFTAB"], cftab)
    put(lay["OVLTAB"], ovltab)
    put(inst_at, inst)
    put(k["MSG_HI"], msg_hi)
    put(k["MSG_LO"], msg_lo)
    put(0x100, asm("jmp {T}", 0x100, T=inst_at)[:3])
    os.makedirs(outdir, exist_ok=True)
    open(os.path.join(outdir, "MM2JP.COM"), "wb").write(imgc)
    open(os.path.join(outdir, "MM2JP.DAT"), "wb").write(dat)
    for n in notes:
        print("注意", n)
    print(f"MM2JP.COM {len(imgc)} バイト（常駐 {resend} バイト = {paras} 区画）、MM2JP.DAT {len(dat)} バイト")
    print(f"  字 {len(enc.glyph_order)}（1バイト {len(enc.single)}）、組 {len(enc.pair_list)}（入る数 {len(LEADS) * NT}）、"
          f"DS の書き換え {nds} 件、出来事 {nev} か所")
    return notes


def asm_res(src, addr, kw):
    k = dict(kw)
    k.update(V)
    k.update(jmp_old=far_jmp(V["OLD21"]), call_old=far_call(V["OLD21"]),
             jmp_jpc=far_jmp(V["JPC"]), jmp_retp=far_jmp(V["RETP"]))
    return asm(src, addr, **k)


if __name__ == "__main__":
    build(*sys.argv[1:4])
