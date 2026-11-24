# マイト・アンド・マジック2 日本語化 ソース

DOS 版 Might and Magic 2 用の常駐プログラム MM2JP.COM と訳のデータ MM2JP.DAT を組み立てる道具です。

- `tools/extract.py` / `tools/extract_data.py` … MM2.EXE・*.OVL と出来事・品物・怪物のデータから訳す文を抜き出す（`lzw.py` で解凍）
- `tools/make_work.py` / `tools/collect.py` … 訳す組を作る・訳を集めて検査する（`jpcommon.py` は折り返し・禁則の共通部分）
- `tools/build_mm2jp.py` … MM2JP.COM と MM2JP.DAT を組み立てる（`asm16.py` で 16 ビットのコードを作る）
- `tools/make_dist.py` … 配布用の zip を作る
- 配布物の `DOSBOX/opengl32.dll` は第1部と同じ物（`../mm1/gl/`）

組み立て: Python 3 と capstone・keystone-engine・Pillow を入れ、
`python tools/build_mm2jp.py <ゲームのフォルダ> <訳のファイル ja.txt> <出力のフォルダ>`。

ゲーム本体（GOG 版）、訳のファイル、美咲フォント（misaki_gothic_2nd.bdf、`font/` に置く）は各自で用意してください。
