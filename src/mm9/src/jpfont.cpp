#define _CRT_SECURE_NO_WARNINGS
// cshell.dll のビットマップフォント部品に日本語の字を足す。
//
// 符号（自前の2バイト符号）:
//   1バイト目 0x80〜0xBF、2バイト目 0xC0〜0xFF。字の番号 = (1バイト目-0x80)*64 + (2バイト目-0xC0)
//   幅の表で 1バイト目 = 日本語の字の幅、2バイト目 = 0 にしておけば、元の幅計算・折り返しがそのまま正しく働く
//   （はみ出しは必ず 1バイト目で起き、そこで行が切れる）。描画だけを差し替える。
//
// 字の表（アトラス）: data\art\fonts\jp\<名>.pcx。64 列 × 行、1 マス = 幅 W × フォントの行の高さ。
// 設定: data\art\fonts\jp\jpfont.txt の各行「<フォントの128の名> <W> <アトラスの名>」
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "mm9jp.h"

extern HMODULE g_cshell;
void patch_ptr(void** where, void* val);
const char* jp_gamedir();

static DWORD g_delta;  // cshell の実際の基底 - 0x10000000
#define CS(a) ((DWORD)(a) + g_delta)

// cshell 内のアドレス（基底 0x10000000 のとき）
static const DWORD VT_FONT = 0x100c88b8;     // CLTGUIFont 系（ビットマップ）
static const DWORD VT_FONT_MM = 0x100c9720;  // fontman.cpp の派生クラス
static const DWORD FN_LOADSURF = 0x100a3f00; // cdecl(name, flag, color, float)
static const DWORD FN_GETCOLOR = 0x100a1a70; // thiscall(idx) ret 4
static const DWORD OBJ_COLORS = 0x100df8a8;

// フォント部品の中身
#define F_W(f, c) (*(WORD*)((BYTE*)(f) + 4 + (c) * 4))
#define F_H(f, c) (*(WORD*)((BYTE*)(f) + 6 + (c) * 4))
#define F_SRCX(f, c) (*(int*)((BYTE*)(f) + 0x464 + (c) * 4))
#define F_LINEH(f) (*(int*)((BYTE*)(f) + 0x408))
#define F_RENDER(f) (*(void**)((BYTE*)(f) + 0x440))
#define F_SURF128(f) (*(void**)((BYTE*)(f) + 0x454))
#define F_SURF256(f) (*(void**)((BYTE*)(f) + 0x458))
#define F_NAME(f) ((char*)(f) + 0x868)

struct JpFontCfg {
    char key[64];    // 例 MAINTEXTE128
    int w;           // 日本語の字の幅（送り）
    char atlas[64];  // 例 MainTextE.pcx
};
static JpFontCfg g_cfg[64];
static int g_ncfg;

struct FontState {
    void* font;
    int cfg;          // -1 = 日本語なし
    void* atlas;      // 読み込んだ面（遅延）
    bool tried;
};
static FontState g_fs[128];
static int g_nfs;

static void load_cfg()
{
    char path[MAX_PATH];
    sprintf(path, "%sdata\\art\\fonts\\jp\\jpfont.txt", jp_gamedir());
    FILE* f = fopen(path, "r");
    if (!f) { jp_log("no %s", path); return; }
    char line[256];
    while (fgets(line, sizeof line, f) && g_ncfg < 64) {
        JpFontCfg c;
        if (line[0] == '#' || line[0] == ';') continue;
        if (sscanf(line, "%63s %d %63s", c.key, &c.w, c.atlas) == 3) {
            _strupr(c.key);
            g_cfg[g_ncfg++] = c;
        }
    }
    fclose(f);
    jp_log("jpfont.txt: %d fonts", g_ncfg);
}

static int find_cfg(const char* fontname)
{
    // "fonts\MainTextE128.fnt" -> "MAINTEXTE128"
    char b[MAX_PATH];
    const char* p = strrchr(fontname, '\\');
    lstrcpynA(b, p ? p + 1 : fontname, sizeof b);
    char* dot = strrchr(b, '.');
    if (dot) *dot = 0;
    _strupr(b);
    for (int i = 0; i < g_ncfg; i++)
        if (!strcmp(g_cfg[i].key, b)) return i;
    return -1;
}

