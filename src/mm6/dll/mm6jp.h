/* MM6 日本語化 DLL（ddraw.dll として読み込ませる）共通の定義 */
#pragma once
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;

/* ---- MM6 1.2（GOG 版）の番地 ---- */
#define A_GetLineWidth   0x442DD0
#define A_GetTextHeight  0x442E90
#define A_WordWrap       0x442F50
#define A_DrawLimited    0x443210
#define A_Draw           0x4435F0
#define A_DrawLine       0x4438F0
#define A_LodLoadFile    0x40C1A0
#define A_IconsLod       0x4CB6D0
#define A_GameAlloc      0x421390   /* thiscall(heap 0x5FCB50, flags, size, name) */
#define A_GameFree       0x420FA0   /* thiscall(heap, ptr) */
#define A_GameMalloc     0x4AE753   /* cdecl malloc */
#define A_Heap           0x5FCB50
#define A_MainWindow     0x61076C
#define A_WindowFlags    0x6107DC
#define A_TextColor      0x55DD80

#define SCREEN   (*(u16 **)0x9B108C)
#define LINEOFS  ((int *)0x4CA718)

typedef struct { int A, B, C; } FontABC;
typedef struct Font {
    u8 first, last, u2, u3, u4, height, u6, u7;
    int palCount;
    u16 *pal[5];          /* 0x0C */
    FontABC abc[256];     /* 0x20 */
    int glyphOff[256];    /* 0xC20 */
    u8 data[1];           /* 0x1020 */
} Font;

typedef struct Dlg { int left, top, width, height, right, bottom; } Dlg;

/* main.c */
void patch_bytes(u32 addr, const void *src, int n);
void hook_jmp(u32 at, void *fn);
void *make_trampoline(u32 at, int nbytes);
void *iat_hook(const char *dll, const char *name, void *fn);
#ifdef MM6JP_TEST
/* 試験版（build.bat test）だけ: 記録（mm6jp.log）と、テスト操作の設定 */
void jlog(const char *fmt, ...);
extern int g_cfg_test;
#else
#define jlog(...) ((void)0)
#endif
extern char g_dir[MAX_PATH];
extern int g_cfg_windowed, g_cfg_scale;
u32 crc32_buf(const void *p, int n);

/* jpfont.c */
int jpfont_load(const char *path);
const u8 *jp_glyph(Font *f, int code, int *w, int *h);   /* 8bpp, 0/1/255 */
int jp_advance(Font *f);

/* text.c */
void text_install(void);
void misc_install(void);

/* lodtext.c */
int lodtext_load(const char *path);
void lodtext_install(void);

/* ddwin.c */
void ddwin_install(void);
#ifdef MM6JP_TEST
void test_install(void);
#endif
HRESULT WINAPI my_DirectDrawCreate(void *guid, void **dd, void *outer);
