// MM9 日本語化: dinput.dll の身代わり。
// 1. 本物の dinput.dll（システム）へ取り次ぐ。EnumDevices はキーボードとマウスだけを返す
//    （ゲーム機器の多い環境で古い DirectInput が HID の列挙中に落ちるのを避ける）
// 2. 日本語表示の仕掛け（mm9jp.cpp）を始動する
#include <windows.h>
#include <stdio.h>
#include "mm9jp.h"
void testinput_hook_di(void* di);

static HMODULE g_real;
typedef HRESULT(WINAPI* PFN_DICreateA)(HINSTANCE, DWORD, void**, IUnknown*);
typedef HRESULT(WINAPI* PFN_DICreateW)(HINSTANCE, DWORD, void**, IUnknown*);
typedef HRESULT(WINAPI* PFN_DICreateEx)(HINSTANCE, DWORD, REFIID, void**, IUnknown*);
typedef HRESULT(WINAPI* PFN_Generic)();

static void load_real()
{
    if (g_real) return;
    char path[MAX_PATH];
    GetSystemDirectoryA(path, MAX_PATH);  // 32bit プロセスでは SysWOW64 になる
    lstrcatA(path, "\\dinput.dll");
    g_real = LoadLibraryA(path);
    jp_log("real dinput: %s -> %p", path, g_real);
}

// IDirectInputA の EnumDevices（vtable の 4 番目）
typedef BOOL(CALLBACK* LPDIENUMDEVICESCALLBACKA)(const void*, LPVOID);
typedef HRESULT(STDMETHODCALLTYPE* PFN_Enum)(void* self, DWORD type, LPDIENUMDEVICESCALLBACKA cb, LPVOID ref, DWORD flags);
static PFN_Enum g_origEnum;

struct EnumCtx { LPDIENUMDEVICESCALLBACKA cb; LPVOID ref; bool stop; };

static BOOL CALLBACK enum_relay(const void* inst, LPVOID p)
{
    EnumCtx* c = (EnumCtx*)p;
    if (c->stop) return FALSE;
    BOOL r = c->cb(inst, c->ref);
    if (!r) c->stop = true;
    return r;
}

static HRESULT STDMETHODCALLTYPE hook_Enum(void* self, DWORD type, LPDIENUMDEVICESCALLBACKA cb, LPVOID ref, DWORD flags)
{
    DWORD base = type & 0xFF;
    jp_log("EnumDevices type=%lu flags=%lu", type, flags);
    if (base == 2 || base == 3) return g_origEnum(self, type, cb, ref, flags);
    if (base != 0) return S_OK;  // ゲーム機器などは無いことにする
    EnumCtx c = { cb, ref, false };
    HRESULT hr = g_origEnum(self, 3, enum_relay, &c, flags);  // キーボード
    if (FAILED(hr)) return hr;
    if (!c.stop) hr = g_origEnum(self, 2, enum_relay, &c, flags);  // マウス
    return hr;
}

static void patch_vtable(void* obj)
{
    void** vt = *(void***)obj;
    if (vt[4] == (void*)hook_Enum) return;
    DWORD old;
    VirtualProtect(&vt[4], sizeof(void*), PAGE_EXECUTE_READWRITE, &old);
    if (!g_origEnum) g_origEnum = (PFN_Enum)vt[4];
    vt[4] = (void*)hook_Enum;
    VirtualProtect(&vt[4], sizeof(void*), old, &old);
}

extern "C" HRESULT WINAPI DirectInputCreateA(HINSTANCE h, DWORD ver, void** out, IUnknown* outer)
{
    load_real();
    jp_start();
    PFN_DICreateA f = (PFN_DICreateA)GetProcAddress(g_real, "DirectInputCreateA");
    HRESULT hr = f(h, ver, out, outer);
    jp_log("DirectInputCreateA ver=%lx hr=%lx", ver, hr);
    if (SUCCEEDED(hr) && out && *out) {
        patch_vtable(*out);
        testinput_hook_di(*out);
    }
    return hr;
}

extern "C" HRESULT WINAPI DirectInputCreateW(HINSTANCE h, DWORD ver, void** out, IUnknown* outer)
{
    load_real();
    PFN_DICreateW f = (PFN_DICreateW)GetProcAddress(g_real, "DirectInputCreateW");
    HRESULT hr = f(h, ver, out, outer);
    if (SUCCEEDED(hr) && out && *out) patch_vtable(*out);
    return hr;
}

extern "C" HRESULT WINAPI DirectInputCreateEx(HINSTANCE h, DWORD ver, REFIID riid, void** out, IUnknown* outer)
{
    load_real();
    PFN_DICreateEx f = (PFN_DICreateEx)GetProcAddress(g_real, "DirectInputCreateEx");
    HRESULT hr = f(h, ver, riid, out, outer);
    if (SUCCEEDED(hr) && out && *out) patch_vtable(*out);
    return hr;
}

extern "C" HRESULT WINAPI DllCanUnloadNow() { return S_FALSE; }

extern "C" HRESULT WINAPI DllGetClassObject(REFCLSID a, REFIID b, void** c)
{
    load_real();
    typedef HRESULT(WINAPI * F)(REFCLSID, REFIID, void**);
    return ((F)GetProcAddress(g_real, "DllGetClassObject"))(a, b, c);
}

extern "C" HRESULT WINAPI DllRegisterServer() { return S_OK; }
extern "C" HRESULT WINAPI DllUnregisterServer() { return S_OK; }

BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(h);
        jp_init(h);
        jp_start();  // IAT の書き換えだけ（cshell.dll の読み込みを待つ）
    }
    return TRUE;
}
