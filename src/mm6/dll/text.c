/* MM6 の文字処理（幅・高さ・折り返し・描画）を EUC-JP 対応に置き換える。
 * 英字だけの文では元の関数と同じ結果になるよう、元の動き（制御文字の扱い、
 * 前後の空き A/C の足し方）をそのまま写している。
 *
 * 制御文字: 0x09 + 3桁 = その行の頭から N 画素の位置へ（以降の行もそこから）
 *           0x0A       = 改行
 *           0x0C + 5桁 = 色（0 なら既定の色）
 *           0x0D + 3桁 = 右寄せ（右端から N 画素）。これを含む文は折り返さない
 */
#include "mm6jp.h"
#include <stdlib.h>

#define IS_JP(p) ((p)[0] >= 0xA1 && (p)[0] <= 0xFE && (p)[1] >= 0xA1 && (p)[1] <= 0xFE)
#define JPCODE(p) (((p)[0] << 8) | (p)[1])

static int valid(Font *f, u8 c)
{
    return (c >= f->first && c <= f->last) || c == 0x0C || c == 0x0D || c == 9 || c == 0x0A;
}

static int num(const u8 *p, int n)
{
    char b[8];
    int i;
    for (i = 0; i < n && p[i]; i++) b[i] = p[i];
    b[i] = 0;
    return atoi(b);
}

/* ---- 幅（改行・字下げ・右寄せの所で止まる） ---- */
static int __fastcall my_GetLineWidth(Font *f, const char *str)
{
    const u8 *s = (const u8 *)str;
    int len, i, w = 0;
    if (!s) return 0;
    len = (int)strlen(str);
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        if (IS_JP(s + i)) {
            w += jp_advance(f);
            i++;
            continue;
        }
        if (!valid(f, c)) continue;
        if (c == 9 || c == 0x0A || c == 0x0D) return w;
        if (c == 0x0C) { i += 5; continue; }
        if (i > 0) w += f->abc[c].A;
        w += f->abc[c].B;
        if (i < len) w += f->abc[c].C;
    }
    return w;
}

/* ---- 折り返し ---- */
#define WRAPMAX 0x8000
static u8 g_wrap[WRAPMAX + 16];
static u8 g_tmp[WRAPMAX + 16];

static int in_list(const u16 *t, int n, int code)
{
    int i;
    for (i = 0; i < n; i++) if (t[i] == code) return 1;
    return 0;
}

/* 行頭に来てはいけない字（この字の前では切らない）: 、。，．・：；？！゛゜ー―‐…‥’”）〕］｝〉》」』】々ぁぃぅぇぉっゃゅょゎァィゥェォッャュョヮヵヶ〜 */
static const u16 NB_BEFORE[] = { 0xA1A2, 0xA1A3, 0xA1A4, 0xA1A5, 0xA1A6, 0xA1A7, 0xA1A8, 0xA1A9, 0xA1AA, 0xA1AB, 0xA1AC, 0xA1BC, 0xA1BD, 0xA1BE, 0xA1C4, 0xA1C5, 0xA1C7, 0xA1C9, 0xA1CB, 0xA1CD, 0xA1CF, 0xA1D1, 0xA1D3, 0xA1D5, 0xA1D7, 0xA1D9, 0xA1DB, 0xA1B9, 0xA4A1, 0xA4A3, 0xA4A5, 0xA4A7, 0xA4A9, 0xA4C3, 0xA4E3, 0xA4E5, 0xA4E7, 0xA4EE, 0xA5A1, 0xA5A3, 0xA5A5, 0xA5A7, 0xA5A9, 0xA5C3, 0xA5E3, 0xA5E5, 0xA5E7, 0xA5EE, 0xA5F5, 0xA5F6, 0xA1C1 };
static int no_break_before(int code) { return in_list(NB_BEFORE, sizeof NB_BEFORE / 2, code); }

/* 行末に来てはいけない字（この字の後では切らない）: ‘“（〔［｛〈《「『【 */
static const u16 NB_AFTER[] = { 0xA1C6, 0xA1C8, 0xA1CA, 0xA1CC, 0xA1CE, 0xA1D0, 0xA1D2, 0xA1D4, 0xA1D6, 0xA1D8, 0xA1DA };
static int no_break_after(int code) { return in_list(NB_AFTER, sizeof NB_AFTER / 2, code); }

