/* 文章ファイル（LOD の txt・STR）の差し替え
 *
 * 0x4121c9 LOD::LoadCompressed(this, 名前, 種類) ret 8 を横取りする。
 *  1. jp\名前 のファイルがあればその中身をそのまま返す（試験用）
 *  2. なければ元の関数で読み、jp\mm8jp.dat にある訳を欄ごとに当てる
 *     txt: 行（\r\n）・欄（タブ）の番号、STR: NUL で区切った番号。
 *     原文の欄の CRC32 が合うときだけ当てる（版が違っても壊さない）
 * 確保は本体と同じやり方: 種類 0 → 0x4253a7(this=0x73f828, 0, 大きさ, 見出し)、それ以外 → 0x4dcda2 (malloc)
 */
#include "mm8jp.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <intrin.h>

typedef void *(__fastcall *PFN_Load)(void *self, int edx, const char *name, int type);
typedef void *(__fastcall *PFN_HeapAlloc)(void *self, int edx, int zero, int size, void *hdr);
typedef void (__fastcall *PFN_HeapFree)(void *self, int edx, void *p);
typedef void *(__cdecl *PFN_Malloc)(int size);
#define GameAlloc  ((PFN_HeapAlloc)A->GameAlloc)
#define GameFree   ((PFN_HeapFree)A->GameFree)
#define GameMalloc ((PFN_Malloc)A->GameMalloc)
static PFN_Load o_Load;
static char g_jpdir[MAX_PATH];

/* ---- 訳の表 ---- */
typedef struct {
    DWORD key;      /* txt: 行<<8 | 欄、STR: 番号 */
    DWORD crc;      /* 原文の欄（生のバイト）の CRC32 */
    DWORD len;
    const char *text;
} Entry;
typedef struct {
    char name[64];
    int n;
    Entry *e;
} FileTr;
static FileTr *g_files;
static int g_nfiles;
static char *g_dat;

static DWORD crc_table[256];
static void crc_init(void)
{
    DWORD i, j, c;
    for (i = 0; i < 256; i++) {
        c = i;
        for (j = 0; j < 8; j++) c = (c & 1) ? 0xEDB88320 ^ (c >> 1) : c >> 1;
        crc_table[i] = c;
    }
}
static DWORD crc32(const char *p, int n)
{
    DWORD c = 0xFFFFFFFF;
    while (n-- > 0) c = crc_table[(c ^ (unsigned char)*p++) & 0xff] ^ (c >> 8);
    return c ^ 0xFFFFFFFF;
}

static void load_dat(void)
{
    char path[MAX_PATH];
    FILE *fp;
    long n;
    char *p;
    int i, j;
    strcpy(path, g_jpdir);
    strcat(path, "mm8jp.dat");
    fp = fopen(path, "rb");
    if (!fp) { jlog("dat: %s がありません", path); return; }
    fseek(fp, 0, SEEK_END);
    n = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    g_dat = (char *)malloc(n);
    fread(g_dat, 1, n, fp);
    fclose(fp);
    if (n < 12 || memcmp(g_dat, "MM8JPDAT", 8)) { jlog("dat: 形が違います"); return; }
    p = g_dat + 8;
    g_nfiles = *(int *)p; p += 4;
    g_files = (FileTr *)calloc(g_nfiles, sizeof(FileTr));
    for (i = 0; i < g_nfiles; i++) {
        memcpy(g_files[i].name, p, 64); p += 64;
        g_files[i].n = *(int *)p; p += 4;
        g_files[i].e = (Entry *)calloc(g_files[i].n, sizeof(Entry));
        for (j = 0; j < g_files[i].n; j++) {
            Entry *e = &g_files[i].e[j];
            e->key = *(DWORD *)p; p += 4;
            e->crc = *(DWORD *)p; p += 4;
            e->len = *(DWORD *)p; p += 4;
            e->text = p; p += e->len;
        }
    }
    jlog("dat: %d ファイル", g_nfiles);
}

static FileTr *find_tr(const char *name);

/* 訳のデータの @ptr の番地（GOG 版）を、動いている版の番地にする */
static DWORD map_ptr(DWORD key)
{
    int i;
    for (i = 0; i < 11; i++)
        if (A->ptr_gog[i] == key) return A->ptr_this[i];
    return 0;
}

