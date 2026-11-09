"""Atomic owned circuit installation; compatible fee is not a retail rule."""
import sqlite3
from contextlib import closing
from pathlib import Path
from els_server.domain.equipment_circuit_rules import catalog,material,target,root,validate_material,validate_grid
from els_server.domain.item_expiration import require_current
from els_server.domain.item_locks import require_unlocked
from els_server.protocol.equipment_circuit_messages import request,acknowledgement
from els_server.storage.inventory_actions import _identity,_previous,_commit
from els_server.storage.inventory_state import load_items
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.equipment_options import replace
from els_server.storage.item_instances import remove
from els_server.storage.npc_trade import balances,charge


def repair_missing(path,owner,randbelow=None):
    """One persistent compatible generation for legacy, unsealed bag circuits.

    Called after inventory initialization, before its login/refresh snapshot.
    Existing native options are preserved. No fee, acquisition or UID creation.
    """
    import json,secrets
    from els_server.domain.equipment_circuit_rules import generate
    from els_server.domain.item_expiration import expired
    from els_server.domain.item_locks import locked
    owner,_=_identity(owner,0x6e7,b'legacy-circuit-options','circuit-legacy-check')
    randbelow=secrets.randbelow if randbelow is None else randbelow
    with snapshot_connection(path) as db:
        db.execute('BEGIN')
        ids=tuple(int(v) for v in catalog()['materials'])
        rows=db.execute('SELECT uid FROM inventory_items WHERE owner=? AND bag_group=1 AND template IN ('+','.join('?' for _ in ids)+')',(owner,*ids)).fetchall()
        if not rows:return []
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_options'").fetchone():
            existing={uid:json.loads(raw) for uid,raw in db.execute('SELECT o.item_uid,o.groups_json FROM equipment_options o JOIN inventory_items i ON i.uid=o.item_uid WHERE i.owner=?',(owner,))}
            if all(existing.get(uid,{}).get('1') for (uid,) in rows):return []
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            items=load_items(db,owner);changed=[]
            for item in items:
                if (item['group']!=1 or material(item['template']) is None or item.get('sealed')
                        or expired(item) or locked(item) or item.get('option_groups',{}).get('1')):continue
                name='circuit-option-compat-v1:'+str(item['uid'])
                old=db.execute('SELECT audit_json FROM inventory_migrations WHERE name=?',(name,)).fetchone()
                previous=item.get('option_groups',{})
                if old:
                    audit=json.loads(old[0])
                    if audit.get('uid')!=item['uid'] or audit.get('template')!=item['template'] or audit.get('policy')!=catalog()['policy_id']:
                        raise ValueError('Conflicting legacy circuit generation evidence')
                    generated={'1':validate_material(item['template'],audit['options'])}
                else:generated=generate(item['template'],randbelow)
                updated={**previous,**generated}
                replace(db,owner,item['uid'],previous,updated)
                audit=dict(owner=owner,template=item['template'],uid=item['uid'],policy=catalog()['policy_id'],options=updated['1'],fee=0)
                if old is None:db.execute('INSERT INTO inventory_migrations VALUES(?,?)',(name,json.dumps(audit,sort_keys=True)))
                changed.append(item['uid'])
            return changed


def perform(path,owner,payload,operation,encode=acknowledgement,*,account_id=None):
    uid,slots,flag=request(payload)
    owner,digest=_identity(owner,0x6e7,payload,operation)
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with write_transaction(db):
            if not db.execute('SELECT 1 FROM characters WHERE uid=?',(owner,)).fetchone():raise ValueError('Unknown circuit owner')
            if account_id is not None:
                from els_server.storage.profession_state import require_owner
                require_owner(db,owner,account_id)
            old=_previous(db,operation,digest);before=load_items(db,owner);balance=balances(db,owner)
            if old is not None:
                return [encode(uid,balance['ed'],current_changes(db,operation,owner,0x6e7,old,before))]
            owned={i['uid']:i for i in before};item=owned.get(uid)
            if item is None or item['group']!=1 or item['count']!=1 or target(item['template']) is None or item.get('identified') is False or item.get('sealed'):
                raise ValueError('Owned identified unequipped circuit armor required')
            require_current(item);require_unlocked(item)
            if root(item['template']) in slots or len(set(slots.values()))!=len(slots) or uid in slots.values():
                raise ValueError('Reserved root, duplicated material or target alias')
            previous=item.get('option_groups',{});grid=validate_grid(item['template'],previous.get('28',[0]*16))
            positions=[(item['group'],item['slot'])];debits=[]
            for pos,value in slots.items():
                source=owned.get(value)
                row=material(source['template']) if source else None
                if source is None or source['group']!=1 or source['count']!=1 or row is None or row['part']!=target(item['template'])['part'] or source.get('sealed'):
                    raise ValueError('Owned matching-part circuit material required')
                require_current(source);require_unlocked(source)
                option=validate_material(source['template'],source.get('option_groups',{}).get('1',[]))[0]
                grid[pos]=option;debits.append(source);positions.append((source['group'],source['slot']))
            validate_grid(item['template'],grid)
            fee=catalog()['install_ed_per_slot']*len(debits)
            if fee>balance['ed']:raise ValueError('Insufficient circuit installation ED')
            ed=charge(db,owner,balance,fee)
            for source in debits:remove(db,owner,source)
            replace(db,owner,uid,previous,{**previous,'28':grid})
            after=load_items(db,owner);current={(i['group'],i['slot']):i for i in after}
            response=[encode(uid,ed,[(p,current.get(p)) for p in positions])]
            _commit(db,operation,digest,owner,0x6e7,positions,before,after)
            return response

from els_server.storage.read_scope import snapshot_connection

from els_server.storage.sqlite_timing import write_transaction
