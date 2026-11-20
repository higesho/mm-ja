/* MM8 の文字描画（フォント部）を Shift_JIS 対応の関数に置き換える。
 *
 * 置き換える関数（すべて __fastcall: ECX・EDX＋スタック、呼ばれた側が片付け）
 *   0x44adf8 GetLineWidth(font, str)
 *   0x44ae82 CalcTextHeight(font, str, win, x, flag)
 *   0x44af21 CalcTextHeight2(font1, font2, str, win, x, flag)
 *   0x44afba GetPageTop(font, str, win, x, page)
 *   0x44b06b FitTextInAWindow(str, font, win, x, flag)      結果は 0x5dc814
 *   0x44b226 FitTwoFontString(str, font1, font2, win, x, flag)
 *   0x44b450 DrawTextInRect(win, font, x, y, color, str, width, reverse)
 *   0x44b786 DrawText(win, font, x, y, color, str, alpha, max_y, shadow)
 *   0x44ba36 DrawTextLineToBuff(font, -, -, dest, str, line_w)
 *   0x44bb6c DrawTextLine(font, -, x, y, str, -)
 * 字を描く下位（本体のまま使う）
 *   0x4a6f56 Render::DrawText(this=0xec1880, x, y, px, w, h, pal, color, shadow)
 *   0x4a6dc0 Render::DrawTextAlpha(this, x, y, px, w, h, pal, flag)
 *   0x410fad DrawCharToBuff(dest, px, w, h, pal, color, pitch)
 */
#include "mm8jp.h"
#include <string.h>
#include <stdlib.h>
#include "jfont.h"

typedef unsigned char u8;

/* ---- 本体の番地 ---- */
#define FIT_BUF      ((char *)A->FitBuf)
#define FIT_BUF_SIZE 0x4700
#define CUR_COLOR    (*(int *)A->CurColor)
#define RENDER       ((void *)A->Render)

typedef void (__fastcall *PFN_RDrawText)(void *self, int edx, int x, int y, const u8 *px, int w, int h, void *pal, int color, int shadow);
typedef void (__fastcall *PFN_RDrawTextAlpha)(void *self, int edx, int x, int y, const u8 *px, int w, int h, void *pal, int flag);
typedef void (__fastcall *PFN_CharToBuff)(void *dest, const u8 *px, int w, int h, void *pal, int color, int pitch);
#define R_DrawText      ((PFN_RDrawText)A->R_DrawText)
#define R_DrawTextAlpha ((PFN_RDrawTextAlpha)A->R_DrawTextAlpha)
#define CharToBuff      ((PFN_CharToBuff)A->CharToBuff)

/* ---- フォントの中身 ---- */
#define F_H(f)      ((int)(f)[5])
#define F_PAL(f)    (*(void **)((f) + 0x0c))
#define F_L(f, c)   (((int *)((f) + 0x20))[(c) * 3 + 0])
#define F_W(f, c)   (((int *)((f) + 0x20))[(c) * 3 + 1])
#define F_R(f, c)   (((int *)((f) + 0x20))[(c) * 3 + 2])
#define F_PX(f, c)  ((f) + 0x1020 + ((DWORD *)((f) + 0xc20))[c])

/* Shift_JIS の 1 バイト目か */
static int is_lead(u8 a) { return (a >= 0x81 && a <= 0x9f) || (a >= 0xe0 && a <= 0xfc); }

static int valid(const u8 *f, u8 c)
{
    return (c >= f[0] && c <= f[1]) || c == 12 || c == 13 || c == 9 || c == 10;
}

/* ---- 日本語の字 ---- */
/* s が 2 バイトの字なら区点の番号（0〜8835）、でなければ -1 */
static int jchar(const u8 *s)
{
    u8 a = s[0], b;
    int ku, ten, k;
    if (!((a >= 0x81 && a <= 0x9f) || (a >= 0xe0 && a <= 0xfc))) return -1;
    b = s[1];
    if (b < 0x40 || b > 0xfc || b == 0x7f) return -1;
    ku = (a - (a < 0xa0 ? 0x81 : 0xc1)) * 2 + 1;
    if (b >= 0x9f) { ku++; ten = b - 0x9f + 1; }
    else ten = b - 0x40 + 1 - (b >= 0x80 ? 1 : 0);
    if (ku < 1 || ku > 94) return -1;
    k = (ku - 1) * 94 + (ten - 1);
    if (!(jfont_have[k >> 3] & (1 << (k & 7)))) return -1;
    return k;
}

