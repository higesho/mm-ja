/* MM6 日本語化 DLL: 入口、ddraw の転送、フックの道具、設定、レジストリの手当て */
#include "mm6jp.h"
#include <stdio.h>
#include <stdarg.h>

char g_dir[MAX_PATH];
int g_cfg_windowed = 1, g_cfg_scale = 2, g_cfg_test = 0;
static HMODULE g_real_ddraw;
static FILE *g_log;

void jlog(const char *fmt, ...)
{
    va_list ap;
    if (!g_log) {
        char p[MAX_PATH];
        wsprintfA(p, "%smm6jp.log", g_dir);
        g_log = fopen(p, "w");
        if (!g_log) return;
    }
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

void patch_bytes(u32 addr, const void *src, int n)
{
    DWORD old;
    VirtualProtect((void *)addr, n, PAGE_EXECUTE_READWRITE, &old);
    memcpy((void *)addr, src, n);
    VirtualProtect((void *)addr, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void *)addr, n);
}

void hook_jmp(u32 at, void *fn)
{
    u8 b[5];
    b[0] = 0xE9;
    *(int *)(b + 1) = (int)((u8 *)fn - (u8 *)(at + 5));
    patch_bytes(at, b, 5);
}

/* 関数の頭 nbytes を写し、続きへ飛ぶ小片を作る（頭に相対番地の命令がないこと） */
void *make_trampoline(u32 at, int nbytes)
{
    u8 *t = (u8 *)VirtualAlloc(0, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, (void *)at, nbytes);
    t[nbytes] = 0xE9;
    *(int *)(t + nbytes + 1) = (int)((u8 *)(at + nbytes) - (t + nbytes + 5));
    return t;
}

