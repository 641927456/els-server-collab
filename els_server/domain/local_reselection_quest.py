"""Local registration of the native first-class re-selection quest 39480.

The pinned client ships this task ([转职变更] 新的选择机会, NPC 10025,
level 15-34, reward 135871 1转晋级宝箱（3日）+ 135872 1转变更券) but the
merged quest catalog never admitted it, so acceptance failed with the
generic "quest unknown" rejection. The definitions below are the exact
native client records with three documented local deviations (see the
data file's deviations field).
"""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    path=PROJECT_ROOT/'els_server/data/local_reselection_quest.json'
    raw=path.read_bytes();manifest=json.loads(path.with_suffix('.manifest.json').read_text(encoding='utf8'))
    row=json.loads(raw);data=client_data()
    if (manifest['schema_version']!=1 or row['schema_version']!=1
        or manifest['client_sha256']!=CLIENT_SHA or row['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=manifest['payload_sha256']
        or row['catalog_sha256']!=data.manifest['catalog_sha256']
        or len(row['quests'])!=manifest['quests'] or len(row['subquests'])!=manifest['subquests']):
        raise ValueError('Local reselection quest catalog identity')
    quest=row['quests']['39480'];sub=row['subquests']['39480']
    # Deviation guards: the local schedule must stay one-time and both
    # rewards must stay permanent grants, or the local claim path changes.
    if quest['m_bRepeat'] or quest['m_eRepeatType']:raise ValueError('Local reselection schedule deviation')
    if any(r['m_iPeriod'] for r in quest['Reward']['m_vecItem'].values()):raise ValueError('Local reselection reward deviation')
    if sub['m_eClearType']!=32 or sub['m_ClearCondition']['m_iDungeonClearCount']!=2:raise ValueError('Local reselection objective source')
    return row

# Bounded reward readers, pinned-record style (no native grant receipt is
# claimed): exact client record digest plus the classification bytes.
_PINNED_REWARDS={
    # 1转晋级宝箱（3日）: type7, metadata0, stack word 0 (nonstackable).
    135871:dict(record_sha256='5be99248c661c81f0c728eeb80d948911256c0c0f16468df3729c757e43aa69a',
                flags4=4198402,flags8=56,stack_word=0),
    # 1转变更券: type7, metadata0, stack word 0 (nonstackable).
    135872:dict(record_sha256='49e73da53e290883c6428f88501715f5b261bd442141fed4db012a22114c5a48',
                flags4=2101258,flags8=56,stack_word=0),
}

def reward_item_definitions():
    """template/metadata/group/max_stack rows for the inventory merge."""
    import struct
    data=client_data()
    rows=[]
    for template,expected in _PINNED_REWARDS.items():
        item=data.item(template)
        raw=item['record']
        if (item['item_type']!=7 or item['metadata']!=0
            or item['flags4']!=expected['flags4'] or item['flags8']!=expected['flags8']
            or struct.unpack_from('<I',raw,0x10)[0]!=expected['stack_word']
            or hashlib.sha256(raw).hexdigest()!=expected['record_sha256']):
            raise ValueError('Local reselection reward resource')
        # Local policy: consumable bag 4 (the career ticket reader requires
        # group 4), single-instance like the native nonstackable source.
        rows.append(dict(template=template,metadata=0,group=4,max_stack=1))
    return rows