static FontState* state_of(void* font, bool create)
{
    for (int i = 0; i < g_nfs; i++)
        if (g_fs[i].font == font) return &g_fs[i];
    if (!create || g_nfs >= 128) return NULL;
    FontState* s = &g_fs[g_nfs++];
    s->font = font;
    s->cfg = find_cfg(F_NAME(font));
    s->atlas = NULL;
    s->tried = false;
    return s;
}

typedef int(__thiscall* PFN_Kern)(void* self, unsigned char c, unsigned char prev);
static int call_kern(void* font, unsigned char c, unsigned char prev)
{
    void** vt = *(void***)font;
    return ((PFN_Kern)vt[0x64 / 4])(font, c, prev);
}

typedef int(__thiscall* PFN_Space)(void* self, int x, int y);
static int call_space(void* font, int x, int y)
{
    void** vt = *(void***)font;
    return ((PFN_Space)vt[0x54 / 4])(font, x, y);
}

typedef bool(__thiscall* PFN_Blit)(void* render, void* dest, int x, int y, void* src, int* rect);
static bool call_blit(void* font, void* dest, int x, int y, void* src, int* rect)
{
    void* r = F_RENDER(font);
    void** vt = *(void***)r;
    return ((PFN_Blit)vt[0xc / 4])(r, dest, x, y, src, rect);
}

// 幅の表に日本語の字を書き込む
static void fix_tables(void* font)
{
    FontState* s = state_of(font, true);
    if (!s) return;
    s->cfg = find_cfg(F_NAME(font));
    jp_log("font %p %s cfg=%d lineh=%d", font, F_NAME(font), s->cfg, F_LINEH(font));
    if (s->cfg < 0) return;
    int w = g_cfg[s->cfg].w;
    int h = F_LINEH(font);
    for (int c = 0x80; c < 0x100; c++) {
        int kern = call_kern(font, (unsigned char)c, 0);
        if (c < 0xC0) F_W(font, c) = (WORD)(w + kern);
        else F_W(font, c) = 0;
        F_H(font, c) = (WORD)h;
        F_SRCX(font, c) = 0;
    }
}

static void* load_atlas(FontState* s)
{
    if (s->tried) return s->atlas;
    s->tried = true;
    char name[128];
    sprintf(name, "fonts\\jp\\%s", g_cfg[s->cfg].atlas);
    typedef DWORD(__thiscall * PFN_GetColor)(void* self, int idx);
    typedef void*(__cdecl * PFN_LoadSurf)(const char*, int, DWORD, float);
    DWORD color = ((PFN_GetColor)CS(FN_GETCOLOR))((void*)CS(OBJ_COLORS), 0x14);
    s->atlas = ((PFN_LoadSurf)CS(FN_LOADSURF))(name, 0, color, 1.0f);
    jp_log("atlas %s color=%08lx -> %p", name, color, s->atlas);
    return s->atlas;
}

// 元の関数
typedef bool(__thiscall* PFN_Init)(void* self, void* s128, DWORD a2, DWORD a3, void* s256);
typedef bool(__thiscall* PFN_LoadCache)(void* self);
typedef bool(__thiscall* PFN_DrawLine)(void* self, void* dest, const unsigned char* str, int len, int* rect);
static PFN_Init g_origInit[2];
static PFN_LoadCache g_origCache[2];
static PFN_DrawLine g_origDraw[2];

static int which(void* font)
{
    return (*(DWORD*)font == CS(VT_FONT_MM)) ? 1 : 0;
}

static bool __fastcall hook_Init(void* self, void*, void* s128, DWORD a2, DWORD a3, void* s256)
{
    bool r = g_origInit[which(self)](self, s128, a2, a3, s256);
    fix_tables(self);
    return r;
}

