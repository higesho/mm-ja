# 配布物を作る
#   dist/マイト・アンド・マジック2日本語化パッチ/ に MM2JP.COM、MM2JP.DAT、dosboxMM2_single.conf、はじめにお読みください.txt を置き、
#   dist/MightAndMagic2_JP.zip と dist/マイト・アンド・マジック2日本語化パッチ.zip（どちらもフォルダなしで4ファイル）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "マイト・アンド・マジック2日本語化パッチ")
os.makedirs(src, exist_ok=True)

# 起動設定: GOG 版の dosboxMM2_single.conf に、MM2JP の起動を足す（改行は CRLF のまま）
#   GOG 版の dosboxMM2.conf は umb=true（MM2JP は上位メモリに入る）なので変えない
conf = open(os.path.join(game, "dosboxMM2_single.conf"), "rb").read().decode("latin-1")
assert "\r\nloadfix -4 mm2.exe\r\n" in conf
conf = conf.replace("\r\nloadfix -4 mm2.exe\r\n", "\r\nMM2JP\r\nloadfix -4 mm2.exe\r\n", 1)
open(os.path.join(src, "dosboxMM2_single.conf"), "wb").write(conf.encode("latin-1"))

for n in ("MM2JP.COM", "MM2JP.DAT"):
    shutil.copyfile(os.path.join(build, n), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = ["MM2JP.COM", "MM2JP.DAT", "dosboxMM2_single.conf", "はじめにお読みください.txt"]
for zname in ["MightAndMagic2_JP.zip", "マイト・アンド・マジック2日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト")
