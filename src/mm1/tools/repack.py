# 前の版の配布 zip をもとに、日本語化の本体と説明書だけを差し替えて新しい版の zip を作る（M&M 1〜3 共通）
#   python repack.py <前の zip> <新しい zip> <説明書の元（UTF-8）> <差し替えるファイル>...
#   - zip の中の名前・順・ほかのファイル（DOSBOX\opengl32.dll など）は前の版のまま
#   - 名前は前の版と同じく Shift_JIS で入れる（UTF-8 の印を付けない）
#   - 説明書は「はじめにお読みください.txt」として、BOM 付き UTF-8・CRLF で入れる
import os
import sys
import zipfile

README = "はじめにお読みください.txt"


class SJISInfo(zipfile.ZipInfo):
    def _encodeFilenameFlags(self):
        return self.filename.encode("cp932"), self.flag_bits & ~0x800


def name_of(info):
    return info.filename if info.flag_bits & 0x800 else info.filename.encode("cp437").decode("cp932")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    old, new, readme_src = sys.argv[1:4]
    repl = {os.path.basename(p): p for p in sys.argv[4:]}
    text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n") + "\n"
    readme = b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8")
    zin = zipfile.ZipFile(old)
    tmp = new + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zout:
        for info in zin.infolist():
            name = name_of(info)
            if name == README:
                data = readme
            elif name in repl:
                data = open(repl.pop(name), "rb").read()
            else:
                data = zin.read(info)
            zi = SJISInfo(name, date_time=info.date_time)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = info.external_attr
            zout.writestr(zi, data)
            print(f"  {name}  {len(data)} バイト")
    assert not repl, f"前の zip にないファイル: {list(repl)}"
    os.replace(tmp, new)
    print("書き出し:", new, os.path.getsize(new), "バイト")


if __name__ == "__main__":
    main()