typedef struct {
    const u8 *font;
    int size, top;          /* 日本語の字の大きさと上の空き */
    u8 **glyph;             /* 区点ごとの点（作ったものだけ） */
} JFont;
static JFont g_jf[32];
static int g_njf;

static JFont *jfont_of(const u8 *f)
{
    int i, h, y, x, top = -1, bot = -1, cen;
    JFont *j;
    for (i = 0; i < g_njf; i++)
        if (g_jf[i].font == f) return &g_jf[i];
    if (g_njf >= 32) return &g_jf[31];
    j = &g_jf[g_njf++];
    j->font = f;
    h = F_H(f);
    j->size = h <= 17 ? 12 : h <= 22 ? 14 : 16;
    /* 英字の 'H' の縦の中心に合わせる */
    if (F_W(f, 'H') > 0) {
        const u8 *p = F_PX(f, 'H');
        int w = F_W(f, 'H');
        for (y = 0; y < h; y++)
            for (x = 0; x < w; x++)
                if (p[y * w + x] > 1) { if (top < 0) top = y; bot = y; }
    }
    if (top >= 0) cen = (top + bot + 1) / 2;
    else cen = h / 2;
    j->top = cen - j->size / 2;
    if (j->top + j->size + 1 > h) j->top = h - j->size - 1;
    if (j->top < 0) j->top = 0;
    j->glyph = (u8 **)calloc(94 * 94, sizeof(u8 *));
    jlog("jfont %p h=%d size=%d top=%d", f, h, j->size, j->top);
    return j;
}

static int jw(const u8 *f) { return jfont_of(f)->size; }

/* 日本語の字の点（幅 size+1、高さはフォントの高さ。255=字、1=影） */
static const u8 *jglyph(const u8 *f, int k)
{
    JFont *j = jfont_of(f);
    int s = j->size, w = s + 1, h = F_H(f), x, y;
    const unsigned short *src;
    u8 *g;
    if (j->glyph[k]) return j->glyph[k];
    g = (u8 *)calloc(w * h, 1);
    src = s == 12 ? &jfont12[k * 12] : s == 14 ? &jfont14[k * 14] : &jfont16[k * 16];
    for (y = 0; y < s; y++)
        for (x = 0; x < s; x++)
            if (src[y] & (0x8000 >> x)) g[(j->top + y) * w + x] = 255;
    for (y = h - 2; y >= 0; y--)
        for (x = w - 2; x >= 0; x--)
            if (g[y * w + x] == 255 && g[(y + 1) * w + x + 1] == 0) g[(y + 1) * w + x + 1] = 1;
    j->glyph[k] = g;
    return g;
}

/* ---- 禁則 ---- */
static int sj(const u8 *s) { return (s[0] << 8) | s[1]; }
static const unsigned short no_start[] = {   /* 行頭に来てはいけない字 */
    0x8141, 0x8142, 0x8143, 0x8144, 0x8145, 0x8146, 0x8147, 0x8148, 0x8149, 0x815b, 0x8160, 0x8163, 0x8164,
    0x8166, 0x8168, 0x816a, 0x816c, 0x816e, 0x8170, 0x8172, 0x8174, 0x8176, 0x8178, 0x817a, 0x8158,
    0x829f, 0x82a1, 0x82a3, 0x82a5, 0x82a7, 0x82c1, 0x82e1, 0x82e3, 0x82e5, 0x82ec,
    0x8340, 0x8342, 0x8344, 0x8346, 0x8348, 0x8362, 0x8383, 0x8385, 0x8387, 0x838e, 0x8395, 0x8396, 0
};
static const unsigned short no_end[] = {     /* 行末に来てはいけない字 */
    0x8165, 0x8167, 0x8169, 0x816b, 0x816d, 0x816f, 0x8171, 0x8173, 0x8175, 0x8177, 0x8179, 0
};
static int in_list(const unsigned short *t, int c)
{
    for (; *t; t++) if (*t == c) return 1;
    return 0;
}
static int ascii_no_start(u8 c)
{
    return c == '.' || c == ',' || c == ')' || c == '!' || c == '?' || c == ':' || c == ';' || c == '"' || c == '\'' || c == ']' || c == '%';
}

