# マイト・アンド・マジック1 日本語化 ソース

DOS 版 Might and Magic 1 用の常駐プログラム MMJP.COM（DOSBox の中で動き、文を日本語にして描く）を組み立てる道具です。

- `tools/extract.py` … MM.EXE・*.OVR から訳す文と参照元を抜き出す（`rsm.py` で記号表 MM.RSM を読む）
- `tools/make_work.py` / `tools/collect.py` … 訳す組を作る・訳を集めて検査する
- `tools/build_mmjp.py` … 訳と字の形から MMJP.COM を組み立てる
- `tools/make_dist.py` / `tools/repack.py` … 配布用の zip を作る
- `gl/` … DOSBox の DOSBOX フォルダに置く opengl32.dll の代わり（窓の大きさの変更と、東雲フォントでの描き直し）。第1〜3部の配布物に同じものが入る
  - `build.bat`（Visual Studio 2022 Build Tools の x86）で配布版 `out/opengl32.dll`、`build.bat test` で試験版 `out/test/opengl32.dll` を作る。試験版は配布しない
  - 組み立てには `exports.h`（本物の opengl32.dll の関数の表）と `glyphs.h`（美咲フォント → 東雲フォントの字の表）が要る。どちらも ultima-ja の `src/ultima1/gl/gen.py` で作る物で、ここには入れていない
  - `ultima_ja.ini` は設定の見本

組み立て: Python 3 と capstone・keystone-engine・Pillow を入れ、
`python tools/build_mmjp.py <MM.EXE> <訳のファイル> <出力 MMJP.COM>`。

ゲーム本体（GOG 版）、訳のファイル、美咲フォント（misaki_gothic_2nd.bdf、`font/` に置く）は各自で用意してください。
