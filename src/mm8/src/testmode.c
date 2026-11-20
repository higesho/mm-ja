/* 試験用（環境変数 MM8JP_TEST があるときだけ）
 * ゲームを前面に出さなくても動き続けるようにし、
 * 送られてきたマウスのメッセージの位置をカーソルの位置として返す。 */
#include "mm8jp.h"

/* 操作道具（tools/mm8_ctl.py）と共有する入力の状態 */
typedef struct {
    BYTE keys[256];     /* 押している仮想キー（1=左ボタン、2=右ボタンも） */
    int mx, my;         /* マウスの位置（窓の中） */
} TestInput;
static TestInput *g_in;

static HWND g_hwnd;
static WNDPROC g_orig_proc;
static POINT g_mouse = {320, 240};
static int g_lbtn, g_rbtn;
static BYTE g_keys[256];
static int g_n_async, g_n_cursor;

static LRESULT CALLBACK test_proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    switch (m) {
    case WM_ACTIVATEAPP:
        if (!w) return 0;
        break;
    case WM_ACTIVATE:
        if (LOWORD(w) == WA_INACTIVE) return 0;
        break;
    case WM_NCACTIVATE:
        if (!w) return 1;
        break;
    case WM_KILLFOCUS:
        return 0;
    case WM_KEYDOWN: case WM_SYSKEYDOWN:
        g_keys[w & 0xff] = 1;
        break;
    case WM_KEYUP: case WM_SYSKEYUP:
        g_keys[w & 0xff] = 0;
        break;
    case WM_LBUTTONUP: case WM_RBUTTONUP:
        /* メニュー中は押した記録 [0x516cd0]=7 が一つの欄に入るだけなので、
           ゲームが読む前に放すと押したことが消える。読まれるまで後回しにする */
        {
            static int defer;
            if (*(BYTE *)A->MenuFlag && *(int *)A->MouseRec == 7 && defer < 300) {
                defer++;
                Sleep(5);
                PostMessageA(h, m, w, l);
                return 0;
            }
            defer = 0;
        }
        /* fall through */
    case WM_MOUSEMOVE:
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN:
        g_mouse.x = (short)LOWORD(l);
        g_mouse.y = (short)HIWORD(l);
        if (m == WM_LBUTTONDOWN) {
            g_lbtn = 1;
            jlog("test: LBUTTONDOWN %d,%d mouseobj=%08x async=%d cursor=%d", g_mouse.x, g_mouse.y,
                 *(DWORD *)A->DbgVal, g_n_async, g_n_cursor);
        }
        if (m == WM_LBUTTONUP) g_lbtn = 0;
        if (m == WM_RBUTTONDOWN) g_rbtn = 1;
        if (m == WM_RBUTTONUP) g_rbtn = 0;
        break;
    }
    return CallWindowProcA(g_orig_proc, h, m, w, l);
}