/* ---- 幅 ---- */
int __fastcall J_GetLineWidth(const u8 *f, const u8 *s)
{
    int len, i, w = 0;
    if (!s) return 0;
    len = (int)strlen((const char *)s);
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        if (jchar(s + i) >= 0) { w += jw(f); i++; continue; }
        if (is_lead(c) && s[i + 1] == 0) break;     /* 1 バイトずつ削られて残った 1 バイト目 */
        if (!valid(f, c)) continue;
        if (c == 9 || c == 10 || c == 13) return w;
        if (c == 12) { i += 5; continue; }
        if (i > 0) w += F_L(f, c);
        w += F_W(f, c) + F_R(f, c);
    }
    return w;
}

/* out[from..to) の幅（行の頭の字は左の空きを足さない） */
static int seg_width(const u8 *f1, const u8 *f2, const u8 *f, const u8 *s, int from, int to)
{
    int i, w = 0, first = 1;
    for (i = from; i < to; i++) {
        u8 c = s[i];
        if (jchar(s + i) >= 0) { w += jw(f); i++; first = 0; continue; }
        if (f2 && c == '_') { f = f2; continue; }
        if (!valid(f, c)) continue;
        if (c == 12) { i += 5; continue; }
        if (c == 9 || c == 10 || c == 13) continue;
        if (!first) w += F_L(f, c);
        w += F_W(f, c) + F_R(f, c);
        first = 0;
    }
    return w;
}

/* ---- 折り返し ----
 * 元の関数は「最後の空白を \n に替える」だけ。日本語は字と字の間でも折れるよう、
 * 必要なら \n を差し込む（禁則つき）。f2 があれば '_' で f2 に切り替わる版。 */
static const char *fit_core(const u8 *str, const u8 *f1, const u8 *f2, const int *win, int x, int flag)
{
    u8 *o = (u8 *)FIT_BUF;
    int cap = FIT_BUF_SIZE - 8;
    int len, i, n = 0, start = x, w = x, width = win[2];
    int brk = -1, brk_space = 0, line_start = 0, brk_font2 = 0, prev_j = 0, prev_noend = 0;
    const u8 *f = f1;
    if (!str) return NULL;
    len = (int)strlen((const char *)str);
    for (i = 0; i < len && n < cap; i++) {
        u8 c = str[i];
        int k = jchar(str + i), need, can_break = 0;
        if (k >= 0) {
            int code = sj(str + i);
            need = jw(f);
            if (n > line_start && !in_list(no_start, code) && !prev_noend) can_break = 1;
        } else if (c == ' ') {
            w += F_W(f, ' ');
            brk = n; brk_space = 1; brk_font2 = (f == f2);
            o[n++] = c; prev_j = 0; prev_noend = 0;
            continue;
        } else if (c == '\n') {
            w = start; o[n++] = c; line_start = n; brk = -1;
            if (f2) f = f1;
            prev_j = 0; prev_noend = 0;
            continue;
        } else if (c == 9) {
            char d[4] = {0};
            strncpy(d, (const char *)str + i + 1, 3);
            w = atoi(d) + x; start = w;
            memcpy(o + n, str + i, 4); n += 4; i += 3;
            continue;
        } else if (c == 12) {
            memcpy(o + n, str + i, 6); n += 6; i += 5;
            continue;
        } else if (c == 13) {
            if (!flag) return (const char *)str;
            o[n++] = c;
            continue;
        } else if (f2 && c == '_') {
            f = f2; o[n++] = c;
            continue;
        } else if (!valid(f, c)) {
            o[n++] = c;
            continue;
        } else {
            need = F_L(f, c) + F_W(f, c) + F_R(f, c);
            if (prev_j && n > line_start && !ascii_no_start(c)) can_break = 1;
        }
        if (can_break) { brk = n; brk_space = 0; brk_font2 = (f == f2); }
        if (w + need >= width && n > line_start) {
            /* 折る */
            if (brk > line_start || (brk == line_start && !brk_space && brk > 0)) {
                if (brk_space) {
                    o[brk] = '\n';
                    line_start = brk + 1;
                } else {
                    memmove(o + brk + 1, o + brk, n - brk);
                    o[brk] = '\n';
                    n++;
                    line_start = brk + 1;
                }
                if (f2 && brk_font2) {
                    memmove(o + line_start + 1, o + line_start, n - line_start);
                    o[line_start] = '_';
                    n++;
                }
                w = start + seg_width(f1, f2, brk_font2 ? f2 : f1, o, line_start, n);
            } else {
                /* 折る所がない（長い語）: 今の字の前で折る */
                o[n++] = '\n';
                line_start = n;
                if (f2 && f == f2) o[n++] = '_';
                w = start;
            }
            brk = -1;
        }
        if (k >= 0) {
            o[n++] = str[i]; o[n++] = str[i + 1]; i++;
            w += need;
            prev_j = 1;
            prev_noend = in_list(no_end, sj(o + n - 2));
        } else {
            if (n > line_start) w += F_L(f, c);
            w += F_W(f, c) + F_R(f, c);
            o[n++] = c;
            prev_j = 0; prev_noend = 0;
        }
    }
    o[n] = 0;
    return (const char *)o;
}

