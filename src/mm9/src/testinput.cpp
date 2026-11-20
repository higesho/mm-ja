#define _CRT_SECURE_NO_WARNINGS
// 試験用の入力: DirectInput のマウスとキーボードに、命令ファイルの入力を差し込む。
// game\mm9jp_test.txt があるときだけ働く（配布物には入れない）。
// 命令ファイル game\mm9jp_cmd.txt（試験の道具が書き、ここで読んで消す）の各行:
//   home              カーソルを左上へ寄せる（大きく負の方向へ動かす）
//   move dx dy        相対移動
//   down / up         左ボタン
//   rdown / rup       右ボタン
//   key <DIK 16進>    キーを押して離す
//   wait <ミリ秒>
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "mm9jp.h"

#ifdef MM9JP_RELEASE
// 配布用: 試験の仕掛けは入れない
void testinput_init() {}
void testinput_hook_di(void*) {}
void testinput_cshell(HMODULE) {}
void run_pending_console() {}
#else

const char* jp_gamedir();
static bool g_test;
static CRITICAL_SECTION g_cs;
static POINT g_fakePos = { 400, 300 };
static bool g_fakeBtn;
static HWND g_gameWnd;
static HWND game_window();

static const GUID GUID_SysMouse_ = { 0x6F1D2B60, 0xD5A0, 0x11CF, { 0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00 } };
static const GUID GUID_SysKeyboard_ = { 0x6F1D2B61, 0xD5A0, 0x11CF, { 0xBF, 0xC7, 0x44, 0x45, 0x53, 0x54, 0x00, 0x00 } };

struct DIOD { DWORD ofs, data, ts, seq; };
struct Ev { int dev; DWORD ofs, data; };  // dev 0 = マウス, 1 = キーボード
static Ev g_q[4096];
static int g_qh, g_qt;
static DWORD g_seq = 1;
static LONG g_mx, g_my;           // GetDeviceState 用の積み残し
static BYTE g_mbtn[4];
static BYTE g_keys[256];
static void* g_mouseDev;
static void* g_kbdDev;

static void push(int dev, DWORD ofs, DWORD data)
{
    EnterCriticalSection(&g_cs);
    int n = (g_qt + 1) % 4096;
    if (n != g_qh) { g_q[g_qt].dev = dev; g_q[g_qt].ofs = ofs; g_q[g_qt].data = data; g_qt = n; }
    if (dev == 0) {
        if (ofs == 0) g_mx += (LONG)data;
        else if (ofs == 4) g_my += (LONG)data;
        else if (ofs >= 12 && ofs < 16) g_mbtn[ofs - 12] = (BYTE)data;
    } else g_keys[ofs & 0xFF] = (BYTE)data;
    LeaveCriticalSection(&g_cs);
}

// IDirectInputDeviceA の差し替え
typedef HRESULT(STDMETHODCALLTYPE* PFN_GetState)(void* self, DWORD cb, void* data);
typedef HRESULT(STDMETHODCALLTYPE* PFN_GetData)(void* self, DWORD cbObj, DIOD* rgdod, DWORD* inout, DWORD flags);
typedef HRESULT(STDMETHODCALLTYPE* PFN_Acquire)(void* self);
static PFN_GetState g_origState;
static PFN_GetData g_origData;
static PFN_Acquire g_origAcquire;
static int g_logn;
static int g_kbdOfsOf[256];  // scancode -> そのゲームの書式での ofs（LithTech は割り当てたキーだけの書式を作る。-1 = 無し）
static bool g_kbdFmt;

static volatile LONG g_cntState[2], g_cntData[2];

static HRESULT STDMETHODCALLTYPE hook_Acquire(void* self)
{
    HRESULT hr = g_origAcquire(self);
    if (g_test) return S_OK;
    return hr;
}

