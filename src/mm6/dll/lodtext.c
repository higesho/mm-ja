/* icons.lod から読まれた表（*.txt）や文字列集（*.str）の欄を、訳に置き換える。
 *
 * mm6jp_text.bin:
 *   "MJT1", u32 nfiles
 *   各ファイル: u8 名前の長さ, 名前（小文字）, u8 種類(1=表 2=文字列集), u32 件数
 *     各件: u32 key（表は 行<<8|列、文字列集は番号）, u32 原文の CRC32（0 は見ない）, u16 長さ, 文（EUC-JP）
 */
#include "mm6jp.h"
#include <stdlib.h>

typedef struct { u32 key, crc; u16 len; const u8 *txt; } Ent;
typedef struct { char name[32]; int type, n; Ent *e; } TFile;

static TFile *g_files;
static int g_nfiles;

/* icons.lod の目録: 名前 → 元の大きさ */
typedef struct { char name[16]; u32 usize; } LodEnt;
static LodEnt *g_lod;
static int g_nlod;

int lodtext_load(const char *path)
{
    HANDLE h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, 0, OPEN_EXISTING, 0, 0);
    DWORD n, got;
    u8 *d, *p;
    int i, k;
    if (h == INVALID_HANDLE_VALUE) return 0;
    n = GetFileSize(h, 0);
    d = (u8 *)HeapAlloc(GetProcessHeap(), 0, n);
    ReadFile(h, d, n, &got, 0);
    CloseHandle(h);
    if (got != n || memcmp(d, "MJT1", 4)) return 0;
    g_nfiles = *(int *)(d + 4);
    g_files = (TFile *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(TFile) * g_nfiles);
    p = d + 8;
    for (i = 0; i < g_nfiles; i++) {
        TFile *f = &g_files[i];
        int nl = *p++;
        memcpy(f->name, p, nl < 31 ? nl : 31);
        p += nl;
        f->type = *p++;
        f->n = *(int *)p;
        p += 4;
        f->e = (Ent *)HeapAlloc(GetProcessHeap(), 0, sizeof(Ent) * (f->n ? f->n : 1));
        for (k = 0; k < f->n; k++) {
            f->e[k].key = *(u32 *)p;
            f->e[k].crc = *(u32 *)(p + 4);
            f->e[k].len = *(u16 *)(p + 8);
            f->e[k].txt = p + 10;
            p += 10 + f->e[k].len;
        }
    }
    jlog("訳: %d ファイル", g_nfiles);
    return 1;
}

static void read_lod_dir(void)
{
    char path[MAX_PATH];
    HANDLE h;
    DWORD got;
    u8 hdr[0x120];
    u32 doff, count, i;
    u8 *dir;
    wsprintfA(path, "%sdata\\icons.lod", g_dir);
    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, 0, OPEN_EXISTING, 0, 0);
    if (h == INVALID_HANDLE_VALUE) { jlog("icons.lod が開けない"); return; }
    ReadFile(h, hdr, 0x120, &got, 0);
    doff = *(u32 *)(hdr + 0x110);
    count = *(u32 *)(hdr + 0x11C);
    dir = (u8 *)HeapAlloc(GetProcessHeap(), 0, count * 32);
    SetFilePointer(h, doff, 0, FILE_BEGIN);
    ReadFile(h, dir, count * 32, &got, 0);
    g_lod = (LodEnt *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, sizeof(LodEnt) * count);
    for (i = 0; i < count; i++) {
        u8 eh[0x30];
        u32 off = doff + *(u32 *)(dir + i * 32 + 16);
        memcpy(g_lod[i].name, dir + i * 32, 15);
        SetFilePointer(h, off, 0, FILE_BEGIN);
        ReadFile(h, eh, 0x30, &got, 0);
        g_lod[i].usize = *(u32 *)(eh + 0x28);
        if (!g_lod[i].usize) g_lod[i].usize = *(u32 *)(eh + 0x14);
    }
    g_nlod = count;
    CloseHandle(h);
}

static u32 lod_usize(const char *name)
{
    int i;
    for (i = 0; i < g_nlod; i++)
        if (!lstrcmpiA(g_lod[i].name, name)) return g_lod[i].usize;
    return 0;
}

static TFile *find_tfile(const char *name)
{
    int i;
    for (i = 0; i < g_nfiles; i++)
        if (!lstrcmpiA(g_files[i].name, name)) return &g_files[i];
    return 0;
}

static Ent *find_ent(TFile *f, u32 key)
{
    int lo = 0, hi = f->n - 1;
    while (lo <= hi) {
        int m = (lo + hi) >> 1;
        if (f->e[m].key == key) return &f->e[m];
        if (f->e[m].key < key) lo = m + 1; else hi = m - 1;
    }
    return 0;
}