const char *__fastcall J_FitText(const u8 *str, const u8 *f, const int *win, int x, int flag)
{
    return fit_core(str, f, NULL, win, x, flag);
}

const char *__fastcall J_FitTwoFont(const u8 *str, const u8 *f1, const u8 *f2, const int *win, int x, int flag)
{
    return fit_core(str, f1, f2, win, x, flag);
}

/* ---- 高さ ---- */
static int text_height(const u8 *f, const u8 *t, int flag)
{
    int h = F_H(f) - 3, i, len;
    if (!t) return h;
    len = (int)strlen((const char *)t);
    for (i = 0; i < len; i++) {
        u8 c = t[i];
        if (jchar(t + i) >= 0) { i++; continue; }
        if (!valid(f, c)) continue;
        switch (c) {
        case 9: case 13: if (flag != 1) i += 3; break;
        case 10: h += F_H(f) - 3; break;
        case 12: i += 5; break;
        }
    }
    return h;
}

int __fastcall J_CalcTextHeight(const u8 *f, const u8 *str, const int *win, int x, int flag)
{
    if (!str) return 0;
    return text_height(f, (const u8 *)J_FitText(str, f, win, x, 0), flag);
}

int __fastcall J_CalcTextHeight2(const u8 *f1, const u8 *f2, const u8 *str, const int *win, int x, int flag)
{
    if (!str) return 0;
    return text_height(f1, (const u8 *)J_FitTwoFont(str, f1, f2, win, x, 0), flag);
}

const char *__fastcall J_GetPageTop(const u8 *f, const u8 *str, const int *win, int x, int page)
{
    const u8 *t;
    int i, len, h = 0, lim;
    if (!str) return NULL;
    t = (const u8 *)J_FitText(str, f, win, x, 0);
    len = (int)strlen((const char *)t);
    lim = win[3] * page;
    for (i = 0; i < len; i++) {
        u8 c = t[i];
        if (jchar(t + i) >= 0) { i++; if (h >= lim) return (const char *)t + i - 1; continue; }
        if (!valid(f, c)) continue;
        switch (c) {
        case 9: case 13: i += 3; break;
        case 10:
            h += F_H(f) - 3;
            if (h >= lim) return (const char *)t + i + 1;
            break;
        case 12: i += 5; break;
        }
        if (h >= lim) return (const char *)t + i;
    }
    return (const char *)t + len;
}

/* ---- 描画 ---- */
static void put_glyph(const u8 *f, int x, int y, const u8 *px, int w, int color, int alpha, int shadow)
{
    if (color)
        R_DrawText(RENDER, 0, x, y, px, w, F_H(f), F_PAL(f), color & 0xffff, shadow & 0xffff);
    else
        R_DrawTextAlpha(RENDER, 0, x, y, px, w, F_H(f), F_PAL(f), alpha);
}

