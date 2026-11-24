/* MM8 日本語化 DLL（dinput.dll の代理として読み込まれる）
 *
 * - DirectInputCreateA は本物の system32\dinput.dll へ渡す
 * - 読み込まれたときに MM8 本体へ手を入れる（レジストリ・文字描画）
 * - 試験用の部分（記録 mm8jp.log、MM8JP_TEST での操作の受け付け）は、
 *   build.bat test で作る試験版（/DMM8JP_TEST）にだけ入る
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "mm8jp.h"

/* ---- 記録（試験版だけ。配布版では何もしない） ---- */
#ifdef MM8JP_TEST
static FILE *g_log;
void jlog(const char *fmt, ...)
{
    va_list ap;
    if (!g_log) return;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}
#endif

/* ---- 本物の dinput.dll ---- */
typedef HRESULT (WINAPI *PFN_DICreateA)(HINSTANCE, DWORD, void **, void *);
static PFN_DICreateA real_DirectInputCreateA;

static void load_real_dinput(void)
{
    char path[MAX_PATH];
    HMODULE h;
    GetSystemDirectoryA(path, MAX_PATH);
    strcat(path, "\\dinput.dll");
    h = LoadLibraryA(path);
    if (h) real_DirectInputCreateA = (PFN_DICreateA)GetProcAddress(h, "DirectInputCreateA");
}

#ifdef MM8JP_TEST
int g_test_mode;
#endif
HRESULT WINAPI DirectInputCreateA(HINSTANCE hinst, DWORD ver, void **out, void *outer)
{
#ifdef MM8JP_TEST
    if (g_test_mode) {
        /* 試験時は DirectInput を使わせない（前面でなくても送ったメッセージで動くように） */
        jlog("test: DirectInputCreateA を断る");
        if (out) *out = NULL;
        return E_FAIL;
    }
#endif
    if (!real_DirectInputCreateA) load_real_dinput();
    if (!real_DirectInputCreateA) return E_FAIL;
    return real_DirectInputCreateA(hinst, ver, out, outer);
}

/* ---- 取り込み表（IAT）の書き換え ---- */
void *patch_iat(const char *dll, const char *func, void *repl)
{
    return patch_iat_mod(GetModuleHandleA(NULL), dll, func, repl);
}

