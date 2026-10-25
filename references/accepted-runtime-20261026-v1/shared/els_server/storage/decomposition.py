"""Atomic ordinary dismantling with current-state replay and no made-up rates."""
from els_server.storage.item_actor import require_active_character
import sqlite3
from contextlib import closing
from collections import Counter
from els_server.domain.decomposition_rules import quote, reward_definition
from els_server.protocol.inventory_management_messages import decompose_request, decompose_ack
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.inventory_management import _updates
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.protocol.profession_messages import level_update
from els_server.storage.profession_state import snapshot,replace
from els_server.domain.profession_growth import ordinary_blacksmith_xp,advance_blacksmith
from els_server.game_data import client_data


def decompose(path, owner, payload, operation, *, account_id=None, encode=decompose_ack, authorize=None, prepare_replay=None):
    uids = decompose_request(payload)
    owner, digest = _identity(owner, 0x1c0, payload, operation)
    with closing(sqlite3.connect(path, timeout=10)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE');_authorize(authorize);require_active_character(db,owner)
        if account_id is not None:
            from els_server.storage.profession_state import require_owner
            require_owner(db,owner,account_id)
        old = _previous(db, operation, digest)
        before = load_items(db, owner)
        if old is not None:
            # Retained affected UIDs may have moved since the first result.
            # Refresh current owned instances, never historical rewards or a
            # different item selected by template after an instance is gone.
            changes = current_changes(db, operation, owner, 0x1c0, old, before)
            response=([Event(0x201, kind=0x1c1, payload=decompose_ack())] + _updates(changes))
            # Full current-user sync can run legacy inventory repair writers.
            # Release this retry transaction before invoking that existing path.
            db.rollback()
            _authorize(authorize)
            if prepare_replay is not None:response=prepare_replay(response)
            for event in response:encode_event(event)
            _authorize(authorize)
            return response
        by_uid = {i['uid']: i for i in before}
        selected = [by_uid[uid] for uid in uids if uid in by_uid]
        if len(selected) != len(uids):
            raise ValueError('Decomposition requires owned items')
        quotes = [quote(i) for i in selected]
        # Current ordinary701000 quote only; modern white-chip118445 rewards stay separate.
        requested_xp=sum(ordinary_blacksmith_xp(client_data().item(item['template'])['record'][0xd1])
            for item,q in zip(selected,quotes) if q['template']==701000)
        growth=None;xp=0;leveled=False;growth_audit=None
        if requested_xp and account_id is not None:
            from els_server.protocol.profession_messages import ProfessionState
            growth=snapshot(db,owner,account_id)
            current_state=ProfessionState(**growth['state'])
            next_state,xp,leveled=advance_blacksmith(current_state,requested_xp)
            if current_state.profession==2:
                from dataclasses import asdict
                eligibility=('maximum_level_unchanged' if current_state.level==10 else
                    'unknown_legacy_required_no_xp_compatibility_preserved' if current_state.required==0 else 'qualified_growth_state')
                growth_audit=dict(eligibility=eligibility,qualified_growth_state=eligibility=='qualified_growth_state',
                    requested_xp=requested_xp,granted_xp=xp,before=growth['state'],after=asdict(next_state))
        rewards=Counter()
        for q in quotes:rewards[q['template']]+=q['quantity']
        definitions={t:reward_definition(t)for t in rewards}
        for item in selected:
            remove(db,owner,item)
        changed = {}
        for template,quantity in sorted(rewards.items()):
            reward=definitions[template]
            remaining=quantity
            while remaining:
                amount=min(99,remaining)
                plan={k:reward[k]for k in('template','metadata','group')}
                for item in grant_items(db,[dict(plan,quantity=amount)],owner):
                    changed[item['uid']]=item
                remaining-=amount
        positions = sorted({(i['group'], i['slot']) for i in selected} |
                           {(i['group'], i['slot']) for i in changed.values()})
        after = load_items(db, owner)
        current = {(i['group'], i['slot']): i for i in after}
        changes = [(p, current.get(p)) for p in positions]
        if xp:replace(db,owner,account_id,growth['revision'],next_state)
        wire=encode(changes,dict(rewards),profession_xp=xp) if xp else encode(changes,dict(rewards))
        response = [Event(0x201, kind=0x1c1, payload=wire)]
        if leveled:response.append(Event(0x201,kind=0x4c4,payload=level_update(owner,next_state,{})))
        for event in response:encode_event(event)
        _commit(db, operation, digest, owner, 0x1c0, positions, before, after)
        if growth_audit is not None:
            import json
            db.execute('CREATE TABLE IF NOT EXISTS blacksmith_decomposition_xp_receipts (operation TEXT PRIMARY KEY REFERENCES inventory_action_receipts(operation_id),owner INTEGER NOT NULL,account_id INTEGER NOT NULL,audit_json TEXT NOT NULL)')
            db.execute('INSERT INTO blacksmith_decomposition_xp_receipts VALUES(?,?,?,?)',(operation,owner,account_id,json.dumps(growth_audit,sort_keys=True)))
        _authorize(authorize)
        return response

def _authorize(authorize):
    if authorize is not None and not authorize():raise ValueError('Decomposition current actor changed')