static void draw_core(const int *win, const u8 *f, int x, int y, int color, const u8 *t,
                      int alpha, int maxy, int shadow)
{
    int len, i, sx, sy, margin = 0, h = F_H(f);
    char d[8];
    len = (int)strlen((const char *)t);
    sx = win[0] + x;
    sy = win[1] + y;
    if (maxy && sy + h > maxy) return;
    for (i = 0; i < len; i++) {
        u8 c = t[i];
        int k = jchar(t + i);
        if (k >= 0) {
            put_glyph(f, sx, sy, jglyph(f, k), jw(f) + 1, color, alpha, shadow);
            sx += jw(f);
            i++;
            continue;
        }
        if (is_lead(c) && t[i + 1] == 0) break;
        if (!valid(f, c)) continue;
        switch (c) {
        case 9:
            memset(d, 0, sizeof d); strncpy(d, (const char *)t + i + 1, 3);
            margin = atoi(d);
            sx = margin + win[0] + x;
            i += 3;
            break;
        case 10:
            y += h - 3;
            sx = win[0] + margin + x;
            sy = win[1] + y;
            if (maxy && sy + h - 3 > maxy) return;
            break;
        case 12:
            memset(d, 0, sizeof d); strncpy(d, (const char *)t + i + 1, 5);
            color = atoi(d);
            i += 5;
            break;
        case 13:
            memset(d, 0, sizeof d); strncpy(d, (const char *)t + i + 1, 3);
            i += 3;
            /* 元の関数は最後の数字から幅を測る（そのまま合わせる） */
            sx = win[4] - J_GetLineWidth(f, t + i) - atoi(d);
            sy = win[1] + y;
            if (maxy && sy + h - 3 > maxy) return;
            break;
        default:
            if (c == '"' && t[i + 1] == '"') { i++; c = t[i]; }
            if (i > 0) sx += F_L(f, c);
            put_glyph(f, sx, sy, F_PX(f, c), F_W(f, c), color, alpha, shadow);
            sx += F_W(f, c) + F_R(f, c);
            break;
        }
    }
}

void __fastcall J_DrawText(const int *win, const u8 *f, int x, int y, int color, const u8 *str,
                           int alpha, int maxy, int shadow)
{
    const u8 *t;
    color &= 0xffff;
    shadow &= 0xffff;
    if (!str || !strcmp((const char *)str, "null")) return;
    t = maxy ? str : (const u8 *)J_FitText(str, f, win, x, 0);
    if (!t) return;
    draw_core(win, f, x, y, color, t, alpha, maxy, shadow);
}

static u8 g_rect_buf[0x1000];

int __fastcall J_DrawTextInRect(const int *win, const u8 *f, int x, int y, int color, const u8 *str,
                                int rect_w, int reverse)
{
    int lw, len, i, w, cut;
    color &= 0xffff;
    if (!str) return 0;
    lw = J_GetLineWidth(f, str);
    if (lw < rect_w) {
        J_DrawText(win, f, x, y, color, str, 0, 0, 0);
        return lw;
    }
    len = (int)strlen((const char *)str);
    if (len >= (int)sizeof g_rect_buf) len = sizeof g_rect_buf - 1;
    if (!reverse) {
        /* 頭から、幅に収まるところまで */
        w = 0; cut = 0;
        for (i = 0; i < len; i++) {
            u8 c = str[i];
            int add;
            if (jchar(str + i) >= 0) add = jw(f);
            else if (!valid(f, c) || c == 9 || c == 10 || c == 13) add = 0;
            else if (c == 12) { i += 5; cut = i + 1; continue; }
            else add = (i > 0 ? F_L(f, c) : 0) + F_W(f, c) + F_R(f, c);
            if (w + add >= rect_w) break;
            w += add;
            if (jchar(str + i) >= 0) i++;
            cut = i + 1;
        }
        memcpy(g_rect_buf, str, cut);
        g_rect_buf[cut] = 0;
    } else {
        /* 後ろから（字の境目は頭から数えて決める） */
        int starts[0x1000], ns = 0, total;
        for (i = 0; i < len; i++) {
            starts[ns++] = i;
            if (jchar(str + i) >= 0) i++;
        }
        total = 0; cut = len;
        for (i = ns - 1; i >= 0; i--) {
            int p = starts[i], add;
            u8 c = str[p];
            if (jchar(str + p) >= 0) add = jw(f);
            else if (!valid(f, c) || c < 32) add = 0;
            else add = F_L(f, c) + F_W(f, c) + F_R(f, c);
            if (total + add >= rect_w) break;
            total += add;
            cut = p;
        }
        strcpy((char *)g_rect_buf, (const char *)str + cut);
    }
    lw = J_GetLineWidth(f, g_rect_buf);
    draw_core(win, f, x, y, color, g_rect_buf, 0, 0, 0);
    return lw;
}

