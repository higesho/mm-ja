# -*- coding: utf-8 -*-
"""訳の道具の共通部分（読み込み、用語集、制御の印・埋め込みの取り出し）。"""
import os, re, glob

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
TR = os.path.join(ROOT, 'translation')

# 訳さない定数（ファイル名、音、Swords of Xeen だけのもの、ロシア語版だけのもの）
CONST_SKIP = {
    'SURFACE_NAMES', 'TOWN_ACTION_MUSIC', 'TOWN_ACTION_SHAPES', 'EVENT_SAMPLES', 'MUSIC_FILES1', 'MUSIC_FILES2',
    'CLOUDS_MAE_NAMES', 'CLOUDS_MIRROR_LOCATIONS', 'CLOUDS_MAP_NAMES', 'CLOUDS_MONSTERS', 'CLOUDS_SPELLS',
    'QUEST_ITEM_NAMES_SWORDS', 'SWORDS_CREDITS1', 'SWORDS_CREDITS2', 'TOWN_PORTAL_SWORDS', 'GOOBER',
}
# 用語集から埋める定数（名前の表）。用語集の種類
CONST_GLOSSARY = {
    'RACE_NAMES': '種族', 'CLASS_NAMES': '職業', 'ALIGNMENT_NAMES': '性格', 'SEX_NAMES': '性別',
    'SKILL_NAMES': '技能', 'CONDITION_NAMES_M': '状態', 'CONDITION_NAMES_F': '状態', 'STAT_NAMES': '能力値',
    'WEAPON_NAMES': '武器', 'ARMOR_NAMES': '防具', 'ACCESSORY_NAMES': '装身具', 'MISC_NAMES': '道具',
    'SPECIAL_NAMES': '特殊', 'ELEMENTAL_NAMES': '属性', 'ATTRIBUTE_NAMES': '能力', 'EFFECTIVENESS_NAMES': '効果',
    'BONUS_NAMES': '強化', 'QUEST_ITEM_NAMES': 'クエスト品', 'MONSTER_SPECIAL_ATTACKS': '特殊攻撃',
    'RATING_TEXT': '評価', 'WEEK_DAY_STRINGS': '曜日', 'TERRAIN_TYPES': '地形', 'OUTDOORS_WALL_TYPES': '壁',
}


def const_base(key):
    return re.sub(r'\[\d+\]$', '', key)


def read_tsv(path, ncol=None):
    rows = []
    for line in open(path, encoding='utf-8-sig'):
        line = line.rstrip('\n').rstrip('\r')
        if not line or line.startswith('#'):
            continue
        p = line.split('\t')
        rows.append(p)
    return rows


def load_trans(pattern):
    """「鍵<TAB>訳」のファイル群 → 辞書（後のファイルが勝つ）。"""
    d = {}
    for p in sorted(glob.glob(pattern)):
        for ln, line in enumerate(open(p, encoding='utf-8-sig'), 1):
            line = line.rstrip('\n').rstrip('\r')
            if not line or line.startswith('#'):
                continue
            if '\t' not in line:
                continue
            k, v = line.split('\t', 1)
            d[k] = v
    return d


def load_glossary():
    """用語集.tsv: (種類, 英語) → 訳、英語 → 訳。"""
    by_kind, by_en = {}, {}
    p = os.path.join(TR, '用語集.tsv')
    if not os.path.exists(p):
        return by_kind, by_en
    for r in read_tsv(p):
        if len(r) < 3:
            continue
        kind, en, ja = r[0], r[1], r[2]
        by_kind[(kind, en)] = ja
        by_en.setdefault(en, ja)
        # 前後の空白や \t100 などを除いた形でも引けるように
        core = split_affix(en)[1].strip()
        if core and core != en:
            by_kind.setdefault((kind, core), ja.strip())
            by_en.setdefault(core, ja.strip())
    return by_kind, by_en


# 制御の印（エスケープした形）: \n \r \t123 \v123 \f12 \fd \x03c \x01 \x02 \x04123 \x07123 \x08 \x05 \x06 \xNN
CTRL_RE = re.compile(r'\\n|\\r|\\t\d{3}|\\v\d{3}|\\f(?:\d\d|d)|\\x03[clr]|\\x0[4]\d{3}|\\x07\d{3}|\\x[0-9A-F]{2}|\\\\')
FMT_RE = re.compile(r'%[-+ #0]*\d*(?:\.\d+)?[sducxX%]')


def ctrl_tokens(s):
    return CTRL_RE.findall(s)


def fmt_tokens(s):
    return [t for t in FMT_RE.findall(s) if t != '%%']


def split_affix(en):
    """英文を（前の制御・空白、中身、後ろの制御・空白）に分ける。"""
    m = re.match(r'^((?:\\[nr]|\\[tv]\d{3}|\\f(?:\d\d|d)|\\x03[clr]|\\x0[12]| )*)(.*?)((?:\\[tv]\d{3}|\\f(?:\d\d|d)|\\x03[clr]|\\x0[12]|\\n| )*)$', en)
    return m.group(1), m.group(2), m.group(3)