static int ascii_no_break_before(u8 c)
{
    return c == '.' || c == ',' || c == '!' || c == '?' || c == ':' || c == ';' || c == ')' || c == ']' ||
           c == '%' || c == '\'' || c == '"';
}

/* 1 字の幅（折り返しの見積もり用。A は first でないときだけ） */
static int char_w(Font *f, const u8 *p, int first)
{
    if (IS_JP(p)) return jp_advance(f);
    if (!valid(f, p[0]) || p[0] < 0x20) return 0;
    return (first ? 0 : f->abc[p[0]].A) + f->abc[p[0]].B + f->abc[p[0]].C;
}

/* out[from..to) の幅（行頭から測る） */
static int span_w(Font *f, const u8 *p, int n)
{
    int i, w = 0, first = 1;
    for (i = 0; i < n; i++) {
        if (p[i] == 0x0C) { i += 5; continue; }
        if (p[i] == 9) { i += 3; continue; }
        if (p[i] < 0x20 && !IS_JP(p + i)) continue;
        w += char_w(f, p + i, first);
        first = 0;
        if (IS_JP(p + i)) i++;
    }
    return w;
}

static char *__fastcall my_WordWrap(const char *str, Font *f, Dlg *d, int x)
{
    const u8 *s;
    u8 *o = g_wrap;
    int len, i, n = 0, w, reset = x, linestart = 0;
    int brk = -1, brk_space = 0;      /* 切ってよい所（o の位置）と、それが空白か */
    int prev_jp = 0, prev_code = 0;
    if (!str) return (char *)str;
    len = (int)strlen(str);
    if (len > WRAPMAX - 1024) len = WRAPMAX - 1024;
    memcpy(g_tmp, str, len);
    g_tmp[len] = 0;
    s = g_tmp;
    w = x;
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        int cw, jp = IS_JP(s + i), code = jp ? JPCODE(s + i) : 0;
        if (!jp && c == 0x0D && valid(f, c)) return (char *)str;   /* 右寄せのある文は折り返さない */
        if (!jp && c == 9) {
            reset = w = x + num(s + i + 1, 3);
            memcpy(o + n, s + i, 4); n += 4; i += 3;
            prev_jp = 0;
            continue;
        }
        if (!jp && c == 0x0A) {
            o[n++] = c;
            w = reset;
            linestart = n; brk = -1;
            prev_jp = 0;
            continue;
        }
        if (!jp && c == 0x0C) {
            memcpy(o + n, s + i, 6); n += 6; i += 5;
            continue;
        }
        if (!jp && c == ' ') {
            brk = n; brk_space = 1;
            o[n++] = c;
            w += f->abc[' '].B;
            prev_jp = 0;
            continue;
        }
        if (!jp && !valid(f, c)) { o[n++] = c; continue; }

        /* 切ってよい所: 日本語の字の前、日本語の後の英数字の前（禁則を守る） */
        if (n > linestart) {
            if (jp && !no_break_before(code) && !(prev_jp && no_break_after(prev_code))) {
                brk = n; brk_space = 0;
            } else if (!jp && prev_jp && !ascii_no_break_before(c) && !no_break_after(prev_code)) {
                brk = n; brk_space = 0;
            }
        }
        cw = char_w(f, s + i, n == linestart);
        if (w + cw >= d->width && n > linestart) {
            int at;
            if (brk > linestart) {
                at = brk;
            } else {
                at = n;          /* 切れる所がなければ、ここで切る */
                brk_space = 0;
            }
            if (brk_space && at == brk) {
                o[at] = 0x0A;
                linestart = at + 1;
            } else {
                memmove(o + at + 1, o + at, n - at);
                o[at] = 0x0A;
                n++;
                linestart = at + 1;
            }
            brk = -1;
            w = reset + span_w(f, o + linestart, n - linestart);
            cw = char_w(f, s + i, n == linestart);
        }
        o[n++] = c;
        if (jp) { o[n++] = s[i + 1]; i++; }
        w += cw;
        prev_jp = jp;
        prev_code = code;
        if (n > WRAPMAX - 16) break;
    }
    o[n] = 0;
    return (char *)o;
}

