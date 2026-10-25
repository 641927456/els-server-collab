"""Atomic old-owned715036 opening; no new source, ED debit, or client logic."""
from contextlib import closing
from pathlib import Path
import sqlite3
import struct
from els_server.domain.wardrobe_ticket_box import BOX,OUTPUTS,entry,validate_existing_box
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.ice_messages import use_request
from els_server.protocol.cube_messages import result
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.inventory_management import _updates
from els_server.storage.npc_trade import balances


def open_box(path,owner,payload,operation,*,account_id):
    if type(account_id) is not int or not 1 <= account_id < 2**63:
        raise ValueError('Existing wardrobe box account identity')
    request = use_request(payload)
    if (request.option != 0 or request.choices
            or any(v not in (0,1) for v in (request.flag1,request.flag2,request.flag3))):
        raise ValueError('Existing wardrobe box has no choices or bulk option')
    definition = entry()
    owner,digest = _identity(owner,0x196,struct.pack('>Qi',account_id,BOX)+payload,operation)
    uri = Path(path).resolve().as_uri() + '?mode=rw'
    with closing(sqlite3.connect(uri,uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        require_owner(db,owner,account_id);require_active_character(db,owner)
        previous = _previous(db,operation,digest)
        before = load_items(db,owner);balance = balances(db,owner)
        if previous is not None:
            events = _updates(current_changes(db,operation,owner,0x196,previous,before))+result(balance['ed'])
            for event in events:encode_event(event)
            return events
        item = next((i for i in before if i['uid'] == request.uid),None)
        validate_existing_box(item)
        require_current(item);require_unlocked(item)
        if item.get('sealed',False) or item.get('seal_used',0):
            raise ValueError('Existing wardrobe box unsupported seal state')
        if balance['revision'] >= 2**63-1:
            raise ValueError('Existing wardrobe box wallet revision overflow')
        source = (item['group'],item['slot'])
        if item['count'] == 1:
            remove(db,owner,item)
        elif db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=? AND count=?',
                        (item['uid'],owner,item['count'])).rowcount != 1:
            raise ValueError('Existing wardrobe box source changed')
        grants = grant_items(db,[dict(template=t,metadata=0,group=4,quantity=1) for t in OUTPUTS],owner)
        if (len(grants) != 6 or {g['template'] for g in grants} != set(OUTPUTS)
                or len({g['uid'] for g in grants}) != 6
                or any(set(g) != {'uid','template','metadata','group','slot','count'}
                    or (g['metadata'],g['group'],g['count']) != (0,4,1)
                    or g['uid'] in {i['uid'] for i in before} for g in grants)):
            raise ValueError('Existing wardrobe box requires six new permanent ticket instances')
        after = load_items(db,owner)
        expected = {i['uid']:dict(i) for i in before if i['uid'] != item['uid']}
        if item['count'] > 1:expected[item['uid']] = dict(item,count=item['count']-1)
        expected.update((g['uid'],g) for g in grants)
        if {i['uid']:dict(i) for i in after} != expected:
            raise ValueError('Existing wardrobe box atomic inventory delta mismatch')
        current = {(i['group'],i['slot']):i for i in after}
        positions = sorted({source,*[(i['group'],i['slot']) for i in grants]})
        events = result(balance['ed'],[(p,current.get(p)) for p in positions],
                        [(r['template'],r['quantity']) for r in definition['entries']])
        for event in events:encode_event(event)
        if db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=? AND revision=?',
                      (owner,balance['revision'])).rowcount != 1:
            raise ValueError('Existing wardrobe box wallet changed')
        _commit(db,operation,digest,owner,0x196,positions,before,after)
        return events