// ゲームのスレッドで実行するコンソール命令（cmd "console ..."）
static char g_console[256];
static volatile LONG g_consolePending;
extern HMODULE g_cshell;
static char g_snap[MAX_PATH];
static volatile LONG g_snapPending;
// 画面の切り替え（ClientDE の FlipScreen = lithtech.exe 0x407bfe）の直前に写真を撮る
typedef int(__cdecl* PFN_Flip)(DWORD flags);
static PFN_Flip g_origFlip;
static int __cdecl hook_Flip(DWORD flags)
{
    if (g_snapPending) {
        typedef void(__cdecl * PFN_Shot)(const char*);
        PFN_Shot f = *(PFN_Shot*)0x49de34;  // lithtech.exe: 描画 DLL の画面写真の関数
        if (f) f(g_snap);
        jp_log("snap %s", g_snap);
        InterlockedExchange(&g_snapPending, 0);
    }
    return g_origFlip(flags);
}
static void hook_flip_once()
{
    static bool done;
    if (done || !g_cshell) return;
    DWORD delta = (DWORD)g_cshell - 0x10000000;
    void** client = *(void***)(0x100dfc4c + delta);
    if (!client) return;
    done = true;
    void patch_ptr(void** where, void* val);
    for (int i = 0; i < 0x400 / 4; i++) {
        if (client[i] == (void*)0x407bfe) {
            g_origFlip = (PFN_Flip)client[i];
            patch_ptr(&client[i], (void*)hook_Flip);
            jp_log("flip hook at +%x", i * 4);
            return;
        }
    }
    jp_log("flip not found");
}
void run_pending_console()
{
    hook_flip_once();
    if (!g_consolePending || !g_cshell) return;
    DWORD delta = (DWORD)g_cshell - 0x10000000;
    void* client = *(void**)(0x100dfc4c + delta);
    if (client) {
        typedef void(__cdecl * PFN_Run)(const char*);
        void** fns = (void**)client;  // ClientDE は関数ポインタの並び
        ((PFN_Run)fns[0x248 / 4])(g_console);
        jp_log("console: %s", g_console);
    }
    InterlockedExchange(&g_consolePending, 0);
}

static HRESULT STDMETHODCALLTYPE hook_GetState(void* self, DWORD cb, void* data)
{
    if (!g_test) return g_origState(self, cb, data);
    run_pending_console();
    InterlockedIncrement(&g_cntState[self == g_kbdDev ? 1 : 0]);
    memset(data, 0, cb);
    EnterCriticalSection(&g_cs);
    if (self == g_mouseDev && cb >= 16) {
        LONG* l = (LONG*)data;
        l[0] = g_mx; l[1] = g_my; l[2] = 0;
        memcpy((BYTE*)data + 12, g_mbtn, 4);
        g_mx = g_my = 0;
    } else if (self == g_kbdDev) {
        for (int k = 0; k < 256; k++) {
            int o = g_kbdFmt ? g_kbdOfsOf[k] : k;
            if (g_keys[k] && o >= 0 && (DWORD)o < cb) ((BYTE*)data)[o] = 0x80;
        }
    }
    LeaveCriticalSection(&g_cs);
    if (g_logn < 20) { g_logn++; jp_log("GetDeviceState %p cb=%lu", self, cb); }
    return S_OK;
}

