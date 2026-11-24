# マイト・アンド・マジック9 日本語化 ソース

GOG 版 Might and Magic 9 用の代理 dinput.dll（日本語の字を描く）と、日本語のデータを作る道具、配布用の MM9JP.exe（手元のゲームのファイルから日本語のファイルを作る）です。

- `src/` … dinput.dll の本体（C++）。`src/build.bat`（試験用）・`src/build_release.bat`（配布用）で Visual Studio（32 ビット）で組み立てる
  - バージョン情報は `src/mm9jp.rc`（`build_release.bat` が組み込む）
- `src/installer/` … MM9JP.exe。`build_setup.bat` で組み立てる（差分データ mm9jp.dlt を同じフォルダに置く。バージョン情報は `mm9jp_setup.rc`）
- `tools/rez.py` / `tools/table.py` / `tools/spec.py` / `tools/extract.py` … REZ 書庫と表を読み、訳す文を抜き出す
- `tools/make_work.py` / `tools/collect.py` / `tools/jpenc.py` … 訳す組を作る・集める・自前の符号にする
- `tools/make_jpfont.py` … 字の表（アトラス）と符号表を作る
- `tools/build_jp.py` / `tools/make_images.py` … 訳を当てたデータ・画像を作る（numpy・opencv-python・Pillow を使う）
- `tools/make_delta.py` / `tools/make_dist.py` … 差分データ mm9jp.dlt と配布物を作る

組み立て: `python tools/build_jp.py` → `python tools/make_images.py` → `python tools/make_dist.py`、DLL は `src/build_release.bat`。

ゲーム本体（GOG 版）、訳のファイル、フォントは各自で用意してください。
