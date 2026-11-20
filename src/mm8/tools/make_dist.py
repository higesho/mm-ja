"""配布物を作る。

dist/マイト・アンド・マジック8日本語化パッチ/ に dinput.dll、jp/mm8jp.dat、はじめにお読みください.txt を置き、
dist/MightAndMagic8_JP.zip と dist/マイト・アンド・マジック8日本語化パッチ.zip（どちらもフォルダなし）を作る。
使い方: python tools/make_dist.py
"""
import os, shutil, sys, zipfile, struct

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.normpath(os.path.join(HERE, '..'))
GAME = os.path.normpath(os.path.join(WORK, '..'))
DIST = os.path.join(WORK, 'dist')
SRC = os.path.join(DIST, 'マイト・アンド・マジック8日本語化パッチ')

dll = os.path.join(WORK, 'build', 'dinput.dll')
dat = os.path.join(GAME, 'jp', 'mm8jp.dat')
readme = os.path.join(WORK, 'dist_readme.txt')

# 検査: dat の頭、DLL の書き出し
d = open(dat, 'rb').read()
assert d[:8] == b'MM8JPDAT', 'dat の形が違う'
assert b'DirectInputCreateA' in open(dll, 'rb').read(), 'DLL に DirectInputCreateA がない'
# 原作の文が入っていないこと（英語の長い文が素通しになっていない）
import re
eng = re.findall(rb'[A-Za-z ,.\'!?]{60,}', d)
assert len(eng) < 30, f'英語の長い文が {len(eng)} か所ある'

if os.path.exists(SRC):
    shutil.rmtree(SRC)
os.makedirs(os.path.join(SRC, 'jp'))
shutil.copyfile(dll, os.path.join(SRC, 'dinput.dll'))
shutil.copyfile(dat, os.path.join(SRC, 'jp', 'mm8jp.dat'))
text = open(readme, encoding='utf-8').read().replace('\r\n', '\n').rstrip('\n')
open(os.path.join(SRC, 'はじめにお読みください.txt'), 'wb').write(
    b'\xef\xbb\xbf' + text.replace('\n', '\r\n').encode('utf-8'))

names = ['dinput.dll', 'jp/mm8jp.dat', 'はじめにお読みください.txt']
for zname in ['MightAndMagic8_JP.zip', 'マイト・アンド・マジック8日本語化パッチ.zip']:
    zpath = os.path.join(DIST, zname)
    tmp = zpath + '.tmp'
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zf:
        for n in names:
            zf.write(os.path.join(SRC, n.replace('/', os.sep)), n)
    os.replace(tmp, zpath)
    print('作成:', zpath, os.path.getsize(zpath), 'バイト')
