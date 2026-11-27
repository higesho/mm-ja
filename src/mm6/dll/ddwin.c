/* 窓表示（32 ビットのデスクトップでも動くように）と、テスト用の操作
 *
 * 窓表示: ゲームの窓表示の作りは「デスクトップと同じ形式のオフスクリーン面に 16 ビットで描き、
 *   主画面へ Blt」なので、オフスクリーン面を 565 で作らせ、主画面への Blt を GDI の
 *   StretchDIBits に置き換える。Scale 倍に広げて写し、マウスの座標は割り戻す。
 *
 * テスト（試験版 = build.bat test で作ったものだけ。mm6jp.ini の [Debug] Test=1）:
 *   共有メモリで命令を受ける。実際のキーボード・マウスは読まず、注入したものだけをゲームに見せる。
 *   窓は前面に出さない。配布版にはこの仕組みを入れない（#ifdef MM6JP_TEST）。
 */
#include "mm6jp.h"
#include <ddraw.h>
#include <stdio.h>
#include <stdlib.h>
#include <intrin.h>

static IDirectDrawSurface *g_primary;
static HRESULT (WINAPI *real_CreateSurface)(IDirectDraw *, LPDDSURFACEDESC, LPDIRECTDRAWSURFACE *, IUnknown *);
static HRESULT (WINAPI *real_Blt)(IDirectDrawSurface *, LPRECT, IDirectDrawSurface *, LPRECT, DWORD, LPDDBLTFX);
static HRESULT (WINAPI *real_GetPixelFormat)(IDirectDrawSurface *, LPDDPIXELFORMAT);
static HRESULT (WINAPI *real_Flip)(IDirectDrawSurface *, IDirectDrawSurface *, DWORD);
static HRESULT (WINAPI *real_Unlock)(IDirectDrawSurface *, LPVOID);
void misc_frame(void);
#ifdef MM6JP_TEST
void heap_check(const char *where);
#else
#define heap_check(w) ((void)0)
#endif
static int g_ddwin_on;
static HRESULT (WINAPI *real_SetCoop)(IDirectDraw *, HWND, DWORD);
static HWND g_coop_hwnd;
static DWORD g_coop_flags;

static void set565(LPDDPIXELFORMAT pf)
{
    memset(pf, 0, sizeof *pf);
    pf->dwSize = sizeof *pf;
    pf->dwFlags = DDPF_RGB;
    pf->dwRGBBitCount = 16;
    pf->dwRBitMask = 0xF800;
    pf->dwGBitMask = 0x07E0;
    pf->dwBBitMask = 0x001F;
}

static HRESULT WINAPI my_Flip(IDirectDrawSurface *s, IDirectDrawSurface *t, DWORD fl)
{
    misc_frame();
    return real_Flip(s, t, fl);
}

static HRESULT WINAPI my_GetPixelFormat(IDirectDrawSurface *s, LPDDPIXELFORMAT pf)
{
    if (g_ddwin_on && s == g_primary) { set565(pf); return DD_OK; }
    return real_GetPixelFormat(s, pf);
}

static int (WINAPI *real_GetDeviceCaps)(HDC, int);
static int WINAPI my_GetDeviceCaps(HDC dc, int i)
{
    if (i == BITSPIXEL) return 16;
    return real_GetDeviceCaps(dc, i);
}

static HWND main_hwnd(void) { return *(HWND *)A_MainWindow; }

#ifdef MM6JP_TEST
/* ---- テスト用の共有メモリ ---- */
typedef struct {
    u32 magic;
    volatile u32 cmd_seq, cmd_done;
    char cmd[512];
    volatile int mx, my;
    volatile u32 mbtn;          /* 1=左 2=右 */
    volatile u8 keys[256];
    volatile u32 frame;
    char reply[512];
} TestCtl;
static TestCtl *g_ctl;
static u32 g_last_cmd;

static void post_mouse(UINT msg, int btnmask)
{
    HWND h = main_hwnd();
    int x = g_ctl->mx * g_cfg_scale, y = g_ctl->my * g_cfg_scale;
    WPARAM wp = (btnmask & 1 ? MK_LBUTTON : 0) | (btnmask & 2 ? MK_RBUTTON : 0);
    if (h) PostMessageA(h, msg, wp, MAKELPARAM(x, y));
}

static void post_key(UINT msg, int vk)
{
    HWND h = main_hwnd();
    UINT sc = MapVirtualKeyA(vk, 0);
    LPARAM lp = 1 | (sc << 16);
    if (msg == WM_KEYUP) lp |= (3u << 30);
    if (h) PostMessageA(h, msg, vk, lp);
}

