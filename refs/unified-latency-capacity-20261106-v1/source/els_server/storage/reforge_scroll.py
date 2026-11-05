"""Native fixed reforge level, one owned voucher, existing equipment sidecars."""
import sqlite3,time
from contextlib import closing
from els_server.domain.owned_scroll_families import catalog
from els_server.domain.equipment_reforge_rules import DEFAULT,state,expected_options
from els_server.storage.equipment_reforge import require_item,replace
from els_server.storage.equipment_options import replace as replace_options
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_state import load_items
from els_server.storage.profession_state import require_owner
from els_server.storage.item_actor import require_active_character
from els_server.storage.npc_trade import balances,charge
from els_server.storage.item_instances import remove
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.reforge_scroll_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event

def perform(path,owner,account,payload,operation,*,prepare,encode=acknowledgement):
    target_uid,source_uid=request(payload);owner,digest=_identity(owner,0xa22,payload,operation)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_owner(db,owner,account);require_active_character(db,owner);prepare()
        old=_previous(db,operation,digest);before=load_items(db,owner)
        if old is not None:
            answer=encode(current_changes(db,operation,owner,0xa22,old,before));encode_event(answer);prepare();return[answer]
        owned={i['uid']:i for i in before};target=owned.get(target_uid);source=owned.get(source_uid);now=int(time.time())
        require_item(target,equipment=True,now=now)
        if source is None or source['group']!=4 or source.get('sealed')or source['template']not in catalog()['reforge']:raise ValueError('Owned reforge scroll required')
        require_current(source,now=now);require_unlocked(source,now=now)
        rule=catalog()['reforge'][source['template']];prior=state(target['template'],target.get('reforge',DEFAULT))
        if target['template']not in rule['targets']or prior[0]>=rule['level']:raise ValueError('Reforge scroll target or level')
        # The voucher supplies a successful new stage. Keep durability, clear
        # the old stage's failure gauge as in existing successful reforging.
        updated=state(target['template'],[rule['level'],prior[1],0]);groups=target.get('option_groups',{})
        replace_options(db,owner,target_uid,groups,{**groups,'13':expected_options(target['template'],updated[0])})
        replace(db,owner,target_uid,prior,updated)
        if source['count']==1:remove(db,owner,source)
        else:db.execute('UPDATE inventory_items SET count=count-1 WHERE owner=? AND uid=?',(owner,source_uid))
        charge(db,owner,balances(db,owner),0)
        positions=[(i['group'],i['slot'])for i in(target,source)];after=load_items(db,owner)
        current={(i['group'],i['slot']):i for i in after};answer=encode([(p,current.get(p))for p in positions]);encode_event(answer)
        _commit(db,operation,digest,owner,0xa22,positions,before,after);prepare();return[answer]