void __fastcall J_DrawTextLine(const u8 *f, int unused, int x, int y, const u8 *str, int unused2)
{
    int len, i, color;
    char d[8];
    if (!str) return;
    color = CUR_COLOR;
    len = (int)strlen((const char *)str);
    for (i = 0; i < len; i++) {
        u8 c = str[i];
        int k = jchar(str + i);
        if (k >= 0) {
            R_DrawText(RENDER, 0, x, y, jglyph(f, k), jw(f) + 1, F_H(f), F_PAL(f), color ? color : 0xffff, 0);
            x += jw(f);
            i++;
            continue;
        }
        if (is_lead(c) && str[i + 1] == 0) break;
        if (!valid(f, c)) continue;
        if (c == 9 || c == 13) continue;
        if (c == 10) return;
        if (c == 12) {
            memset(d, 0, sizeof d); strncpy(d, (const char *)str + i + 1, 5);
            color = atoi(d); CUR_COLOR = color;
            i += 5;
            continue;
        }
        if (!F_W(f, c)) continue;
        if (i > 0) x += F_L(f, c);
        R_DrawText(RENDER, 0, x, y, F_PX(f, c), F_W(f, c), F_H(f), F_PAL(f), color ? color : 0xffff, 0);
        x += F_W(f, c) + F_R(f, c);
    }
}

void __fastcall J_DrawTextLineToBuff(const u8 *f, int unused, int unused2, unsigned short *dest,
                                     const u8 *str, int line_w)
{
    int len, i, color;
    char d[8];
    if (!str) return;
    color = CUR_COLOR;
    len = (int)strlen((const char *)str);
    for (i = 0; i < len; i++) {
        u8 c = str[i];
        int k = jchar(str + i);
        if (k >= 0) {
            CharToBuff(dest, jglyph(f, k), jw(f) + 1, F_H(f), F_PAL(f), color ? color : 0xffff, line_w * 2);
            dest += jw(f);
            i++;
            continue;
        }
        if (!valid(f, c)) continue;
        if (c == 9 || c == 13 || c == '_') continue;
        if (c == 10) return;
        if (c == 12) {
            memset(d, 0, sizeof d); strncpy(d, (const char *)str + i + 1, 5);
            color = atoi(d); CUR_COLOR = color;
            i += 5;
            continue;
        }
        if (!F_W(f, c)) continue;
        if (i > 0) dest += F_L(f, c);
        CharToBuff(dest, F_PX(f, c), F_W(f, c), F_H(f), F_PAL(f), color ? color : 0xffff, line_w * 2);
        dest += F_W(f, c) + F_R(f, c);
    }
}

void jp_init(void)
{
    hook_jmp(A->GetLineWidth, J_GetLineWidth);
    hook_jmp(A->CalcTextHeight, J_CalcTextHeight);
    hook_jmp(A->CalcTextHeight2, J_CalcTextHeight2);
    hook_jmp(A->GetPageTop, J_GetPageTop);
    hook_jmp(A->FitText, J_FitText);
    hook_jmp(A->FitTwoFont, J_FitTwoFont);
    hook_jmp(A->DrawTextInRect, J_DrawTextInRect);
    hook_jmp(A->DrawText, J_DrawText);
    hook_jmp(A->DrawTextLineToBuff, J_DrawTextLineToBuff);
    hook_jmp(A->DrawTextLine, J_DrawTextLine);
    jlog("font hooks installed");
}
