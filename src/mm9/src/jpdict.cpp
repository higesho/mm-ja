#define _CRT_SECURE_NO_WARNINGS
// 表示時の辞書: 英語の文字列（完全一致）→ 訳（自前の符号）。
// プログラムに直書きの語や、データの中で鍵として使われる名前（怪物名・呪文名など）を
// 画面に出る瞬間だけ置き換える。辞書は data\jp\dict.txt（英語<TAB>訳 の行。訳は符号化済み）。
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <string>
#include <unordered_map>
#include "mm9jp.h"

const char* jp_gamedir();
static std::unordered_map<std::string, std::string>* g_dict;

void jpdict_load()
{
    char path[MAX_PATH];
    sprintf(path, "%sdata\\jp\\dict.txt", jp_gamedir());
    FILE* f = fopen(path, "rb");
    if (!f) { jp_log("no dict %s", path); return; }
    g_dict = new std::unordered_map<std::string, std::string>();
    static char line[8192];
    while (fgets(line, sizeof line, f)) {
        size_t n = strlen(line);
        while (n && (line[n - 1] == '\n' || line[n - 1] == '\r')) line[--n] = 0;
        char* tab = strchr(line, '\t');
        if (!tab || tab == line) continue;
        *tab = 0;
        (*g_dict)[std::string(line)] = std::string(tab + 1);
    }
    fclose(f);
    jp_log("dict: %u entries", (unsigned)g_dict->size());
}

// s を置き換える。len は NULL（NUL 終端）か、文字数（0 以下は NUL 終端と同じ）。
// 部分文字列（len が全体より短い）は置き換えない。置き換えたら len も直す。
const char* jpdict_xl(const char* s, int* len)
{
    if (!g_dict || !s || !*s) return s;
    size_t full = strlen(s);
    size_t L = full;
    if (len && *len > 0) {
        if ((size_t)*len != full) return s;
        L = (size_t)*len;
    }
    if (L == 0 || (unsigned char)s[0] >= 0x80) return s;  // 既に日本語
    auto it = g_dict->find(std::string(s, L));
    if (it == g_dict->end()) return s;
    if (len && *len > 0) *len = (int)it->second.size();
    return it->second.c_str();
}
