# 配布物を作る
#   dist/マイト・アンド・マジック1日本語化パッチ/ に MMJP.COM、dosboxMM1_single.conf、はじめにお読みください.txt を置き、
#   dist/MightAndMagic1_JP.zip と dist/マイト・アンド・マジック1日本語化パッチ.zip（どちらもフォルダなしで3ファイル）を作る
# 使い方: python make_dist.py <ゲームのフォルダ> <MMJP.COM> <説明書の元（UTF-8）> <dist フォルダ>
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")
game, com, readme_src, dist = sys.argv[1:5]
src = os.path.join(dist, "マイト・アンド・マジック1日本語化パッチ")
os.makedirs(src, exist_ok=True)

# 起動設定: GOG 版の dosboxMM1_single.conf に、MMJP の起動を足す（改行は CRLF のまま）
#   画面の種類は GOG 版の dosboxMM1.conf がもともと svga_s3 なので変えない
conf = open(os.path.join(game, "dosboxMM1_single.conf"), "rb").read().decode("latin-1")
assert "\r\nmm.exe\r\n" in conf
conf = conf.replace("\r\nmm.exe\r\n", "\r\nMMJP\r\nmm.exe\r\n", 1)
open(os.path.join(src, "dosboxMM1_single.conf"), "wb").write(conf.encode("latin-1"))

shutil.copyfile(com, os.path.join(src, "MMJP.COM"))

# 説明書: BOM 付き UTF-8、改行は CRLF
text = open(readme_src, encoding="utf-8").read().replace("\r\n", "\n").rstrip("\n")
open(os.path.join(src, "はじめにお読みください.txt"), "wb").write(
    b"\xef\xbb\xbf" + text.replace("\n", "\r\n").encode("utf-8"))

names = ["MMJP.COM", "dosboxMM1_single.conf", "はじめにお読みください.txt"]
for zname in ["MightAndMagic1_JP.zip", "マイト・アンド・マジック1日本語化パッチ.zip"]:
    zpath = os.path.join(dist, zname)
    tmp = zpath + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(src, n), n)
    os.replace(tmp, zpath)
    print("作成:", zpath, os.path.getsize(zpath), "バイト")