static void run_cmd(void)
{
    char c[512], *a1, *a2;
    memcpy(c, g_ctl->cmd, sizeof c);
    c[511] = 0;
    g_ctl->reply[0] = 0;
    a1 = strchr(c, ' ');
    if (a1) *a1++ = 0;
    a2 = a1 ? strchr(a1, ' ') : 0;
    if (a2) *a2++ = 0;
    if (!strcmp(c, "move") && a1 && a2) {
        g_ctl->mx = atoi(a1); g_ctl->my = atoi(a2);
        post_mouse(WM_MOUSEMOVE, g_ctl->mbtn);
    } else if (!strcmp(c, "click") || !strcmp(c, "rclick")) {
        int b = c[0] == 'r' ? 2 : 1;
        if (a1 && a2) { g_ctl->mx = atoi(a1); g_ctl->my = atoi(a2); }
        post_mouse(WM_MOUSEMOVE, 0);
        Sleep(60);
        g_ctl->mbtn |= b;
        post_mouse(b == 1 ? WM_LBUTTONDOWN : WM_RBUTTONDOWN, g_ctl->mbtn);
        Sleep(120);
        g_ctl->mbtn &= ~b;
        post_mouse(b == 1 ? WM_LBUTTONUP : WM_RBUTTONUP, g_ctl->mbtn);
        Sleep(60);
    } else if ((!strcmp(c, "mdown") || !strcmp(c, "mup")) && a1) {   /* mdown 1|2 / mup 1|2 */
        int b = atoi(a1);
        if (c[1] == 'd') {
            g_ctl->mbtn |= b;
            post_mouse(b == 1 ? WM_LBUTTONDOWN : WM_RBUTTONDOWN, g_ctl->mbtn);
        } else {
            g_ctl->mbtn &= ~b;
            post_mouse(b == 1 ? WM_LBUTTONUP : WM_RBUTTONUP, g_ctl->mbtn);
        }
    } else if (!strcmp(c, "key") && a1) {
        int vk = strtol(a1, 0, 16);
        g_ctl->keys[vk & 255] = 1;
        post_key(WM_KEYDOWN, vk);
        Sleep(120);
        g_ctl->keys[vk & 255] = 0;
        post_key(WM_KEYUP, vk);
        Sleep(60);
    } else if (!strcmp(c, "hold") && a1) {          /* キーを押したままにする / 0 で離す */
        int vk = strtol(a1, 0, 16);
        int on = a2 ? atoi(a2) : 1;
        g_ctl->keys[vk & 255] = (u8)on;
        post_key(on ? WM_KEYDOWN : WM_KEYUP, vk);
    } else if (!strcmp(c, "char") && a1) {
        HWND h = main_hwnd();
        if (h) PostMessageA(h, WM_CHAR, (u8)a1[0], 1);
    } else {
        lstrcpyA(g_ctl->reply, "unknown");
    }
}

static DWORD WINAPI test_thread(LPVOID p)
{
    for (;;) {
        if (g_ctl->cmd_seq != g_last_cmd) {
            g_last_cmd = g_ctl->cmd_seq;
            run_cmd();
            g_ctl->cmd_done = g_last_cmd;
        }
        Sleep(10);
    }
    return 0;
}

static void test_frame(void)
{
    if (g_ctl) g_ctl->frame++;
}
#endif /* MM6JP_TEST */

/* ---- 主画面へ写す ---- */
/* 窓の外形の大きさ（中が 640*Scale x 480*Scale になる）と、画面からはみ出さない位置 */
static void fit_window(HWND h, int *x, int *y, int *w, int *hh)
{
    RECT rc = { 0, 0, 640 * g_cfg_scale, 480 * g_cfg_scale }, wa;
    DWORD st = GetWindowLongA(h, GWL_STYLE);
    if (!(st & (WS_CAPTION | WS_BORDER))) return;     /* 全画面のときは触らない */
    AdjustWindowRectEx(&rc, st, GetMenu(h) != 0, GetWindowLongA(h, GWL_EXSTYLE));
    *w = rc.right - rc.left;
    *hh = rc.bottom - rc.top;
    if (SystemParametersInfoA(SPI_GETWORKAREA, 0, &wa, 0)) {
        if (*x + *w > wa.right) *x = wa.right - *w;
        if (*y + *hh > wa.bottom) *y = wa.bottom - *hh;
        if (*x < wa.left) *x = wa.left;
        if (*y < wa.top) *y = wa.top;
    }
}