static bool __fastcall hook_LoadCache(void* self, void*)
{
    bool r = g_origCache[which(self)](self);
    if (r) fix_tables(self);
    return r;
}

const char* jpdict_xl(const char* s, int* len);
void run_pending_console();
void jpdict_load();

// 文字列を受け取る入口（幅・折り返し・描画）。3 つの vtable（0=元、1=派生、2=GDI）× 枠
static const DWORD VTS[3] = { VT_FONT, VT_FONT_MM, 0x100c8874 };
static void* g_slot[3][0x40];
static int vt_index(void* self)
{
    DWORD v = *(DWORD*)self;
    for (int i = 0; i < 3; i++) if (v == CS(VTS[i])) return i;
    return 0;
}
#define ORIG(self, off) g_slot[vt_index(self)][(off) / 4]

typedef int(__thiscall* PFN_S1)(void*, const char*, void*, int);
typedef int(__thiscall* PFN_S2)(void*, const char*, int);
typedef int(__thiscall* PFN_D4)(void*, void*, const char*, int, void*);
typedef int(__thiscall* PFN_D5)(void*, void*, const char*, int, void*, int);

static int __fastcall h04(void* self, void*, const char* s, void* rect, int flag)
{
    s = jpdict_xl(s, NULL);
    return ((PFN_S1)ORIG(self, 0x04))(self, s, rect, flag);
}
static int __fastcall h08(void* self, void*, const char* s, int len)
{
    s = jpdict_xl(s, &len);
    return ((PFN_S2)ORIG(self, 0x08))(self, s, len);
}
static int __fastcall h0c(void* self, void*, const char* s, int len)
{
    s = jpdict_xl(s, &len);
    return ((PFN_S2)ORIG(self, 0x0c))(self, s, len);
}
static int __fastcall h20(void* self, void*, void* dest, const char* s, int len, void* rect, int j)
{
    s = jpdict_xl(s, &len);
    return ((PFN_D5)ORIG(self, 0x20))(self, dest, s, len, rect, j);
}
static int __fastcall h28(void* self, void*, void* dest, const char* s, int len, void* rect, int out)
{
    s = jpdict_xl(s, &len);
    return ((PFN_D5)ORIG(self, 0x28))(self, dest, s, len, rect, out);
}
static int __fastcall h2c(void* self, void*, void* dest, const char* s, int len, void* rect)
{
    s = jpdict_xl(s, &len);
    return ((PFN_D4)ORIG(self, 0x2c))(self, dest, s, len, rect);
}
static int __fastcall h30(void* self, void*, void* dest, const char* s, int len, void* rect)
{
    s = jpdict_xl(s, &len);
    return ((PFN_D4)ORIG(self, 0x30))(self, dest, s, len, rect);
}

static void hook_entries(int i)
{
    void** v = (void**)CS(VTS[i]);
    struct { int off; void* fn; } hs[] = { { 0x04, (void*)h04 }, { 0x08, (void*)h08 }, { 0x0c, (void*)h0c },
        { 0x20, (void*)h20 }, { 0x28, (void*)h28 }, { 0x2c, (void*)h2c }, { 0x30, (void*)h30 } };
    for (auto& h : hs) {
        g_slot[i][h.off / 4] = v[h.off / 4];
        patch_ptr(&v[h.off / 4], h.fn);
    }
}

