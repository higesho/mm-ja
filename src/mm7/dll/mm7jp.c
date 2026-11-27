/* Might and Magic VII 日本語化 dinput.dll
 *  - 本物の dinput.dll へ DirectInputCreate* を渡す
 *  - MM7-Rel.exe（GOG 版 1.1）のフォント部の関数を Shift_JIS 対応のものに置き換える
 *  - Events.lod から読む txt / STR を日本語のものに差し替える
 */
#include <windows.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include "jfont.h"

typedef unsigned char u8;
typedef unsigned short u16;

/* ---- 本物の dinput.dll ---- */
static HMODULE real_dinput;
static FARPROC get_real(const char *name)
{
    if (!real_dinput) {
        char path[MAX_PATH];
        GetSystemDirectoryA(path, MAX_PATH);
        strcat(path, "\\dinput.dll");
        real_dinput = LoadLibraryA(path);
        if (!real_dinput) return NULL;
    }
    return GetProcAddress(real_dinput, name);
}
typedef HRESULT (WINAPI *DICreateA)(HINSTANCE, DWORD, void **, void *);
typedef HRESULT (WINAPI *DICreateEx)(HINSTANCE, DWORD, const void *, void **, void *);
typedef HRESULT (WINAPI *DIGetClass)(const void *, const void *, void **);
typedef HRESULT (WINAPI *DICanUnload)(void);
HRESULT WINAPI DirectInputCreateA(HINSTANCE h, DWORD v, void **o, void *u)
{ DICreateA f = (DICreateA)get_real("DirectInputCreateA"); return f ? f(h, v, o, u) : E_FAIL; }
HRESULT WINAPI DirectInputCreateW(HINSTANCE h, DWORD v, void **o, void *u)
{ DICreateA f = (DICreateA)get_real("DirectInputCreateW"); return f ? f(h, v, o, u) : E_FAIL; }
HRESULT WINAPI DirectInputCreateEx(HINSTANCE h, DWORD v, const void *r, void **o, void *u)
{ DICreateEx f = (DICreateEx)get_real("DirectInputCreateEx"); return f ? f(h, v, r, o, u) : E_FAIL; }
HRESULT WINAPI DllGetClassObject(const void *a, const void *b, void **c)
{ DIGetClass f = (DIGetClass)get_real("DllGetClassObject"); return f ? f(a, b, c) : E_FAIL; }
HRESULT WINAPI DllCanUnloadNow(void)
{ DICanUnload f = (DICanUnload)get_real("DllCanUnloadNow"); return f ? f() : S_FALSE; }

/* ---- 本体の部品 ---- */
#define RENDER ((void *)0xDF1A68)
typedef void (__fastcall *RenderDrawText_t)(void *ecx, int edx, int x, int y, const u8 *pix, int w, int h, const void *pal, int color, int shadow);
typedef void (__fastcall *RenderDrawTextPal_t)(void *ecx, int edx, int x, int y, const u8 *pix, int w, int h, const void *pal, int transp);
typedef void (__fastcall *DrawCharToBuff_t)(u16 *dst, const u8 *pix, int w, int h, const void *pal, int color, int pitchbytes);
#define RenderDrawText ((RenderDrawText_t)0x4A6BDF)
#define RenderDrawTextPal ((RenderDrawTextPal_t)0x4A6A41)
#define DrawCharToBuff ((DrawCharToBuff_t)0x40F851)
#define FIT_BUF ((u8 *)0x5C4430)
#define FIT_BUF_SIZE 0x1800
#define RECT_BUF ((u8 *)0x5C6400)
#define CUR_COLOR (*(int *)0x5C6C34)
#define STATUS_BUF ((u8 *)0x5C32A8)

typedef struct { int x, y, w, h, z, ww; } Win;

/* フォントの中身 */
#define F_H(f) ((int)(f)[5])
#define F_MET(f, c) ((const int *)((f) + 0x20 + (c) * 12))
#define F_PIX(f, c) ((f) + 0x1020 + *(const unsigned *)((f) + 0xC20 + (c) * 4))
#define F_PAL(f) ((const void *)*(const unsigned *)((f) + 0xC))

static int is_lead(u8 c) { return (c >= 0x81 && c <= 0x9F) || (c >= 0xE0 && c <= 0xFC); }
/* s の字が 2 バイト字か */
static int is_dbcs(const u8 *s) { return is_lead(s[0]) && s[1] >= 0x40; }

static int valid(const u8 *f, u8 c)
{
    return (c >= f[0] && c <= f[1]) || c == 9 || c == 10 || c == 12 || c == 13;
}

/* ---- 日本語の字 ---- */
typedef struct {
    const u8 *font;
    int size;       /* 12/14/16 */
    int top;        /* 字の上端の行 */
    u8 main;        /* 字の点の値 */
    int shadow;     /* 影をつけるか */
} JInfo;
static JInfo jinfo[32];
static int njinfo;

