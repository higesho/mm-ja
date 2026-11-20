"""呪文名の割れを調べる: SPELLS.TXT の名前（:2）の訳が、同じ英語名を含む ITEMS・Global・NPCTOPIC の訳に入っているか"""
import os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect
from extract import unesc
en = collect.en_map()
ja = {}
for l in open(os.path.join(os.path.dirname(__file__), '..', 'translation', 'ja', 'all.tsv'), encoding='utf-8'):
    k, _, v = l.rstrip('\n').partition('\t'); ja[k] = unesc(v)
sp = {}
for k, s in en.items():
    if k.startswith('SPELLS.TXT:') and k.endswith(':2') and k in ja and len(s) > 3:
        sp[s.strip()] = ja[k]
out = []
for k, s in en.items():
    f = k.split(':')[0]
    if f not in ('ITEMS.TXT', 'Global.txt', 'NPCTOPIC.TXT', '2DEvents.txt') or k not in ja:
        continue
    if f == 'ITEMS.TXT' and not k.endswith(':2'):
        continue
    for e, j in sp.items():
        if re.search(r'\b' + re.escape(e) + r'\b', s) and j not in ja[k]:
            out.append(f'{k}\t{s}\t{ja[k]}\t[{e}={j}]')
open(os.path.join(os.path.dirname(__file__), '..', 'translation', 'spell_report.tsv'), 'w', encoding='utf-8').write('\n'.join(out) + '\n')
print(len(out))
