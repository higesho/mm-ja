# マイト・アンド・マジック8 日本語化 ソース

GOG 版 Might and Magic 8 用の代理 dinput.dll（日本語の字を描き、文を実行時に訳へ差し替える）と、訳のデータ jp/mm8jp.dat を作る道具です。

- `src/` … dinput.dll の本体（C）。`src/build.bat` で Visual Studio（32 ビット）で組み立てる
- `tools/mkjfont.py` … 東雲フォント（BDF）から字の表 `src/jfont.h` を作る（組み立ての前に必要）
- `tools/lod.py` / `tools/extract.py` … LOD 書庫を読み、訳す文を抜き出す
- `tools/make_work.py` / `tools/collect_glossary.py` … 訳す組と名前の対訳表を作る
- `tools/build_dat.py` … 訳から jp/mm8jp.dat を作る
- `tools/make_dist.py` … 配布用の zip を作る

組み立て: `python tools/mkjfont.py` で jfont.h を作ってから `src/build.bat`、`python tools/build_dat.py`。

ゲーム本体（GOG 版）、訳のファイル、東雲フォント（BDF）は各自で用意してください。