static JInfo *jfont_info(const u8 *f)
{
    int i, h, w, y, x, top = -1, bot = -1, n1 = 0, n255 = 0;
    const u8 *p;
    const int *m;
    JInfo *j;
    for (i = 0; i < njinfo; i++) if (jinfo[i].font == f) return &jinfo[i];
    if (njinfo >= 32) njinfo = 0;
    j = &jinfo[njinfo++];
    j->font = f;
    h = F_H(f);
    j->size = h >= 25 ? 16 : (h >= 22 ? 14 : 12);
    m = F_MET(f, 'A');
    w = m[1];
    p = F_PIX(f, 'A');
    for (y = 0; y < h; y++) {
        int any = 0;
        for (x = 0; x < w; x++) {
            u8 v = p[y * w + x];
            if (v) any = 1;
            if (v == 1) n1++; else if (v == 255) n255++;
        }
        if (any) { if (top < 0) top = y; bot = y; }
    }
    if (n255) { j->main = 255; j->shadow = n1 > 0; }
    else { j->main = 1; j->shadow = 0; }
    if (top < 0) { top = 0; bot = h - 1; }
    /* 「A」の上下の真ん中に合わせる */
    j->top = (top + bot + 1) / 2 - j->size / 2;
    if (j->top + j->size + j->shadow > h) j->top = h - j->size - j->shadow;
    if (j->top < 0) j->top = 0;
    return j;
}

static int jwidth(const u8 *f)
{
    JInfo *j = jfont_info(f);
    return j->size + j->shadow;
}

static const unsigned short *jglyph(int size, const u8 *s)
{
    int l = s[0], t = s[1], j1, j2, idx;
    if (l >= 0xE0) l -= 0x40;
    j1 = (l - 0x81) * 2;
    if (t >= 0x9F) { j1++; j2 = t - 0x9F; }
    else j2 = t - (t >= 0x80 ? 0x41 : 0x40);
    if (j1 < 0 || j1 >= 94 || j2 < 0 || j2 >= 94) return NULL;
    idx = j1 * 94 + j2;
    if (size == 16) return jf16[idx];
    if (size == 14) return jf14[idx];
    return jf12[idx];
}

static u8 gbuf[40 * 40];
/* 日本語の字の点を元のフォントと同じ形（0/1/255）で作る。幅を返す */
static int make_jglyph(const u8 *f, const u8 *s)
{
    JInfo *j = jfont_info(f);
    int w = j->size + j->shadow, h = F_H(f), x, y;
    const unsigned short *g = jglyph(j->size, s);
    memset(gbuf, 0, w * h);
    if (!g) {
        /* 無い字は四角 */
        for (y = 0; y < j->size; y++) for (x = 0; x < j->size - 1; x++)
            if (y == 0 || y == j->size - 1 || x == 0 || x == j->size - 2) gbuf[(j->top + y) * w + x] = j->main;
        return w;
    }
    for (y = 0; y < j->size; y++) {
        unsigned r = g[y];
        for (x = 0; x < j->size; x++) {
            if (r & (0x8000 >> x)) {
                gbuf[(j->top + y) * w + x] = j->main;
                if (j->shadow && j->top + y + 1 < h) {
                    u8 *q = &gbuf[(j->top + y + 1) * w + x + 1];
                    if (*q == 0) *q = 1;
                }
            }
        }
    }
    /* 影が字の点を上書きしないよう、字の点を描き直す（上の順なら上書きは無いが念のため） */
    for (y = 0; y < j->size; y++) {
        unsigned r = g[y];
        for (x = 0; x < j->size; x++) if (r & (0x8000 >> x)) gbuf[(j->top + y) * w + x] = j->main;
    }
    return w;
}

/* 1 字の幅（左の空き＋幅＋右の空き）。n に字のバイト数 */
static int char_full_width(const u8 *f, const u8 *s, int *n)
{
    if (is_dbcs(s)) { *n = 2; return jwidth(f); }
    *n = 1;
    {
        const int *m = F_MET(f, s[0]);
        return m[0] + m[1] + m[2];
    }
}

static int atoi_n(const u8 *s, int n)
{
    int v = 0, i;
    for (i = 0; i < n && s[i] >= '0' && s[i] <= '9'; i++) v = v * 10 + (s[i] - '0');
    return v;
}

static int codelist_has(const unsigned short *list, const u8 *s)
{
    unsigned short c;
    if (!is_dbcs(s)) return 0;
    c = (unsigned short)(s[0] << 8 | s[1]);
    while (*list) if (*list++ == c) return 1;
    return 0;
}
static int no_start(const u8 *s)
{
    if (!is_dbcs(s)) return s[0] == ',' || s[0] == '.' || s[0] == ')' || s[0] == '!' || s[0] == '?' || s[0] == ':' || s[0] == ';';
    return codelist_has(nostart, s);
}
static int no_end(const u8 *s) { return !is_dbcs(s) ? (s[0] == '(') : codelist_has(noend, s); }

/* ---- GetLineWidth 0x44C54A ---- */
int __fastcall J_GetLineWidth(const u8 *f, const u8 *s)
{
    int w = 0, i = 0, len;
    if (!s) return 0;
    len = (int)strlen((const char *)s);
    while (i < len) {
        u8 c = s[i];
        if (!valid(f, c)) { i++; continue; }
        if (c == 9 || c == 10 || c == 13) break;
        if (c == 12) { i += 6; continue; }
        if (is_dbcs(s + i)) { w += jwidth(f); i += 2; continue; }
        {
            const int *m = F_MET(f, c);
            if (i > 0) w += m[0];
            w += m[1] + m[2];
        }
        i++;
    }
    return w;
}