/* exe の中の文: @ptr（命令の中の文の番地を差し替える）、@inline（その場に 31 バイトまで書く） */
static void exe_patch(int do_ptr, int do_inline)
{
    FileTr *f;
    int i, n = 0;
    if (do_ptr && (f = find_tr("@ptr")) != NULL) {
        for (i = 0; i < f->n; i++) {
            Entry *e = &f->e[i];
            DWORD at = map_ptr(e->key);
            const char *orig;
            char *t;
            DWORD old;
            if (!at) continue;
            orig = *(const char **)at;
            if (IsBadReadPtr(orig, 1) || crc32(orig, (int)strlen(orig)) != e->crc) {
                jlog("exe: %08x は合わない (%08x)", at, (DWORD)orig);
                continue;
            }
            t = (char *)malloc(e->len + 1);
            memcpy(t, e->text, e->len);
            t[e->len] = 0;
            VirtualProtect((void *)at, 4, PAGE_EXECUTE_READWRITE, &old);
            *(char **)at = t;
            VirtualProtect((void *)at, 4, old, &old);
            n++;
        }
    }
    if (do_inline && (f = find_tr("@inline")) != NULL) {
        for (i = 0; i < f->n; i++) {
            Entry *e = &f->e[i];
            char *dst;
            DWORD old;
            if (e->key < CARD_TABLE_GOG || e->key >= CARD_TABLE_GOG + CARD_TABLE_SIZE) continue;
            dst = (char *)(e->key - CARD_TABLE_GOG + A->card_table);
            if (crc32(dst, (int)strlen(dst)) != e->crc || e->len > 31) continue;
            VirtualProtect(dst, 32, PAGE_READWRITE, &old);
            memcpy(dst, e->text, e->len);
            memset(dst + e->len, 0, 32 - e->len);
            VirtualProtect(dst, 32, old, &old);
            n++;
        }
    }
    jlog("exe: %d 件の文を差し替え", n);
}

static FileTr *find_tr(const char *name)
{
    int i;
    for (i = 0; i < g_nfiles; i++)
        if (!_stricmp(g_files[i].name, name)) return &g_files[i];
    return NULL;
}

static const Entry *find_entry(FileTr *f, DWORD key)
{
    int lo = 0, hi = f->n - 1;
    while (lo <= hi) {
        int m = (lo + hi) / 2;
        if (f->e[m].key == key) return &f->e[m];
        if (f->e[m].key < key) lo = m + 1; else hi = m - 1;
    }
    return NULL;
}

static void *game_alloc(int size, int type)
{
    if (type == 0) {
        char hdr[0x60];
        memset(hdr, 0, sizeof hdr);
        return GameAlloc((void *)A->Heap, 0, 0, size, hdr);
    }
    return GameMalloc(size);
}

/* 訳を当てた新しい中身を作る（malloc。*outlen に大きさ） */
static char *apply(FileTr *f, const char *src, int srclen, int *outlen, int *applied, int *missed)
{
    int is_str, cap, n = 0, k;
    char *out;
    const char *p = src, *end = src + srclen;
    DWORD row = 0, col = 0;
    const char *ext = strrchr(f->name, '.');
    is_str = ext && !_stricmp(ext, ".str");
    cap = srclen + 16;
    for (k = 0; k < f->n; k++) cap += f->e[k].len + 1;
    out = (char *)malloc(cap);
    if (!out) return NULL;
    if (is_str) {
        DWORD idx = 0;
        while (p < end) {
            const char *q = memchr(p, 0, end - p);
            int l = q ? (int)(q - p) : (int)(end - p);
            const Entry *e = find_entry(f, idx);
            if (e && e->crc == crc32(p, l)) {
                memcpy(out + n, e->text, e->len); n += e->len; (*applied)++;
            } else {
                if (e) (*missed)++;
                memcpy(out + n, p, l); n += l;
            }
            if (!q) break;
            out[n++] = 0;
            p = q + 1;
            idx++;
        }
        *outlen = n;
        return out;
    }
    for (;;) {
        /* 欄の終わり: タブ・\r\n・終わり */
        const char *q = p;
        int l;
        const Entry *e;
        while (q < end && *q != '\t' && !(q[0] == '\r' && q + 1 < end && q[1] == '\n')) q++;
        l = (int)(q - p);
        e = col < 256 ? find_entry(f, (row << 8) | col) : NULL;
        if (e && e->crc == crc32(p, l)) {
            memcpy(out + n, e->text, e->len); n += e->len; (*applied)++;
        } else {
            if (e) (*missed)++;
            memcpy(out + n, p, l); n += l;
        }
        if (q >= end) break;
        if (*q == '\t') { out[n++] = '\t'; col++; p = q + 1; }
        else { out[n++] = '\r'; out[n++] = '\n'; row++; col = 0; p = q + 2; }
    }
    out[n] = 0;
    *outlen = n;
    return out;
}

