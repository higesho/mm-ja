# -*- coding: utf-8 -*-
"""配布物（dist/ソード・オブ・ジーン日本語化パッチ/ と dist/SwordsOfXeen_JP.zip）を作る。

前もって作っておくもの:
  - build/ja/xeen_ja.dat                  （tools/build_ja.py）
  - build/msvc_pub/Releasex64/scummvm.exe  （公開用 ScummVM。試験用の仕掛けなし、ウインドウ型）
文書の {SOURCE_URL} は、引数で渡した URL に置き換える。

使い方: python -I tools/make_dist.py [ソースの URL]
"""
import sys, os, shutil, glob, zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DIST = os.path.join(ROOT, 'dist')
NAME = 'ソード・オブ・ジーン日本語化パッチ'
OUT = os.path.join(DIST, NAME)
ZIP = os.path.join(DIST, 'SwordsOfXeen_JP.zip')
SRC_URL = sys.argv[1] if len(sys.argv) > 1 else '（公開時に記入）'

JA_DAT = os.path.join(ROOT, 'build', 'ja', 'xeen_ja.dat')
SVM_EXE = os.path.join(ROOT, 'build', 'msvc_pub', 'Releasex64', 'scummvm.exe')
SDL_DLL = os.path.join(ROOT, 'build', 'libs', 'lib', 'x64', 'SDL2.dll')
SVM_SRC = os.path.join(ROOT, 'build', 'scummvm-src')
SDL_LIC = os.path.join(ROOT, '..', '..', 'Ultima 8', 'jp_work', 'build', 'sdl2', 'SDL2-2.32.10', 'LICENSE.txt')


def text_out(src, dst):
    """文書を BOM 付き UTF-8・CRLF で書く（メモ帳で確実に読めるように）。"""
    t = open(src, encoding='utf-8-sig').read().replace('\r\n', '\n').replace('{SOURCE_URL}', SRC_URL)
    open(dst, 'w', encoding='utf-8-sig', newline='\r\n').write(t)


def main():
    for p in (JA_DAT, SVM_EXE, SDL_DLL, SDL_LIC):
        if not os.path.exists(p):
            sys.exit('見つからない: ' + p)
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    sv = os.path.join(OUT, 'ScummVM-XeenJP')
    os.makedirs(sv)
    os.makedirs(os.path.join(OUT, 'フォントのライセンス'))
    files = os.path.join(DIST, 'files')

    shutil.copy(JA_DAT, OUT)
    shutil.copy(os.path.join(files, 'ソード・オブ・ジーン日本語版.bat'), OUT)
    text_out(os.path.join(files, 'はじめにお読みください.txt'), os.path.join(OUT, 'はじめにお読みください.txt'))

    shutil.copy(SVM_EXE, sv)
    shutil.copy(SDL_DLL, sv)
    shutil.copy(os.path.join(files, 'ScummVM-XeenJP', 'scummvm-xeenjp.ini'), sv)
    text_out(os.path.join(files, 'ScummVM-XeenJP', '非公式ビルドについて.txt'), os.path.join(sv, '非公式ビルドについて.txt'))
    shutil.copy(os.path.join(SVM_SRC, 'COPYING'), os.path.join(sv, 'COPYING.txt'))
    shutil.copy(os.path.join(SVM_SRC, 'COPYRIGHT'), os.path.join(sv, 'COPYRIGHT.txt'))
    shutil.copy(os.path.join(SVM_SRC, 'AUTHORS'), os.path.join(sv, 'AUTHORS.txt'))
    for f in glob.glob(os.path.join(SVM_SRC, 'LICENSES', '*')):
        b = os.path.basename(f)
        shutil.copy(f, os.path.join(sv, b if b.endswith('.txt') else b + '.txt'))
    shutil.copy(SDL_LIC, os.path.join(sv, 'SDL2-LICENSE.txt'))

    # 美咲フォントの説明（MM1 と同じく readme を付ける）
    for f in ('readme.txt', 'misaki.txt'):
        p = os.path.join(ROOT, 'font', f)
        if os.path.exists(p):
            shutil.copy(p, os.path.join(OUT, 'フォントのライセンス', '美咲フォント_' + f))

    if os.path.exists(ZIP):
        os.remove(ZIP)
    with zipfile.ZipFile(ZIP, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, dirs, fs in os.walk(OUT):
            for f in sorted(fs):
                p = os.path.join(base, f)
                z.write(p, os.path.relpath(p, DIST))
    n = sum(len(fs) for _, _, fs in os.walk(OUT))
    print('配布物: %s（%d ファイル）' % (OUT, n))
    print('zip: %s（%.1f MB）' % (ZIP, os.path.getsize(ZIP) / 1048576))


main()