/* ---- 折り返し（FitTextInAWindow / FitTwoFontStringINWindow） ---- */
static u8 wrap_in[FIT_BUF_SIZE * 2];

static int seg_width(const u8 *f, const u8 *s, int len)
{
    int w = 0, i = 0, n;
    while (i < len) {
        u8 c = s[i];
        if (c == 12) { i += 6; continue; }
        if (c == 9 || c == 13) { i += 4; continue; }
        if (c == '\n' || c == '_' && 0) { i++; continue; }
        if (!valid(f, c)) { i++; continue; }
        w += char_full_width(f, s + i, &n);
        i += n;
    }
    return w;
}

static u8 *wrap(const u8 *text, const u8 *font1, const u8 *font2, const Win *win, int uX, int ret_on_cr)
{
    u8 *out = FIT_BUF;
    const u8 *in, *f = font1;
    int i = 0, o = 0, x = uX, bp = -1, bptype = 0, line_start = 0, prev = -1, len;
    int limit = FIT_BUF_SIZE - 8;

    if (!text) return NULL;
    len = (int)strlen((const char *)text);
    if (len >= (int)sizeof(wrap_in)) len = sizeof(wrap_in) - 1;
    memcpy(wrap_in, text, len);
    wrap_in[len] = 0;
    in = wrap_in;

    while (i < len && o < limit) {
        u8 c = in[i];
        int n, cw;
        if (c == 9) {           /* \tNNN */
            x = atoi_n(in + i + 1, 3) + uX;
            memcpy(out + o, in + i, 4); o += 4; i += 4;
            prev = -1;
            continue;
        }
        if (c == 10) {
            out[o++] = 10; i++;
            x = uX; bp = -1; line_start = o; prev = -1;
            f = font1;
            continue;
        }
        if (c == 12) {          /* \fNNNNN */
            memcpy(out + o, in + i, 6); o += 6; i += 6;
            continue;
        }
        if (c == 13) {          /* \rNNN */
            if (!ret_on_cr) return (u8 *)text;
            memcpy(out + o, in + i, 4); o += 4; i += 4;
            continue;
        }
        if (font2 && c == '_') {
            f = font2;
            out[o++] = c; i++;
            continue;
        }
        if (!valid(f, c)) { out[o++] = c; i++; continue; }

        cw = char_full_width(f, in + i, &n);
        /* この字の前で切れるか */
        if (c == ' ') {
            /* 空白は後で決める */
        } else if (prev >= 0 && (is_dbcs(in + i) || is_dbcs(out + prev)) && !no_start(in + i) && !no_end(out + prev)) {
            bp = o; bptype = 2;
        }
        if (x + cw >= win->w && c != ' ') {
            int cut = -1;
            if (bp > line_start) cut = bp;
            else if (bp >= 0 && bptype == 1 && bp >= line_start) cut = bp;
            if (cut < 0 && !no_start(in + i) && o > line_start) { cut = o; bptype = 2; }
            if (cut >= 0) {
                int newstart;
                if (bptype == 1 && cut == bp) {
                    out[cut] = 10;
                    newstart = cut + 1;
                } else {
                    memmove(out + cut + 1, out + cut, o - cut);
                    out[cut] = 10;
                    o++;
                    newstart = cut + 1;
                }
                if (font2 && f == font2) {
                    memmove(out + newstart + 1, out + newstart, o - newstart);
                    out[newstart] = '_';
                    o++;
                    newstart++;
                }
                line_start = newstart;
                x = uX + seg_width(f, out + line_start, o - line_start);
                bp = -1;
            }
        }
        memcpy(out + o, in + i, n);
        if (c == ' ') { bp = o; bptype = 1; }
        prev = o;
        o += n; i += n;
        x += cw;
    }
    out[o] = 0;
    return out;
}

/* 0x44C794 */
u8 *__fastcall J_FitText(const u8 *text, const u8 *font, const Win *win, int uX, int ret_on_cr)
{
    return wrap(text, font, NULL, win, uX, ret_on_cr);
}
/* 0x44C95F */
u8 *__fastcall J_FitText2(const u8 *text, const u8 *font1, const u8 *font2, const Win *win, int uX, int ret_on_cr)
{
    return wrap(text, font1, font2, win, uX, ret_on_cr);
}

/* ---- 高さ 0x44C5C9 ---- */
static int count_height(const u8 *f, const u8 *s, int ret_on_cr)
{
    int h = F_H(f) - 3, i = 0, len;
    if (!s) return 0;
    len = (int)strlen((const char *)s);
    while (i < len) {
        u8 c = s[i];
        if (c == 9 || c == 13) { if (ret_on_cr != 1) i += 3; }
        else if (c == 10) h += F_H(f) - 3;
        else if (c == 12) i += 5;
        i++;
    }
    return h;
}
int __fastcall J_CalcTextHeight(const u8 *f, const u8 *text, const Win *win, int uX, int ret_on_cr)
{
    if (!text) return 0;
    return count_height(f, J_FitText(text, f, win, uX, 0), ret_on_cr);
}
/* 0x44C65A */
int __fastcall J_GetStringHeight2(const u8 *f1, const u8 *f2, const u8 *text, const Win *win, int uX, int ret_on_cr)
{
    if (!text) return 0;
    return count_height(f1, J_FitText2(text, f1, f2, win, uX, 0), ret_on_cr);
}
/* 0x44C6EE */
u8 *__fastcall J_GetPageTop(const u8 *f, const u8 *text, const Win *win, int uX, int page)
{
    u8 *s;
    int y = 0, i = 0, len;
    if (!text) return NULL;
    s = J_FitText(text, f, win, uX, 0);
    len = (int)strlen((const char *)s);
    if (y >= win->h * page) return s;
    while (i < len) {
        u8 c = s[i];
        if (c == 9 || c == 13) i += 3;
        else if (c == 12) i += 5;
        else if (c == 10) {
            y += F_H(f) - 3;
            if (y >= win->h * page) return s + i + 1;
        }
        i++;
    }
    return s + i;
}