static void present(IDirectDrawSurface *src)
{
    DDSURFACEDESC sd;
    HWND h = main_hwnd();
    memset(&sd, 0, sizeof sd);
    sd.dwSize = sizeof sd;
    if (src->lpVtbl->Lock(src, 0, &sd, DDLOCK_WAIT, 0) != DD_OK) return;
    if (h) {
        struct { BITMAPINFOHEADER h; DWORD m[3]; } bi;
        RECT rc;
        HDC dc;
        GetClientRect(h, &rc);
        if ((rc.right != 640 * g_cfg_scale || rc.bottom != 480 * g_cfg_scale) && !IsIconic(h) && !IsZoomed(h)) {
            RECT wr;
            int x, y, w, hh;
            GetWindowRect(h, &wr);
            x = wr.left; y = wr.top; w = wr.right - wr.left; hh = wr.bottom - wr.top;
            fit_window(h, &x, &y, &w, &hh);
            if (w != wr.right - wr.left || hh != wr.bottom - wr.top) {
                SetWindowPos(h, 0, x, y, w, hh, SWP_NOZORDER | SWP_NOACTIVATE);
                GetClientRect(h, &rc);
            }
        }
        dc = GetDC(h);
        memset(&bi, 0, sizeof bi);
        bi.h.biSize = sizeof bi.h;
        bi.h.biWidth = sd.lPitch / 2;
        bi.h.biHeight = -480;
        bi.h.biPlanes = 1;
        bi.h.biBitCount = 16;
        bi.h.biCompression = BI_BITFIELDS;
        bi.m[0] = 0xF800; bi.m[1] = 0x07E0; bi.m[2] = 0x001F;
        SetStretchBltMode(dc, COLORONCOLOR);
        StretchDIBits(dc, 0, 0, rc.right, rc.bottom, 0, 0, 640, 480, sd.lpSurface,
                      (BITMAPINFO *)&bi, DIB_RGB_COLORS, SRCCOPY);
        ReleaseDC(h, dc);
    }
#ifdef MM6JP_TEST
    test_frame();
#endif
    misc_frame();
    if (real_Unlock) real_Unlock(src, 0); else src->lpVtbl->Unlock(src, 0);
}

/* 映像（Smacker）は窓表示のとき主画面をロックして、窓の画面上の位置へじかに書く（0x4A5E87〜0x4A6054）。
   主画面は 640x480 の仮の面なので、位置は窓の中の座標のままにさせ（my_ClientToScreen）、
   アンロックされたら窓へ写す */
static HRESULT WINAPI my_Unlock(IDirectDrawSurface *s, LPVOID p)
{
    HRESULT r = real_Unlock(s, p);
    if (g_ddwin_on && s == g_primary) present(s);
    return r;
}

static HRESULT WINAPI my_Blt(IDirectDrawSurface *s, LPRECT dr, IDirectDrawSurface *src, LPRECT sr, DWORD fl, LPDDBLTFX fx)
{
    HRESULT r;
    if (g_ddwin_on && s == g_primary && src) {
        heap_check("present の前");
        present(src);
        heap_check("present の後");
        return DD_OK;
    }
    heap_check("Blt の前");
    r = real_Blt(s, dr, src, sr, fl, fx);
    heap_check("Blt の後");
    return r;
}

