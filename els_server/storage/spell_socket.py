"""One atomic spell-stone fill into an owned mystic weapon column."""
import secrets, sqlite3
from contextlib import closing
from els_server.domain.equipment_spell_rules import capacity, option_ids
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.artifact_socket_messages import request, acknowledgement
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.equipment_options import replace
from els_server.storage.profession_state import require_owner

STONE_GROUPS={136109:10,136110:11,136111:9,136112:12,135877:9,135880:10,135883:11,135886:12}

def _pool(group,template):
    values=list(option_ids(group))
    abyss=[v for v in values if 64000000<=v<65000000]
    if template in (136109,136110,136111,136112):return abyss or values
    return [v for v in values if not 64000000<=v<65000000] or values

def confirm(path,owner,uid,operation,*,account_id=None):
    owner,digest=_identity(owner,0x6e7,str(uid).encode(),operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if account_id is not None:require_owner(db,owner,account_id)
        balance=balances(db,owner);items=load_items(db,owner)
        target=next((i for i in items if i['uid']==uid),None)
        if target is None:raise ValueError('Spell apply target not owned')
        changes=[((target['group'],target['slot']),target)]
        return [acknowledgement(uid,balance['ed'],changes,mode=4,option=0,options=())]

def perform(path,owner,payload,operation,randbelow=secrets.randbelow,*,account_id=None):
    uid,groups,flag,mode=request(payload)
    if mode!=2 or flag not in (0,1) or len(groups)!=1:raise ValueError('Spell fill request mode')
    group,values=next(iter(groups.items()))
    if group not in (9,10,11,12) or not values:raise ValueError('Spell column required')
    owner,digest=_identity(owner,0x6e7,payload,operation)
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if account_id is not None:require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
        current={(i['group'],i['slot']):i for i in before};by_uid={i['uid']:i for i in before}
        target=by_uid.get(uid)
        if old is not None:
            affected={uid,*values.values()}
            positions=list(dict.fromkeys([*old,*[(i['group'],i['slot']) for i in before if i['uid'] in affected]]))
            return [acknowledgement(uid,balance['ed'],[(p,current.get(p)) for p in positions],mode=2,option=0,options=())]
        if target is None or target['count']!=1 or target.get('identified') is False or target.get('sealed'):
            raise ValueError('Owned identified mystic weapon required')
        require_current(target);require_unlocked(target)
        slots=capacity(target,group)
        installed=0;consumed={}
        vector=list(target.get('option_groups',{}).get(str(group),[]));vector+=[0]*(slots-len(vector))
        for slot,material_uid in sorted(values.items()):
            if not 0<=slot<slots:raise ValueError('Spell slot exceeds capacity')
            material=by_uid.get(material_uid)
            if material is None or material['template'] not in STONE_GROUPS or STONE_GROUPS[material['template']]!=group:
                raise ValueError('Owned matching spell stone required')
            require_current(material);require_unlocked(material)
            pool=_pool(group,material['template']);option=pool[randbelow(len(pool))]
            if type(option) is not int:raise ValueError('Spell roll bound')
            vector[slot]=option;installed=option
            consumed[material_uid]=consumed.get(material_uid,0)+1
        previous=target.get('option_groups',{});updated={**previous,str(group):vector}
        positions=[(target['group'],target['slot'])]
        for material_uid,count in consumed.items():
            material=by_uid[material_uid];positions.append((material['group'],material['slot']))
            if material['count']==count:remove(db,owner,material)
            else:db.execute('UPDATE inventory_items SET count=count-? WHERE owner=? AND uid=?',(count,owner,material_uid))
        replace(db,owner,uid,previous,updated);after=load_items(db,owner)
        current={(i['group'],i['slot']):i for i in after}
        wire=acknowledgement(uid,balance['ed'],[(p,current.get(p)) for p in positions],mode=2,option=installed,options=())
        _commit(db,operation,digest,owner,0x6e7,positions,before,after)
        return [wire]
