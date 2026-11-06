"""User-local chip reset: preserve base options, one matching coupon, zero ED.

Only existing owned inventory is consumed. No grant, RNG or client logic is added.
The original fourth tuning byte is backed by a lifetime UID quota tombstone.
"""
import json,sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_chip_rules import TEMPLATE,state
from els_server.domain.equipment_chip_reset_items import ticket
from els_server.domain.inventory_items import validate_item
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_chip_reset_messages import reset_request,reset_ack
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.equipment_chip import require_item,replace as replace_tuning
from els_server.storage.equipment_chip_reset_history import used,record as record_quota
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances
from els_server.storage.profession_state import require_owner

POLICY_ID='user-local-chip-reset-preserve-base-one-ticket-no-ED-v1'
WRITER_ENABLED=True


def require_ticket(item):
    definition=ticket(item['template']) if item is not None else None
    if (definition is None or item['group']!=4 or item['metadata']!=definition['metadata']
        or type(item['count']) is not int or item['count']<1 or item.get('sealed')
        or item.get('identified') is False):
        raise ValueError('Owned reset ticket required')
    require_current(item);require_unlocked(item)


def reset_image(items,ticket_uid,chip_uid):
    """Independent in-memory effect definition; no RNG/options reroll or fee."""
    expected={i['uid']:dict(i) for i in items}
    coupon=expected[ticket_uid];chip=expected[chip_uid]
    attempts,successes,probability,count=state(TEMPLATE,chip.get('chip_tuning',[0,0,0,0]))
    if attempts<1 or count>=3:raise ValueError('Chip reset stage/quota')
    # Existing local canonical initial state is raw0; native fallback displays50.
    expected[chip_uid]={**chip,'chip_tuning':[0,0,0,count+1]}
    if coupon['count']==1:del expected[ticket_uid]
    else:expected[ticket_uid]={**coupon,'count':coupon['count']-1}
    return expected


def receipt(db,operation,owner,ticket_uid,chip_uid,positions):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()
    if row is None or row[:2]!=(owner,0xbbc):raise ValueError('Chip reset receipt owner/kind')
    before,after=(json.loads(raw) for raw in row[2:])
    if (not isinstance(before,list) or not isinstance(after,list)
        or any(not isinstance(i,dict) for i in before+after)):
        raise ValueError('Chip reset receipt arrays')
    before=[validate_item(i) for i in before];after=[validate_item(i) for i in after]
    old={i['uid']:i for i in before};new={i['uid']:i for i in after}
    if len(old)!=len(before) or len(new)!=len(after) or ticket_uid not in old or chip_uid not in old:
        raise ValueError('Chip reset receipt identities')
    require_ticket_definition= ticket(old[ticket_uid]['template'])
    if (require_ticket_definition is None or old[ticket_uid]['group']!=4
        or old[chip_uid]['template']!=TEMPLATE or old[chip_uid]['group']!=1
        or old[chip_uid]['count']!=1):
        raise ValueError('Chip reset receipt templates')
    points=[(old[u]['group'],old[u]['slot']) for u in (ticket_uid,chip_uid)]
    if positions!=points or new!=reset_image(before,ticket_uid,chip_uid):
        raise ValueError('Chip reset receipt exact effect')
    if used(db,chip_uid)<new[chip_uid]['chip_tuning'][3]:
        raise ValueError('Chip reset durable quota history')
    return points


def current_changes(items,points,ticket_uid,chip_uid):
    owned={i['uid']:i for i in items};chip=owned.get(chip_uid)
    # A consumed/banked target cannot yield a made-up current bag record. Keep the
    # original success receipt and reject this replay without a second debit.
    if chip is None or chip['template']!=TEMPLATE or chip['group']!=1:
        raise ValueError('Chip reset replay target is not in owned bag')
    positions=list(points)
    for uid in (ticket_uid,chip_uid):
        item=owned.get(uid)
        if item is not None:
            pos=(item['group'],item['slot'])
            if pos not in positions:positions.append(pos)
    now={(i['group'],i['slot']):i for i in items}
    return [(p,now.get(p))for p in positions]


def perform(path,owner,account_id,payload,operation,*,prepare,encode=reset_ack):
    if WRITER_ENABLED is not True:raise ValueError('Chip reset writer is closed')
    if not callable(prepare) or not callable(encode):raise ValueError('Chip reset transaction context')
    ticket_uid,chip_uid=reset_request(payload)
    owner,digest=_identity(owner,0xbbc,payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);require_active_character(db,owner);require_owner(db,owner,account_id)
        old=_previous(db,operation,digest)
        before=load_items(db,owner);wallet=balances(db,owner)
        if old is not None:
            points=receipt(db,operation,owner,ticket_uid,chip_uid,old)
            reply=encode(current_changes(before,points,ticket_uid,chip_uid))
            prepare(db);encode_event(reply)
            return [reply]
        owned={i['uid']:i for i in before};coupon=owned.get(ticket_uid);chip=owned.get(chip_uid)
        require_ticket(coupon);require_item(chip,chip=True)
        expected=reset_image(before,ticket_uid,chip_uid)
        previous=state(TEMPLATE,chip.get('chip_tuning',[0,0,0,0]))
        if used(db,chip_uid)!=previous[3]:raise ValueError('Chip reset current quota')
        positions=[(coupon['group'],coupon['slot']),(chip['group'],chip['slot'])]
        if coupon['count']==1:remove(db,owner,coupon)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                        (ticket_uid,owner,coupon['count'])).rowcount!=1:
            raise ValueError('Chip reset ticket changed')
        # First reset transient tuning under the old quota; then increment the
        # persistent lifetime counter. A failure anywhere rolls both back.
        replace_tuning(db,owner,chip_uid,previous,[0,0,0,previous[3]])
        record_quota(db,owner,chip_uid,previous[3])
        after=load_items(db,owner)
        if {i['uid']:i for i in after}!=expected or balances(db,owner)!=wallet:
            raise ValueError('Chip reset exact inventory/wallet effect')
        reply=encode(current_changes(after,positions,ticket_uid,chip_uid))
        prepare(db);encode_event(reply)
        _commit(db,operation,digest,owner,0xbbc,positions,before,after)
        return [reply]
