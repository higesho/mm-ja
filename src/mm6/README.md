# マイト・アンド・マジック6 日本語化 ソース

GOG 版 Might and Magic 6 用の代理 ddraw.dll（日本語の字を描き、表や文を実行時に訳へ差し替える）と、訳のデータを作る道具です。

- `dll/` … ddraw.dll の本体（C）。`dll/build.bat` で Visual Studio（32 ビット）で組み立てる
- `tools/lod.py` / `tools/extract_text.py` … icons.lod から表・文字列集を取り出し、訳す欄を抜き出す
- `tools/packets.py` / `tools/names.py` … 訳す組を作る・名前の対訳表を作る
- `tools/build.py` … 訳から mm6jp_text.bin とフォントの mm6jp_font.bin を作る
- `tools/mkdist.py`、`dist_files/mm6jp.ini` … 配布用の zip を作る
- `tools/rebuild.sh` … DLL とデータを作り直してゲームのフォルダへ置く

組み立て: `dll/build.bat` を実行し、`python tools/build.py`（Python 3 と Pillow）。

ゲーム本体（GOG 版）、訳のファイル、PixelMplus フォント（TTF）は各自で用意してください。