// 禁則処理: 折り返し位置の関数（0x1008a4e0、呼び出し元は 0x1008ae51 の1か所）を包む
static bool g_noStart[4096], g_noEnd[4096];
static DWORD g_origWrapPos;
static void load_kinsoku()
{
    char path[MAX_PATH];
    sprintf(path, "%sdata\\jp\\kinsoku.txt", jp_gamedir());
    FILE* f = fopen(path, "r");
    if (!f) return;
    char kind[16];
    unsigned code;
    while (fscanf(f, "%15s %x", kind, &code) == 2) {
        unsigned idx = ((code >> 8) - 0x80) * 64 + ((code & 0xFF) - 0xC0);
        if (idx < 4096) {
            if (kind[0] == 'S') g_noStart[idx] = true;
            else g_noEnd[idx] = true;
        }
    }
    fclose(f);
}
static int jp_index_at(const unsigned char* s, int i, int len)
{
    if (i < 0 || i + 1 >= len + 1) return -1;
    if (s[i] >= 0x80 && s[i] < 0xC0 && i + 1 < len && s[i + 1] >= 0xC0)
        return (s[i] - 0x80) * 64 + (s[i + 1] - 0xC0);
    return -1;
}
typedef int(__thiscall* PFN_WrapPos)(void*, const unsigned char*, int, int, int, int, int, int);
static int __fastcall hook_WrapPos(void* self, void*, const unsigned char* str, int len, int r0, int r1, int r2, int r3, int flag)
{
    int n = ((PFN_WrapPos)g_origWrapPos)(self, str, len, r0, r1, r2, r3, flag);
    static int logn;
    if (logn < 60) { logn++; jp_log("wrap len=%d rect=%d,%d,%d,%d flag=%d -> %d", len, r0, r1, r2, r3, flag, n); }
    if (n <= 0 || n >= len) return n;
    int orig = n;
    for (int k = 0; k < 3 && n >= 4; k++) {
        int next = jp_index_at(str, n, len);
        int prev = jp_index_at(str, n - 2, len);
        if (prev < 0) break;
        bool bad = (next >= 0 && g_noStart[next]) || g_noEnd[prev];
        if (!bad) break;
        n -= 2;
    }
    // 1行に1字しか残らないほど戻すなら、元のまま
    if (n < 4) n = orig;
    return n;
}
static void hook_wrap()
{
    BYTE* site = (BYTE*)CS(0x1008ae51);
    if (site[0] != 0xE8) return;
    DWORD target = (DWORD)(site + 5) + *(DWORD*)(site + 1);
    if (target != CS(0x1008a4e0)) return;
    g_origWrapPos = target;
    DWORD rel = (DWORD)hook_WrapPos - (DWORD)(site + 5);
    DWORD old;
    VirtualProtect(site + 1, 4, PAGE_EXECUTE_READWRITE, &old);
    *(DWORD*)(site + 1) = rel;
    VirtualProtect(site + 1, 4, old, &old);
    FlushInstructionCache(GetCurrentProcess(), site, 5);
    jp_log("wrap hook installed");
}

// 描いた文字列の記録（試験用: game\mm9jp_seen.txt があるとき、初めての文字列を追記）
static FILE* g_seen;
static bool g_seenInit;
static unsigned g_seenHash[65536];
static void note_seen(const char* tag, void* font, const unsigned char* str, int len)
{
    if (!g_seenInit) {
        g_seenInit = true;
        char path[MAX_PATH];
        sprintf(path, "%smm9jp_seen.txt", jp_gamedir());
        if (GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES) g_seen = fopen(path, "ab");
    }
    if (!g_seen || len <= 0) return;
    unsigned h = 2166136261u;
    for (int i = 0; i < len; i++) h = (h ^ str[i]) * 16777619u;
    unsigned slot = h & 0xFFFF;
    for (int k = 0; k < 8; k++) {
        unsigned s = (slot + k) & 0xFFFF;
        if (g_seenHash[s] == h) return;
        if (!g_seenHash[s]) { g_seenHash[s] = h; break; }
    }
    const char* fname = font ? F_NAME(font) : "";
    fprintf(g_seen, "%s\t%s\t", tag, fname);
    fwrite(str, 1, len, g_seen);
    fputs("\r\n", g_seen);
    fflush(g_seen);
}

// GDI 経路（エンジンの TrueType）の DrawLine（vtable 0x100c8874 の 0x24）
static PFN_DrawLine g_origGdiDraw;
static bool __fastcall hook_GdiDraw(void* self, void*, void* dest, const unsigned char* str, int len, int* rect)
{
    str = (const unsigned char*)jpdict_xl((const char*)str, &len);
    note_seen("GDI", NULL, str, len);
    return g_origGdiDraw(self, dest, str, len, rect);
}