static HRESULT WINAPI my_CreateSurface(IDirectDraw *dd, LPDDSURFACEDESC d, LPDIRECTDRAWSURFACE *out, IUnknown *outer)
{
    HRESULT r;
    DDSURFACEDESC c;
    int primary = (d->dwFlags & DDSD_CAPS) && (d->ddsCaps.dwCaps & DDSCAPS_PRIMARYSURFACE);
    if (!g_ddwin_on) {
        /* 全画面の設定: 作りは変えない */
    } else if (primary && !(g_coop_flags & DDSCL_EXCLUSIVE)) {
        /* 窓表示のときは本物の主画面は作らない（他のゲームが排他モードだと作れない）。写すのは GDI で行う */
        memset(&c, 0, sizeof c);
        c.dwSize = sizeof c;
        c.dwFlags = DDSD_CAPS | DDSD_WIDTH | DDSD_HEIGHT | DDSD_PIXELFORMAT;
        c.ddsCaps.dwCaps = DDSCAPS_OFFSCREENPLAIN | DDSCAPS_SYSTEMMEMORY;
        c.dwWidth = 640;
        c.dwHeight = 480;
        set565(&c.ddpfPixelFormat);
        d = &c;
    } else if (!(d->dwFlags & DDSD_PIXELFORMAT)) {
        c = *d;
        c.dwFlags |= DDSD_PIXELFORMAT;
        set565(&c.ddpfPixelFormat);
        d = &c;
    }
    r = real_CreateSurface(dd, d, out, outer);
    jlog("CreateSurface fl=%x caps=%x %dx%d pf=%d -> %08X %p", d->dwFlags, d->ddsCaps.dwCaps, d->dwWidth, d->dwHeight,
         (d->dwFlags & DDSD_PIXELFORMAT) ? d->ddpfPixelFormat.dwRGBBitCount : 0, r, out ? *out : 0);
    if (r == DDERR_NOCOOPERATIVELEVELSET && real_SetCoop) {
        /* たまに起きる。設定し直してもう一度 */
        int k;
        for (k = 0; k < 5 && r == DDERR_NOCOOPERATIVELEVELSET; k++) {
            HRESULT c = real_SetCoop(dd, g_coop_hwnd ? g_coop_hwnd : main_hwnd(), g_coop_flags ? g_coop_flags : DDSCL_NORMAL);
            jlog("CreateSurface をやり直す（SetCooperativeLevel -> %08X）", c);
            Sleep(50);
            r = real_CreateSurface(dd, d, out, outer);
        }
    }
    if (r == DD_OK && *out) {
        if (primary) g_primary = (!g_ddwin_on || (g_coop_flags & DDSCL_EXCLUSIVE)) ? 0 : *out;
        if (!real_Blt) {
            void **vt = *(void ***)*out;
            DWORD old;
            real_Blt = vt[5];
            real_GetPixelFormat = vt[21];
            real_Flip = vt[11];
            real_Unlock = vt[32];
            VirtualProtect(vt, 4 * 32, PAGE_EXECUTE_READWRITE, &old);
            vt[5] = (void *)my_Blt;
            vt[11] = (void *)my_Flip;
            vt[32] = (void *)my_Unlock;
            vt[21] = (void *)my_GetPixelFormat;
            VirtualProtect(vt, 4 * 32, old, &old);
        }
    } else {
        jlog("CreateSurface 失敗 %08X caps=%08X", r, d->ddsCaps.dwCaps);
    }
    return r;
}

HRESULT WINAPI real_DirectDrawCreate(void *guid, void **dd, void *outer);
static HRESULT WINAPI my_SetCoop(IDirectDraw *dd, HWND h, DWORD fl)
{
    HRESULT r = real_SetCoop(dd, h, fl);
    g_coop_hwnd = h;
    g_coop_flags = fl;
    jlog("SetCooperativeLevel %p %x -> %08X", h, fl, r);
    return r;
}

HRESULT WINAPI my_DirectDrawCreate(void *guid, void **dd, void *outer)
{
    HRESULT r = real_DirectDrawCreate(guid, dd, outer);
    if (r == DD_OK && !real_CreateSurface) {
        void **vt = *(void ***)*dd;
        DWORD old;
        real_CreateSurface = vt[6];
        real_SetCoop = vt[20];
        VirtualProtect(vt, 4 * 24, PAGE_EXECUTE_READWRITE, &old);
        vt[6] = (void *)my_CreateSurface;
        vt[20] = (void *)my_SetCoop;
        VirtualProtect(vt, 4 * 24, old, &old);
    }
    return r;
}