/* ---- 1 字を描く ---- */
static void put_char(const u8 *f, int x, int y, const u8 *s, int color, int shadow, int transp, int *adv)
{
    const u8 *pix;
    int w, h = F_H(f);
    if (is_dbcs(s)) {
        w = make_jglyph(f, s);
        pix = gbuf;
    } else {
        w = F_MET(f, s[0])[1];
        pix = F_PIX(f, s[0]);
    }
    if (w > 0) {
        if (color) RenderDrawText(RENDER, 0, x, y, pix, w, h, F_PAL(f), color & 0xFFFF, shadow & 0xFFFF);
        else RenderDrawTextPal(RENDER, 0, x, y, pix, w, h, F_PAL(f), transp);
    }
    *adv = w;
}

/* ---- DrawText 0x44CE34 ---- */
void __fastcall J_DrawText(const Win *win, const u8 *f, int x, int y, int color, const u8 *text, int transp, int maxh, int shadow)
{
    const u8 *s;
    int len, i, px, py, tab = 0, h = F_H(f);
    if (!text) return;
    if (!strcmp((const char *)text, "null")) return;
    len = (int)strlen((const char *)text);
    if (x == 0) x = 12;
    if (maxh == 0) {
        s = J_FitText(text, f, win, x, 0);
        len = (int)strlen((const char *)s);
    } else s = text;
    color &= 0xFFFF;
    px = win->x + x;
    py = win->y + y;
    if (maxh && py + h > maxh) return;
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        if (!valid(f, c)) continue;
        if (c == 9) {
            tab = atoi_n(s + i + 1, 3);
            i += 3;
            px = tab + win->x + x;
        } else if (c == 10) {
            y += h - 3;
            px = win->x + tab + x;
            py = win->y + y;
            if (maxh && py + h - 3 > maxh) return;
        } else if (c == 12) {
            color = atoi_n(s + i + 1, 5);
            i += 5;
        } else if (c == 13) {
            int num = atoi_n(s + i + 1, 3), lw;
            i += 3;
            lw = J_GetLineWidth(f, s + i);
            px = win->z - lw - num;
            py = win->y + y;
            if (maxh && py + h - 3 > maxh) return;
        } else {
            int adv;
            if (is_dbcs(s + i)) {
                put_char(f, px, py, s + i, color, shadow, transp, &adv);
                px += adv;
                i++;
                continue;
            }
            if (c == '"' && s[i + 1] == '"') i++;
            {
                const int *m = F_MET(f, s[i]);
                if (i > 0) px += m[0];
                put_char(f, px, py, s + i, color, shadow, transp, &adv);
                px += m[1];
                if (i < len) px += m[2];
            }
        }
    }
}

/* ---- DrawTextInRect 0x44CB7B ---- */
int __fastcall J_DrawTextInRect(const Win *win, const u8 *f, int x, int y, int color, const u8 *text, int rectw, int reverse)
{
    int lw, len, i, px, py, h = F_H(f);
    u8 *buf = RECT_BUF;
    if (!text) return 0;
    lw = J_GetLineWidth(f, text);
    if (lw < rectw) {
        J_DrawText(win, f, x, y, color, text, 0, 0, 0);
        return lw;
    }
    len = (int)strlen((const char *)text);
    if (len > 2000) len = 2000;
    if (!reverse) {
        /* 先頭から幅に入るだけ */
        int w = 0, n, end = 0;
        i = 0;
        while (i < len) {
            u8 c = text[i];
            if (c == 12) { i += 6; end = i; continue; }
            if (c == 9 || c == 10 || c == 13) { i++; end = i; continue; }
            w += char_full_width(f, text + i, &n);
            if (w >= rectw) break;
            i += n; end = i;
        }
        memcpy(buf, text, end);
        buf[end] = 0;
    } else {
        /* 後ろから幅に入るだけ（字の切れ目を先に数える） */
        static int starts[2048];
        int ns = 0, w = 0, k, n, from = len;
        i = 0;
        while (i < len && ns < 2048) {
            starts[ns++] = i;
            if (text[i] == 12) { i += 6; continue; }
            i += is_dbcs(text + i) ? 2 : 1;
        }
        for (k = ns - 1; k >= 0; k--) {
            const u8 *p = text + starts[k];
            if (p[0] == 12 || p[0] < 32) { from = starts[k]; continue; }
            w += char_full_width(f, p, &n);
            if (w >= rectw) break;
            from = starts[k];
        }
        memcpy(buf, text + from, len - from);
        buf[len - from] = 0;
    }
    lw = J_GetLineWidth(f, buf);
    color &= 0xFFFF;
    px = win->x + x;
    py = win->y + y;
    len = (int)strlen((const char *)buf);
    for (i = 0; i < len; i++) {
        u8 c = buf[i];
        int adv;
        if (!valid(f, c)) continue;
        if (c == 9) { i += 3; continue; }
        if (c == 10) { y += h - 3; px = x; py = y + h - 3; continue; }
        if (c == 12) { color = atoi_n(buf + i + 1, 5); i += 5; continue; }
        if (c == 13) {
            int num = atoi_n(buf + i + 1, 3), w2;
            i += 3;
            w2 = J_GetLineWidth(f, buf + i);
            px = win->z - w2 - num;
            py = y;
            continue;
        }
        if (is_dbcs(buf + i)) {
            put_char(f, px, py, buf + i, color, 0, 0, &adv);
            px += adv; i++;
            continue;
        }
        {
            const int *m = F_MET(f, c);
            if (i > 0) px += m[0];
            put_char(f, px, py, buf + i, color, 0, 0, &adv);
            px += m[1];
            if (i < len) px += m[2];
        }
    }
    return lw;
}

