#pragma once
#include <windows.h>

void jlog(const char *fmt, ...);
void *patch_iat(const char *dll, const char *func, void *repl);
void *patch_iat_mod(HMODULE mod, const char *dll, const char *func, void *repl);
void hook_jmp(DWORD addr, void *fn);
void patch_bytes(DWORD addr, const void *bytes, int n);

void jp_init(void);
void test_init(void);
void test_late_init(void);
extern int g_test_mode;
void text_init(const char *gamedir);
void text_late_init(void);
void item_init(void);

/* 本体の版ごとの番地（GOG 版 MM8-Rel.exe と、GrayFace パッチの mm8.exe） */
typedef struct {
    const char *name;
    DWORD check_at, check_val;          /* 字体の読み込みの push imm */
    /* 字体の関数 */
    DWORD GetLineWidth, CalcTextHeight, CalcTextHeight2, GetPageTop, FitText, FitTwoFont,
          DrawTextInRect, DrawText, DrawTextLineToBuff, DrawTextLine;
    DWORD R_DrawText, R_DrawTextAlpha, CharToBuff;
    DWORD FitBuf, CurColor, Render;
    /* 文の読み込み */
    DWORD LoadCompressed, LoadToBuf, RetFromLoadToBuf;
    DWORD GameAlloc, GameFree, GameMalloc, Heap;
    /* 品物の名前 */
    DWORD ItemName, EnchStd, EnchSpc;
    /* 本体の中の文（訳のデータは GOG 版の番地で持つ） */
    DWORD card_table;                   /* アルカメイジのカード表 */
    DWORD ptr_gog[11], ptr_this[11];    /* 命令の中の文の番地 */
    /* 試験用 */
    DWORD MenuFlag, MouseRec, DbgVal;
    /* GrayFace: 本体の始まり（WinMain）。0 なら使わない */
    DWORD WinMain;
} Addrs;

extern const Addrs *A;
#define CARD_TABLE_GOG 0x4f2218
#define CARD_TABLE_SIZE (102 * 0x6c)
