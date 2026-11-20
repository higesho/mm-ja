// マイト・アンド・マジック9（GOG版）日本語化パッチ MM9JP.exe
//
// ゲームのフォルダ（lithtech.exe と data フォルダがある所）に置いて実行すると、
// data フォルダの REZ（ゲームのデータの束）から元のファイルを取り出し、差分を当てて
// 日本語化したファイルを data フォルダの中に書く（DATA\、RUDE\、SCRIPTS\、localart\、art\fonts\jp\、jp\）。
// LithTech は REZ より data フォルダの素のファイルを優先して読む。REZ そのものは書き換えない。
// 差分データ（mm9jp.dlt）は実行ファイルの中（リソース 1 番）に入っている。差分には訳と描き直した画素と
// 自作の字の表だけが入り、ゲーム本体のデータは含まない。元のファイルが GOG 版と違うときは何もしない。
//
//   MM9JP.exe            日本語化する
//   MM9JP.exe /uninstall 書いたファイルを消して元に戻す（dinput.dll も消す）
//
// ビルド: build_setup.bat（rc で mm9jp.dlt をリソースに入れて cl でつなぐ）

#include <windows.h>
#include <string>
#include <vector>
#include <map>
#include <algorithm>
#include <cstdint>
#include <cstdio>

static void say(const std::wstring &s) {
	std::wstring t = s + L"\r\n";
	HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);
	DWORD n;
	if (!WriteConsoleW(h, t.c_str(), (DWORD)t.size(), &n, nullptr)) {
		int len = WideCharToMultiByte(CP_UTF8, 0, t.c_str(), (int)t.size(), nullptr, 0, nullptr, nullptr);
		std::string u(len, 0);
		WideCharToMultiByte(CP_UTF8, 0, t.c_str(), (int)t.size(), &u[0], len, nullptr, nullptr);
		WriteFile(h, u.data(), (DWORD)u.size(), &n, nullptr);
	}
}

static bool g_quiet;

static void waitEnter() {
	if (g_quiet)
		return;
	say(L"");
	say(L"Enter キーを押すと閉じます。");
	HANDLE in = GetStdHandle(STD_INPUT_HANDLE);
	FlushConsoleInputBuffer(in);
	wchar_t buf[16];
	DWORD n;
	ReadConsoleW(in, buf, 16, &n, nullptr);
}

static uint32_t crc32of(const uint8_t *p, size_t n) {
	static uint32_t table[256];
	static bool init = false;
	if (!init) {
		for (uint32_t i = 0; i < 256; i++) {
			uint32_t c = i;
			for (int k = 0; k < 8; k++)
				c = (c & 1) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
			table[i] = c;
		}
		init = true;
	}
	uint32_t c = 0xFFFFFFFFu;
	for (size_t i = 0; i < n; i++)
		c = table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
	return c ^ 0xFFFFFFFFu;
}

static std::wstring widen(const std::string &u) {
	int len = MultiByteToWideChar(CP_UTF8, 0, u.c_str(), (int)u.size(), nullptr, 0);
	std::wstring w(len, 0);
	MultiByteToWideChar(CP_UTF8, 0, u.c_str(), (int)u.size(), &w[0], len);
	for (auto &c : w)
		if (c == L'/')
			c = L'\\';
	return w;
}

static bool isDir(const std::wstring &p) {
	DWORD a = GetFileAttributesW(p.c_str());
	return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}