/* ---- DrawTextLineToBuff 0x44D0E1（クレジット） ---- */
void __fastcall J_DrawTextLineToBuff(const u8 *f, int color, int color2, u16 *dst, const u8 *text, int pitch)
{
    int len, i, h = F_H(f);
    (void)color; (void)color2;
    if (!text) return;
    color = CUR_COLOR;
    len = (int)strlen((const char *)text);
    for (i = 0; i < len; i++) {
        u8 c = text[i];
        if (!valid(f, c)) continue;
        if (c == 9 || c == 13 || c == '_') continue;
        if (c == 10) return;
        if (c == 12) { color = atoi_n(text + i + 1, 5); CUR_COLOR = color; i += 5; continue; }
        if (is_dbcs(text + i)) {
            int w = make_jglyph(f, text + i);
            DrawCharToBuff(dst, gbuf, w, h, F_PAL(f), color ? color : 0xFFFF, pitch * 2);
            dst += w; i++;
            continue;
        }
        {
            const int *m = F_MET(f, c);
            if (m[1] == 0) continue;
            if (i > 0) dst += m[0];
            DrawCharToBuff(dst, F_PIX(f, c), m[1], h, F_PAL(f), color ? color : 0xFFFF, pitch * 2);
            dst += m[1];
            if (i < len) dst += m[2];
        }
    }
}

/* ---- DrawTextLine 0x44D213 ---- */
void __fastcall J_DrawTextLine(const u8 *f, int color, int x, int y, const u8 *text, int maxlen)
{
    int len, i, adv;
    (void)color; (void)maxlen;
    if (!text) return;
    color = CUR_COLOR;
    len = (int)strlen((const char *)text);
    for (i = 0; i < len; i++) {
        u8 c = text[i];
        if (!valid(f, c)) continue;
        if (c == 9 || c == 13) continue;
        if (c == 10) return;
        if (c == 12) { color = atoi_n(text + i + 1, 5); CUR_COLOR = color; i += 5; continue; }
        if (is_dbcs(text + i)) {
            put_char(f, x, y, text + i, color ? color : 0xFFFF, 0, 0, &adv);
            x += adv; i++;
            continue;
        }
        {
            const int *m = F_MET(f, c);
            if (m[1] == 0) continue;
            if (i > 0) x += m[0];
            put_char(f, x, y, text + i, color ? color : 0xFFFF, 0, 0, &adv);
            x += m[1];
            if (i < len) x += m[2];
        }
    }
}

/* ---- 状態表示行 0x44C1A1 ---- */
static u8 tramp_status[16];
typedef void (__fastcall *Status_t)(const u8 *s, int sec);
void __fastcall J_ShowStatus(const u8 *s, int sec)
{
    int i = 0, last = 0;
    ((Status_t)(void *)tramp_status)(s, sec);
    /* 半端な 1 バイト目を消す */
    while (STATUS_BUF[i]) {
        last = i;
        i += (is_dbcs(STATUS_BUF + i)) ? 2 : 1;
    }
    if (i > 0 && is_lead(STATUS_BUF[last]) && STATUS_BUF[last + 1] == 0) STATUS_BUF[last] = 0;
}

/* ---- 品物の名前 0x4564DF（鑑定済みの名前、thiscall ecx=品物） ----
 * 元は「名前 of 〜」（後付け）と「〜 名前」（前付け）がある。日本語ではどちらも「〜名前」（空白なし）にする。
 * 訳では後付けの語も「腕力の」のように前に付く形で書く */