#define RET_FROM_LOADTOBUF (A->RetFromLoadToBuf)

static void *__fastcall J_Load(void *self, int edx, const char *name, int type)
{
    char path[MAX_PATH];
    FILE *fp;
    FileTr *f;
    void *orig;
    int from_buf = (DWORD)_ReturnAddress() == RET_FROM_LOADTOBUF;
    if (!from_buf && strlen(g_jpdir) + strlen(name) < MAX_PATH - 1) {
        strcpy(path, g_jpdir);
        strcat(path, name);
        fp = fopen(path, "rb");
        if (fp) {
            long n;
            char *buf;
            fseek(fp, 0, SEEK_END);
            n = ftell(fp);
            fseek(fp, 0, SEEK_SET);
            buf = (char *)game_alloc(n + 1, type);
            if (buf) {
                fread(buf, 1, n, fp);
                buf[n] = 0;
            }
            fclose(fp);
            jlog("text: %s をファイルで差し替え (%ld)", name, n);
            return buf;
        }
    }
    orig = o_Load(self, edx, name, type);
    if (from_buf) return orig;     /* STR・EVT は J_LoadToBuf で当てる */
    f = find_tr(name);
    if (orig && f) {
        int applied = 0, missed = 0, len = 0;
        char *t = apply(f, (const char *)orig, (int)strlen((const char *)orig), &len, &applied, &missed);
        jlog("text: %s に訳 %d 件（合わない %d 件）", name, applied, missed);
        if (t) {
            char *g = (char *)game_alloc(len + 1, type);
            if (g) {
                memcpy(g, t, len + 1);
                if (type == 0) GameFree((void *)A->Heap, 0, orig);
                free(t);
                return g;
            }
            free(t);
        }
    }
    return orig;
}

/* 0x4419ae LoadToBuffer(ecx=名前, edx=先, 最大) ret 4: LOD の元の大きさだけ写して大きさを返す */
typedef int (__fastcall *PFN_LoadToBuf)(const char *name, char *dest, int max);
static PFN_LoadToBuf o_LoadToBuf;
static int __fastcall J_LoadToBuf(const char *name, char *dest, int max)
{
    int size = o_LoadToBuf(name, dest, max);
    FileTr *f = find_tr(name);
    if (f && size > 0) {
        int applied = 0, missed = 0, len = 0;
        char *t = apply(f, dest, size, &len, &applied, &missed);
        if (t && len < max) {
            memcpy(dest, t, len);
            memset(dest + len, 0, size > len ? size - len : 0);
            jlog("text: %s に訳 %d 件（合わない %d 件）%d→%d", name, applied, missed, size, len);
            size = len;
        } else {
            jlog("text: %s は訳を当てると大きすぎます (%d / %d)", name, len, max);
        }
        free(t);
    }
    return size;
}