static HRESULT STDMETHODCALLTYPE hook_GetData(void* self, DWORD cbObj, DIOD* rgdod, DWORD* inout, DWORD flags)
{
    if (!g_test) return g_origData(self, cbObj, rgdod, inout, flags);
    run_pending_console();
    int dev = (self == g_mouseDev) ? 0 : (self == g_kbdDev) ? 1 : -1;
    InterlockedIncrement(&g_cntData[dev == 1 ? 1 : 0]);
    {
        static int seenKinds;
        int kind = (rgdod ? 1 : 0) | (flags ? 2 : 0) | (dev == 1 ? 4 : 0) | ((*inout > 1) ? 8 : 0);
        if (!(seenKinds & (1 << kind))) { seenKinds |= 1 << kind; jp_log("GetDeviceData kind dev=%d rgdod=%p max=%lu flags=%lu cb=%lu", dev, rgdod, *inout, flags, cbObj); }
    }
    DWORD max = *inout, n = 0;
    EnterCriticalSection(&g_cs);
    // 先頭から、この機器の出来事だけを取り出す
    int i = g_qh;
    while (i != g_qt && n < max) {
        if (g_q[i].dev == dev) {
            if (rgdod) {
                DIOD* d = (DIOD*)((BYTE*)rgdod + n * cbObj);
                DWORD o = g_q[i].ofs;
                if (dev == 1 && g_kbdFmt) o = (g_kbdOfsOf[o & 0xFF] >= 0) ? (DWORD)g_kbdOfsOf[o & 0xFF] : 0xFFFFFFFF;
                d->ofs = o; d->data = g_q[i].data; d->ts = GetTickCount(); d->seq = g_seq++;
            }
            n++;
            g_q[i].dev = -1;  // 使用済み
        }
        i = (i + 1) % 4096;
    }
    while (g_qh != g_qt && g_q[g_qh].dev == -1) g_qh = (g_qh + 1) % 4096;
    LeaveCriticalSection(&g_cs);
    *inout = n;
    if (n && dev == 1) jp_log("kbd data n=%lu first ofs=%lu data=%lu", n, rgdod ? rgdod->ofs : 0, rgdod ? rgdod->data : 0);
    return S_OK;
}

struct DIOBJFMT { const GUID* pguid; DWORD ofs, type, flags; };
struct DIDATAFMT { DWORD size, objsize, flags, datasize, nobj; DIOBJFMT* objs; };
typedef HRESULT(STDMETHODCALLTYPE* PFN_SetFmt)(void* self, const DIDATAFMT* f);
static PFN_SetFmt g_origSetFmt;
static HRESULT STDMETHODCALLTYPE hook_SetFmt(void* self, const DIDATAFMT* f)
{
    jp_log("SetDataFormat %p datasize=%lu nobj=%lu", self, f->datasize, f->nobj);
    if (self == g_kbdDev) {
        for (DWORD i = 0; i < f->nobj && i < 300; i++) {
            DWORD inst = (f->objs[i].type >> 8) & 0xFFFF;
            if (i == 0) for (int k = 0; k < 256; k++) g_kbdOfsOf[k] = -1;
            if (inst < 256) g_kbdOfsOf[inst] = (int)f->objs[i].ofs;
        }
        jp_log("kbd format: %lu keys", f->nobj);
        g_kbdFmt = true;
    }
    return g_origSetFmt(self, f);
}

static void hook_device(void* dev)
{
    void** vt = *(void***)dev;
    void patch_ptr(void** where, void* val);
    if (vt[11] != (void*)hook_SetFmt) {
        g_origSetFmt = (PFN_SetFmt)vt[11];
        patch_ptr(&vt[11], (void*)hook_SetFmt);
    }
    if (vt[9] != (void*)hook_GetState) {
        g_origAcquire = (PFN_Acquire)vt[7];
        g_origState = (PFN_GetState)vt[9];
        g_origData = (PFN_GetData)vt[10];
        patch_ptr(&vt[7], (void*)hook_Acquire);
        patch_ptr(&vt[9], (void*)hook_GetState);
        patch_ptr(&vt[10], (void*)hook_GetData);
    }
}

// IDirectInputA::CreateDevice（vtable 3）
typedef HRESULT(STDMETHODCALLTYPE* PFN_CreateDev)(void* self, REFGUID g, void** out, IUnknown* outer);
static PFN_CreateDev g_origCreate;