/* ---- 高さ ---- */
static int __fastcall my_GetTextHeight(Font *f, const char *str, Dlg *d, int x)
{
    const u8 *p;
    int h;
    if (!str) return 0;
    h = f->height - 3;
    p = (const u8 *)my_WordWrap(str, f, d, x);
    for (; *p; p++) {
        if (IS_JP(p)) { p++; continue; }
        if (!valid(f, *p)) continue;
        if (*p == 0x0A) h += f->height - 3;
        else if (*p == 0x0C) { if (!p[1]) break; p += 5; }
        else if (*p == 9 || *p == 0x0D) { if (!p[1]) break; p += 3; }
    }
    return h;
}

/* ---- 字を置く ---- */
static void blit(u16 *dst, int pitch, const u8 *g, int w, int h, const u16 *pal, int color, int colored)
{
    int x, y;
    for (y = 0; y < h; y++, dst += pitch, g += w)
        for (x = 0; x < w; x++) {
            u8 v = g[x];
            if (!v) continue;
            if (colored) dst[x] = v == 1 ? pal[1] : (u16)color;
            else dst[x] = pal[v];
        }
}

static void put_char(Font *f, u16 *dst, int pitch, const u8 *p, int color, int colored)
{
    if (IS_JP(p)) {
        int w, h;
        const u8 *g = jp_glyph(f, JPCODE(p), &w, &h);
        blit(dst, pitch, g, w, h, f->pal[0], color, colored);
    } else {
        u8 c = p[0];
        blit(dst, pitch, f->data + f->glyphOff[c], f->abc[c].B, f->height, f->pal[0], color, colored);
    }
}

#define SCRBYTES (640 * 480 * 2)

static void __fastcall my_Draw(Dlg *d, Font *f, int x, int y, int color, const char *str)
{
    const u8 *s;
    int len, i, tabN = 0;
    u16 *pos, *line;
    if (!d || !str) return;
    if (!x) x = 12;
    s = (const u8 *)my_WordWrap(str, f, d, x);
    len = (int)strlen((const char *)s);
    line = pos = SCREEN + LINEOFS[d->top + y] + d->left + x;
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        if (IS_JP(s + i)) {
            put_char(f, pos, 640, s + i, color, (color & 0xFFFF) != 0);
            pos += jp_advance(f);
            i++;
            continue;
        }
        if (!valid(f, c)) continue;
        switch (c) {
        case 9:
            tabN = num(s + i + 1, 3);
            pos = line + tabN;
            i += 3;
            break;
        case 0x0A:
            y += f->height - 3;
            line = pos = SCREEN + LINEOFS[d->top + y] + d->left + tabN + x;
            if ((int)(((u8 *)pos - (u8 *)SCREEN) + f->height * 1280) > SCRBYTES) return;
            break;
        case 0x0C:
            color = num(s + i + 1, 5);
            i += 5;
            break;
        case 0x0D: {
            int N = num(s + i + 1, 3);
            int w;
            i += 3;
            w = my_GetLineWidth(f, (const char *)s + i);
            pos = SCREEN + LINEOFS[d->top + y] + d->right - w - N;
            break;
        }
        default:
            if (i > 0) pos += f->abc[c].A;
            put_char(f, pos, 640, s + i, color, (color & 0xFFFF) != 0);
            pos += f->abc[c].B;
            if (i < len) pos += f->abc[c].C;
            break;
        }
    }
}

/* ---- 幅に収まらない所を切って 1 行で描く。測った幅を返す ---- */
static u8 g_lim[4096];

