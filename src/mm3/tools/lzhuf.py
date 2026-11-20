"""MM3.CC の圧縮（LZHUF、Okumura 1988。N=4096 F=60 THRESHOLD=2）
項目の形: 2 バイト = 辞書の初期値（ふつう "  "）、2 バイト = 解凍後の大きさ（上位が先）、続いて圧縮の本体。"""

N = 4096
F = 60
THRESHOLD = 2
N_CHAR = 256 - THRESHOLD + F
T = N_CHAR * 2 - 1
R = T - 1
MAX_FREQ = 0x8000

p_len = [0x03, 0x04, 0x04, 0x04, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05, 0x05,
         0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06, 0x06,
         0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
         0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07,
         0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08, 0x08,
         0x08, 0x08, 0x08, 0x08]
p_code = [0x00, 0x20, 0x30, 0x40, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78, 0x80, 0x88,
          0x90, 0x94, 0x98, 0x9C, 0xA0, 0xA4, 0xA8, 0xAC, 0xB0, 0xB4, 0xB8, 0xBC,
          0xC0, 0xC2, 0xC4, 0xC6, 0xC8, 0xCA, 0xCC, 0xCE, 0xD0, 0xD2, 0xD4, 0xD6,
          0xD8, 0xDA, 0xDC, 0xDE, 0xE0, 0xE2, 0xE4, 0xE6, 0xE8, 0xEA, 0xEC, 0xEE,
          0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFB,
          0xFC, 0xFD, 0xFE, 0xFF]
d_code = [0] * 256
d_len = [0] * 256
_j = 0
for _i, (_c, _l) in enumerate(zip(p_code, p_len)):
    _n = 1 << (8 - _l + 2) if False else None
# 表を作る（d_code / d_len は上位 8 ビットから位置の上位と長さを引く）
_k = 0
for _i in range(64):
    _cnt = {3: 32, 4: 16, 5: 8, 6: 4, 7: 2, 8: 1}[p_len[_i]]
    for _ in range(_cnt):
        d_code[_k] = _i; d_len[_k] = p_len[_i]; _k += 1


class Huff:
    def __init__(self):
        self.freq = [0] * (T + 1)
        self.prnt = [0] * (T + N_CHAR)
        self.son = [0] * T
        for i in range(N_CHAR):
            self.freq[i] = 1
            self.son[i] = i + T
            self.prnt[i + T] = i
        i, j = 0, N_CHAR
        while j <= R:
            self.freq[j] = self.freq[i] + self.freq[i + 1]
            self.son[j] = i
            self.prnt[i] = self.prnt[i + 1] = j
            i += 2; j += 1
        self.freq[T] = 0xFFFF
        self.prnt[R] = 0

    def reconst(self):
        freq, son, prnt = self.freq, self.son, self.prnt
        j = 0
        for i in range(T):
            if son[i] >= T:
                freq[j] = (freq[i] + 1) // 2
                son[j] = son[i]
                j += 1
        i, j = 0, N_CHAR
        while j < T:
            k = i + 1
            f = freq[j] = freq[i] + freq[k]
            k = j - 1
            while f < freq[k]:
                k -= 1
            k += 1
            freq[k + 1:j + 1] = freq[k:j]
            freq[k] = f
            son[k + 1:j + 1] = son[k:j]
            son[k] = i
            i += 2; j += 1
        for i in range(T):
            k = son[i]
            if k >= T:
                prnt[k] = i
            else:
                prnt[k] = prnt[k + 1] = i

    def update(self, c):
        freq, son, prnt = self.freq, self.son, self.prnt
        if freq[R] == MAX_FREQ:
            self.reconst()
        c = prnt[c + T]
        while True:
            freq[c] += 1
            k = freq[c]
            l = c + 1
            if k > freq[l]:
                while k > freq[l + 1]:
                    l += 1
                freq[c] = freq[l]
                freq[l] = k
                i = son[c]
                prnt[i] = l
                if i < T: prnt[i + 1] = l
                j = son[l]
                son[l] = i
                prnt[j] = c
                if j < T: prnt[j + 1] = c
                son[c] = j
                c = l
            c = prnt[c]
            if c == 0:
                break


class BitIn:
    def __init__(self, data):
        self.d = data; self.p = 0; self.buf = 0; self.len = 0

    def bit(self):
        if self.len == 0:
            b = self.d[self.p] if self.p < len(self.d) else 0
            self.p += 1
            self.buf = b; self.len = 8
        self.len -= 1
        return (self.buf >> self.len) & 1

    def byte(self):
        v = 0
        for _ in range(8):
            v = (v << 1) | self.bit()
        return v