/* 表を組み直す。out は十分大きいこと。書いた長さを返す */
static int merge_table(TFile *tf, const u8 *src, int n, u8 *out, int *nrep, int *nbad)
{
    int i = 0, o = 0, row = 0, col = 0, cs = 0;
    for (;;) {
        int end = (i >= n), sep = !end && (src[i] == '\t' || src[i] == '\r');
        if (end || sep) {
            Ent *e = find_ent(tf, (row << 8) | col);
            if (e && (!e->crc || e->crc == crc32_buf(src + cs, i - cs))) {
                memcpy(out + o, e->txt, e->len);
                o += e->len;
                (*nrep)++;
            } else {
                if (e) (*nbad)++;
                memcpy(out + o, src + cs, i - cs);
                o += i - cs;
            }
            if (end) break;
            out[o++] = src[i];
            if (src[i] == '\t') {
                col++;
            } else {
                /* 行は \r で区切る（続く \n も行の区切りに含める）。\n だけは欄の中身 */
                if (i + 1 < n && src[i + 1] == '\n') { out[o++] = '\n'; i++; }
                row++; col = 0;
            }
            i++;
            cs = i;
            continue;
        }
        i++;
    }
    return o;
}

static int merge_strs(TFile *tf, const u8 *src, int n, u8 *out, int *nrep, int *nbad)
{
    int i = 0, o = 0, idx = 0;
    while (i < n) {
        int s = i;
        Ent *e;
        while (i < n && src[i]) i++;
        e = find_ent(tf, idx);
        if (e && (!e->crc || e->crc == crc32_buf(src + s, i - s))) {
            memcpy(out + o, e->txt, e->len);
            o += e->len;
            (*nrep)++;
        } else {
            if (e) (*nbad)++;
            memcpy(out + o, src + s, i - s);
            o += i - s;
        }
        if (i < n) { out[o++] = 0; i++; }
        idx++;
    }
    return o;
}

typedef void *(__fastcall *LodLoad_t)(void *lod, int edx, const char *name, int useMalloc);
typedef void *(__fastcall *GameAlloc_t)(void *heap, int edx, int flags, int size, const char *name);
typedef void (__fastcall *GameFree_t)(void *heap, int edx, void *p);
typedef void *(__cdecl *GameMalloc_t)(int size);
static LodLoad_t real_LodLoad;

/* 文字列集（*.str）は、読んだあとゲームが LOD の見出しをもう一度読み、そこにある「元の大きさ」ぶんを使う。
 *   0x439660  マップの *.str: その大きさぶんを 0x54D044 へ写し、NUL を数えて文字列の表を作る
 *   0x452D0B  intro.str、0x4A6E97 win.str・lose.str: その大きさぶんの NUL を改行に変え、末尾に NUL を置く
 * 訳は元と長さが違うので、そのままでは後ろのごみまで読む（短いとき）か、末尾が切れる（長いとき）。
 * この 3 か所の「見出しを読む fread」を包んで、大きさを置き換え後のものにする。 */
#define A_Fread 0x4AE63C
typedef u32 (__cdecl *Fread_t)(void *buf, u32 size, u32 count, void *fp);
static u32 g_last_size;        /* 直前に置き換えたファイルの、置き換え後の大きさ（置き換えていなければ 0） */
#ifdef MM6JP_TEST
static char g_last_name[32];
static int g_tail_fill;        /* 試験: 置き換えた文の後ろを '#' で埋め、読み過ぎを画面で見えるようにする */
#endif

static u32 __cdecl my_fread_hdr(void *buf, u32 size, u32 count, void *fp)
{
    u32 r = ((Fread_t)A_Fread)(buf, size, count, fp);
    if (g_last_size && size * count >= 0x30) {
        jlog("%s: 大きさ %u（元 %u）", g_last_name,
             g_last_size, *(u32 *)((u8 *)buf + 0x28) ? *(u32 *)((u8 *)buf + 0x28) : *(u32 *)((u8 *)buf + 0x14));
        *(u32 *)((u8 *)buf + 0x28) = g_last_size;   /* 0 でなければこちらが使われる（0 なら +0x14） */
    }
    g_last_size = 0;
    return r;
}

/* at にある「call A_Fread」を my_fread_hdr へ向ける */
static void hook_fread_call(u32 at)
{
    u8 b[5];
    u32 rel = (u32)my_fread_hdr - (at + 5);
    if (*(u8 *)at != 0xE8 || at + 5 + *(u32 *)(at + 1) != A_Fread) { jlog("fread の呼び出しが違う: %x", at); return; }
    b[0] = 0xE8;
    memcpy(b + 1, &rel, 4);
    patch_bytes(at, b, 5);
}

