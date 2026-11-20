# マイト・アンド・マジック1 日本語化 ソース

DOS 版 Might and Magic 1 用の常駐プログラム MMJP.COM（DOSBox の中で動き、文を日本語にして描く）を組み立てる道具です。

- `tools/extract.py` … MM.EXE・*.OVR から訳す文と参照元を抜き出す（`rsm.py` で記号表 MM.RSM を読む）
- `tools/make_work.py` / `tools/collect.py` … 訳す組を作る・訳を集めて検査する
- `tools/build_mmjp.py` … 訳と字の形から MMJP.COM を組み立てる
- `tools/make_dist.py` / `tools/repack.py` … 配布用の zip を作る

組み立て: Python 3 と capstone・keystone-engine・Pillow を入れ、
`python tools/build_mmjp.py <MM.EXE> <訳のファイル> <出力 MMJP.COM>`。

ゲーム本体（GOG 版）、訳のファイル、美咲フォント（misaki_gothic_2nd.bdf、`font/` に置く）は各自で用意してください。