/* 元の関数の頭 n バイトを写した踏み台（頭が call/jmp rel32 なら飛び先を直す） */
static void *make_trampoline(DWORD addr, int n)
{
    BYTE *t = (BYTE *)VirtualAlloc(NULL, 32, MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    memcpy(t, (void *)addr, n);
    if (n >= 5 && (t[0] == 0xE8 || t[0] == 0xE9))
        *(DWORD *)(t + 1) += addr - (DWORD)t;
    t[n] = 0xE9;
    *(DWORD *)(t + n + 1) = (addr + n) - ((DWORD)t + n + 5);
    return t;
}

void text_init(const char *gamedir)
{
    static const BYTE head[6] = {0x55, 0x8B, 0xEC, 0x83, 0xEC, 0x7C};
    strcpy(g_jpdir, gamedir);
    strcat(g_jpdir, "jp\\");
    crc_init();
    load_dat();
    /* GrayFace 版: 命令の中の文は GrayFace が元の値を確かめてから書き換えるので、WinMain の時点で当てる */
    exe_patch(A->WinMain == 0, 1);
    if (memcmp((void *)A->LoadCompressed, head, 6)) {
        jlog("text: LoadCompressed の頭が違うので差し替えません");
        return;
    }
    o_Load = (PFN_Load)make_trampoline(A->LoadCompressed, 6);
    hook_jmp(A->LoadCompressed, J_Load);
    {
        static const BYTE h2[9] = {0x55, 0x8B, 0xEC, 0x81, 0xEC, 0xE4, 0x00, 0x00, 0x00};
        if (!memcmp((void *)A->LoadToBuf, h2, 9)) {
            o_LoadToBuf = (PFN_LoadToBuf)make_trampoline(A->LoadToBuf, 9);
            hook_jmp(A->LoadToBuf, J_LoadToBuf);
        }
    }
    jlog("text hook installed (%s)", g_jpdir);
}

/* ---- GrayFace の DLL が mm8lang.ini から読んだ文言 ----
 * GrayFace は文言を Delphi の文字列（[-8] 参照数、[-4] 長さ）として変数に持つ。
 * MM8patch.dll の書き込める区画から、英語の既定のままの文字列を指す変数を探して日本語に向け直す。
 * 利用者が mm8lang.ini を書き換えていれば一致しないので触らない。 */
typedef struct { int ref, len; char s[64]; } DStr;
static DStr *dstr(const char *s)
{
    /* ソースは UTF-8 なので Shift_JIS にする */
    WCHAR w[64];
    DStr *d = (DStr *)calloc(1, sizeof(DStr));
    d->ref = -1;                /* 定数の文字列（解放も書き換えもしない） */
    MultiByteToWideChar(CP_UTF8, 0, s, -1, w, 64);
    WideCharToMultiByte(932, 0, w, -1, d->s, sizeof d->s - 1, NULL, NULL);
    d->len = (int)strlen(d->s);
    return d;
}
static const char *const GF_STR[][2] = {
    {"\n\nRecovery time: %d", "\n\n硬直時間: %d"},
    {"That player is not active", "その人物は今は動けません"},
    {"Double Speed", "倍速"},
    {"Normal Speed", "通常の速さ"},
    {"%s halves armor of %s", "%sが%sの防御力を半分にした"},
    {"No Attack Spell", "攻撃スペルなし"},
    {"Set as Attack Spell", "攻撃スペルにする"},
    {"Change Attack Spell (%s)", "攻撃スペルを変える（%s）"},
    {"Remove Attack Spell (%s)", "攻撃スペルを外す（%s）"},
    {"Energy", "エネルギー"},
    /* 呪文の残り時間の単位（mm8lang.ini から読むと頭の空白が落ちる） */
    {"%d:yr", "%d年"},
    {"%d:mo", "%dか月"},
    {"%d:dy", "%d日"},
    {"%d:hr", "%d時間"},
    {"%d:mn", "%d分"},
};
#define GF_NSTR (sizeof GF_STR / sizeof GF_STR[0])
static void gf_strings(void)
{
    BYTE *base = (BYTE *)GetModuleHandleA("MM8patch.dll");
    IMAGE_NT_HEADERS *nt;
    IMAGE_SECTION_HEADER *sec;
    DStr *ja[GF_NSTR];
    int i, k, n = 0;
    if (!base) return;
    for (k = 0; k < (int)GF_NSTR; k++) ja[k] = dstr(GF_STR[k][1]);
    nt = (IMAGE_NT_HEADERS *)(base + ((IMAGE_DOS_HEADER *)base)->e_lfanew);
    sec = IMAGE_FIRST_SECTION(nt);
    for (i = 0; i < nt->FileHeader.NumberOfSections; i++, sec++) {
        DWORD *p, *end;
        if (!(sec->Characteristics & IMAGE_SCN_MEM_WRITE)) continue;
        p = (DWORD *)(base + sec->VirtualAddress);
        end = (DWORD *)(base + sec->VirtualAddress + (sec->Misc.VirtualSize & ~3));
        for (; p < end; p++) {
            const char *s = (const char *)*p;
            if ((DWORD)s < 0x10000 || IsBadReadPtr(s - 8, 8)) continue;
            for (k = 0; k < (int)GF_NSTR; k++) {
                int l = (int)strlen(GF_STR[k][0]);
                if (*(const int *)(s - 4) != l || IsBadReadPtr(s, l + 1)) continue;
                if (memcmp(s, GF_STR[k][0], l + 1)) continue;
                *p = (DWORD)ja[k]->s;
                n++;
                break;
            }
        }
    }
    /* GrayFace が本体の命令に書き込んだ文の番地も */
    for (i = 0; i < 11; i++) {
        DWORD at = A->ptr_this[i], old;
        const char *s = *(const char **)at;
        if (IsBadReadPtr(s, 1)) continue;
        for (k = 0; k < (int)GF_NSTR; k++) {
            if (strcmp(s, GF_STR[k][0])) continue;
            VirtualProtect((void *)at, 4, PAGE_EXECUTE_READWRITE, &old);
            *(DWORD *)at = (DWORD)ja[k]->s;
            VirtualProtect((void *)at, 4, old, &old);
            n++;
            break;
        }
    }
    jlog("GrayFace の文言 %d 件を日本語に", n);
}

/* GrayFace: WinMain の頭で呼ばれる。GrayFace が LoadCompressed の頭を
 * call LodFilesHook; nop（DataFiles）に書き換えていたら、その上にかぶせ直す。 */
void text_late_init(void)
{
    BYTE *p = (BYTE *)A->LoadCompressed;
    exe_patch(1, 0);
    gf_strings();
    if (!o_Load) return;
    if (p[0] == 0xE9 && *(DWORD *)(p + 1) == (DWORD)J_Load - (A->LoadCompressed + 5)) {
        jlog("text: LoadCompressed はそのまま");
        return;
    }
    if (p[0] != 0xE8 && p[0] != 0xE9) {
        jlog("text: LoadCompressed の頭が知らない形 %02x", p[0]);
        return;
    }
    o_Load = (PFN_Load)make_trampoline(A->LoadCompressed, 6);
    hook_jmp(A->LoadCompressed, J_Load);
    jlog("text: LoadCompressed を GrayFace の上にかぶせ直した");
}

/* ---- 品物の名前 ----
 * 0x455156 Item::GetFullName(this) は「名前 + 空白 + of 〜」（後ろ付け）か「〜 + 空白 + 名前」（前付け）を
 * 0x5e47c0 に作る。付け足しの語が日本語なら、どちらも「〜名前」の形（空白なし）にする。
 *   標準の付加: [item+4] → 0x5f9160 + n*20 の名前、特別の付加: [item+0xc] → 0x5f9338 + n*0x1c の名前 */
typedef char *(__fastcall *PFN_ItemName)(DWORD *item);
static PFN_ItemName o_ItemName;
static char *__fastcall J_ItemName(DWORD *item)
{
    char *buf = o_ItemName(item);
    const char *x = NULL;
    size_t lx, lb;
    if (!buf) return buf;
    if (item[1]) x = *(const char **)(A->EnchStd + item[1] * 20);
    else if (item[3]) x = *(const char **)(A->EnchSpc + item[3] * 0x1c);
    if (!x || !*x || (unsigned char)x[0] < 0x80) return buf;
    lx = strlen(x);
    lb = strlen(buf);
    if (lb > lx + 1 && !strcmp(buf + lb - lx, x) && buf[lb - lx - 1] == ' ') {
        char tmp[512];
        buf[lb - lx - 1] = 0;
        if (lb + 1 < sizeof tmp) {
            strcpy(tmp, x);
            strcat(tmp, buf);
            strcpy(buf, tmp);
        }
    } else if (lb > lx && !strncmp(buf, x, lx) && buf[lx] == ' ') {
        memmove(buf + lx, buf + lx + 1, lb - lx);
    }
    return buf;
}

void item_init(void)
{
    static const BYTE head[5] = {0x56, 0x8B, 0xF1, 0x8B, 0x06};
    if (memcmp((void *)A->ItemName, head, 5)) { jlog("item: 頭が違う"); return; }
    o_ItemName = (PFN_ItemName)make_trampoline(A->ItemName, 5);
    hook_jmp(A->ItemName, J_ItemName);
    jlog("item hook installed");
}
