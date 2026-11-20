# -*- coding: utf-8 -*-
"""訳すファイルと欄の定義。

各項目: (組の名, REZ 内の道筋, 形式, 欄, 鍵に使う欄, 最初の行を飛ばすか)
  形式: 'csv' / 'tsv' / 'lines'（1行1件）
  欄: 訳す欄の番号のリスト（lines では無視）
"""

DATA = [
    # 組,          道筋,                                      形式,  欄,                         鍵欄, 見出し行
    ('gametext',   'DATA/GAMETEXT.TXT',                       'lines', None,                     None, False),
    ('book',       'DATA/BOOK AND SCROLL TEXT.CSV',           'csv', [1, 2, 3],                  0,    False),
    ('journal',    'DATA/JOURNAL.TXT',                        'tsv', [1, 2],                     0,    True),
    ('skill',      'DATA/SKILL AND MASTERY DESC.CSV',         'csv', [0, 1, 2, 3, 4, 5],         None, True),
    ('statdesc',   'DATA/STATDESC.CSV',                       'csv', [1],                        0,    True),
    ('item',       'DATA/MASTERITEMLIST.CSV',                 'csv', [1, 8],                     0,    False),
    ('concat',     'DATA/CONCAT.CSV',                         'csv', [1, 24],                    0,    False),
    ('spell',      'DATA/SPELL.TXT',                          'tsv', [8, 9, 18, 19, 28, 29, 38, 39, 48], 0, True),
    ('shops',      'DATA/MMIXSHOPS.TXT',                      'tsv', [0],                        1,    True),
    ('mapstats',   'DATA/MAPSTATS.TXT',                       'tsv', [1],                        0,    True),
    ('scripttext', 'SCRIPTS/MMIXSCRIPTTEXT.CSV',              'csv', [1],                        0,    False),
    ('npcname',    'RUDE/NPCNAME.RUDE',                       'csv', [1],                        0,    False),
    ('blurb',      'RUDE/TOPBLURB.RUDE',                      'csv', [2],                        0,    False),
]

PCVOICES = ['Angry', 'Arrogant', 'Assertive', 'Cowardly', 'Dim', 'HalfOrcLich', 'Happy', 'Lich', 'Sarcastic']

# REZ ファイルと、その中の道筋の頭
REZ_OF = {'DATA': 'DATA.REZ', 'RUDE': 'RUDE.REZ', 'SCRIPTS': 'SCRIPTS.REZ'}