/* ---- 窓の大きさとマウス座標の倍率 ---- */
static WNDPROC g_orig_proc;
static HWND (WINAPI *real_CreateWindowExA)(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
static HWND WINAPI my_CreateWindowExA(DWORD, LPCSTR, LPCSTR, DWORD, int, int, int, int, HWND, HMENU, HINSTANCE, LPVOID);
static BOOL (WINAPI *real_MoveWindow)(HWND, int, int, int, int, BOOL);
static BOOL (WINAPI *real_ScreenToClient)(HWND, LPPOINT);
static BOOL (WINAPI *real_ClientToScreen)(HWND, LPPOINT);
static BOOL (WINAPI *real_GetClientRect)(HWND, LPRECT);
#ifdef MM6JP_TEST
static BOOL (WINAPI *real_GetCursorPos)(LPPOINT);
static SHORT (WINAPI *real_GetAsyncKeyState)(int);
#endif

static BOOL WINAPI my_MoveWindow(HWND h, int x, int y, int w, int hh, BOOL rp)
{
    if (h == main_hwnd()) fit_window(h, &x, &y, &w, &hh);
    return real_MoveWindow(h, x, y, w, hh, rp);
}

static BOOL WINAPI my_ScreenToClient(HWND h, LPPOINT p)
{
    BOOL r = real_ScreenToClient(h, p);
    if (h == main_hwnd() && g_cfg_scale > 1) {
        p->x /= g_cfg_scale;
        p->y /= g_cfg_scale;
    }
    return r;
}

/* 映像を主画面へ書く処理（0x4A5EDC）から呼ばれたときは、窓の中の座標のままにする（my_Unlock を参照） */
static BOOL WINAPI my_ClientToScreen(HWND h, LPPOINT p)
{
    u32 ra = (u32)_ReturnAddress();
    if (g_ddwin_on && ra >= 0x4A5E00 && ra < 0x4A6090) return TRUE;
    return real_ClientToScreen(h, p);
}

static BOOL WINAPI my_GetClientRect(HWND h, LPRECT r)
{
    BOOL ok = real_GetClientRect(h, r);
    if (ok && h == main_hwnd() && g_cfg_scale > 1) {
        r->right /= g_cfg_scale;
        r->bottom /= g_cfg_scale;
    }
    return ok;
}

#ifdef MM6JP_TEST
/* テスト: 注入したマウスの位置・ボタンとキーだけをゲームに見せる */
static BOOL WINAPI my_GetCursorPos(LPPOINT p)
{
    if (g_ctl) {
        POINT q = { g_ctl->mx * g_cfg_scale, g_ctl->my * g_cfg_scale };
        ClientToScreen(main_hwnd(), &q);
        *p = q;
        return TRUE;
    }
    return real_GetCursorPos(p);
}

static SHORT WINAPI my_GetAsyncKeyState(int vk)
{
    if (g_ctl) {
        if (vk == VK_LBUTTON) return (g_ctl->mbtn & 1) ? (SHORT)0x8000 : 0;
        if (vk == VK_RBUTTON) return (g_ctl->mbtn & 2) ? (SHORT)0x8000 : 0;
        return g_ctl->keys[vk & 255] ? (SHORT)0x8000 : 0;
    }
    return real_GetAsyncKeyState(vk);
}
#endif

void ddwin_install(void)
{
    g_ddwin_on = 1;
    *(u32 *)A_WindowFlags |= 1;    /* -window と同じ */
    real_MoveWindow = iat_hook("USER32.dll", "MoveWindow", my_MoveWindow);
    real_ScreenToClient = iat_hook("USER32.dll", "ScreenToClient", my_ScreenToClient);
    real_ClientToScreen = iat_hook("USER32.dll", "ClientToScreen", my_ClientToScreen);
#ifdef MM6JP_TEST
    real_GetCursorPos = iat_hook("USER32.dll", "GetCursorPos", my_GetCursorPos);
    real_GetAsyncKeyState = iat_hook("USER32.dll", "GetAsyncKeyState", my_GetAsyncKeyState);
#endif
    real_GetClientRect = iat_hook("USER32.dll", "GetClientRect", my_GetClientRect);
    real_CreateWindowExA = iat_hook("USER32.dll", "CreateWindowExA", my_CreateWindowExA);
    real_GetDeviceCaps = iat_hook("GDI32.dll", "GetDeviceCaps", my_GetDeviceCaps);
#ifdef MM6JP_TEST
    if (!real_GetCursorPos) real_GetCursorPos = GetCursorPos;
    if (!real_GetAsyncKeyState) real_GetAsyncKeyState = GetAsyncKeyState;
#endif
}

/* ---- 窓の手続き: Scale 倍のマウス座標を割り戻す（テストのときは非アクティブにならない） ---- */

static LRESULT CALLBACK win_proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
#ifdef MM6JP_TEST
    if (g_ctl) {
        if (m == WM_ACTIVATEAPP && !w) w = 1;
        if (m == WM_ACTIVATE && LOWORD(w) == WA_INACTIVE) w = WA_ACTIVE;
        if (m == WM_KILLFOCUS) return 0;
    }
#endif
    if (g_cfg_scale > 1 && m >= WM_MOUSEMOVE && m <= WM_MBUTTONDBLCLK) {
        int x = (short)LOWORD(l) / g_cfg_scale, y = (short)HIWORD(l) / g_cfg_scale;
        l = MAKELPARAM(x, y);
    }
    return CallWindowProcA(g_orig_proc, h, m, w, l);
}

