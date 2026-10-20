"""Deterministic colored-column swap; one unambiguous plain or Luriel count1 ticket."""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_spell_rules import exchange,catalog
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_spell_exchange import request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_options import replace
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.item_instances import remove

def perform(path,owner,payload,operation,encode=acknowledgement,*,account_id=None):
    left_uid,right_uid,group,index=request(payload)
    owner,digest=_identity(owner,0x971,payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone():raise ValueError('Unknown mystic owner')
        if account_id is not None:
            from els_server.storage.profession_state import require_owner
            require_owner(db,owner,account_id)
        old=_previous(db,operation,digest);before=load_items(db,owner)
        if old is not None:
            return [encode(current_changes(db,operation,owner,0x971,old,before))]
        owned={i['uid']:i for i in before};left=owned.get(left_uid);right=owned.get(right_uid)
        if left is None or right is None:raise ValueError('Both mystic weapons must belong to this character')
        for item in (left,right):
            require_current(item);require_unlocked(item)
        updated_left,updated_right=exchange(left,right,group,index)
        # Match the requested original color, retaining the existing unique
        # whole-instance rule; no unproven cross-variant priority is invented.
        templates={r['template'] for r in catalog()['tickets'] if r['group']==group}
        eligible=[i for i in before if i['template'] in templates]
        if len(eligible)!=1 or (eligible[0]['group'],eligible[0]['metadata'],eligible[0]['count'])!=(4,0,1):
            raise ValueError('Exactly one owned single-count matching color transfer ticket required')
        ticket=eligible[0];require_current(ticket);require_unlocked(ticket)
        if ticket.get('sealed') or ticket.get('identified') is False:raise ValueError('Current unsealed matching color ticket required')
        replace(db,owner,left_uid,left.get('option_groups',{}),updated_left)
        replace(db,owner,right_uid,right.get('option_groups',{}),updated_right)
        remove(db,owner,ticket)
        positions=[(i['group'],i['slot']) for i in (left,right,ticket)]
        after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
        response=[encode([(p,current.get(p)) for p in positions])]
        # Complete response encoding must precede any durable commit.
        from els_server.protocol.protocol_codec import encode_event
        for event in response:encode_event(event)
        _commit(db,operation,digest,owner,0x971,positions,before,after)
        return response