static u8 tramp_itemname[16];
typedef char *(__fastcall *ItemName_t)(int *it, int edx);
#define ITEM_REC(id) ((u8 *)0x5D2860 + (id) * 0x30)
char *__fastcall J_ItemName(int *it, int edx)
{
    char *buf = ((ItemName_t)(void *)tramp_itemname)(it, edx);
    int id = it[0];
    const char *name = *(const char **)(ITEM_REC(id) + 8);
    const char *add = NULL;
    static char tmp[256];
    if (!buf || !name || id == 0x259 || !strcmp(buf, name)) return buf;
    if (it[1]) add = *(const char **)(0x5DBE50 + it[1] * 20);
    else if (it[3]) add = *(const char **)(0x5DC028 + it[3] * 0x1C);
    if (!add) return buf;
    _snprintf(tmp, sizeof(tmp) - 1, "%s%s", add, name);
    tmp[sizeof(tmp) - 1] = 0;
    strcpy(buf, tmp);
    return buf;
}

/* ---- フォントの高さを広げる 0x44C474（LoadFont、cdecl） ----
 * 12 ドットの字＋影が行に収まるよう、高さが MIN_FONT_H 未満のフォントは下に空きの行を足した形に作り直す */
#define MIN_FONT_H 17
static u8 tramp_loadfont[16];
typedef u8 *(__cdecl *LoadFont_t)(const char *, const char *, const char *, const char *, const char *, const char *, const char *, const char *);
static u8 *grow_font(u8 *f)
{
    int h = F_H(f), nh = MIN_FONT_H, c, total = 0;
    u8 *nf, *dst;
    if (!f || h >= MIN_FONT_H) return f;
    for (c = 0; c < 256; c++) total += F_MET(f, c)[1] * nh;
    nf = (u8 *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, 0x1020 + total + 64);
    if (!nf) return f;
    memcpy(nf, f, 0x1020);
    nf[5] = (u8)nh;
    dst = nf + 0x1020;
    for (c = 0; c < 256; c++) {
        int w = F_MET(f, c)[1];
        *(unsigned *)(nf + 0xC20 + c * 4) = (unsigned)(dst - (nf + 0x1020));
        if (w > 0) memcpy(dst, F_PIX(f, c), w * h);
        dst += w * nh;
    }
    return nf;
}
u8 *__cdecl J_LoadFont(const char *a, const char *b, const char *c, const char *d, const char *e, const char *f, const char *g, const char *h)
{
    u8 *font = ((LoadFont_t)(void *)tramp_loadfont)(a, b, c, d, e, f, g, h);
    return grow_font(font);
}

/* ---- txt の差し替え 0x410897 ---- */
static u8 tramp_lod[16];
typedef u8 *(__fastcall *LodLoad_t)(void *lod, int edx, const char *name, int kind);
typedef void *(__fastcall *GameAlloc_t)(void *ecx, int edx, int a, int size, void *hdr);
typedef void (__fastcall *GameFree_t)(void *ecx, int edx, void *p);
typedef void *(__cdecl *CrtMalloc_t)(size_t);
#define GameAlloc ((GameAlloc_t)0x4266FE)
#define GameFree ((GameFree_t)0x42641D)
#define CrtMalloc ((CrtMalloc_t)0x4CADC2)
#define ALLOCATOR ((void *)0x7029A8)

static char jpdir[MAX_PATH];
static char gamedir[MAX_PATH];

#include "lodpatch.inc"

/* ---- レジストリ: 管理者でないと HKLM を書き込み可で開けないので、読み取りだけで開き直す ---- */
static LONG WINAPI J_RegOpenKeyExA(HKEY k, LPCSTR sub, DWORD opt, REGSAM sam, PHKEY out)
{
    LONG r = RegOpenKeyExA(k, sub, opt, sam, out);
    if (r == ERROR_ACCESS_DENIED) r = RegOpenKeyExA(k, sub, opt, KEY_READ, out);
    return r;
}

#ifdef MM7JP_TEST
/* ---- 調べ用の記録（試験版だけ。環境変数 MM7JP_LOG があるとき） ---- */
static FILE *logf;
static void logmsg(const char *fmt, ...)
{
    va_list ap;
    if (!logf) return;
    va_start(ap, fmt);
    vfprintf(logf, fmt, ap);
    va_end(ap);
    fflush(logf);
}
static HANDLE WINAPI L_CreateFileA(LPCSTR n, DWORD a, DWORD sh, LPSECURITY_ATTRIBUTES sa, DWORD cd, DWORD fl, HANDLE t)
{
    HANDLE h = CreateFileA(n, a, sh, sa, cd, fl, t);
    logmsg("CreateFileA %s acc=%x -> %p err=%u\n", n, a, h, h == INVALID_HANDLE_VALUE ? GetLastError() : 0);
    return h;
}
static void WINAPI L_GlobalMemoryStatus(LPMEMORYSTATUS m)
{
    GlobalMemoryStatus(m);
    logmsg("GlobalMemoryStatus total=%u avail=%u virt=%u availvirt=%u\n", m->dwTotalPhys, m->dwAvailPhys, m->dwTotalVirtual, m->dwAvailVirtual);
}
static void set_iat(DWORD at, void *fn)
{
    DWORD old;
    VirtualProtect((void *)at, 4, PAGE_READWRITE, &old);
    *(void **)at = fn;
    VirtualProtect((void *)at, 4, old, &old);
}
#endif /* MM7JP_TEST */