static HRESULT STDMETHODCALLTYPE hook_CreateDev(void* self, REFGUID g, void** out, IUnknown* outer)
{
    HRESULT hr = g_origCreate(self, g, out, outer);
    if (SUCCEEDED(hr) && out && *out) {
        if (IsEqualGUID(g, GUID_SysMouse_)) g_mouseDev = *out;
        else if (IsEqualGUID(g, GUID_SysKeyboard_)) g_kbdDev = *out;
        jp_log("CreateDevice %s -> %p", IsEqualGUID(g, GUID_SysMouse_) ? "mouse" : IsEqualGUID(g, GUID_SysKeyboard_) ? "kbd" : "other", *out);
        hook_device(*out);
    }
    return hr;
}

void testinput_hook_di(void* di)
{
    if (!g_test) return;
    void patch_ptr(void** where, void* val);
    void** vt = *(void***)di;
    if (vt[3] != (void*)hook_CreateDev) {
        g_origCreate = (PFN_CreateDev)vt[3];
        patch_ptr(&vt[3], (void*)hook_CreateDev);
    }
}

static DWORD WINAPI cmd_thread(LPVOID)
{
    char path[MAX_PATH];
    sprintf(path, "%smm9jp_cmd.txt", jp_gamedir());
    for (;;) {
        Sleep(50);
        FILE* f = fopen(path, "r");
        if (!f) continue;
        static char lines[256][512];
        int n = 0;
        while (n < 256 && fgets(lines[n], 512, f)) n++;
        fclose(f);
        DeleteFileA(path);
        for (int i = 0; i < n; i++) {
            char cmd[16] = "";
            int a = 0, b = 0;
            sscanf(lines[i], "%15s %i %i", cmd, &a, &b);
            if (!strcmp(cmd, "home")) { for (int k = 0; k < 20; k++) push(0, 0, (DWORD)-200), push(0, 4, (DWORD)-200); }
            else if (!strcmp(cmd, "move")) {
                // 細かく分けて送る
                while (a || b) {
                    int sx = a > 50 ? 50 : a < -50 ? -50 : a;
                    int sy = b > 50 ? 50 : b < -50 ? -50 : b;
                    if (sx) push(0, 0, (DWORD)sx);
                    if (sy) push(0, 4, (DWORD)sy);
                    a -= sx; b -= sy;
                }
            }
            else if (!strcmp(cmd, "down")) push(0, 12, 0x80);
            else if (!strcmp(cmd, "up")) push(0, 12, 0);
            else if (!strcmp(cmd, "rdown")) push(0, 13, 0x80);
            else if (!strcmp(cmd, "rup")) push(0, 13, 0);
            else if (!strcmp(cmd, "key")) { push(1, a, 0x80); Sleep(300); push(1, a, 0); }
            else if (!strcmp(cmd, "keydown")) push(1, a, 0x80);
            else if (!strcmp(cmd, "keyup")) push(1, a, 0);
            else if (!strcmp(cmd, "wait")) Sleep(a);
            else if (!strcmp(cmd, "stats")) jp_log("stats mouse state=%ld data=%ld kbd state=%ld data=%ld", g_cntState[0], g_cntData[0], g_cntState[1], g_cntData[1]);
            else if (!strcmp(cmd, "snap")) {
                const char* p = strstr(lines[i], "snap") + 5;
                while (g_snapPending) Sleep(10);
                lstrcpynA(g_snap, p, sizeof g_snap);
                char* e = g_snap + strlen(g_snap);
                while (e > g_snap && (e[-1] == 10 || e[-1] == 13)) *--e = 0;
                InterlockedExchange(&g_snapPending, 1);
            }
            else if (!strcmp(cmd, "console")) {
                const char* p = strstr(lines[i], "console") + 8;
                while (g_consolePending) Sleep(10);
                lstrcpynA(g_console, p, sizeof g_console);
                char* e = g_console + strlen(g_console);
                while (e > g_console && (e[-1] == '\n' || e[-1] == '\r')) *--e = 0;
                InterlockedExchange(&g_consolePending, 1);
            }
            else if (!strcmp(cmd, "pos")) {
                g_fakePos.x = a; g_fakePos.y = b;
                HWND h = game_window();
                if (h) PostMessageA(h, WM_MOUSEMOVE, 0, MAKELPARAM(a, b));
            }
            else if (!strcmp(cmd, "ldown")) {
                g_fakeBtn = true;
                HWND h = game_window();
                if (h) PostMessageA(h, WM_LBUTTONDOWN, MK_LBUTTON, MAKELPARAM(g_fakePos.x, g_fakePos.y));
            }
            else if (!strcmp(cmd, "lup")) {
                g_fakeBtn = false;
                HWND h = game_window();
                if (h) PostMessageA(h, WM_LBUTTONUP, 0, MAKELPARAM(g_fakePos.x, g_fakePos.y));
            }
            jp_log("cmd %s %d %d", cmd, a, b);
            Sleep(30);
        }
    }
    return 0;
}

