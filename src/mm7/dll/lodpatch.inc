#ifdef MM7JP_TEST
static void logmsg(const char *fmt, ...);
#endif
/* LOD の目録から、解いた後の大きさを読む（見出し 0x30 の +0x28。圧縮なしなら +0x14 を使う） */
static int lod_size(void *lod, const char *name)
{
    char path[MAX_PATH];
    HANDLE h;
    DWORD got;
    u8 head[0x120];
    unsigned diroff, count, i, size = 0;
    u8 *dir;
    const char *f = lod == (void *)0x6BE8D8 ? "data\\events.lod" : lod == (void *)0x6D0490 ? "data\\icons.lod" : NULL;
    if (!f) return -1;
    _snprintf(path, MAX_PATH, "%s\\%s", gamedir, f);
    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return -1;
    ReadFile(h, head, 0x120, &got, NULL);
    diroff = *(unsigned *)(head + 0x110);
    count = *(unsigned *)(head + 0x11C);
    dir = (u8 *)HeapAlloc(GetProcessHeap(), 0, count * 0x20);
    SetFilePointer(h, diroff, NULL, FILE_BEGIN);
    ReadFile(h, dir, count * 0x20, &got, NULL);
    for (i = 0; i < count; i++) {
        char n[17];
        memcpy(n, dir + i * 0x20, 16); n[16] = 0;
        if (!_stricmp(n, name)) {
            u8 rh[0x30];
            SetFilePointer(h, diroff + *(unsigned *)(dir + i * 0x20 + 16), NULL, FILE_BEGIN);
            ReadFile(h, rh, 0x30, &got, NULL);
            size = *(unsigned *)(rh + 0x28);
            if (!size) size = *(unsigned *)(rh + 0x14);
            break;
        }
    }
    HeapFree(GetProcessHeap(), 0, dir);
    CloseHandle(h);
    return i < count ? (int)size : -1;
}

/* 訳の表 MM7JP\mm7jp.tsv（Shift_JIS、鍵<TAB>訳、訳の中の改行は \n）*/
typedef struct { char file[16]; int row, col; const char *val; int len; } Tr;
static Tr *trs;
static int ntr;
static void load_tr(void)
{
    char path[MAX_PATH];
    HANDLE h;
    DWORD size, got;
    char *d, *p, *e;
    static int done;
    if (done) return;
    done = 1;
    _snprintf(path, MAX_PATH, "%s\\mm7jp.tsv", jpdir);
    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    size = GetFileSize(h, NULL);
    d = (char *)HeapAlloc(GetProcessHeap(), 0, size + 1);
    ReadFile(h, d, size, &got, NULL);
    CloseHandle(h);
    d[got] = 0;
    for (p = d; *p; p++) if (*p == '\n') ntr++;
    trs = (Tr *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, (ntr + 2) * sizeof(Tr));
    ntr = 0;
    p = d;
    while (*p) {
        char *tab, *c1, *c2, *w, *r, *next;
        Tr *t;
        e = strchr(p, '\n');
        if (e) { next = e + 1; *e = 0; } else next = p + strlen(p);
        if (e && e > p && e[-1] == '\r') e[-1] = 0;
        tab = strchr(p, '\t');
        c1 = strchr(p, ':');
        if (*p == '#' || !tab || !c1 || c1 > tab || c1 - p >= 16) { p = next; continue; }
        *tab = 0;
        t = &trs[ntr];
        memcpy(t->file, p, c1 - p); t->file[c1 - p] = 0;
        t->row = atoi(c1 + 1);
        c2 = strchr(c1 + 1, ':');
        t->col = c2 ? atoi(c2 + 1) : -1;
        /* \n \t \\ を戻す（その場で）。2 バイト字の 2 バイト目の \ は字の一部 */
        for (w = r = tab + 1; *r; r++) {
            if (is_lead((u8)*r) && r[1]) { *w++ = *r++; *w++ = *r; continue; }
            if (*r == '\\' && r[1]) {
                r++;
                *w++ = *r == 'n' ? '\n' : *r == 't' ? '\t' : *r;
                continue;
            }
            *w++ = *r;
        }
        *w = 0;
        t->val = tab + 1;
        t->len = (int)(w - (tab + 1));
        ntr++;
        p = next;
    }
}
static int tr_cmp(const void *a, const void *b)
{
    const Tr *x = *(const Tr **)a, *y = *(const Tr **)b;
    if (x->row != y->row) return x->row - y->row;
    return x->col - y->col;
}