static LONG WINAPI J_RegCreateKeyExA(HKEY k, LPCSTR sub, DWORD res, LPSTR cls, DWORD opt, REGSAM sam,
                                     const LPSECURITY_ATTRIBUTES sa, PHKEY out, LPDWORD disp)
{
    LONG r = RegCreateKeyExA(k, sub, res, cls, opt, sam, sa, out, disp);
    if (r == ERROR_ACCESS_DENIED) {
        r = RegOpenKeyExA(k, sub, 0, KEY_READ, out);
        if (r == ERROR_SUCCESS && disp) *disp = REG_OPENED_EXISTING_KEY;
    }
    return r;
}

#ifdef MM7JP_TEST
/* 試験用: MM7JP_SOFT があるとき "Use D3D" を 0 として返す（窓ではソフト描画にする） */
static LONG WINAPI T_RegQueryValueExA(HKEY k, LPCSTR name, LPDWORD res, LPDWORD type, LPBYTE data, LPDWORD size)
{
    LONG r = RegQueryValueExA(k, name, res, type, data, size);
    if (name && !_stricmp(name, "Use D3D") && data && size && *size >= 4) {
        *(DWORD *)data = 0;
        if (type) *type = REG_DWORD;
        r = ERROR_SUCCESS;
    }
    return r;
}

/* 試験用: 共有メモリ MM7JP_INPUT {有効, x, y, ボタン} があればマウスの状態をそれで返す */
typedef struct { int active, x, y, buttons, shot_req, shot_done; u8 keys[256]; } FakeInput;
static FakeInput *fake;
static HWND game_wnd;
static BOOL CALLBACK find_game(HWND h, LPARAM l)
{
    DWORD pid; char t[64];
    GetWindowThreadProcessId(h, &pid);
    if (pid == GetCurrentProcessId() && GetWindowTextA(h, t, 64) && !strncmp(t, "Might", 5)) { game_wnd = h; return FALSE; }
    return TRUE;
}
static FakeInput *get_fake(void)
{
    if (!fake) {
        HANDLE m = OpenFileMappingA(FILE_MAP_READ | FILE_MAP_WRITE, FALSE, "MM7JP_INPUT");
        if (m) fake = (FakeInput *)MapViewOfFile(m, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, sizeof(FakeInput));
    }
    return (fake && fake->active) ? fake : NULL;
}
static SHORT WINAPI T_GetAsyncKeyState(int vk)
{
    FakeInput *f = get_fake();
    if (f && (vk == VK_LBUTTON || vk == VK_RBUTTON)) return (f->buttons & (vk == VK_LBUTTON ? 1 : 2)) ? (SHORT)0x8000 : 0;
    if (fake && vk >= 0 && vk < 256 && fake->keys[vk]) return (SHORT)0x8001;
    return GetAsyncKeyState(vk);
}
static BOOL WINAPI T_GetCursorPos(LPPOINT pt)
{
    FakeInput *f = get_fake();
    if (f) {
        if (!game_wnd) EnumWindows(find_game, 0);
        pt->x = f->x; pt->y = f->y;
        if (game_wnd) ClientToScreen(game_wnd, pt);
        return TRUE;
    }
    return GetCursorPos(pt);
}

/* 試験用: 前面でなくても止まらないようにする */
static BOOL WINAPI T_WaitMessage(void)
{
    *(u8 *)0x6BE1E5 &= ~1;
    Sleep(1);
    return TRUE;
}
static HWND WINAPI T_GetForegroundWindow(void)
{
    if (!game_wnd) EnumWindows(find_game, 0);
    return game_wnd ? game_wnd : GetForegroundWindow();
}

/* 試験用: 画面を離す直前（EndScene 0x4A520D）に、頼まれていれば 640x480 の 16bit 画面をファイルに書く */
static u8 tramp_endscene[16];
static char jpdir_shot[MAX_PATH];
typedef void (__fastcall *EndScene_t)(u8 *r, int edx);
void __fastcall T_EndScene(u8 *r, int edx)
{
    FakeInput *f;
    if (!fake) get_fake();
    f = fake;
    if (f && f->shot_req != f->shot_done && *(int *)(r + 0x400E4) == 1) {
        const u16 *px = *(const u16 **)(r + 0x400EC);
        int pitch = *(int *)(r + 0x400F0), y;
        if (px && pitch >= 640) {
            FILE *o = fopen(jpdir_shot, "wb");
            if (o) {
                for (y = 0; y < 480; y++) fwrite(px + y * pitch, 2, 640, o);
                fclose(o);
            }
            f->shot_done = f->shot_req;
        }
    }
    ((EndScene_t)(void *)tramp_endscene)(r, edx);
}
#endif /* MM7JP_TEST */

/* ---- 書き換え ---- */
static int code_ok = 1;
static void write_jmp(DWORD at, void *to)
{
    DWORD old;
    u8 *p = (u8 *)at;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xE9;
    *(DWORD *)(p + 1) = (DWORD)to - (at + 5);
    VirtualProtect(p, 5, old, &old);
}
static void make_tramp(u8 *tramp, DWORD at, int n)
{
    DWORD old;
    memcpy(tramp, (void *)at, n);
    tramp[n] = 0xE9;
    *(DWORD *)(tramp + n + 1) = (at + n) - ((DWORD)tramp + n + 5);
    VirtualProtect(tramp, 16, PAGE_EXECUTE_READWRITE, &old);
}
static int check(DWORD at, const char *hex)
{
    const u8 *p = (const u8 *)at;
    int i = 0;
    while (hex[0] && hex[1]) {
        unsigned v;
        sscanf(hex, "%2x", &v);
        if (p[i++] != (u8)v) return 0;
        hex += 2;
    }
    return 1;
}

