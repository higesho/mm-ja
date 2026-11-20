"""MM2 (GOG DOS) の LZW。9->12 ビット、LSB 先、0x100=clear 0x101=stop。"""
import struct

MASK = {9: 0x1FF, 10: 0x3FF, 11: 0x7FF, 12: 0xFFF}


def decompress(src, size):
    out = bytearray()
    pref = [0] * 4096
    suf = [0] * 4096
    bits = 0
    width = 9
    limit = 0x200
    nxt = 0x102
    prev = None

    def read():
        nonlocal bits
        base = bits >> 3
        if base >= len(src):
            return None
        w = src[base] | ((src[base + 1] if base + 1 < len(src) else 0) << 8) | ((src[base + 2] if base + 2 < len(src) else 0) << 16)
        w >>= bits & 7
        bits += width
        return w & MASK[width]

    def expand(c):
        s = []
        while c >= 0x102:
            s.append(suf[c])
            c = pref[c]
        s.append(c & 0xFF)
        s.reverse()
        return s

    while len(out) < size:
        c = read()
        if c is None or c == 0x101:
            break
        if c == 0x100:
            width, limit, nxt = 9, 0x200, 0x102
            c = read()
            if c is None:
                break
            out.append(c & 0xFF)
            prev = c
            continue
        if prev is None:
            out.append(c & 0xFF)
            prev = c
            continue
        if c < nxt:
            chars = expand(c)
        else:
            p = expand(prev)
            chars = p + [p[0]]
        out.extend(chars)
        if nxt < 4096:
            pref[nxt] = prev
            suf[nxt] = chars[0]
            nxt += 1
            if nxt >= limit and width < 12:
                width += 1
                limit <<= 1
        prev = c
    return bytes(out[:size])


def unpack(blob):
    size = struct.unpack_from('<I', blob, 0)[0]
    return decompress(blob[4:], size)


def compress(data):
    """LZW 圧縮（clear で始め stop で終える）。復号側が1つ遅れることに合わせる。"""
    outbits = []
    acc = 0
    nb = 0
    res = bytearray()

    def emit(code, w):
        nonlocal acc, nb
        acc |= code << nb
        nb += w
        while nb >= 8:
            res.append(acc & 0xFF)
            acc >>= 8
            nb -= 8

    width = 9
    limit = 0x200
    nxt = 0x102
    table = {}
    emit(0x100, 9)
    if not data:
        emit(0x101, 9)
        if nb:
            res.append(acc & 0xFF)
        return bytes(res)
    # 最初の1字は clear の後に生で
    w = data[0]
    first = True
    i = 1
    # 復号側の状態を写す: decoder adds an entry after each code (except the first after clear)
    dnxt = 0x102
    dwidth = 9
    dlimit = 0x200
    while i < len(data):
        c = data[i]
        key = (w, c)
        if key in table:
            w = table[key]
            i += 1
            continue
        emit(w, dwidth)
        if first:
            first = False
        else:
            if dnxt < 4096:
                dnxt += 1
                if dnxt >= dlimit and dwidth < 12:
                    dwidth += 1
                    dlimit <<= 1
        if nxt < 4096:
            table[key] = nxt
            nxt += 1
        else:
            # 表が満ちたら clear
            emit(0x100, dwidth)
            table = {}
            nxt = 0x102
            dnxt = 0x102
            dwidth = 9
            dlimit = 0x200
            first = True
            emit(c, 9)
            # after clear the decoder reads a raw byte -> that is c itself
            w = None
            i += 1
            if i < len(data):
                w = data[i - 1]
            # restart: treat c as current string
            w = c
            # the raw byte already emitted; mark so next emit is the 'first' after clear? decoder: raw byte becomes prev, no add.
            # The next code emitted will add an entry -> first=False now
            first = False
            skip_emit_w = True
            continue
        w = c
        i += 1
    emit(w, dwidth)
    if not first:
        if dnxt < 4096:
            dnxt += 1
            if dnxt >= dlimit and dwidth < 12:
                dwidth += 1
                dlimit <<= 1
    emit(0x101, dwidth)
    if nb:
        res.append(acc & 0xFF)
    return bytes(res)


def pack(data):
    return struct.pack('<I', len(data)) + compress(data)