static int __fastcall my_DrawLimited(Dlg *d, Font *f, int x, int y, int color, const char *str, int maxw, int truncStart)
{
    int w, len, i, n, tabN = 0;
    u16 *pos, *line;
    const u8 *s = (const u8 *)str;
    if (!d || !str) return 0;
    w = my_GetLineWidth(f, str);
    if (w < maxw) {
        my_Draw(d, f, x, y, color, str);
        return w;
    }
    len = (int)strlen(str);
    if (len > (int)sizeof g_lim - 1) len = sizeof g_lim - 1;
    if (!truncStart) {
        /* 頭から、幅に収まる所まで */
        int acc = 0, last = 0;
        for (i = 0; i < len;) {
            int step = IS_JP(s + i) ? 2 : (s[i] == 0x0C ? 6 : 1);
            if (!(s[i] == 0x0C)) acc += char_w(f, s + i, i == 0);
            if (acc >= maxw) break;
            i += step;
            last = i;
        }
        memcpy(g_lim, s, last);
        g_lim[last] = 0;
    } else {
        /* 後ろから、幅に収まる所まで（字の切れ目を数えておく） */
        int starts[2048], ns = 0, acc = 0, from = len;
        for (i = 0; i < len && ns < 2048;) {
            starts[ns++] = i;
            i += IS_JP(s + i) ? 2 : 1;
        }
        while (ns > 0) {
            int k = starts[ns - 1];
            acc += char_w(f, s + k, 0);
            if (acc >= maxw) break;
            from = k;
            ns--;
        }
        n = len - from;
        memcpy(g_lim, s + from, n);
        g_lim[n] = 0;
    }
    w = my_GetLineWidth(f, (const char *)g_lim);
    n = (int)strlen((const char *)g_lim);
    line = pos = SCREEN + LINEOFS[d->top + y] + x + d->left;
    for (i = 0; i < n; i++) {
        u8 c = g_lim[i];
        if (IS_JP(g_lim + i)) {
            put_char(f, pos, 640, g_lim + i, color, (color & 0xFFFF) != 0);
            pos += jp_advance(f);
            i++;
            continue;
        }
        if (!valid(f, c)) continue;
        switch (c) {
        case 0x0C:
            color = num(g_lim + i + 1, 5);
            i += 5;
            break;
        case 9:
            tabN = num(g_lim + i + 1, 3);
            pos = line + tabN;
            i += 3;
            break;
        case 0x0D: {
            int N = num(g_lim + i + 1, 3);
            i += 3;
            pos = SCREEN + LINEOFS[y] + d->right - my_GetLineWidth(f, (const char *)g_lim + i) - N;
            break;
        }
        case 0x0A:
            line = pos = line + LINEOFS[f->height - 3];
            y += f->height - 3;
            break;
        default:
            if (i > 0) pos += f->abc[c].A;
            put_char(f, pos, 640, g_lim + i, color, (color & 0xFFFF) != 0);
            pos += f->abc[c].B;
            if (i < n) pos += f->abc[c].C;
            break;
        }
    }
    return w;
}

/* ---- 1 行を任意のバッファへ（中央寄せなどが使う）。色は [0x55DD80] ---- */
static void __fastcall my_DrawLine(Font *f, int unused, u16 *dst, const char *str, int pitch)
{
    const u8 *s = (const u8 *)str;
    int len, i, color;
    if (!s) return;
    color = *(int *)A_TextColor;
    len = (int)strlen(str);
    for (i = 0; i < len; i++) {
        u8 c = s[i];
        if (IS_JP(s + i)) {
            put_char(f, dst, pitch, s + i, color ? color : 0xFFFF, 1);
            dst += jp_advance(f);
            i++;
            continue;
        }
        if (!valid(f, c)) continue;
        if (c == 9 || c == 0x0D) continue;
        if (c == 0x0A) return;
        if (c == 0x0C) {
            color = num(s + i + 1, 5);
            *(int *)A_TextColor = color;
            i += 5;
            continue;
        }
        if (!f->abc[c].B) continue;
        if (i > 0) dst += f->abc[c].A;
        put_char(f, dst, pitch, s + i, color ? color : 0xFFFF, 1);
        dst += f->abc[c].B;
        if (i < len) dst += f->abc[c].C;
    }
}

void text_install(void)
{
    hook_jmp(A_GetLineWidth, my_GetLineWidth);
    hook_jmp(A_GetTextHeight, my_GetTextHeight);
    hook_jmp(A_WordWrap, my_WordWrap);
    hook_jmp(A_DrawLimited, my_DrawLimited);
    hook_jmp(A_Draw, my_Draw);
    hook_jmp(A_DrawLine, my_DrawLine);
}