/* 元の表 src[0..n) に訳を当てた新しい中身を作る。返り値は大きさ（*outp は HeapAlloc）。訳が無ければ -1 */
static int apply_tr(const char *name, const u8 *src, int n, u8 **outp)
{
    Tr **list;
    int nl = 0, i, li = 0, row = 0, col = 0, o = 0, cap;
    u8 *out;
    int is_str;
    const char *ext = strrchr(name, '.');
    load_tr();
    if (!ntr) return -1;
    list = (Tr **)HeapAlloc(GetProcessHeap(), 0, ntr * sizeof(Tr *));
    for (i = 0; i < ntr; i++) if (!_stricmp(trs[i].file, name)) list[nl++] = &trs[i];
    if (!nl) { HeapFree(GetProcessHeap(), 0, list); return -1; }
    qsort(list, nl, sizeof(Tr *), tr_cmp);
    is_str = ext && !_stricmp(ext, ".str");
    cap = n + 65536;
    for (i = 0; i < nl; i++) cap += list[i]->len * 2 + 4;
    out = (u8 *)HeapAlloc(GetProcessHeap(), 0, cap);
    i = 0;
    for (;;) {
        /* 1 欄を読む */
        int start = i, end, quoted = 0;
        if (is_str) {
            while (i < n && src[i]) i++;
        } else {
            if (i < n && src[i] == '"') {
                quoted = 1;
                i++;
                while (i < n) {
                    if (src[i] == '"') { if (i + 1 < n && src[i + 1] == '"') { i += 2; continue; } break; }
                    i++;
                }
                if (i < n) i++;
            }
            while (i < n && src[i] != '\t' && src[i] != '\r' && src[i] != '\n') i++;
        }
        end = i;
        while (li < nl && (list[li]->row < row || (!is_str && list[li]->row == row && list[li]->col < col))) li++;
        if (li < nl && list[li]->row == row && (is_str || list[li]->col == col)) {
            const Tr *t = list[li];
            int k, q = !is_str && (quoted || memchr(t->val, '\n', t->len) || memchr(t->val, '\t', t->len) || memchr(t->val, '"', t->len));
            if (q) out[o++] = '"';
            for (k = 0; k < t->len; k++) {
                if (q && t->val[k] == '"') out[o++] = '"';
                out[o++] = (u8)t->val[k];
            }
            if (q) out[o++] = '"';
        } else {
            memcpy(out + o, src + start, end - start);
            o += end - start;
        }
        if (i >= n) break;
        /* 区切り */
        if (is_str) { out[o++] = 0; i++; row++; continue; }
        if (src[i] == '\t') { out[o++] = '\t'; i++; col++; continue; }
        if (src[i] == '\r' && i + 1 < n && src[i + 1] == '\n') { out[o++] = '\r'; out[o++] = '\n'; i += 2; }
        else { out[o++] = src[i]; i++; }
        row++; col = 0;
    }
    HeapFree(GetProcessHeap(), 0, list);
    *outp = out;
    return o;
}

/* 地図ごとの文字列集（*.str）と出来事（*.evt）は 0x443D04 が読む。0x410897 で読んだあと LOD の見出しを
 * もう一度読み、そこにある「元の大きさ」ぶんを決まった場所（0x5B0FA0）へ写して、NUL を数えて文字列の表を作る。
 * 訳を当てた文字列集は元と長さが違うので、そのままでは後ろを読み過ぎる（短いとき）か、末尾が切れる（長いとき）。
 * 見出しを読む fread（0x443D54）を包んで、大きさを訳後のものにする。 */
typedef unsigned (__cdecl *Fread_t)(void *buf, unsigned size, unsigned count, void *fp);
static int last_size;       /* 直前に差し替えたファイルの、差し替え後の大きさ（差し替えていなければ 0） */
static unsigned __cdecl J_FreadHdr(void *buf, unsigned size, unsigned count, void *fp)
{
    unsigned r = ((Fread_t)0x4CB8A5)(buf, size, count, fp);
    if (last_size > 0 && size * count >= 0x30) {
#ifdef MM7JP_TEST
        logmsg("見出しの大きさ %u -> %d\n", *(unsigned *)((u8 *)buf + 0x28) ? *(unsigned *)((u8 *)buf + 0x28) : *(unsigned *)((u8 *)buf + 0x14), last_size);
#endif
        *(unsigned *)((u8 *)buf + 0x28) = (unsigned)last_size;   /* 0 でなければこちらが使われる（0 なら +0x14） */
    }
    last_size = 0;
    return r;
}

u8 *__fastcall J_LodLoad(void *lod, int edx, const char *name, int kind)
{
    u8 *orig;
    char path[MAX_PATH];
    HANDLE h;
    DWORD size, got;
    u8 *buf, *tmp = NULL;
    int n, m, cap;
    static char hdr[0x30];
    const char *ext = name ? strrchr(name, '.') : NULL;
    last_size = 0;
    orig = ((LodLoad_t)(void *)tramp_lod)(lod, edx, name, kind);
    if (!orig || !ext || (_stricmp(ext, ".txt") && _stricmp(ext, ".str"))) return orig;
    strncpy(hdr, name, 15);
    /* 開発用: MM7JP\<名前> があればそれを丸ごと使う */
    _snprintf(path, MAX_PATH, "%s\\%s", jpdir, name);
    h = CreateFileA(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (h != INVALID_HANDLE_VALUE) {
        size = GetFileSize(h, NULL);
        buf = kind == 0 ? (u8 *)GameAlloc(ALLOCATOR, 0, 0, size + 1, hdr) : (u8 *)CrtMalloc(size + 1);
        if (!buf) { CloseHandle(h); return orig; }
        ReadFile(h, buf, size, &got, NULL);
        CloseHandle(h);
        buf[got] = 0;
        if (kind == 0) GameFree(ALLOCATOR, 0, orig);
        last_size = (int)got;
        return buf;
    }
    /* 訳の表を元の中身に当てる */
    n = lod_size(lod, name);
    if (n <= 0) return orig;
    m = apply_tr(name, orig, n, &tmp);
#ifdef MM7JP_TEST
    logmsg("LodLoad %s kind=%d size=%d -> %d\n", name, kind, n, m);
#endif
    if (m < 0) return orig;
    /* 元の大きさより小さくは取らない（元の大きさぶん読まれても、後ろは 0） */
    cap = (m > n ? m : n) + 16;
    buf = kind == 0 ? (u8 *)GameAlloc(ALLOCATOR, 0, 0, cap, hdr) : (u8 *)CrtMalloc(cap);
    if (!buf) { HeapFree(GetProcessHeap(), 0, tmp); return orig; }
    memcpy(buf, tmp, m);
    memset(buf + m, 0, cap - m);
    HeapFree(GetProcessHeap(), 0, tmp);
    if (kind == 0) GameFree(ALLOCATOR, 0, orig);
    last_size = m;
    return buf;
}
