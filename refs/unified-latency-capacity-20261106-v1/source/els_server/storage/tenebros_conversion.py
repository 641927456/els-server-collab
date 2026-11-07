"""Atomic owned-ticket selection, existing group25 codec and inventory receipts.

No RNG, wallet write, capacity/storage writer, eager DDL or new receipt schema.
"""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.tenebros_conversion_rules import selection
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.domain.inventory_items import validate_item
from els_server.protocol.tenebros_conversion_messages import request,acknowledgement
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.equipment_options import replace
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances


def image(items,target_uid,ticket_uid,slot,option):
    owned={i['uid']:dict(i) for i in items}
    if len(owned)!=len(items):raise ValueError('Duplicate conversion item identity')
    target=owned.get(target_uid);ticket=owned.get(ticket_uid)
    updated=selection(target,ticket,slot,option)
    owned[target_uid]={**target,'option_groups':updated}
    if ticket['count']==1:del owned[ticket_uid]
    else:owned[ticket_uid]={**ticket,'count':ticket['count']-1}
    return owned


def receipt(db,operation,owner,target_uid,ticket_uid,slot,option,positions):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0xb0e):raise ValueError('Tenebros select receipt owner/kind')
    try:
        before,after=(json.loads(raw) for raw in row[2:])
        if not isinstance(before,list) or not isinstance(after,list) or any(not isinstance(i,dict) for i in before+after):
            raise ValueError('Tenebros select receipt arrays')
        before=[validate_item(i) for i in before];after=[validate_item(i) for i in after]
        old={i['uid']:i for i in before};new={i['uid']:i for i in after}
        points=[(old[u]['group'],old[u]['slot']) for u in (target_uid,ticket_uid)]
        if len(old)!=len(before) or len(new)!=len(after) or positions!=points or new!=image(before,target_uid,ticket_uid,slot,option):
            raise ValueError('Tenebros select receipt exact one-ticket/one-slot effect')
        return points
    except (TypeError,KeyError,json.JSONDecodeError) as exc:
        raise ValueError('Tenebros select receipt history') from exc


def current_changes(items,positions,target_uid,ticket_uid):
    # Replay carries current occupants, including replacements in historic slots.
    # It neither restores historical options nor removes a later replacement.
    target=next((i for i in items if i['uid']==target_uid),None)
    if target is None or target['group']!=1:
        raise ValueError('Tenebros replay target no longer in owned bag')
    points=list(positions)
    for item in items:
        if item['uid'] in (target_uid,ticket_uid):
            point=(item['group'],item['slot'])
            if point not in points:points.append(point)
    now={(i['group'],i['slot']):i for i in items}
    return [(point,now.get(point)) for point in points]


def perform(path,owner,account_id,payload,operation,*,prepare,encode=acknowledgement):
    if not callable(prepare) or not callable(encode):raise ValueError('Tenebros select transaction context')
    target_uid,slot,option,ticket_uid=request(payload)
    owner,digest=_identity(owner,0xb0e,payload,operation)
    path=Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        def guard():
            if Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()!=path:
                raise ValueError('Tenebros select database authority')
            prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
        guard()
        old=_previous(db,operation,digest);before=load_items(db,owner);wallet=balances(db,owner)
        if old is not None:
            points=receipt(db,operation,owner,target_uid,ticket_uid,slot,option,old)
            reply=encode(current_changes(before,points,target_uid,ticket_uid));encode_event(reply);guard()
            return [reply]
        owned={i['uid']:i for i in before};target=owned.get(target_uid);ticket=owned.get(ticket_uid)
        updated=selection(target,ticket,slot,option)
        for item in (target,ticket):require_current(item);require_unlocked(item)
        expected=image(before,target_uid,ticket_uid,slot,option)
        points=[(i['group'],i['slot']) for i in (target,ticket)]
        # Verify the entire native reply before mutating SQL, then encode current
        # rows again before commit. Either encoder failure rolls back everything.
        preview=encode(current_changes(list(expected.values()),points,target_uid,ticket_uid));encode_event(preview);guard()
        if ticket['count']==1:remove(db,owner,ticket)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                        (ticket_uid,owner,ticket['count'])).rowcount!=1:
            raise ValueError('Tenebros select ticket changed')
        replace(db,owner,target_uid,target.get('option_groups',{}),updated)
        after=load_items(db,owner)
        if {i['uid']:i for i in after}!=expected or balances(db,owner)!=wallet:
            raise ValueError('Tenebros select exact inventory/wallet effect')
        reply=encode(current_changes(after,points,target_uid,ticket_uid));encode_event(reply);guard()
        _commit(db,operation,digest,owner,0xb0e,points,before,after)
        guard()
        return [reply]