static HWND WINAPI my_CreateWindowExA(DWORD ex, LPCSTR cls, LPCSTR name, DWORD st, int x, int y, int w, int hh,
                                      HWND parent, HMENU menu, HINSTANCE inst, LPVOID param)
{
    HWND h;
#ifdef MM6JP_TEST
    if (g_ctl) ex &= ~WS_EX_TOPMOST;
#endif
    h = real_CreateWindowExA(ex, cls, name, st, x, y, w, hh, parent, menu, inst, param);
    if (h && !parent && !g_orig_proc) {
        RECT r;
        int nx, ny, nw, nh;
        g_orig_proc = (WNDPROC)SetWindowLongA(h, GWL_WNDPROC, (LONG)win_proc);
        GetWindowRect(h, &r);
        nx = r.left; ny = r.top; nw = r.right - r.left; nh = r.bottom - r.top;
        fit_window(h, &nx, &ny, &nw, &nh);
        SetWindowPos(h, 0, nx, ny, nw, nh, SWP_NOZORDER | SWP_NOACTIVATE);
    }
    return h;
}

#ifdef MM6JP_TEST
/* ---- テスト: 窓を前面に出さない・非アクティブにならない ---- */
static BOOL WINAPI my_SetForegroundWindow(HWND h) { return TRUE; }
static HWND WINAPI my_SetActiveWindow(HWND h) { return main_hwnd(); }
static HWND WINAPI my_GetForegroundWindow(void) { return main_hwnd(); }
static HWND WINAPI my_GetActiveWindow(void) { return main_hwnd(); }
static HWND WINAPI my_GetFocus(void) { return main_hwnd(); }
static BOOL (WINAPI *real_ShowWindow)(HWND, int);
static BOOL WINAPI my_ShowWindow(HWND h, int cmd)
{
    if (cmd == SW_SHOW || cmd == SW_SHOWNORMAL || cmd == SW_RESTORE) cmd = SW_SHOWNOACTIVATE;
    return real_ShowWindow(h, cmd);
}
static int (WINAPI *real_ShowCursor)(BOOL);
static int WINAPI my_ShowCursor(BOOL b) { return b ? 1 : -1; }

static HANDLE (WINAPI *real_CreateFileA)(LPCSTR, DWORD, DWORD, LPSECURITY_ATTRIBUTES, DWORD, DWORD, HANDLE);
static HANDLE WINAPI my_CreateFileA(LPCSTR n, DWORD a, DWORD sh, LPSECURITY_ATTRIBUTES sa, DWORD cd, DWORD fl, HANDLE t)
{
    HANDLE h = real_CreateFileA(n, a, sh, sa, cd, fl, t);
    if (h == INVALID_HANDLE_VALUE) jlog("CreateFileA 失敗: %s (%u)", n, GetLastError());
    return h;
}

void test_install(void)
{
    HANDLE m = CreateFileMappingA(INVALID_HANDLE_VALUE, 0, PAGE_READWRITE, 0, sizeof(TestCtl), "MM6JP_TEST");
    if (!m) return;
    g_ctl = (TestCtl *)MapViewOfFile(m, FILE_MAP_ALL_ACCESS, 0, 0, sizeof(TestCtl));
    if (!g_ctl) return;
    g_ctl->magic = 0x31544A4D;
    g_last_cmd = g_ctl->cmd_seq;
    iat_hook("USER32.dll", "SetForegroundWindow", my_SetForegroundWindow);
    iat_hook("USER32.dll", "SetActiveWindow", my_SetActiveWindow);
    iat_hook("USER32.dll", "GetForegroundWindow", my_GetForegroundWindow);
    iat_hook("USER32.dll", "GetActiveWindow", my_GetActiveWindow);
    iat_hook("USER32.dll", "GetFocus", my_GetFocus);
    real_ShowWindow = iat_hook("USER32.dll", "ShowWindow", my_ShowWindow);
    real_ShowCursor = iat_hook("USER32.dll", "ShowCursor", my_ShowCursor);
    real_CreateFileA = iat_hook("KERNEL32.dll", "CreateFileA", my_CreateFileA);
    if (!real_GetCursorPos) real_GetCursorPos = GetCursorPos;
    if (!real_GetAsyncKeyState) real_GetAsyncKeyState = GetAsyncKeyState;
    CreateThread(0, 0, test_thread, 0, 0, 0);
    jlog("テスト操作を有効にした");
}
#endif /* MM6JP_TEST */