void *iat_hook(const char *dll, const char *name, void *fn)
{
    u8 *base = (u8 *)GetModuleHandleA(0);
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *d = (IMAGE_IMPORT_DESCRIPTOR *)(base +
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    for (; d->Name; d++) {
        IMAGE_THUNK_DATA *ot, *ft;
        if (lstrcmpiA((char *)(base + d->Name), dll)) continue;
        ot = (IMAGE_THUNK_DATA *)(base + d->OriginalFirstThunk);
        ft = (IMAGE_THUNK_DATA *)(base + d->FirstThunk);
        for (; ot->u1.AddressOfData; ot++, ft++) {
            IMAGE_IMPORT_BY_NAME *ibn;
            void *old;
            if (ot->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            ibn = (IMAGE_IMPORT_BY_NAME *)(base + ot->u1.AddressOfData);
            if (strcmp((char *)ibn->Name, name)) continue;
            old = (void *)ft->u1.Function;
            patch_bytes((u32)&ft->u1.Function, &fn, 4);
            return old;
        }
    }
    jlog("iat_hook: %s!%s が見つからない", dll, name);
    return 0;
}

static u32 crc_tab[256];
u32 crc32_buf(const void *p, int n)
{
    const u8 *s = (const u8 *)p;
    u32 c = 0xFFFFFFFF;
    int i;
    if (!crc_tab[1]) {
        for (i = 0; i < 256; i++) {
            u32 v = i;
            int k;
            for (k = 0; k < 8; k++) v = (v & 1) ? 0xEDB88320 ^ (v >> 1) : v >> 1;
            crc_tab[i] = v;
        }
    }
    while (n--) c = crc_tab[(c ^ *s++) & 0xFF] ^ (c >> 8);
    return ~c;
}

/* ---- レジストリ: HKLM を書き込みで開けないときは読み取りで開き直す ---- */
typedef LONG (WINAPI *RegOpenKeyExA_t)(HKEY, LPCSTR, DWORD, REGSAM, PHKEY);
typedef LONG (WINAPI *RegCreateKeyExA_t)(HKEY, LPCSTR, DWORD, LPSTR, DWORD, REGSAM, LPSECURITY_ATTRIBUTES, PHKEY, LPDWORD);
static RegOpenKeyExA_t real_RegOpenKeyExA;
static RegCreateKeyExA_t real_RegCreateKeyExA;

/* キー名に 0x80 以上の字（® など）があれば cp1252 として読む（日本語の Windows では cp932 と取り違える） */
static int to_wide1252(LPCSTR s, WCHAR *w, int n)
{
    const u8 *p = (const u8 *)s;
    if (!s) return 0;
    for (; *p; p++)
        if (*p >= 0x80) return MultiByteToWideChar(1252, 0, s, -1, w, n) > 0;
    return 0;
}

static LONG WINAPI my_RegOpenKeyExA(HKEY k, LPCSTR sub, DWORD opt, REGSAM sam, PHKEY out)
{
    WCHAR w[512];
    int wide = to_wide1252(sub, w, 512);
    LONG r = wide ? RegOpenKeyExW(k, w, opt, sam, out) : real_RegOpenKeyExA(k, sub, opt, sam, out);
    if (r == ERROR_ACCESS_DENIED && (sam & (KEY_SET_VALUE | KEY_CREATE_SUB_KEY)))
        r = wide ? RegOpenKeyExW(k, w, opt, KEY_READ, out) : real_RegOpenKeyExA(k, sub, opt, KEY_READ, out);
    if (g_cfg_test) jlog("RegOpenKeyExA %p %s %x -> %d", k, sub ? sub : "", sam, r);
    return r;
}

static LONG WINAPI my_RegCreateKeyExA(HKEY k, LPCSTR sub, DWORD res, LPSTR cls, DWORD opt, REGSAM sam,
                                      LPSECURITY_ATTRIBUTES sa, PHKEY out, LPDWORD disp)
{
    WCHAR w[512];
    int wide = to_wide1252(sub, w, 512);
    LONG r = wide ? RegCreateKeyExW(k, w, res, 0, opt, sam, sa, out, disp)
                  : real_RegCreateKeyExA(k, sub, res, cls, opt, sam, sa, out, disp);
    if (r == ERROR_ACCESS_DENIED) {
        r = wide ? RegOpenKeyExW(k, w, 0, KEY_READ, out) : real_RegOpenKeyExA(k, sub, 0, KEY_READ, out);
        if (r == ERROR_SUCCESS && disp) *disp = REG_OPENED_EXISTING_KEY;
    }
    if (g_cfg_test) jlog("RegCreateKeyExA %p %s %x -> %d", k, sub ? sub : "", sam, r);
    return r;
}

/* ---- ddraw.dll の転送 ---- */
static FARPROC real_proc(const char *name)
{
    if (!g_real_ddraw) {
        char p[MAX_PATH];
        GetSystemDirectoryA(p, MAX_PATH);
        lstrcatA(p, "\\ddraw.dll");
        g_real_ddraw = LoadLibraryA(p);
    }
    return g_real_ddraw ? GetProcAddress(g_real_ddraw, name) : 0;
}

HRESULT WINAPI real_DirectDrawCreate(void *guid, void **dd, void *outer)
{
    typedef HRESULT (WINAPI *f_t)(void *, void **, void *);
    f_t f = (f_t)real_proc("DirectDrawCreate");
    return f ? f(guid, dd, outer) : E_FAIL;
}

HRESULT WINAPI ex_DirectDrawCreate(void *guid, void **dd, void *outer)
{
    return my_DirectDrawCreate(guid, dd, outer);
}

HRESULT WINAPI ex_DirectDrawCreateEx(void *guid, void **dd, void *iid, void *outer)
{
    typedef HRESULT (WINAPI *f_t)(void *, void **, void *, void *);
    f_t f = (f_t)real_proc("DirectDrawCreateEx");
    return f ? f(guid, dd, iid, outer) : E_FAIL;
}

HRESULT WINAPI ex_DirectDrawEnumerateA(void *cb, void *ctx)
{
    typedef HRESULT (WINAPI *f_t)(void *, void *);
    f_t f = (f_t)real_proc("DirectDrawEnumerateA");
    return f ? f(cb, ctx) : E_FAIL;
}

HRESULT WINAPI ex_DirectDrawEnumerateExA(void *cb, void *ctx, DWORD fl)
{
    typedef HRESULT (WINAPI *f_t)(void *, void *, DWORD);
    f_t f = (f_t)real_proc("DirectDrawEnumerateExA");
    return f ? f(cb, ctx, fl) : E_FAIL;
}

HRESULT WINAPI ex_DirectDrawCreateClipper(DWORD fl, void **c, void *outer)
{
    typedef HRESULT (WINAPI *f_t)(DWORD, void **, void *);
    f_t f = (f_t)real_proc("DirectDrawCreateClipper");
    return f ? f(fl, c, outer) : E_FAIL;
}

/* ---- 設定 ---- */
static void load_config(void)
{
    char ini[MAX_PATH];
    wsprintfA(ini, "%smm6jp.ini", g_dir);
    g_cfg_windowed = GetPrivateProfileIntA("Display", "Windowed", 1, ini);
    g_cfg_scale = GetPrivateProfileIntA("Display", "Scale", 2, ini);
    if (g_cfg_scale < 1) g_cfg_scale = 1;
    if (g_cfg_scale > 4) g_cfg_scale = 4;
    g_cfg_test = GetPrivateProfileIntA("Debug", "Test", 0, ini);
}

static int check_version(void)
{
    static const u8 w[] = { 0x83, 0xEC, 0x08, 0x56, 0x8B, 0xF2 };
    static const u8 l[] = { 0x6A, 0xFF, 0x68, 0x08, 0x8B, 0x4B, 0x00 };
    __try {
        return !memcmp((void *)A_GetLineWidth, w, sizeof w) && !memcmp((void *)A_LodLoadFile, l, sizeof l);
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

static void init(void)
{
    char p[MAX_PATH], *s;
    GetModuleFileNameA(0, g_dir, MAX_PATH);
    s = strrchr(g_dir, '\\');
    if (s) s[1] = 0;
    load_config();

    real_RegOpenKeyExA = (RegOpenKeyExA_t)iat_hook("ADVAPI32.dll", "RegOpenKeyExA", my_RegOpenKeyExA);
    real_RegCreateKeyExA = (RegCreateKeyExA_t)iat_hook("ADVAPI32.dll", "RegCreateKeyExA", my_RegCreateKeyExA);
    if (!real_RegOpenKeyExA) real_RegOpenKeyExA = RegOpenKeyExA;
    if (!real_RegCreateKeyExA) real_RegCreateKeyExA = RegCreateKeyExA;

    if (!check_version()) {
        MessageBoxA(0, "MM6.exe の版が違うため、日本語化を行いません。\n(GOG 版 1.2 が必要です)",
                    "MM6 日本語化", MB_OK | MB_ICONWARNING);
        return;
    }
    wsprintfA(p, "%smm6jp_font.bin", g_dir);
    if (!jpfont_load(p)) jlog("フォントが読めない: %s", p);
    wsprintfA(p, "%smm6jp_text.bin", g_dir);
    if (!lodtext_load(p)) jlog("訳が読めない: %s", p);
    text_install();
    misc_install();
    lodtext_install();
    if (g_cfg_windowed) ddwin_install();
    if (g_cfg_test) test_install();
}

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        /* 自分が MM6.exe に読まれたときだけ働く */
        if (GetModuleHandleA(0) == (HMODULE)0x400000) init();
    }
    return TRUE;
}
