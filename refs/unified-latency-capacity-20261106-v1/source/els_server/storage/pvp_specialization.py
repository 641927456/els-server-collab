"""Native specialization: item, material, AP and receipt share one transaction."""
from contextlib import closing
import sqlite3,time
from els_server.domain.pvp_specialization import request,target,advance
from els_server.protocol.spell_socket_messages import acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.equipment_options import replace
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.pvp_official_profiles import snapshot,spend_ap

def perform(path,owner,account,payload,operation,guard,*,now=None):
    uid,group,slot,choice,mode=request(payload)
    owner,digest=_identity(owner,0x6e7,payload,operation);stamp=int(time.time())if now is None else now
    def authority(db):
        from els_server.storage.item_actor import require_active_character
        from els_server.storage.profession_state import require_owner
        guard(db);require_active_character(db,owner);require_owner(db,owner,account)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');authority(db)
        before=load_items(db,owner);wallet=balances(db,owner);old=_previous(db,operation,digest)
        if old is not None:
            profile=snapshot(db,owner,account)
            if profile is None:raise ValueError('Missing PvP AP profile')
            event=acknowledgement(uid,wallet['ed'],current_changes(db,operation,owner,0x6e7,old,before),mode=mode,ap=profile[0].ap)
            encode_event(event);authority(db);return[event]
        item=next((i for i in before if i['uid']==uid),None)
        if item is None or item['group']not in(1,9)or item['count']!=1 or item.get('sealed')or item.get('identified')is False or item.get('enhancement',0)<0:raise ValueError('Owned identified usable PvP equipment required')
        from els_server.domain.item_expiration import require_current,expired
        from els_server.domain.item_locks import require_unlocked,locked
        require_current(item,now=stamp);require_unlocked(item,now=stamp)
        from els_server.storage.seal_quests import load_character
        character=load_character(db,owner,account)
        if target(item['template'])['unit_type']!=character['unit_type']:raise ValueError('PvP equipment role mismatch')
        previous=item.get('option_groups',{});values,cost=advance(item['template'],character,group,previous.get(str(group),[0]*4),slot,choice,mode)
        remaining=cost['quantity'];selected=[]
        for material in sorted(before,key=lambda i:(cost['templates'].index(i['template'])if i['template']in cost['templates']else len(cost['templates']),i['uid'])):
            if material['template']not in cost['templates']or expired(material,now=stamp)or locked(material,now=stamp)or material.get('sealed'):continue
            take=min(remaining,material['count']);selected.append((material,take));remaining-=take
            if not remaining:break
        if remaining or wallet['revision']>=2**63-1:raise ValueError('Insufficient PvP specialization materials/revision')
        profile=spend_ap(db,owner,account,cost['ap'])
        for material,take in selected:
            if take==material['count']:remove(db,owner,material)
            else:db.execute('UPDATE inventory_items SET count=count-?WHERE uid=?AND owner=?',(take,material['uid'],owner))
        replace(db,owner,uid,previous,{**previous,str(group):values})
        positions=sorted({(i['group'],i['slot'])for i in[item]+[m for m,n in selected]})
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        event=acknowledgement(uid,wallet['ed'],[(p,current.get(p))for p in positions],mode=mode,ap=profile[0].ap)
        encode_event(event);authority(db)
        if snapshot(db,owner,account)!=profile or balances(db,owner)!=wallet:raise ValueError('Late PvP specialization balance changed')
        db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
        _commit(db,operation,digest,owner,0x6e7,positions,before,after);authority(db)
        return[event]