static void *__fastcall my_LodLoad(void *lod, int edx, const char *name, int useMalloc)
{
    void *buf;
    TFile *tf;
    u32 us;
    u8 *out, *nb;
    int n, nrep = 0, nbad = 0, total = 0, k, pad = 16;
    g_last_size = 0;
    buf = real_LodLoad(lod, edx, name, useMalloc);
    if (!buf || (u32)lod != A_IconsLod || !g_nfiles) return buf;
    tf = find_tfile(name);
    if (!tf) return buf;
    us = lod_usize(name);
    if (!us) { jlog("%s の大きさが分からない", name); return buf; }
    for (k = 0; k < tf->n; k++) total += tf->e[k].len;
    out = (u8 *)HeapAlloc(GetProcessHeap(), 0, us + total + 16);
    if (tf->type == 3) {
        /* バイナリの表: 鍵の位置の 32 バイトの欄（NUL 終わり）を置き換える。大きさは変わらない */
        memcpy(out, buf, us);
        n = us;
        for (k = 0; k < tf->n; k++) {
            Ent *e = &tf->e[k];
            if (e->key + 32 > us || e->len > 31) { nbad++; continue; }
            if (e->crc && e->crc != crc32_buf(out + e->key, (int)strnlen((char *)out + e->key, 32))) { nbad++; continue; }
            memset(out + e->key, 0, 32);
            memcpy(out + e->key, e->txt, e->len);
            nrep++;
        }
    } else if (tf->type == 2) n = merge_strs(tf, (u8 *)buf, us, out, &nrep, &nbad);
    else n = merge_table(tf, (u8 *)buf, us, out, &nrep, &nbad);
#ifdef MM6JP_TEST
    if (g_tail_fill) pad = 4096;
#endif
    if (useMalloc) {
        nb = (u8 *)((GameMalloc_t)A_GameMalloc)(n + pad);
    } else {
        nb = (u8 *)((GameAlloc_t)A_GameAlloc)((void *)A_Heap, 0, 0, n + pad, name);
        ((GameFree_t)A_GameFree)((void *)A_Heap, 0, buf);
    }
    memcpy(nb, out, n);
    memset(nb + n, 0, 16);
#ifdef MM6JP_TEST
    if (g_tail_fill) memset(nb + n + 1, '#', pad - 1);   /* NUL 1 つのあとは全部ごみ */
    lstrcpynA(g_last_name, name, sizeof g_last_name);
#endif
    g_last_size = n;
    HeapFree(GetProcessHeap(), 0, out);
    jlog("%s: %d 件を置き換え（原文が違い飛ばした %d 件）", name, nrep, nbad);
    return nb;
}

#ifdef MM6JP_TEST
/* 試験: マップの文字列集をすべてゲーム自身の読み込み（0x439EA0）に通し、出来た文字列の表を
 * mm6jp_strdump.txt へ書き出して終わる。ゲームの主スレッドから呼ぶこと。
 *   F <名前> <大きさ> <本数>
 *   <番号> <文の 16 進>                                                              */
void lodtext_test_dump(void)
{
    char path[MAX_PATH], line[4200], nm[32];
    HANDLE h;
    DWORD w;
    int i, k, j, o;
    wsprintfA(path, "%smm6jp_strdump.txt", g_dir);
    h = CreateFileA(path, GENERIC_WRITE, 0, 0, CREATE_ALWAYS, 0, 0);
    if (h == INVALID_HANDLE_VALUE) return;
    for (i = 0; i < g_nfiles; i++) {
        TFile *f = &g_files[i];
        char *dot;
        int cnt, size;
        if (f->type != 2) continue;
        lstrcpynA(nm, f->name, sizeof nm);
        dot = strrchr(nm, '.');
        if (dot) *dot = 0;
        if (!lstrcmpiA(nm, "intro") || !lstrcmpiA(nm, "win") || !lstrcmpiA(nm, "lose")) continue;
        ((void (__fastcall *)(const char *))0x439EA0)(nm);
        size = *(int *)0x551D18;
        cnt = *(int *)0x54FCE0;
        o = wsprintfA(line, "F %s %d %d\r\n", f->name, size, cnt);
        WriteFile(h, line, o, &w, 0);
        for (k = 0; k < cnt; k++) {
            const u8 *s = (const u8 *)0x54D044 + ((int *)0x551F9C)[k];
            o = wsprintfA(line, "%d ", k);
            for (j = 0; s[j] && j < 2000; j++) o += wsprintfA(line + o, "%02x", s[j]);
            o += wsprintfA(line + o, "\r\n");
            WriteFile(h, line, o, &w, 0);
        }
    }
    CloseHandle(h);
    jlog("文字列集の書き出し終わり");
    ExitProcess(0);
}
#endif

void lodtext_install(void)
{
    read_lod_dir();
    real_LodLoad = (LodLoad_t)make_trampoline(A_LodLoadFile, 7);
    hook_jmp(A_LodLoadFile, my_LodLoad);
#ifdef MM6JP_TEST
    {
        char ini[MAX_PATH];
        wsprintfA(ini, "%smm6jp.ini", g_dir);
        g_tail_fill = GetPrivateProfileIntA("Debug", "TailFill", 0, ini);
        if (GetPrivateProfileIntA("Debug", "Off", 0, ini) & 8) { jlog("大きさの差し替えなし"); return; }
    }
#endif
    hook_fread_call(0x43970A);
    hook_fread_call(0x452DB4);
    hook_fread_call(0x4A6F48);
}
