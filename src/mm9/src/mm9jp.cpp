#define _CRT_SECURE_NO_WARNINGS
// MM9 日本語化の本体: cshell.dll の読み込みを待って、文字の描画を差し替える
#include <windows.h>
#include <stdio.h>
#include <stdarg.h>
#include "mm9jp.h"

static HINSTANCE g_self;
static char g_dir[MAX_PATH];
static FILE* g_log;
static bool g_started;
HMODULE g_cshell;

void jp_log(const char* fmt, ...)
{
    if (!g_log) return;
    va_list ap;
    va_start(ap, fmt);
    vfprintf(g_log, fmt, ap);
    va_end(ap);
    fputc('\n', g_log);
    fflush(g_log);
}

void jp_init(HINSTANCE self)
{
    g_self = self;
    GetModuleFileNameA(self, g_dir, MAX_PATH);
    char* p = strrchr(g_dir, '\\');
    if (p) p[1] = 0;
    char lp[MAX_PATH];
    lstrcpyA(lp, g_dir);
    lstrcatA(lp, "mm9jp.log");
    if (GetFileAttributesA(lp) != INVALID_FILE_ATTRIBUTES || GetEnvironmentVariableA("MM9JP_LOG", NULL, 0))
        g_log = fopen(lp, "w");
    jp_log("mm9jp init dir=%s", g_dir);
}

void cshell_loaded(HMODULE h);

// lithtech.exe の LoadLibraryA を横取りして cshell.dll の読み込みを知る
typedef HMODULE(WINAPI* PFN_LoadLibraryA)(LPCSTR);
static PFN_LoadLibraryA g_origLoadLibraryA;

static HMODULE WINAPI hook_LoadLibraryA(LPCSTR name)
{
    HMODULE h = g_origLoadLibraryA(name);
    jp_log("LoadLibraryA(%s) = %p", name ? name : "(null)", h);
    if (h && name) {
        const char* b = strrchr(name, '\\');
        b = b ? b + 1 : name;
        if (!lstrcmpiA(b, "cshell.dll") && h != g_cshell) {
            g_cshell = h;
            cshell_loaded(h);
        }
    }
    return h;
}

static void** find_iat(HMODULE mod, const char* dll, const char* func)
{
    BYTE* base = (BYTE*)mod;
    IMAGE_NT_HEADERS* nt = (IMAGE_NT_HEADERS*)(base + ((IMAGE_DOS_HEADER*)base)->e_lfanew);
    IMAGE_DATA_DIRECTORY d = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    IMAGE_IMPORT_DESCRIPTOR* imp = (IMAGE_IMPORT_DESCRIPTOR*)(base + d.VirtualAddress);
    for (; imp->Name; imp++) {
        if (lstrcmpiA((char*)(base + imp->Name), dll)) continue;
        IMAGE_THUNK_DATA* orig = (IMAGE_THUNK_DATA*)(base + imp->OriginalFirstThunk);
        IMAGE_THUNK_DATA* iat = (IMAGE_THUNK_DATA*)(base + imp->FirstThunk);
        for (; orig->u1.AddressOfData; orig++, iat++) {
            if (orig->u1.Ordinal & IMAGE_ORDINAL_FLAG) continue;
            IMAGE_IMPORT_BY_NAME* n = (IMAGE_IMPORT_BY_NAME*)(base + orig->u1.AddressOfData);
            if (!lstrcmpA((char*)n->Name, func)) return (void**)&iat->u1.Function;
        }
    }
    return NULL;
}

void** find_iat_pub(HMODULE mod, const char* dll, const char* func) { return find_iat(mod, dll, func); }

void patch_ptr(void** where, void* val)
{
    DWORD old;
    VirtualProtect(where, sizeof(void*), PAGE_EXECUTE_READWRITE, &old);
    *where = val;
    VirtualProtect(where, sizeof(void*), old, &old);
}

void testinput_init();

void jp_start()
{
    if (g_started) return;
    g_started = true;
    testinput_init();
    HMODULE exe = GetModuleHandleA(NULL);
    void** p = find_iat(exe, "KERNEL32.dll", "LoadLibraryA");
    jp_log("IAT LoadLibraryA at %p", p);
    if (p) {
        g_origLoadLibraryA = (PFN_LoadLibraryA)*p;
        patch_ptr(p, (void*)hook_LoadLibraryA);
    }
    HMODULE cs = GetModuleHandleA("cshell.dll");
    if (cs) {
        g_cshell = cs;
        cshell_loaded(cs);
    }
}

void jpfont_install(HMODULE cs);

const char* jp_gamedir() { return g_dir; }

void cshell_loaded(HMODULE h)
{
    jp_log("cshell.dll loaded at %p", h);
    jpfont_install(h);
    void testinput_cshell(HMODULE cs);
    testinput_cshell(h);
}
