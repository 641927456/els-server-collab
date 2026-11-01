"""Exact reactor debit,200000ED,option installation and guide fact in one TX."""
from contextlib import closing
import hashlib,sqlite3,time
from els_server.domain.equipment_tuning import catalog,target,options,request
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.spell_socket_messages import acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_state import load_items
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.equipment_options import replace
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge
from els_server.game_data import client_data

def perform(path,owner,account_id,payload,operation,*,validate=lambda:True,now=None):
    uid,source_uid=request(payload);owner,digest=_identity(owner,0x6e7,payload,operation)
    now=int(time.time()) if now is None else now
    def actor(db):
        require_owner(db,owner,account_id);require_active_character(db,owner)
        if not validate():raise ValueError('Native tuning selected lease changed')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');actor(db)
        old=_previous(db,operation,digest);before=load_items(db,owner);wallet=balances(db,owner)
        if old is not None:
            event=acknowledgement(uid,wallet['ed'],current_changes(db,operation,owner,0x6e7,old,before),mode=14)
            encode_event(event);actor(db);return [event]
        raise ValueError('Permanent guide recovery permits saved readers and committed replay only')
        owned={i['uid']:i for i in before};item=owned.get(uid);source=owned.get(source_uid)
        row=target(item['template']) if item else None
        material=next((r for r in catalog()['materials'] if source and r['template']==source['template']),None)
        if (row is None or material is None or item['group']not in(1,9) or source['group']!=1 or item['count']!=1 or source['count']!=1
            or row['position']!=material['position'] or item.get('identified')is False or source.get('identified')is False
            or item.get('sealed') or source.get('sealed') or item.get('enhancement',0)<0):raise ValueError('Native tuning owned identified matching armor/reactor')
        for i,r in ((item,row),(source,material)):
            require_current(i,now=now);require_unlocked(i,now=now)
            if hashlib.sha256(client_data().item(i['template'])['record']).hexdigest()!=r['record_sha256']:raise ValueError('Native tuning original template')
        if source.get('option_groups',{}).get('1')!=[material['option']]:raise ValueError('Native tuning reactor fixed effect missing')
        if wallet['ed']<catalog()['fee_ed'] or wallet['revision']>=2**63-1:raise ValueError('Native tuning ED/revision')
        previous=item.get('option_groups',{});updated={**previous,'26':options(item['template'],[material['option']])}
        ed=charge(db,owner,wallet,catalog()['fee_ed']);remove(db,owner,source);replace(db,owner,uid,previous,updated)
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after};positions=sorted({(i['group'],i['slot']) for i in (item,source)})
        event=acknowledgement(uid,ed,[(p,current.get(p)) for p in positions],mode=14)
        encode_event(event);actor(db);_commit(db,operation,digest,owner,0x6e7,positions,before,after);actor(db)
        return [event]
