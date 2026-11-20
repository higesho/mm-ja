# 英文・訳文の書き方（書式の記号を印にする）
#   0x0A 改行     → \n
#   0x01          → {big}     大きい字
#   0x02          → {small}   小さい字
#   0x03 + 字     → {c} {l} {r}（寄せ）、そのほかは {3:字}
#   0x04 + 3 桁   → {4:nnn}   その x まで塗る
#   0x05 + 4 桁   → {5:hhhh}  絵
#   0x06          → {sp}      空白の字
#   0x07 + 3 桁   → {7:nnn}   塗る色
#   0x08          → {bs}      重ね
#   0x09 + 3 桁   → {x:nnn}   横の位置
#   0x0B + 3 桁   → {y:nnn}   縦の位置
#   0x0C + 2 字   → {k:nn}    字の色（{k:d} は元の色）
#   0x0D          → {home}
#   %s %d などの書式（printf）はそのまま
import re

NAMES = {1: "big", 2: "small", 6: "sp", 8: "bs", 13: "home"}
ARGS = {4: ("4", 3), 5: ("5", 4), 7: ("7", 3), 9: ("x", 3), 11: ("y", 3)}


PRINTF = re.compile(rb"%[-+ 0#]*[0-9]*[lh]?[a-zA-Z]")


def _arg(b, i, k, digits):
    """i から k 字の引数を取る。printf の書式なら書式ごと取る。取れなければ None"""
    m = PRINTF.match(b, i)
    if m:
        return m.group().decode("latin1"), m.end()
    a = b[i:i + k]
    if len(a) == k and all(chr(x) in digits for x in a):
        return a.decode("latin1"), i + k
    return None


def to_text(b):
    out = []
    i = 0
    while i < len(b):
        c = b[i]
        if c == 10:
            out.append("\\n"); i += 1
        elif c in NAMES:
            out.append("{%s}" % NAMES[c]); i += 1
        elif c == 3 and i + 1 < len(b) and 0x61 <= b[i + 1] <= 0x7A:
            x = chr(b[i + 1])
            out.append("{%s}" % x if x in "clr" else "{3:%s}" % x); i += 2
        elif c in ARGS and _arg(b, i + 1, ARGS[c][1], "0123456789ABCDEFabcdef " if c == 5 else "0123456789 "):
            a, j = _arg(b, i + 1, ARGS[c][1], "0123456789ABCDEFabcdef " if c == 5 else "0123456789 ")
            out.append("{%s:%s}" % (ARGS[c][0], a)); i = j
        elif c == 12 and b[i + 1:i + 2] == b"d":
            out.append("{k:d}"); i += 2
        elif c == 12 and _arg(b, i + 1, 2, "0123456789"):
            a, j = _arg(b, i + 1, 2, "0123456789")
            out.append("{k:%s}" % a); i = j
        elif c < 0x20 or c >= 0x7F:
            out.append("{%02X}" % c); i += 1
        elif c == ord("{") or c == ord("\\"):
            out.append("\\" + chr(c)); i += 1
        else:
            out.append(chr(c)); i += 1
    return "".join(out)


TOKEN = re.compile(r"\\n|\\\{|\\\\|\{[^{}]*\}")


def from_text(t):
    """印の文字列を、元の書式のバイト列（日本語の字は str のまま）に戻す。戻り値は str（latin1 の範囲は1バイト）"""
    out = []
    pos = 0
    for m in TOKEN.finditer(t):
        out.append(t[pos:m.start()])
        x = m.group()
        pos = m.end()
        if x == "\\n":
            out.append("\n")
        elif x in ("\\{", "\\\\"):
            out.append(x[1])
        else:
            body = x[1:-1]
            inv = {v: k for k, v in NAMES.items()}
            if body in inv:
                out.append(chr(inv[body]))
            elif body in ("c", "l", "r"):
                out.append("\x03" + body)
            elif body.startswith("3:"):
                out.append("\x03" + body[2:])
            elif ":" in body:
                n, a = body.split(":", 1)
                code = {"4": 4, "5": 5, "7": 7, "x": 9, "y": 11, "k": 12}[n]
                out.append(chr(code) + a)
            elif re.fullmatch(r"[0-9A-F]{2}", body):
                out.append(chr(int(body, 16)))
            else:
                raise ValueError("知らない印: " + x)
    out.append(t[pos:])
    return "".join(out)


def tokens(t):
    """書式の印の並び（改行を除く）"""
    return [m.group() for m in TOKEN.finditer(t) if m.group().startswith("{")]
