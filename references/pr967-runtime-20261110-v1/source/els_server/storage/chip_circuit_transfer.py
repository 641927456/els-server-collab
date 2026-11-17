"""Both existing instance groups and exact native response in one SQL writer."""
from contextlib import closing
from pathlib import Path
from uuid import UUID
import json
import sqlite3
import time
from els_server.domain.chip_circuit_transfer_rules import transform
from els_server.domain.inventory_items import validate_item
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.chip_circuit_transfer_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
WRITER_ENABLED=True


def _authority(db,path,owner,account_id,prepare,now):
    main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
    if (not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path
        or any(r[1]not in('main','temp')for r in db.execute('PRAGMA database_list'))
        or db.execute('PRAGMA foreign_keys').fetchone()!=(1,)or not callable(prepare)):
        raise ValueError('Transfer exact original writer')
    require_active_character(db,owner);require_owner(db,owner,account_id)
    if prepare(db,now)is not True:
        raise ValueError('Transfer current actor authorization refused')


def _usable(item,now):
    if (item is None or item['group']!=1 or item['count']!=1
        or item.get('identified')is False or item.get('sealed')
        or item.get('enhancement',0)<0 or item.get('durability',0)<=0):
        raise ValueError('Owned unequipped unsealed identified transfer armor')
    validate_item(item);require_current(item,now=now);require_unlocked(item,now=now)


def _history(db,operation,digest,owner,account_id,source,target):
    row=db.execute('SELECT owner,kind,request_hash,positions_json,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:3]!=(owner,0xd2e,digest):
        raise ValueError('Exact paired transfer receipt required')
    try:
        points=json.loads(row[3]);before=json.loads(row[4]);after=json.loads(row[5])
        if (type(before)is not list or type(after)is not list or len(before)!=2 or len(after)!=2
            or [i['uid']for i in before]!=[source,target]or [i['uid']for i in after]!=[source,target]
            or points!=[[i['group'],i['slot']]for i in before]):
            raise ValueError('Transfer receipt exact instances/positions')
        expected=transform(*before)
        for first,last,groups in zip(before,after,expected):
            validate_item(first);validate_item(last)
            if ({k:v for k,v in first.items()if k!='option_groups'}!=
                {k:v for k,v in last.items()if k!='option_groups'}
                or last.get('option_groups',{})!=groups):
                raise ValueError('Transfer receipt rewrote unrelated attributes')
    except(KeyError,TypeError,json.JSONDecodeError)as exc:
        raise ValueError('Malformed transfer history')from exc


def perform(path,owner,payload,operation,*,account_id,prepare,encode=acknowledgement):
    if not WRITER_ENABLED:
        raise ValueError('New chip/circuit transfers closed')
    source_uid,target_uid=request(payload)
    if type(account_id)is not int or not 1<=account_id<2**63:
        raise ValueError('Transfer account identity')
    if type(operation)is not str:
        raise ValueError('Transfer operation identity')
    generation=operation.split(':',1)[0]
    if (str(UUID(generation))!=generation or UUID(generation).version!=4
        or not operation.startswith(generation+':chip-circuit-transfer:'+str(owner)+':')):
        raise ValueError('Transfer original operation generation')
    import struct
    owner,digest=_identity(owner,0xd2e,struct.pack('>Q',account_id)+payload,operation)
    path=Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');now=int(time.time())
        _authority(db,path,owner,account_id,prepare,now)
        old=_previous(db,operation,digest);before=load_items(db,owner)
        owned={i['uid']:i for i in before};source=owned.get(source_uid);target=owned.get(target_uid)
        if old is not None:
            _history(db,operation,digest,owner,account_id,source_uid,target_uid)
            # Only actual current records: never clear old slots or replacements.
            if source is None or target is None:
                event=encode(source_uid,target_uid,result=2005)
            else:
                event=encode(source_uid,target_uid,[((i['group'],i['slot']),i)for i in(source,target)])
            encode_event(event);_authority(db,path,owner,account_id,prepare,now)
            return [event]
        _usable(source,now);_usable(target,now)
        source_groups,target_groups=transform(source,target)
        for item,updated in((source,source_groups),(target,target_groups)):
            replace(db,owner,item['uid'],item.get('option_groups',{}),updated)
        # A paid preview of either changed item is superseded without refund.
        from els_server.storage import market_conversion_pending as pending
        preview=pending.get(db,owner)
        if preview is not None and preview['item_uid']in(source_uid,target_uid):
            pending.clear(db,owner)
        _authority(db,path,owner,account_id,prepare,now)
        after=load_items(db,owner);current={i['uid']:i for i in after}
        if set(current)!=set(owned):
            raise ValueError('Transfer changed inventory identities')
        for uid,original in owned.items():
            expected=original
            if uid in(source_uid,target_uid):
                expected={**original}
                groups=source_groups if uid==source_uid else target_groups
                if groups:expected['option_groups']=groups
                else:expected.pop('option_groups',None)
            if current[uid]!=expected:
                raise ValueError('Transfer changed unrelated inventory state')
        selected=[current[source_uid],current[target_uid]]
        event=encode(source_uid,target_uid,[((i['group'],i['slot']),i)for i in selected])
        encode_event(event)
        _authority(db,path,owner,account_id,prepare,now)
        _commit(db,operation,digest,owner,0xd2e,[(i['group'],i['slot'])for i in(source,target)],
                [source,target],selected)
        _authority(db,path,owner,account_id,prepare,now)
        return [event]