def decode(entry):
    fill = entry[0]
    size = (entry[2] << 8) | entry[3]
    bi = BitIn(entry[4:])
    h = Huff()
    text = bytearray([fill]) * (N + F)
    # 初期値は 2 バイトの語で埋める
    for i in range(0, N - F, 2):
        text[i] = entry[0]; text[i + 1] = entry[1]
    r = N - F
    out = bytearray()
    while len(out) < size:
        c = h.son[R]
        while c < T:
            c = h.son[c + bi.bit()]
        c -= T
        h.update(c)
        if c < 256:
            out.append(c)
            text[r] = c; r = (r + 1) & (N - 1)
        else:
            i = bi.byte()
            cc = d_code[i] << 6
            j = d_len[i] - 2
            while j:
                i = (i << 1) + bi.bit(); j -= 1
            pos = cc | (i & 0x3F)
            i = (r - pos - 1) & (N - 1)
            j = c - 255 + THRESHOLD
            for k in range(j):
                c2 = text[(i + k) & (N - 1)]
                out.append(c2)
                text[r] = c2; r = (r + 1) & (N - 1)
    return bytes(out[:size])


if __name__ == '__main__':
    import sys
    d = open(sys.argv[1], 'rb').read()
    out = decode(d)
    open(sys.argv[2], 'wb').write(out)
    print(len(out))


class BitOut:
    def __init__(self):
        self.out = bytearray(); self.buf = 0; self.len = 0

    def put(self, nbits, code):
        """code の上位 nbits ビット（16 ビットの語の上から）を書く"""
        for k in range(nbits):
            bit = (code >> (15 - k)) & 1
            self.buf = (self.buf << 1) | bit; self.len += 1
            if self.len == 8:
                self.out.append(self.buf); self.buf = 0; self.len = 0

    def flush(self):
        if self.len:
            self.out.append(self.buf << (8 - self.len)); self.buf = 0; self.len = 0


def _encode_char(h, bo, c):
    bits = []
    k = h.prnt[c + T]
    while True:
        bits.append(k & 1)
        k = h.prnt[k]
        if k == R:
            break
    for b in reversed(bits):
        bo.put(1, b << 15)
    h.update(c)


def _encode_pos(bo, c):
    i = c >> 6
    bo.put(p_len[i], p_code[i] << 8)
    bo.put(6, (c & 0x3F) << 10)


def encode(data, fill=b"  "):
    """data を圧縮して、ゲームの形（辞書の初期値 2 + 大きさ 2 + 本体）で返す"""
    assert len(data) < 0x10000
    h = Huff()
    bo = BitOut()
    text = bytearray(N + F)
    for i in range(0, N - F, 2):
        text[i] = fill[0]; text[i + 1] = fill[1]
    r = N - F
    # 窓の中の位置を素朴に探す（文のファイルは小さいので十分速い）
    hist = {}   # 3 バイトの並び → 出力の位置の一覧
    out_pos = 0
    n = len(data)
    # 位置 p の内容は text[(p + (N-F)) & (N-1)] で、初期値の部分も参照できるが、ここでは出力済みの範囲だけを使う
    i = 0
    while i < n:
        best_len, best_pos = 0, 0
        if i + 2 < n:
            key = bytes(data[i:i + 3])
            for p in reversed(hist.get(key, [])):
                if i - p > N - F - 1:
                    break
                l = 3
                while l < F and i + l < n and data[p + l] == data[i + l]:
                    l += 1
                if l > best_len:
                    best_len, best_pos = l, p
                    if l == F:
                        break
        if best_len > THRESHOLD:
            _encode_char(h, bo, 255 - THRESHOLD + best_len)
            # 復号側: i = (r - pos - 1) & (N-1) が写し始めの位置。r は出力の位置 + (N-F)
            ri = (i + N - F) & (N - 1)
            src = (best_pos + N - F) & (N - 1)
            _encode_pos(bo, (ri - src - 1) & (N - 1))
            step = best_len
        else:
            _encode_char(h, bo, data[i])
            step = 1
        for k in range(i, min(i + step, n - 2)):
            hist.setdefault(bytes(data[k:k + 3]), []).append(k)
        i += step
    bo.flush()
    return bytes(fill[:2]) + bytes([n >> 8, n & 0xFF]) + bytes(bo.out)


def inplace_ok(entry):
    """ゲームはその場で解凍する: 置き場 = 大きさ + 0x10、圧縮データ（4 バイトの頭を除く）を後ろに置く。
    出力が、まだ読んでいない入力を追い越さないかを確かめる（ゲームは 2 バイトずつ読むので 2 バイトの余裕を見る）"""
    size = (entry[2] << 8) | entry[3]
    body = entry[4:]
    start = size + 0x10 - len(body)
    if start < 0:
        return False
    bi = BitIn(body)
    h = Huff()
    o = 0
    while o < size:
        c = h.son[R]
        while c < T:
            c = h.son[c + bi.bit()]
        c -= T
        h.update(c)
        if c < 256:
            k = 1
        else:
            i = bi.byte()
            j = d_len[i] - 2
            while j:
                bi.bit(); j -= 1
            k = c - 255 + THRESHOLD
        if o + k > start + bi.p - 2 and bi.p < len(body):
            return False
        o += k
    return True