// 1行を描く（元の DrawLine と同じ流れに、日本語の字を足したもの）
static bool __fastcall hook_DrawLine(void* self, void*, void* dest, const unsigned char* str, int len, int* rect)
{
    str = (const unsigned char*)jpdict_xl((const char*)str, &len);
    note_seen("BMP", self, str, len);
    FontState* s = state_of(self, false);
    bool jp = s && s->cfg >= 0;
    if (!jp) {
        // 日本語の字が無ければ元のまま
        return g_origDraw[which(self)](self, dest, str, len, rect);
    }
    int x = rect[0], y = rect[1];
    int right = rect[0] + rect[2];
    int jw = g_cfg[s->cfg].w;
    int lh = F_LINEH(self);
    for (int i = 0; i < len; i++) {
        unsigned char c = str[i];
        if (c == '\n' || c == '\r') continue;
        if (c == ' ') {
            x += call_space(self, x, y);
            continue;
        }
        if (c >= 0x80 && c < 0xC0 && i + 1 < len && str[i + 1] >= 0xC0) {
            unsigned char t = str[i + 1];
            if (x + jw > right) return true;
            void* atlas = load_atlas(s);
            if (atlas) {
                int src[4] = { (t - 0xC0) * jw, (c - 0x80) * lh, jw, lh };
                call_blit(self, dest, x, y, atlas, src);
            }
            x += jw;
            i++;
            continue;
        }
        if (c >= 0x80) continue;  // 対になっていない字は飛ばす
        int sx = F_SRCX(self, c);
        if (sx == -1) return false;
        int w = F_W(self, c), h = F_H(self, c);
        int kern = call_kern(self, c, i ? str[i - 1] : 0);
        if (x + w > right + kern) return true;
        int src[4] = { sx, 0, w, h };
        if (which(self) == 1) {
            // 派生クラスは字間を先に引いて描く
            x -= kern;
            if (!call_blit(self, dest, x, y, F_SURF128(self), src)) return false;
            x += w;
        } else {
            if (!call_blit(self, dest, x, y, F_SURF128(self), src)) return false;
            x += w - kern;
        }
    }
    return true;
}

static void hook_vt(DWORD vt, int idx)
{
    void** v = (void**)CS(vt);
    g_origInit[idx] = (PFN_Init)v[0x44 / 4];
    g_origCache[idx] = (PFN_LoadCache)v[0x4c / 4];
    g_origDraw[idx] = (PFN_DrawLine)v[0x24 / 4];
    patch_ptr(&v[0x44 / 4], (void*)hook_Init);
    patch_ptr(&v[0x4c / 4], (void*)hook_LoadCache);
    patch_ptr(&v[0x24 / 4], (void*)hook_DrawLine);
}

void jpfont_install(HMODULE cs)
{
    g_delta = (DWORD)cs - 0x10000000;
    // 念のため: 中身が想定どおりか（vtable の DrawLine の値で確かめる）
    void** v1 = (void**)CS(VT_FONT);
    void** v2 = (void**)CS(VT_FONT_MM);
    if (v1[0x24 / 4] != (void*)CS(0x1008b780) || v2[0x24 / 4] != (void*)CS(0x100a16d0)) {
        jp_log("cshell.dll の版が違う（vtable 不一致）。日本語フォントは使わない");
        return;
    }
    load_cfg();
    jpdict_load();
    load_kinsoku();
    if (!GetEnvironmentVariableA("MM9JP_NOWRAP", NULL, 0)) hook_wrap();
    for (int i = 0; i < 3; i++) hook_entries(i);
    hook_vt(VT_FONT, 0);
    hook_vt(VT_FONT_MM, 1);
    {
        void** v = (void**)CS(0x100c8874);
        g_origGdiDraw = (PFN_DrawLine)v[0x24 / 4];
        patch_ptr(&v[0x24 / 4], (void*)hook_GdiDraw);
    }
    jp_log("font hooks installed (delta %08lx)", g_delta);
}
