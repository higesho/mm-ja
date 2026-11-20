/* 日本語に合わせた細かい手当て */
#include "mm6jp.h"
#include <string.h>

/* 品物の名前（鑑定済み）: 元は「名前 + 空白 + 付加名（of Might など）」。
 * 付加名が日本語（EUC）なら「付加名 + 名前」（腕力の + 長剣）にする。 */
#define A_GetIdentifiedName 0x448680
#define ITEMS_TXT 0x560C18      /* 0x28 バイトずつ: +0 名前, +0x10 装備の種類(byte) */
#define STDITEMS_TXT 0x5666C8   /* 0x14 バイトずつ: +0 付加名 */
#define SPCITEMS_TXT 0x5667D8   /* 0x1C バイトずつ: +0 付加名 */
#define NAMEBUF ((char *)0x56B708)

static char *__fastcall my_GetIdentifiedName(int *item)
{
    u8 *it = (u8 *)(item[0] * 40);
    const char *name = *(const char **)(it + ITEMS_TXT);
    const char *add = 0;
    char *buf = NAMEBUF;
    if (!name) name = "";
    if (it[ITEMS_TXT + 0x10] != 0x12) {
        if (item[1]) add = *(const char **)(item[1] * 20 + STDITEMS_TXT);
        else if (item[3]) add = *(const char **)(item[3] * 28 + SPCITEMS_TXT);
    }
    if (!add || !*add) {
        lstrcpynA(buf, name, 200);
    } else if ((u8)add[0] >= 0xA1) {
        lstrcpynA(buf, add, 100);
        lstrcpynA(buf + strlen(buf), name, 100);
    } else {
        lstrcpynA(buf, name, 100);
        lstrcatA(buf, " ");
        lstrcpynA(buf + strlen(buf), add, 100);
    }
    return buf;
}

/* 状態表示（画面下の 1 行）: 元は幅 450 に収まるまで末尾を 1 バイトずつ削る。
 * 日本語の字を半分に切らないよう、字の単位で削る。 */
#define A_StatusText 0x442C60
typedef int (__fastcall *GetLineWidth_t)(void *font, const char *s);

static void __cdecl my_StatusText(void)
{
    char *buf = (char *)0x55BC04;
    const char *src = *(const char **)0x56C054;
    void *font = *(void **)0x55BDB4;
    GetLineWidth_t width = (GetLineWidth_t)A_GetLineWidth;
    int n;
    if (*(int *)0x55BD94) return;
    lstrcpynA(buf, src ? src : "", 0x190);
    *(DWORD *)0x55BD94 = GetTickCount() + 2000;
    while (width(font, buf) > 450 && (n = (int)strlen(buf)) > 0) {
        /* 最後の字の頭を探す（EUC の 2 バイト目なら 2 つ戻る） */
        int i = 0, last = 0;
        while (i < n) {
            last = i;
            i += ((u8)buf[i] >= 0xA1 && i + 1 < n && (u8)buf[i + 1] >= 0xA1) ? 2 : 1;
        }
        buf[last] = 0;
    }
}

void misc_install(void)
{
    static const u8 sig2[] = { 0xA1, 0x94, 0xBD, 0x55, 0x00, 0x57 };
    if (!memcmp((void *)A_StatusText, sig2, sizeof sig2))
        hook_jmp(A_StatusText, my_StatusText);
    static const u8 sig[] = { 0x53, 0x8B, 0xD9, 0x56, 0x57, 0x8B, 0x03 };
    if (!memcmp((void *)A_GetIdentifiedName, sig, sizeof sig))
        hook_jmp(A_GetIdentifiedName, my_GetIdentifiedName);
}

/* マップ上の怪物の名前（マップのファイルに英語で入っている）を、怪物の表（訳済み）の名前にする。
 * 毎フレーム呼ばれる。MapMonster: +0 名前[32], +0x34 種類番号, 大きさ 0x224（0x56F478 から [0x5B22F8] 個）
 * 怪物の表: 0x56C188 から 0x48 バイトずつ、+0 名前, +8 種類番号 */
void misc_frame(void)
{
    static const char *byid[256];
    static int ready;
    int n = *(int *)0x5B22F8, i;
    u8 *m = (u8 *)0x56F478;
    if (!ready) {
        const u8 *t = (const u8 *)0x56C188;
        for (i = 0; i < 174; i++) {
            const char *nm = *(const char **)(t + i * 0x48);
            if (nm && (u8)nm[0] >= 0xA1 && !byid[t[i * 0x48 + 8]]) byid[t[i * 0x48 + 8]] = nm;
        }
        ready = byid[1] || byid[2] || byid[3];
        if (!ready) return;
    }
    if (n < 0 || n > 500) return;
    for (i = 0; i < n; i++, m += 0x224) {
        const char *nm;
        int k = 0;
        if (!m[0] || m[0] >= 0x80) continue;
        nm = byid[m[0x34]];
        if (!nm) continue;
        while (nm[k] && k < 30) {
            if ((u8)nm[k] >= 0xA1 && nm[k + 1]) {
                if (k + 2 > 30) break;
                m[k] = nm[k]; m[k + 1] = nm[k + 1]; k += 2;
            } else {
                m[k] = nm[k]; k++;
            }
        }
        m[k] = 0;
    }
}
