# 訳文の組み立て（折り返し・禁則・寄せ）と字の検査で共通に使うもの
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "..", "font", "misaki_gothic_2nd.bdf")
NO_HEAD = set("、。，．・：；？！ー～…‥」』）］｝〉》】ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ")
NO_TAIL = set("「『（［｛〈《【")
BAD_HALF = set("[]\\^`{}~|")          # ゲームでは絵になる半角の字（| は区切りの印）


def is_jp(ch):
    return not (0x20 <= ord(ch) < 0x7F) and ch != "\n"


def norm_ascii(t):
    """全角の英数字・空白を半角に"""
    out = []
    for ch in t:
        o = ord(ch)
        if 0xFF01 <= o <= 0xFF5E and ch not in "（）［］｛｝｜～＼＾｀":
            out.append(chr(o - 0xFEE0))
        elif ch == "　":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def unesc(t):
    """訳のファイルの \\n を改行に"""
    out = []
    i = 0
    while i < len(t):
        if t[i] == "\\" and i + 1 < len(t) and t[i + 1] == "n":
            out.append("\n")
            i += 2
        elif t[i] == "\\" and i + 1 < len(t) and t[i + 1] == "\\":
            out.append("\\")
            i += 2
        else:
            out.append(t[i])
            i += 1
    return "".join(out)


def layout(t, width):
    """訳文を width マスで折り返す（1字＝1マス）。行頭禁則は追い出し（2字まで）、行末禁則は次の行へ送る。
    戻り値: (行の一覧, 注意の一覧)"""
    notes = []
    out = []
    for li, line in enumerate(t.split("\n")):
        if li and line[:1] in NO_HEAD:
            notes.append(f"改行の直後が行頭禁則の字「{line[0]}」")
        cur = ""
        for ch in line:
            if len(cur) >= width:
                carry = ""
                k = 0
                # 英字・数字・記号のひと続き（「(y/n)?」「10,000」など）は行をまたがせず、まとめて次の行へ送る
                if ch != " " and ord(ch) < 0x80 and cur[-1] != " " and ord(cur[-1]) < 0x80:
                    j = len(cur)
                    while j > 0 and cur[j - 1] != " " and ord(cur[j - 1]) < 0x80:
                        j -= 1
                    if j > 0 and len(cur) - j <= 12:
                        carry = cur[j:]
                        cur = cur[:j]
                while cur and k < 2 and (ch in NO_HEAD if not carry else carry[0] in NO_HEAD):
                    carry = cur[-1] + carry
                    cur = cur[:-1]
                    k += 1
                while cur and cur[-1] in NO_TAIL:
                    carry = cur[-1] + carry
                    cur = cur[:-1]
                out.append(cur.rstrip(" "))
                cur = carry.lstrip(" ") if carry.strip() else ""
                if ch == " " and not cur:
                    continue
            cur += ch
        out.append(cur)
    return out, notes


def load_bdf(path=BDF):
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


def fit_spaces(ja, en):
    """英文の前後の半角空白を訳に引き継ぐ（訳の前後に空白がないとき）"""
    lead = len(en) - len(en.lstrip(" "))
    trail = len(en) - len(en.rstrip(" "))
    if not ja.startswith(" "):
        ja = " " * lead + ja
    if not ja.endswith(" ") and not ja.endswith("\n"):
        ja = ja + " " * trail
    return ja


def align(ja, width):
    """{c}{l}{r} の寄せ。戻り値: (文, 寄せたか)"""
    for tag, f in (("{c}", str.center), ("{l}", str.ljust), ("{r}", str.rjust)):
        if ja.startswith(tag):
            body = ja[len(tag):]
            if len(body) > width:
                return body, False
            if tag == "{c}":
                pad = width - len(body)
                return " " * (pad // 2) + body + " " * (pad - pad // 2), True
            return f(body, width), True
    return ja, False
