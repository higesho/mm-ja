# 配布物を作る
#   dist/マイト・アンド・マジック3日本語化パッチ/ に MM3JP.COM、MM3JP.DAT、dosboxMM3_single.conf、はじめにお読みください.txt を置き、
#   dist/MightAndMagic3_JP.zip と dist/マイト・アンド・マジック3日本語化パッチ.zip（どちらもフォルダなしで4ファイル）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <build フォルダ> <説明書の元（UTF-8）> <dist フォルダ>
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, build, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "マイト・アンド・マジック3日本語化パッチ")
os.makedirs(src, exist_ok=True)

# 起動設定: GOG 版の dosboxMM3_single.conf のランチャーで、mm3.com の前に MM3JP の常駐を足す（改行は CRLF のまま）
conf = open(os.path.join(game, "dosboxMM3_single.conf"), "rb").read().decode("latin-1")
old = "\r\n:game\r\ncls\r\nmm3.com\r\n"
assert old in conf
conf = conf.replace(old, "\r\n:game\r\ncls\r\nLH MM3JP\r\nmm3.com\r\n", 1)
open(os.path.join(src, "dosboxMM3_single.conf"), "wb").write(conf.encode("latin-1"))

for n in ["MM3JP.COM", "MM3JP.DAT"]:
    shutil.copyfile(os.path.join(build, n), os.path.join(src, n))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = ["MM3JP.COM", "MM3JP.DAT", "dosboxMM3_single.conf", "はじめにお読みください.txt"]
for zname in ["MightAndMagic3_JP.zip", "マイト・アンド・マジック3日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト")
