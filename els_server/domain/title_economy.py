"""Owned title's dungeon economy, separate from native combat/HP effects.

Rates come from current tables. Float32 product/truncation and positive ED
minimum one reuse legacy reward semantics as bounded local compatibility;
current CN rounding and stacking with other bonus sources remain unverified.
Conditional effects require the server's committed/issued dungeon identity,
current enum DT_SECRET3 and explicit current dungeon table type3.
"""
import functools,struct,time
from els_server.domain.title_option_data import catalog

ED='m_fIncreaseEDPercent';EXP='m_fIncreaseDCBExpPercent'
REVIEWED=frozenset((20205,20210,20215,20305,20307,20308,20310,60914,60928,74044,74097,87017))
CONDITIONAL=frozenset((200164,200167,300006))
HELD=frozenset()
_GROUPS={'m_setMonsterIDForDamageUp','m_SkillLevelUpID','m_SetMonsterIDDamageReduced','m_setMonsterIDForEvade'}
f32=lambda v:struct.unpack('<f',struct.pack('<f',v))[0]

@functools.lru_cache(maxsize=1)
def effects():
    result={}
    for key in REVIEWED|CONDITIONAL:
        row=catalog()[key];field=ED if ED in row else EXP
        if key in CONDITIONAL:
            expected={'ID',field,'TYPE','STAT','DUNGEON_ONLY','DUNGEON_ONLY_TYPE'}
            if key in (200164,200167):expected.add('m_bUseDescEvadeByMonsterAttack')
            if row.get('DUNGEON_ONLY_TYPE')!=3 or row.get('m_bUseDescEvadeByMonsterAttack',1)!=1:raise ValueError('Unreviewed conditional title economy')
        else:
            expected={'ID',field,'TYPE','STAT'}|_GROUPS
            if key not in (60914,60928):expected.add('DUNGEON_ONLY')
            if any(row[k]!='Group 0' for k in _GROUPS):raise ValueError('Unreviewed grouped title economy')
        if set(row)!=expected or row['STAT'] or row['TYPE']!=(1 if key in (60914,60928) else 7) or row.get('DUNGEON_ONLY',1)!=1:raise ValueError('Unreviewed title economy condition')
        value=row[field]
        if type(value) not in (int,float) or not 0<value<=1:raise ValueError('Title economy rate bound')
        result[key]=(field,f32(value),row.get('DUNGEON_ONLY_TYPE',0))
    return result

def bonus(base,rate,*,ed=False):
    if not base or not rate:return 0
    value=int(f32(f32(base)*rate))
    return max(1,value) if ed else value

@functools.lru_cache(maxsize=740)
def dungeon_type(dungeon):
    from els_server.game_data import client_data
    data=client_data()
    if data.resource('Enum.lua')['DUNGEON_TYPE']['DT_SECRET']!=3:raise ValueError('Current secret dungeon enum changed')
    # Missing type does not establish any conditional mode, including secret.
    mode=data.dungeon(dungeon).get('m_eDungeonType',0)
    if type(mode) is not int or not 0<=mode<8:raise ValueError('Current dungeon type bound')
    return mode

def resolve(db,uid,source,base_ed,base_exp,dungeon):
    from els_server.storage import titles
    from els_server.domain.titles import definition
    # No implicit title schema/ownership or new acquisition is created here.
    mode=dungeon_type(dungeon)
    active=0;options=[];skipped=[];ed_rate=exp_rate=0.0
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='characters'").fetchone():
        character=db.execute('SELECT 1 FROM characters WHERE uid=?',(uid,)).fetchone()
        if character:
            active=titles.snapshot(db,uid,int(time.time()))['title']
    if active:
        keys=sorted({v for v in definition(active)['SOCKET_OPTION'].values() if v})
        for key in keys:
            if key not in REVIEWED|CONDITIONAL:continue
            field,rate,required=effects()[key]
            # Current CN secret clear rewards accept only secret-specific
            # options; these clear-only effects never augment ground coins.
            if required and (mode!=required or source!='clear') or not required and mode==3:
                skipped.append(key);continue
            options.append(key)
            if field==ED:ed_rate=f32(ed_rate+rate)
            elif source=='clear':exp_rate=f32(exp_rate+rate)
    from els_server.domain.equipment_economy import resolve as equipment_effects
    equipment=equipment_effects(db,uid,source,mode)
    ed_rate=f32(ed_rate+equipment['ed_rate']);exp_rate=f32(exp_rate+equipment['experience_rate'])
    from els_server.domain.ariel_attendance_mark import economy as ariel_mark_economy
    ariel=ariel_mark_economy(db,uid,source)
    exp_rate=f32(exp_rate+ariel['experience_rate'])
    ed_extra=bonus(base_ed,ed_rate,ed=True);exp_extra=bonus(base_exp,exp_rate)
    result=dict(version=3,owner=uid,source=source,dungeon=dungeon,dungeon_type=mode,title=active,options=options,held_options=[],skipped_mode_options=skipped,equipment=equipment,
                ed_rate=ed_rate,experience_rate=exp_rate,base_ed=base_ed,base_experience=base_exp,
                bonus_ed=ed_extra,bonus_experience=exp_extra,ed=base_ed+ed_extra,experience=base_exp+exp_extra)

    if ariel['experience_rate']:result['ariel_mark']=ariel
    return result