static void install(void)
{
    char *p;
    /* GOG 版 1.1 か確かめる */
    if (!check(0x44C54A, "51578954240485D28BF9") || !check(0x44CE34, "558BEC83EC2C") ||
        !check(0x410897, "558BEC83EC4C") || !check(0x44C1A1, "5657BFA8325C00") ||
        !check(0x44C794, "558BEC83EC1C") ||
        !check(0x44C474, "558BEC83EC0C")) {
        code_ok = 0;
        return;
    }
    GetModuleFileNameA(NULL, jpdir, MAX_PATH);
    p = strrchr(jpdir, '\\');
    if (p) *p = 0;
    strcpy(gamedir, jpdir);
    strcat(jpdir, "\\MM7JP");

    {
        DWORD old;
        void **iat = (void **)0x4D8000;      /* RegOpenKeyExA */
        if (*iat == (void *)GetProcAddress(GetModuleHandleA("advapi32.dll"), "RegOpenKeyExA")) {
            VirtualProtect(iat, 4, PAGE_READWRITE, &old);
            *iat = (void *)J_RegOpenKeyExA;
            VirtualProtect(iat, 4, old, &old);
        }
        iat = (void **)0x4D800C;              /* RegCreateKeyExA */
        if (*iat == (void *)GetProcAddress(GetModuleHandleA("advapi32.dll"), "RegCreateKeyExA")) {
            VirtualProtect(iat, 4, PAGE_READWRITE, &old);
            *iat = (void *)J_RegCreateKeyExA;
            VirtualProtect(iat, 4, old, &old);
        }
    }
#ifdef MM7JP_TEST
    /* 試験版だけ: 環境変数で記録・ソフト描画・試験の操作口・フックなしを選ぶ */
    if (GetEnvironmentVariableA("MM7JP_LOG", NULL, 0)) {
        char lp[MAX_PATH];
        strcpy(lp, jpdir);
        strcat(lp, "_log.txt");
        logf = fopen(lp, "w");
        set_iat(0x4D8074, (void *)L_CreateFileA);
        set_iat(0x4D8168, (void *)L_GlobalMemoryStatus);
    }
    if (GetEnvironmentVariableA("MM7JP_SOFT", NULL, 0)) set_iat(0x4D8008, (void *)T_RegQueryValueExA);
    if (GetEnvironmentVariableA("MM7JP_TEST", NULL, 0)) {
        set_iat(0x4D8260, (void *)T_GetAsyncKeyState);
        set_iat(0x4D825C, (void *)T_GetCursorPos);
        set_iat(0x4D8270, (void *)T_WaitMessage);
        set_iat(0x4D81BC, (void *)T_GetForegroundWindow);
        strcpy(jpdir_shot, jpdir);
        strcat(jpdir_shot, "_shot.raw");
        if (check(0x4A520D, "518D81E400040056")) {
            make_tramp(tramp_endscene, 0x4A520D, 7);
            write_jmp(0x4A520D, (void *)T_EndScene);
        }
    }
    if (GetEnvironmentVariableA("MM7JP_NOHOOK", NULL, 0)) return;
#endif /* MM7JP_TEST */
    write_jmp(0x44C54A, (void *)J_GetLineWidth);
    write_jmp(0x44C5C9, (void *)J_CalcTextHeight);
    write_jmp(0x44C65A, (void *)J_GetStringHeight2);
    write_jmp(0x44C6EE, (void *)J_GetPageTop);
    write_jmp(0x44C794, (void *)J_FitText);
    write_jmp(0x44C95F, (void *)J_FitText2);
    write_jmp(0x44CB7B, (void *)J_DrawTextInRect);
    write_jmp(0x44CE34, (void *)J_DrawText);
    write_jmp(0x44D0E1, (void *)J_DrawTextLineToBuff);
    write_jmp(0x44D213, (void *)J_DrawTextLine);
    make_tramp(tramp_status, 0x44C1A1, 7);
    write_jmp(0x44C1A1, (void *)J_ShowStatus);
    if (check(0x4564DF, "568BF1578B06")) {
        make_tramp(tramp_itemname, 0x4564DF, 6);
        write_jmp(0x4564DF, (void *)J_ItemName);
    }
    make_tramp(tramp_loadfont, 0x44C474, 6);
    write_jmp(0x44C474, (void *)J_LoadFont);
    make_tramp(tramp_lod, 0x410897, 6);
    write_jmp(0x410897, (void *)J_LodLoad);
    /* 0x443D54「call fread（LOD の見出し）」を包む。文字列集の大きさを訳後のものにする */
    if (*(u8 *)0x443D54 == 0xE8 && 0x443D54 + 5 + *(int *)0x443D55 == 0x4CB8A5) {
        DWORD old;
        VirtualProtect((void *)0x443D54, 5, PAGE_EXECUTE_READWRITE, &old);
        *(DWORD *)0x443D55 = (DWORD)J_FreadHdr - (0x443D54 + 5);
        VirtualProtect((void *)0x443D54, 5, old, &old);
    }
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        install();
    }
    return TRUE;
}
