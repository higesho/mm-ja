# -*- coding: utf-8 -*-
"""配布物を作る。
  1. build/jpdata（build_jp.py と make_images.py の出力）から差分 src/installer/mm9jp.dlt を作る
  2. MM9JP.exe をビルドする（差分をリソースに入れる）
  3. dist/マイト・アンド・マジック9日本語化パッチ/ に MM9JP.exe・dinput.dll（試験の仕掛けは game\\mm9jp_test.txt が
     無ければ働かない）・元に戻す.bat・はじめにお読みください.txt を置き、dist/MightAndMagic9_JP.zip を作る
python tools/make_dist.py [サイトの URL]
"""
import os
import sys
import shutil
import subprocess
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
DIST = os.path.join(ROOT, 'dist')
PKG = os.path.join(DIST, 'マイト・アンド・マジック9日本語化パッチ')
URL = sys.argv[1] if len(sys.argv) > 1 else 'https://higesho.github.io/mm-ja/mm9/'


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    subprocess.check_call([sys.executable, os.path.join(ROOT, 'tools', 'make_delta.py'),
                           os.path.join(ROOT, 'src', 'installer', 'mm9jp.dlt')])
    subprocess.check_call(['cmd', '/c', os.path.join(ROOT, 'src', 'installer', 'build_setup.bat')])
    subprocess.check_call(['cmd', '/c', os.path.join(ROOT, 'src', 'build_release.bat')])
    if os.path.exists(PKG):
        shutil.rmtree(PKG)
    os.makedirs(PKG)
    shutil.copyfile(os.path.join(ROOT, 'src', 'installer', 'MM9JP.exe'), os.path.join(PKG, 'MM9JP.exe'))
    shutil.copyfile(os.path.join(ROOT, 'build', 'release', 'dinput.dll'), os.path.join(PKG, 'dinput.dll'))
    bat = '@echo off\r\ncd /d "%~dp0"\r\nMM9JP.exe /uninstall\r\n'
    open(os.path.join(PKG, '元に戻す.bat'), 'wb').write(bat.encode('cp932'))
    text = open(os.path.join(ROOT, 'release', 'readme.txt'), encoding='utf-8').read().replace('{SITE_URL}', URL)
    text = text.replace('\r\n', '\n').rstrip('\n').replace('\n', '\r\n') + '\r\n'
    open(os.path.join(PKG, 'はじめにお読みください.txt'), 'wb').write(b'\xef\xbb\xbf' + text.encode('utf-8'))
    zpath = os.path.join(DIST, 'MightAndMagic9_JP.zip')
    tmp = zpath + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for n in sorted(os.listdir(PKG)):
            zf.write(os.path.join(PKG, n), n)
    os.replace(tmp, zpath)
    print('作成:', zpath, os.path.getsize(zpath), 'バイト')


if __name__ == '__main__':
    main()