static bool readFile(const std::wstring &p, std::vector<uint8_t> &out) {
	HANDLE f = CreateFileW(p.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
	if (f == INVALID_HANDLE_VALUE)
		return false;
	LARGE_INTEGER sz;
	GetFileSizeEx(f, &sz);
	out.resize((size_t)sz.QuadPart);
	DWORD n = 0;
	bool ok = out.empty() || (ReadFile(f, out.data(), (DWORD)out.size(), &n, nullptr) && n == out.size());
	CloseHandle(f);
	return ok;
}

static bool makeDirs(const std::wstring &path) {
	// path の親フォルダを作る
	size_t pos = 0;
	while ((pos = path.find(L'\\', pos + 1)) != std::wstring::npos) {
		std::wstring d = path.substr(0, pos);
		if (d.size() > 2 && !isDir(d))
			CreateDirectoryW(d.c_str(), nullptr);
	}
	return true;
}

static bool writeFile(const std::wstring &p, const std::vector<uint8_t> &d) {
	makeDirs(p);
	SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL);
	HANDLE f = CreateFileW(p.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
	if (f == INVALID_HANDLE_VALUE)
		return false;
	DWORD n = 0;
	bool ok = d.empty() || (WriteFile(f, d.data(), (DWORD)d.size(), &n, nullptr) && n == d.size());
	CloseHandle(f);
	return ok;
}

// ---- REZ（RezMgr Version 1）----
struct RezEntry {
	uint32_t pos, size;
};

struct Rez {
	HANDLE f = INVALID_HANDLE_VALUE;
	std::map<std::string, RezEntry> entries;  // 大文字の道筋 → 位置
	~Rez() {
		if (f != INVALID_HANDLE_VALUE)
			CloseHandle(f);
	}
	bool readAt(uint32_t pos, void *buf, uint32_t n) {
		LARGE_INTEGER li;
		li.QuadPart = pos;
		SetFilePointerEx(f, li, nullptr, FILE_BEGIN);
		DWORD got = 0;
		return ReadFile(f, buf, n, &got, nullptr) && got == n;
	}
	bool walk(uint32_t pos, uint32_t size, const std::string &path, int depth) {
		if (depth > 16 || size > 64 * 1024 * 1024)
			return false;
		std::vector<uint8_t> b(size);
		if (!readAt(pos, b.data(), size))
			return false;
		size_t i = 0;
		auto u32 = [&](size_t at) { return (uint32_t)(b[at] | (b[at + 1] << 8) | (b[at + 2] << 16) | ((uint32_t)b[at + 3] << 24)); };
		while (i + 16 <= b.size()) {
			uint32_t type = u32(i), p = u32(i + 4), s = u32(i + 8);
			i += 16;
			if (type == 1) {
				std::string name((const char *)&b[i]);
				i += name.size() + 1;
				if (!walk(p, s, path + name + "/", depth + 1))
					return false;
			} else {
				if (i + 12 > b.size())
					return false;
				uint32_t ext = u32(i + 4), nkeys = u32(i + 8);
				i += 12;
				std::string name((const char *)&b[i]);
				i += name.size() + 1;
				std::string desc((const char *)&b[i]);
				i += desc.size() + 1 + 4 * nkeys;
				char e[5] = {(char)(ext >> 24), (char)(ext >> 16), (char)(ext >> 8), (char)ext, 0};
				std::string es;
				for (int k = 0; k < 4; k++)
					if (e[k])
						es += e[k];
				std::string full = path + name + (es.empty() ? "" : "." + es);
				for (auto &c : full)
					c = (char)toupper((unsigned char)c);
				entries[full] = RezEntry{p, s};
			}
		}
		return true;
	}
	bool open(const std::wstring &fn) {
		f = CreateFileW(fn.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
		if (f == INVALID_HANDLE_VALUE)
			return false;
		uint8_t h[40];
		if (!readAt(127, h, 40))
			return false;
		uint32_t rootPos = h[4] | (h[5] << 8) | (h[6] << 16) | ((uint32_t)h[7] << 24);
		uint32_t rootSize = h[8] | (h[9] << 8) | (h[10] << 16) | ((uint32_t)h[11] << 24);
		return walk(rootPos, rootSize, "", 0);
	}
	bool get(const std::string &path, std::vector<uint8_t> &out) {
		std::string k = path;
		for (auto &c : k)
			c = (char)toupper((unsigned char)c);
		auto it = entries.find(k);
		if (it == entries.end())
			return false;
		out.resize(it->second.size);
		return out.empty() || readAt(it->second.pos, out.data(), it->second.size);
	}
};

struct Reader {
	const uint8_t *p, *end;
	bool ok = true;
	uint32_t u32() {
		if (end - p < 4) { ok = false; return 0; }
		uint32_t v = p[0] | (p[1] << 8) | (p[2] << 16) | ((uint32_t)p[3] << 24);
		p += 4;
		return v;
	}
	uint16_t u16() {
		if (end - p < 2) { ok = false; return 0; }
		uint16_t v = (uint16_t)(p[0] | (p[1] << 8));
		p += 2;
		return v;
	}
	uint8_t u8() {
		if (end - p < 1) { ok = false; return 0; }
		return *p++;
	}
	std::string str() {
		uint16_t n = u16();
		if (end - p < n) { ok = false; return ""; }
		std::string s((const char *)p, n);
		p += n;
		return s;
	}
};

static const wchar_t *LISTNAME = L"mm9jp_files.txt";

static int uninstall(const std::wstring &dir) {
	std::vector<uint8_t> list;
	std::wstring lp = dir + L"\\data\\" + LISTNAME;
	int n = 0;
	std::vector<std::wstring> dirs;
	if (readFile(lp, list)) {
		std::string s(list.begin(), list.end());
		size_t a = 0;
		while (a < s.size()) {
			size_t b = s.find('\n', a);
			if (b == std::string::npos)
				b = s.size();
			std::string line = s.substr(a, b - a);
			if (!line.empty() && line.back() == '\r')
				line.pop_back();
			if (!line.empty() && line.find("..") == std::string::npos) {
				std::wstring p = dir + L"\\data\\" + widen(line);
				SetFileAttributesW(p.c_str(), FILE_ATTRIBUTE_NORMAL);
				if (DeleteFileW(p.c_str()))
					n++;
				// 親フォルダを覚えておく（空になったら消す）
				std::wstring d = p;
				while (true) {
					size_t k = d.find_last_of(L'\\');
					if (k == std::wstring::npos)
						break;
					d = d.substr(0, k);
					if (d.size() <= dir.size() + 5)  // dir\data まで
						break;
					dirs.push_back(d);
				}
			}
			a = b + 1;
		}
		DeleteFileW(lp.c_str());
	}
	// 深い所から、空のフォルダだけ消す（RemoveDirectory は空でないと失敗する）
	std::sort(dirs.begin(), dirs.end(), [](const std::wstring &a, const std::wstring &b) { return a.size() > b.size(); });
	for (auto &d : dirs)
		RemoveDirectoryW(d.c_str());
	DeleteFileW((dir + L"\\dinput.dll").c_str());
	say(L"日本語化のファイルを " + std::to_wstring(n) + L" 個消しました。英語版に戻りました。");
	return 0;
}

int wmain(int argc, wchar_t **argv) {
	bool un = false;
	for (int i = 1; i < argc; i++) {
		std::wstring a = argv[i];
		if (a == L"/uninstall" || a == L"-uninstall")
			un = true;
		if (a == L"/quiet")
			g_quiet = true;
	}
	say(L"マイト・アンド・マジック9（GOG版）日本語化パッチ");
	say(L"================================================");

	wchar_t exe[MAX_PATH * 2];
	GetModuleFileNameW(nullptr, exe, MAX_PATH * 2);
	std::wstring dir = exe;
	dir = dir.substr(0, dir.find_last_of(L'\\'));
	std::wstring data = dir + L"\\data";
	if (!isDir(data) || GetFileAttributesW((dir + L"\\lithtech.exe").c_str()) == INVALID_FILE_ATTRIBUTES) {
		say(L"エラー: このフォルダに lithtech.exe と data フォルダが見つかりません。");
		say(L"MM9JP.exe は、マイト・アンド・マジック9 のフォルダ（lithtech.exe がある所）に置いてから実行してください。");
		say(L"  いまの場所: " + dir);
		waitEnter();
		return 1;
	}
	if (un) {
		int r = uninstall(dir);
		waitEnter();
		return r;
	}

	HRSRC rs = FindResourceW(nullptr, MAKEINTRESOURCEW(1), MAKEINTRESOURCEW(10));
	HGLOBAL rg = rs ? LoadResource(nullptr, rs) : nullptr;
	const uint8_t *z = rg ? (const uint8_t *)LockResource(rg) : nullptr;
	DWORD zsize = rs ? SizeofResource(nullptr, rs) : 0;
	if (!z || zsize < 16 || memcmp(z, "MM9JPDL1", 8) != 0) {
		say(L"エラー: パッチのデータが壊れています。配布されたファイルをもう一度展開してください。");
		waitEnter();
		return 1;
	}
	std::vector<uint8_t> raw(z + 8, z + zsize);

	std::map<std::string, Rez *> rezs;
	Reader r{raw.data(), raw.data() + raw.size()};
	uint32_t nfiles = r.u32();
	std::string listText;
	int written = 0;
	say(L"日本語のファイルを作っています……");
	for (uint32_t i = 0; i < nfiles && r.ok; i++) {
		std::string dst = r.str();
		uint8_t nsrc = r.u8();
		std::vector<uint8_t> src, part;
		for (int k = 0; k < nsrc; k++) {
			std::string rezName = r.str(), path = r.str();
			Rez *&rz = rezs[rezName];
			if (!rz) {
				rz = new Rez();
				if (!rz->open(data + L"\\" + widen(rezName))) {
					say(L"エラー: " + widen(rezName) + L" を読めません。");
					waitEnter();
					return 1;
				}
			}
			if (!rz->get(path, part)) {
				say(L"エラー: " + widen(rezName) + L" の中に " + widen(path) + L" がありません。");
				say(L"GOG 版（TELP 1.3 パッチ入り）のマイト・アンド・マジック9 ではないようです。");
				waitEnter();
				return 1;
			}
			src.insert(src.end(), part.begin(), part.end());
		}
		uint32_t srcSize = r.u32(), srcCrc = r.u32(), dstSize = r.u32(), dstCrc = r.u32(), nops = r.u32();
		if (src.size() != srcSize || crc32of(src.data(), src.size()) != srcCrc) {
			say(L"エラー: 元のファイル " + widen(dst) + L" が GOG 版と違います（すでに別のパッチが当たっているかもしれません）。");
			say(L"何も変えずに終わります。");
			waitEnter();
			return 1;
		}
		std::vector<uint8_t> out;
		out.reserve(dstSize);
		for (uint32_t k = 0; k < nops && r.ok; k++) {
			uint8_t op = r.u8();
			if (op == 0) {
				uint32_t pos = r.u32(), len = r.u32();
				if ((uint64_t)pos + len > src.size()) { r.ok = false; break; }
				out.insert(out.end(), src.begin() + pos, src.begin() + pos + len);
			} else {
				uint32_t len = r.u32();
				if (r.end - r.p < (ptrdiff_t)len) { r.ok = false; break; }
				out.insert(out.end(), r.p, r.p + len);
				r.p += len;
			}
		}
		if (!r.ok || out.size() != dstSize || crc32of(out.data(), out.size()) != dstCrc) {
			say(L"エラー: " + widen(dst) + L" をうまく作れませんでした。");
			waitEnter();
			return 1;
		}
		if (!writeFile(data + L"\\" + widen(dst), out)) {
			say(L"エラー: " + widen(dst) + L" を書けません。フォルダに書き込めるか確かめてください。");
			waitEnter();
			return 1;
		}
		listText += dst + "\r\n";
		written++;
	}
	writeFile(data + L"\\" + LISTNAME, std::vector<uint8_t>(listText.begin(), listText.end()));
	for (auto &kv : rezs)
		delete kv.second;
	say(L"完了しました（" + std::to_wstring(written) + L" 個）。");
	if (GetFileAttributesW((dir + L"\\dinput.dll").c_str()) == INVALID_FILE_ATTRIBUTES) {
		say(L"注意: このフォルダに dinput.dll がありません。配布物の dinput.dll も一緒に置いてください。");
	}
	say(L"いつもどおりゲームを起動してください。元に戻すときは「元に戻す.bat」を実行します。");
	waitEnter();
	return 0;
}
