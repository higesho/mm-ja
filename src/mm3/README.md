# マイト・アンド・マジックIII 日本語化 ソース

DOS 版 Might and Magic III 用の常駐プログラム MM3JP.COM と訳のデータ MM3JP.DAT を組み立てる道具です。

- `tools/emu.py` … MM3.EXE を模擬実行して、解いた後のメモリ像 build/mem.bin を作る
- `tools/extract.py` / `tools/ds_refs.py` / `tools/answers.py` … 訳す文・参照・答えの言葉を抜き出す
- `tools/cc.py` / `tools/ccx.py` / `tools/lzhuf.py` … MM3.CC 書庫の読み書きと解凍
- `tools/textfmt.py` … 文の中の書式の記号の扱い
- `tools/make_work.py` / `tools/collect.py` … 訳す組を作る・訳を集めて検査する
- `tools/build_mm3jp.py` … MM3JP.COM と MM3JP.DAT を組み立てる
- `tools/make_dist.py` … 配布用の zip を作る

組み立て: Python 3 と capstone・keystone-engine・unicorn・Pillow を入れ、`emu.py` → `extract.py` → `build_mm3jp.py` の順に動かします。

ゲーム本体（GOG 版）、訳のファイル、美咲フォント（misaki_gothic_2nd.bdf、`font/` に置く）は各自で用意してください。
