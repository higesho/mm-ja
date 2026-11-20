# ワールド・オブ・ジーン（マイト・アンド・マジック 4-5）日本語化 ソース

ScummVM の非公式ビルド用の日本語データ xeen_ja.dat と字の形の表を作る道具、配布物の起動用ファイルです。

エンジン部分（ScummVM の改造）はここには入っていません。フォーク
[higesho/scummvm](https://github.com/higesho/scummvm) の `ja` ブランチにあり、元のライセンス（GPL）に従います。

- `tools/extract.py` … XEEN.CC・DARK.CC・INTRO.CC から訳す文を抜き出す（`cc.py` は CC 書庫の読み書き）
- `tools/constants.py` … ScummVM の mm.dat の中の定数（画面の部品の文）を読み書きする
- `tools/make_work.py` / `tools/gather.py` / `tools/check.py` / `tools/terms.py` / `tools/common.py` … 訳す組を作る・集める・検査する
- `tools/cd_diff.py` … CD 版とフロッピー版の文の違いを書き出す
- `tools/build_ja.py` … 訳から xeen_ja.dat を組み立てる
- `tools/build_font.py` / `tools/build_font12.py` … 美咲フォント・東雲フォント（BDF）から font_ja.bin・font_ja12.bin を作る
- `tools/add_vorbis.py` … ScummVM の VS プロジェクトに Ogg Vorbis を足す
- `build/vsbuild.bat` … ScummVM を Visual Studio で組み立てる
- `tools/make_dist.py`、`dist/files/` … 配布物の起動用 bat・設定・CD 版の準備スクリプト

組み立て: Python 3 を入れ、`python tools/extract.py` → 訳を置く → `python tools/build_ja.py`。

ゲーム本体（GOG 版）、訳のファイル、フォント（BDF）は各自で用意してください。
