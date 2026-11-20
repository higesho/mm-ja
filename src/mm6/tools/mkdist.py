"""配布用の zip（dist/MightAndMagic6_JP.zip）を作る。

中身: ddraw.dll（日本語化の本体）、mm6jp_text.bin（訳文と原文の CRC だけ。原文は入れない）、
      mm6jp_font.bin（PixelMplus から作った字形）、mm6jp.ini、説明書、フォントのライセンス
"""
import os, sys, zipfile, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B

WORK = B.WORK
DIST = os.path.join(WORK, 'dist')


def main():
    os.makedirs(DIST, exist_ok=True)
    files = [
        (os.path.join(WORK, 'dll', 'out', 'ddraw.dll'), 'ddraw.dll'),
        (os.path.join(WORK, 'out', 'mm6jp_text.bin'), 'mm6jp_text.bin'),
        (os.path.join(WORK, 'out', 'mm6jp_font.bin'), 'mm6jp_font.bin'),
        (os.path.join(WORK, 'dist_files', 'mm6jp.ini'), 'mm6jp.ini'),
        (os.path.join(WORK, 'dist_files', 'MM6日本語化_説明.txt'), 'MM6日本語化_説明.txt'),
        (os.path.join(WORK, 'dist_files', 'PixelMplus_LICENSE.txt'), 'PixelMplus_LICENSE.txt'),
    ]
    # 訳文の中に原文の英文がそのまま入っていないか（念のため）
    t = open(files[1][0], 'rb').read()
    assert t[:4] == b'MJT1'
    zp = os.path.join(DIST, 'MightAndMagic6_JP.zip')
    with zipfile.ZipFile(zp, 'w', zipfile.ZIP_DEFLATED) as z:
        for src, name in files:
            z.write(src, name)
    for src, name in files:
        print('%-26s %9d' % (name, os.path.getsize(src)))
    print(zp, os.path.getsize(zp))


if __name__ == '__main__':
    main()