void *patch_iat_mod(HMODULE mod, const char *dll, const char *func, void *repl)
{
    BYTE *base = (BYTE *)mod;
    IMAGE_DOS_HEADER *dos = (IMAGE_DOS_HEADER *)base;
    IMAGE_NT_HEADERS *nt = (IMAGE_NT_HEADERS *)(base + dos->e_lfanew);
    IMAGE_IMPORT_DESCRIPTOR *imp = (IMAGE_IMPORT_DESCRIPTOR *)(base +
        nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
    for (; imp->Name; imp++) {
        IMAGE_THUNK_DATA *oft, *ft;
        if (_stricmp((char *)(base + imp->Name), dll)) continue;
        oft = (IMAGE_THUNK_DATA *)(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
        ft = (IMAGE_THUNK_DATA *)(base + imp->FirstThunk);
        for (; oft->u1.AddressOfData; oft++, ft++) {
            IMAGE_IMPORT_BY_NAME *ibn;
            if (oft->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            ibn = (IMAGE_IMPORT_BY_NAME *)(base + oft->u1.AddressOfData);
            if (!strcmp((char *)ibn->Name, func)) {
                DWORD old;
                void *orig = (void *)ft->u1.Function;
                VirtualProtect(&ft->u1.Function, 4, PAGE_READWRITE, &old);
                ft->u1.Function = (DWORD)repl;
                VirtualProtect(&ft->u1.Function, 4, old, &old);
                return orig;
            }
        }
    }
    return NULL;
}

/* 機械語の頭を jmp に書き換える */
void hook_jmp(DWORD addr, void *fn)
{
    DWORD old;
    BYTE *p = (BYTE *)addr;
    VirtualProtect(p, 5, PAGE_EXECUTE_READWRITE, &old);
    p[0] = 0xE9;
    *(DWORD *)(p + 1) = (DWORD)fn - (addr + 5);
    VirtualProtect(p, 5, old, &old);
    FlushInstructionCache(GetCurrentProcess(), p, 5);
}

void patch_bytes(DWORD addr, const void *bytes, int n)
{
    DWORD old;
    VirtualProtect((void *)addr, n, PAGE_EXECUTE_READWRITE, &old);
    memcpy((void *)addr, bytes, n);
    VirtualProtect((void *)addr, n, old, &old);
    FlushInstructionCache(GetCurrentProcess(), (void *)addr, n);
}

/* ---- レジストリ: 管理者でなくても動くように ----
 * 本体は HKLM\SOFTWARE を KEY_ALL_ACCESS で開こうとし、失敗すると CD を探しにいく。
 * 書き込みの権限で開けなければ読み取りで開き直す。 */
typedef LONG (WINAPI *PFN_RegOpenKeyExA)(HKEY, LPCSTR, DWORD, REGSAM, PHKEY);
typedef LONG (WINAPI *PFN_RegCreateKeyExA)(HKEY, LPCSTR, DWORD, LPSTR, DWORD, REGSAM, void *, PHKEY, LPDWORD);
static PFN_RegOpenKeyExA o_RegOpenKeyExA;
static PFN_RegCreateKeyExA o_RegCreateKeyExA;

static LONG WINAPI my_RegOpenKeyExA(HKEY k, LPCSTR sub, DWORD opt, REGSAM sam, PHKEY out)
{
    LONG r = o_RegOpenKeyExA(k, sub, opt, sam, out);
    if (r == ERROR_ACCESS_DENIED)
        r = o_RegOpenKeyExA(k, sub, opt, KEY_READ, out);
    return r;
}

static LONG WINAPI my_RegCreateKeyExA(HKEY k, LPCSTR sub, DWORD res, LPSTR cls, DWORD opt, REGSAM sam,
                                      void *sa, PHKEY out, LPDWORD disp)
{
    LONG r = o_RegCreateKeyExA(k, sub, res, cls, opt, sam, sa, out, disp);
    if (r == ERROR_ACCESS_DENIED) {
        r = o_RegOpenKeyExA(k, sub, 0, KEY_READ, out);
        if (disp) *disp = REG_OPENED_EXISTING_KEY;
    }
    return r;
}

/* ---- 版ごとの番地 ---- */
static const Addrs ADDR_GOG = {
    "GOG MM8-Rel.exe", 0x41bb0e, 0x4f5e60,
    0x44adf8, 0x44ae82, 0x44af21, 0x44afba, 0x44b06b, 0x44b226,
    0x44b450, 0x44b786, 0x44ba36, 0x44bb6c,
    0x4a6f56, 0x4a6dc0, 0x410fad,
    0x5dc814, 0x5e2ef8, 0xec1880,
    0x4121c9, 0x4419ae, 0x4419cb,
    0x4253a7, 0x4250a9, 0x4dcda2, 0x73f828,
    0x455156, 0x5f9160, 0x5f9338,
    0x4f2218,
    {0x40b237, 0x40b727, 0x40eb44, 0x433145, 0x41de1d, 0x41de43, 0x41de77, 0x41deb3, 0x41def7, 0x41df43, 0x48e893},
    {0x40b237, 0x40b727, 0x40eb44, 0x433145, 0x41de1d, 0x41de43, 0x41de77, 0x41deb3, 0x41def7, 0x41df43, 0x48e893},
    0x516dc2, 0x516cd0, 0x75cd14,
    0,
};
/* GrayFace MM8 Patch の mm8.exe（2005 年の組み立て。番地は tools/mapaddr.py で照らし合わせた） */
static const Addrs ADDR_GF = {
    "GrayFace mm8.exe", 0x41b3d5, 0x4f3e70,
    0x449c7b, 0x449cfc, 0x449d8e, 0x449e23, 0x449eca, 0x44a058,
    0x44a253, 0x44a50f, 0x44a7b2, 0x44a8e5,
    0x4a4e9f, 0x4a4d01, 0x410aa5,
    0x5dc8e0, 0x5e2fc4, 0xec1980,
    0x411c9b, 0x440b07, 0x440b24,
    0x424b4d, 0x424863, 0x4d9f62, 0x73f910,
    0x453d58, 0x5f9248, 0x5f9420,
    0x4f0218,
    {0x40b237, 0x40b727, 0x40eb44, 0x433145, 0x41de1d, 0x41de43, 0x41de77, 0x41deb3, 0x41def7, 0x41df43, 0x48e893},
    {0x40af4d, 0x40b40d, 0x40e661, 0x4326fc, 0x41d678, 0x41d69e, 0x41d6d2, 0x41d70e, 0x41d752, 0x41d79e, 0x48ccd4},
    0x516e6a, 0x516d78, 0x75cdfc,
    0x460c50,
};
const Addrs *A;

static int check_ver(const Addrs *a)
{
    const BYTE *p = (const BYTE *)a->check_at;
    __try {
        return p[0] == 0x68 && *(DWORD *)(p + 1) == a->check_val;
    } __except (EXCEPTION_EXECUTE_HANDLER) {
        return 0;
    }
}

/* ---- GrayFace: 本体の始まりで一度だけ ----
 * GrayFace は WinMain に入る直前に文の読み込みの入口を自分の呼び出しで書き換える。
 * WinMain の頭に一度だけ止まり、そのあとで日本語化の横取りをかぶせ直す。 */
static BYTE g_winmain_head[5];
static DWORD g_winmain;
static void late_init(void)
{
    patch_bytes(g_winmain, g_winmain_head, 5);
#ifdef MM8JP_TEST
    if (g_test_mode) test_late_init();
#endif
    text_late_init();
}
static __declspec(naked) void J_WinMainOnce(void)
{
    __asm {
        pushad
        call late_init
        popad
        jmp dword ptr [g_winmain]
    }
}

BOOL WINAPI DllMain(HINSTANCE hi, DWORD reason, LPVOID rsv)
{
    if (reason == DLL_PROCESS_ATTACH) {
        char path[MAX_PATH], *s;
        DisableThreadLibraryCalls(hi);
#ifdef MM8JP_TEST
        GetModuleFileNameA(hi, path, MAX_PATH);
        s = strrchr(path, '\\');
        if (s) strcpy(s + 1, "mm8jp.log"); else strcpy(path, "mm8jp.log");
        {
            char tmp[8];
            /* 記録は環境変数 MM8JP_LOG か MM8JP_TEST があるときだけ */
            if (GetEnvironmentVariableA("MM8JP_LOG", tmp, sizeof tmp) || GetEnvironmentVariableA("MM8JP_TEST", tmp, sizeof tmp))
                g_log = fopen(path, "w");
        }
#else
        (void)s; (void)path;
#endif
        if (check_ver(&ADDR_GOG)) A = &ADDR_GOG;
        else if (check_ver(&ADDR_GF)) A = &ADDR_GF;
        else {
            jlog("知らない版なので何もしません");
            return TRUE;
        }
        jlog("版: %s", A->name);
        o_RegOpenKeyExA = (PFN_RegOpenKeyExA)patch_iat("ADVAPI32.dll", "RegOpenKeyExA", my_RegOpenKeyExA);
        o_RegCreateKeyExA = (PFN_RegCreateKeyExA)patch_iat("ADVAPI32.dll", "RegCreateKeyExA", my_RegCreateKeyExA);
        jlog("reg hook %p %p", o_RegOpenKeyExA, o_RegCreateKeyExA);
#ifdef MM8JP_TEST
        if (GetEnvironmentVariableA("MM8JP_TEST", path, MAX_PATH)) { g_test_mode = 1; test_init(); }
#endif
        jp_init();
        {
            char dir[MAX_PATH], *e;
            GetModuleFileNameA(NULL, dir, MAX_PATH);
            e = strrchr(dir, '\\');
            if (e) e[1] = 0;
            text_init(dir);
            item_init();
        }
        if (A->WinMain) {
            g_winmain = A->WinMain;
            memcpy(g_winmain_head, (void *)g_winmain, 5);
            hook_jmp(g_winmain, J_WinMainOnce);
        }
    }
    return TRUE;
}
