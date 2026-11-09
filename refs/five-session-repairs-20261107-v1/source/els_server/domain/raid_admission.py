"""Current native raid qualifications shared by selection and actual admission."""
import sqlite3,time
from contextlib import closing
from els_server.domain import formal_raid_economy as rules
from els_server.game_data import client_data


def native_definition(identity):
    if rules.definition(identity)is None:
        from els_server.domain.dungeon_routes import route_catalog
        from els_server.domain.raid_party import raid_definition
        if raid_definition(identity)is None and not any(n['dungeon']==identity for p in route_catalog()._data['challenges']for n in p['nodes']):return None
    return client_data().dungeon(identity)


def armor_allowed(character,items,minimum):
    """Native tier1 is Tenebrous+, tier2 is Exascale+; use pinned armor families."""
    from els_server.domain.equipment_reforge_rules import catalog
    from els_server.domain.character_stats import equipment_contributes
    targets=catalog()['targets'];parts=set()
    for item in items:
        if item['group']!=9:continue
        row=targets.get(str(item['template']))
        if row is not None and row['reforge_class']>=minimum+1 and equipment_contributes(item,character):
            parts.add(row['part'])
    return parts>={8,9,10,11}


def progression_allowed(db,owner,definition,now):
    from els_server.storage import raid_economy_state as state
    family=definition['family'];ordinal=definition['ordinal'];week=state.week_at(now)
    if ordinal==1:return True
    definitions=[(int(mid),row)for mid,row in rules.policy()['maps'].items()
                 if row['family']==family and row['week_bucket']==definition['week_bucket']]
    if family=='marcus' and definition['mode']=='story':
        # Story has no weekly loot slot; its genuine phase receipts still carry progress.
        if not state.exists(db,'formal_raid_phases'):return False
        ids=[mid for mid,row in definitions if row['mode']=='story']
        rows={(rules.definition(mid)['ordinal'],rules.definition(mid)['phases'][str(stage)])
              for mid,stage in db.execute('SELECT dungeon,stage FROM formal_raid_phases WHERE owner=? AND week=? AND dungeon IN ('+
                  ','.join('?'for _ in ids)+')',(owner,week,*ids))}
    else:
        if not state.exists(db,'formal_raid_weeks'):return False
        rows=set(db.execute('SELECT ordinal,phase FROM formal_raid_weeks WHERE owner=? AND bucket=? AND week=?',
                            (owner,definition['week_bucket'],week)))
    phases={n:set()for n in range(1,ordinal)}
    for mid,row in definitions:
        if row['ordinal']in phases:phases[row['ordinal']].update(row['phases'].values())
    complete=lambda n:bool(phases[n]) and all((n,p)in rows for p in phases[n])
    if family=='abyss':
        if not complete(1):return False
        if ordinal==4 and not (complete(2) or complete(3)):return False
    elif not all(complete(n)for n in phases):return False
    if family=='barkat' and ordinal==5:
        # Each same-mode full Escape clear permits one later full Fall clear.
        # Failed Fall attempts do not consume it. Historical source receipts remain immutable.
        if not state.exists(db,'formal_raid_phases'):return False
        maps={mid:row for mid,row in definitions if row['mode']==definition['mode'] and row['ordinal']in(4,5)}
        runs={}
        for run,mid,stage in db.execute('SELECT run,dungeon,stage FROM formal_raid_phases WHERE owner=? AND week=? AND dungeon IN ('+
                ','.join('?'for _ in maps)+')',(owner,week,*maps)):
            runs.setdefault((run,mid),set()).add(stage)
        counts={4:0,5:0}
        for (run,mid),stages in runs.items():
            if stages==set(map(int,maps[mid]['phases'])):counts[maps[mid]['ordinal']]+=1
        return counts[4]>counts[5]
    return True


def allowed(account,identity,character):
    policy=rules.policy()
    if str(identity)in policy['held_maps']:return False
    definition=rules.definition(identity)
    native=native_definition(identity)
    if native is None:return True
    from els_server.domain.character_rules import CLASSES
    if not native.get('m_MinLevel',1)<=character['level']<=native.get('m_MaxLevel',99):return False
    if CLASSES[character['unit_class']]['stage']<native.get('m_iUnitClassLevel',0):return False
    minimum=native.get('m_iRequireEquipItemTier',0)
    if minimum and not armor_allowed(character,account.get_inventory_snapshot()['items'],minimum):return False
    if definition is None:return True  # Challenge progress belongs to its own active attempt.
    with closing(sqlite3.connect(account.store.path,timeout=10))as db:
        return progression_allowed(db,account.uid,definition,int(time.time()))
