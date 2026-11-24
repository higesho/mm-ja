# マイト・アンド・マジック7 日本語化 ソース

GOG 版 Might and Magic 7 用の代理 dinput.dll（日本語の字を描き、表や文を実行時に訳へ差し替える）と、訳の表を作る道具です。

- `dll/mm7jp.c`・`dll/lodpatch.inc`・`dll/dinput.def`・`dll/mm7jp.rc`（バージョン情報） … dinput.dll の本体。`dll/build.bat` で Visual Studio（32 ビット）で組み立てる
- `tools/mkjfont.py` … 東雲フォント（BDF）から字の表 `dll/jfont.h` を作る（組み立ての前に必要）
- `tools/lod.py` / `tools/tables.py` / `tools/extract.py` … LOD 書庫と txt 表・STR を読み、訳す文を抜き出す
- `tools/make_work.py` / `tools/collect.py` / `tools/make_review.py` … 訳す組を作る・集める・読み直しの組を作る
- `tools/check_all.py` / `tools/check_spells.py` / `tools/check_terms.py` … 訳の検査
- `tools/build.py` … 訳を集めてゲームが読む形に書き出す
- `tools/make_dist.py` … 配布用の zip を作る

組み立て: `python tools/mkjfont.py` で jfont.h を作ってから `dll/build.bat`。

`dll/build.bat test` は試験用の仕組み（`MM7JP_TEST`）を入れた試験版を `dll/test/dinput.dll` に作ります。試験版は配布しません。

ゲーム本体（GOG 版）、訳のファイル、東雲フォント（BDF）は各自で用意してください。