typedef HWND (WINAPI *PFN_CreateWindowExA)(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
static PFN_CreateWindowExA o_CreateWindowExA;
static HWND WINAPI my_CreateWindowExA(DWORD ex, LPCSTR cls, LPCSTR name, DWORD st, int x, int y, int w, int h,
                                      HWND par, HMENU menu, HINSTANCE hi, LPVOID p)
{
    HWND r = o_CreateWindowExA(ex, cls, name, st, x, y, w, h, par, menu, hi, p);
    if (r && !par && !g_hwnd) {
        g_hwnd = r;
        g_orig_proc = (WNDPROC)SetWindowLongA(r, GWL_WNDPROC, (LONG)test_proc);
        jlog("test: window %p", r);
    }
    return r;
}

static HWND WINAPI my_GetActiveWindow(void) { return g_hwnd; }
static HWND WINAPI my_GetFocus(void) { return g_hwnd; }
static BOOL WINAPI my_IsIconic(HWND h) { return FALSE; }

typedef BOOL (WINAPI *PFN_ShowWindow)(HWND, int);
static PFN_ShowWindow o_ShowWindow;
static BOOL WINAPI my_ShowWindow(HWND h, int cmd)
{
    if (h == g_hwnd && (cmd == SW_MINIMIZE || cmd == SW_SHOWMINIMIZED || cmd == SW_SHOWMINNOACTIVE || cmd == SW_FORCEMINIMIZE))
        return TRUE;
    return o_ShowWindow(h, cmd);
}

static BOOL WINAPI my_GetCursorPos(LPPOINT p)
{
    g_n_cursor++;
    p->x = g_mouse.x;
    p->y = g_mouse.y;
    if (g_hwnd) ClientToScreen(g_hwnd, p);
    return TRUE;
}

static BOOL WINAPI my_SetCursorPos(int x, int y) { return TRUE; }
static BOOL WINAPI my_ClipCursor(const RECT *r) { return TRUE; }

typedef SHORT (WINAPI *PFN_GetAsyncKeyState)(int);
static PFN_GetAsyncKeyState o_GetAsyncKeyState;
static SHORT WINAPI my_GetAsyncKeyState(int vk)
{
    g_n_async++;
    MSG msg;
    if (g_in && vk != VK_LBUTTON && vk != VK_RBUTTON) return g_in->keys[vk & 0xff] ? (SHORT)0x8000 : 0;
    /* ゲームはボタンを放すまでメッセージを処理せずに待つことがある。
       待ち行列に「放した」があれば放したことにする */
    if (vk == VK_LBUTTON) {
        if (g_lbtn && PeekMessageA(&msg, g_hwnd, WM_LBUTTONUP, WM_LBUTTONUP, PM_NOREMOVE)) g_lbtn = 0;
        return g_lbtn ? (SHORT)0x8000 : 0;
    }
    if (vk == VK_RBUTTON) {
        if (g_rbtn && PeekMessageA(&msg, g_hwnd, WM_RBUTTONUP, WM_RBUTTONUP, PM_NOREMOVE)) g_rbtn = 0;
        return g_rbtn ? (SHORT)0x8000 : 0;
    }
    if (g_keys[vk & 0xff] && PeekMessageA(&msg, g_hwnd, WM_KEYUP, WM_KEYUP, PM_NOREMOVE) && (msg.wParam & 0xff) == (vk & 0xff))
        g_keys[vk & 0xff] = 0;
    /* 実際のキーボードの状態は見せず、送られたキーの状態を返す */
    return g_keys[vk & 0xff] ? (SHORT)0x8000 : 0;
}

static BOOL WINAPI my_SetForegroundWindow(HWND h) { return TRUE; }

void test_init(void)
{
    HANDLE hm = CreateFileMappingA(INVALID_HANDLE_VALUE, NULL, PAGE_READWRITE, 0, sizeof(TestInput), "MM8JP_TEST_INPUT");
    if (hm) g_in = (TestInput *)MapViewOfFile(hm, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(TestInput));
    if (g_in) { memset(g_in, 0, sizeof *g_in); g_in->mx = 320; g_in->my = 240; }
    o_CreateWindowExA = (PFN_CreateWindowExA)patch_iat("USER32.dll", "CreateWindowExA", my_CreateWindowExA);
    patch_iat("USER32.dll", "GetActiveWindow", my_GetActiveWindow);
    patch_iat("USER32.dll", "GetFocus", my_GetFocus);
    patch_iat("USER32.dll", "IsIconic", my_IsIconic);
    o_ShowWindow = (PFN_ShowWindow)patch_iat("USER32.dll", "ShowWindow", my_ShowWindow);
    patch_iat("USER32.dll", "GetCursorPos", my_GetCursorPos);
    patch_iat("USER32.dll", "SetCursorPos", my_SetCursorPos);
    patch_iat("USER32.dll", "ClipCursor", my_ClipCursor);
    patch_iat("USER32.dll", "SetForegroundWindow", my_SetForegroundWindow);
    o_GetAsyncKeyState = (PFN_GetAsyncKeyState)patch_iat("USER32.dll", "GetAsyncKeyState", my_GetAsyncKeyState);
    jlog("test mode on");
}

/* GrayFace: MM8patch.dll もマウス・キー・前面の窓を自分で読むので、同じ仕掛けを入れる */
static HWND WINAPI my_GetForegroundWindow(void) { return g_hwnd; }
void test_late_init(void)
{
    HMODULE m = GetModuleHandleA("MM8patch.dll");
    if (!m) return;
    patch_iat_mod(m, "USER32.dll", "GetFocus", my_GetFocus);
    patch_iat_mod(m, "USER32.dll", "GetForegroundWindow", my_GetForegroundWindow);
    patch_iat_mod(m, "USER32.dll", "IsIconic", my_IsIconic);
    patch_iat_mod(m, "USER32.dll", "GetCursorPos", my_GetCursorPos);
    patch_iat_mod(m, "USER32.dll", "SetCursorPos", my_SetCursorPos);
    patch_iat_mod(m, "USER32.dll", "ClipCursor", my_ClipCursor);
    patch_iat_mod(m, "USER32.dll", "GetAsyncKeyState", my_GetAsyncKeyState);
    jlog("test: MM8patch.dll にも仕掛けを入れた");
}