// Windows のカーソル位置とボタンの差し替え（cshell / lithtech の IAT）
static int g_nCur, g_nAsync, g_nKey;

static HWND game_window()
{
    if (g_gameWnd && IsWindow(g_gameWnd)) return g_gameWnd;
    struct P { DWORD pid; HWND h; } p = { GetCurrentProcessId(), NULL };
    EnumWindows([](HWND h, LPARAM l) -> BOOL {
        P* p = (P*)l;
        DWORD pid;
        GetWindowThreadProcessId(h, &pid);
        char cls[64];
        if (pid == p->pid && IsWindowVisible(h)) { p->h = h; return FALSE; }
        (void)cls;
        return TRUE;
    }, (LPARAM)&p);
    g_gameWnd = p.h;
    return p.h;
}

static BOOL WINAPI hook_GetCursorPos(LPPOINT pt)
{
    if (g_nCur < 10) { g_nCur++; jp_log("GetCursorPos called"); }
    *pt = g_fakePos;
    HWND h = game_window();
    if (h) ClientToScreen(h, pt);
    return TRUE;
}

static SHORT WINAPI hook_GetAsyncKeyState(int vk)
{
    if (g_nAsync < 10) { g_nAsync++; jp_log("GetAsyncKeyState %d", vk); }
    if (vk == VK_LBUTTON) return g_fakeBtn ? (SHORT)0x8000 : 0;
    return 0;
}

static SHORT WINAPI hook_GetKeyState(int vk)
{
    if (g_nKey < 10) { g_nKey++; jp_log("GetKeyState %d", vk); }
    if (vk == VK_LBUTTON) return g_fakeBtn ? (SHORT)0x8000 : 0;
    return 0;
}

void** find_iat_pub(HMODULE mod, const char* dll, const char* func);
void patch_ptr(void** where, void* val);

static void iat(HMODULE m, const char* fn, void* hook)
{
    void** p = find_iat_pub(m, "USER32.dll", fn);
    if (p) patch_ptr(p, hook);
    jp_log("IAT %p %s -> %p", m, fn, p);
}

void testinput_cshell(HMODULE cs)
{
    if (!g_test) return;
    iat(cs, "GetCursorPos", (void*)hook_GetCursorPos);
    iat(cs, "GetAsyncKeyState", (void*)hook_GetAsyncKeyState);
    iat(cs, "GetKeyState", (void*)hook_GetKeyState);
    iat(GetModuleHandleA(NULL), "GetAsyncKeyState", (void*)hook_GetAsyncKeyState);
}

void testinput_init()
{
    InitializeCriticalSection(&g_cs);
    char path[MAX_PATH];
    sprintf(path, "%smm9jp_test.txt", jp_gamedir());
    g_test = GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
    if (g_test) {
        jp_log("test input enabled");
        CreateThread(NULL, 0, cmd_thread, NULL, 0, NULL);
    }
}
#endif
