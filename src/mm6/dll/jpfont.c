/* 日本語の字形（mm6jp_font.bin）を読み、ゲームの字形と同じ 8bpp（0=透明 1=影 255=字）に直して返す
 *
 * mm6jp_font.bin:
 *   "MJF1", u32 nsizes, u32 nglyphs
 *   u32 size[nsizes]
 *   u16 code[nglyphs]           EUC-JP（上位バイト<<8|下位）昇順
 *   各 size ごとに nglyphs × size 行 × u16（左が最上位ビット）
 */
#include "mm6jp.h"

static u8 *g_data;
static int g_nsizes, g_nglyphs;
static int *g_sizes;
static u16 *g_codes;
static u16 *g_bits[4];

int jpfont_load(const char *path)
{
    HANDLE h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    DWORD n, got;
    u8 *p;
    int i;
    if (h == INVALID_HANDLE_VALUE) return 0;
    n = GetFileSize(h, 0);
    g_data = (u8 *)HeapAlloc(GetProcessHeap(), 0, n);
    ReadFile(h, g_data, n, &got, 0);
    CloseHandle(h);
    if (got != n || memcmp(g_data, "MJF1", 4)) return 0;
    g_nsizes = *(int *)(g_data + 4);
    g_nglyphs = *(int *)(g_data + 8);
    if (g_nsizes > 4) return 0;
    g_sizes = (int *)(g_data + 12);
    g_codes = (u16 *)(g_data + 12 + 4 * g_nsizes);
    p = (u8 *)(g_codes + g_nglyphs);
    if ((u32)p & 1) p++;
    for (i = 0; i < g_nsizes; i++) {
        g_bits[i] = (u16 *)p;
        p += g_nglyphs * g_sizes[i] * 2;
    }
    jlog("フォント: %d 字, %d 種", g_nglyphs, g_nsizes);
    return 1;
}

static int find_code(int code)
{
    int lo = 0, hi = g_nglyphs - 1;
    while (lo <= hi) {
        int m = (lo + hi) >> 1;
        if (g_codes[m] == code) return m;
        if (g_codes[m] < code) lo = m + 1; else hi = m - 1;
    }
    return -1;
}

/* フォントの高さから字の大きさを選ぶ。拡大率も返す */
static int pick_size(Font *f, int *scale)
{
    int want = f->height <= 16 ? 10 : 12, i, best = 0;
    *scale = f->height >= 25 ? 2 : 1;
    for (i = 0; i < g_nsizes; i++)
        if (g_sizes[i] == want) return i;
    for (i = 0; i < g_nsizes; i++)
        if (g_sizes[i] > g_sizes[best]) best = i;
    return best;
}

int jp_advance(Font *f)
{
    int sc, si;
    if (!g_nglyphs) return 0;
    si = pick_size(f, &sc);
    return g_sizes[si] * sc + 1;
}

/* 基準線: 'A' の字の色の画素がある最も下の行 */
static int baseline(Font *f)
{
    int c = 'A', w = f->abc[c].B, h = f->height, x, y;
    const u8 *g = f->data + f->glyphOff[c];
    for (y = h - 1; y >= 0; y--)
        for (x = 0; x < w; x++)
            if (g[y * w + x] > 1) return y;
    return h - 4;
}

/* 字形の控え（フォントと符号ごと） */
typedef struct { Font *f; int code; u8 *g; int w, h; } Cache;
#define NCACHE 16384
static Cache g_cache[NCACHE];

const u8 *jp_glyph(Font *f, int code, int *pw, int *ph)
{
    u32 k = ((u32)f * 31u + (u32)code * 2654435761u) & (NCACHE - 1);
    int idx, si, sc, S, W, H, top, x, y, dx, dy;
    u8 *g;
    const u16 *bits;
    for (;;) {
        Cache *c = &g_cache[k];
        if (!c->g) break;
        if (c->f == f && c->code == code) { *pw = c->w; *ph = c->h; return c->g; }
        k = (k + 1) & (NCACHE - 1);
    }
    idx = find_code(code);
    if (idx < 0) idx = find_code(0xA2A3); /* 無い字は □ */
    si = pick_size(f, &sc);
    S = g_sizes[si];
    W = S * sc + 1;
    H = f->height;
    g = (u8 *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, W * H);
    top = baseline(f) + 2 - S * sc;
    if (top + S * sc + 1 > H) top = H - S * sc - 1;
    if (top < 0) top = 0;
    if (idx >= 0) {
        bits = g_bits[si] + idx * S;
        for (y = 0; y < S; y++)
            for (x = 0; x < S; x++) {
                if (!(bits[y] & (0x8000 >> x))) continue;
                for (dy = 0; dy < sc; dy++)
                    for (dx = 0; dx < sc; dx++) {
                        int yy = top + y * sc + dy, xx = x * sc + dx;
                        if (yy < H && xx < W) g[yy * W + xx] = 255;
                    }
            }
        /* 影は右下へ 1 画素 */
        for (y = H - 2; y >= 0; y--)
            for (x = W - 2; x >= 0; x--)
                if (g[y * W + x] == 255 && !g[(y + 1) * W + x + 1]) g[(y + 1) * W + x + 1] = 1;
    }
    g_cache[k].f = f;
    g_cache[k].code = code;
    g_cache[k].g = g;
    g_cache[k].w = W;
    g_cache[k].h = H;
    *pw = W;
    *ph = H;
    return g;
}
