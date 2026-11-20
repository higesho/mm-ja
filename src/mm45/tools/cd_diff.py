# -*- coding: utf-8 -*-
"""CD 版（2 枚組 CD のトーキー版）とフロッピー版で文が違う所を書き出す。

python -I tools/cd_diff.py <CD 版の CC があるフォルダ> [出力 tsv]
出力（既定 translation/cd_diff.tsv）: 番号  フロッピー版の英文  CD 版の英文  今の訳
番号は cc_en.tsv と同じ（X:7C91:3 など）。文の数と並びはどのファイルも同じ（違えば止まる）。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cc
import constants as C
from gather import gather_cc
from common import ROOT

ARC = {'X': 'XEEN.CC', 'D': 'DARK.CC', 'I': 'INTRO.CC'}


def load(path):
    data = open(path, 'rb').read()
    return {fid: bytes(b ^ 0x35 for b in data[off:off + size]) for fid, off, size in cc.read_index(data)}


def main():
    cd_dir = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'translation', 'cd_diff.tsv')
    game = os.path.normpath(os.path.join(ROOT, '..'))
    rows, trans, _ = gather_cc()
    fids = sorted({tuple(r[0].split(':')[:2]) for r in rows})
    out = []
    cache = {}
    for arc in ARC:
        cache[arc] = (load(os.path.join(game, ARC[arc])), load(os.path.join(cd_dir, ARC[arc])))
    nfile = 0
    for arc, fid in fids:
        A, B = cache[arc]
        i = int(fid, 16)
        a, b = A.get(i), B.get(i)
        if a == b:
            continue
        if b is None:
            print('CD 版にない:', arc, fid)
            continue
        sa, sb = a.split(b'\0'), b.split(b'\0')
        assert len(sa) == len(sb), (arc, fid, len(sa), len(sb))
        nfile += 1
        for n, (x, y) in enumerate(zip(sa, sb)):
            if x != y:
                k = '%s:%s:%d' % (arc, fid, n)
                out.append('\t'.join([k, C.esc(x), C.esc(y), trans.get(k, '')]))
    with open(outp, 'w', encoding='utf-8', newline='\n') as f:
        f.write('番号\tフロッピー版\tCD 版\t今の訳\n')
        f.write('\n'.join(out) + '\n')
    print('違うファイル %d、違う文 %d → %s' % (nfile, len(out), outp))


if __name__ == '__main__':
    main()
