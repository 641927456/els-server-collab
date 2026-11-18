"""Sweep tickets, shared weekly quota and fixed rewards in one writer."""
from contextlib import closing
import sqlite3
import uuid

from els_server.domain.secret_clear_rewards import _week,_ensure,_coupon,policy
from els_server.protocol.secret_dungeon_sweep import request,acknowledgement

TICKETS=frozenset((720016,720017))
# Original 2FDABF0: the stage selector expands to these dungeon identities.
STAGES=((33041,33031,33051),(33191,33261),(41141,41271),(35170,),(35180,),(35190,))


def weekly_used(db,account,now):
    if not db.in_transaction:raise ValueError('Secret count snapshot requires caller transaction')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='secret_reward_weeks'").fetchone():
        return 0
    week=_week(now)
    future=db.execute('SELECT MAX(week) FROM secret_reward_weeks WHERE account_id=?',(account,)).fetchone()[0]
    if future is not None and future>week:raise ValueError('Secret saved future week')
    row=db.execute('SELECT used FROM secret_reward_weeks WHERE account_id=? AND week=?',(account,week)).fetchone()
    used=0 if row is None else row[0]
    if type(used)is not int or not 0<=used<=5:raise ValueError('Secret saved quota bounds')
    return used


def sweep(path,owner,account,payload,operation,rewards,guard,qualify,now):
    from els_server.storage.inventory_actions import _identity,_previous,_commit
    from els_server.storage.inventory_state import load_items
    from els_server.storage.equipment_receipt_state import current_changes
    from els_server.storage.item_instances import remove
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    from els_server.storage.npc_trade import balances
    from els_server.storage.ariel_daily_special import notification
    from els_server.domain.item_expiration import require_current
    from els_server.domain.item_locks import require_unlocked
    from els_server.domain.legacy_pve_exp import experience_limit
    from els_server.protocol.protocol_codec import encode_event

    uid,stage=request(payload)
    owner,digest=_identity(owner,0xc0f,payload,operation)
    if rewards.uid!=owner or rewards.account_id!=account:
        raise ValueError('Secret sweep reward owner')
    announcements=[]
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        guard(db);require_active_character(db,owner);require_owner(db,owner,account)
        before=load_items(db,owner)
        previous=_previous(db,operation,digest)
        if previous is not None:
            changes=current_changes(db,operation,owner,0xc0f,previous,before)
        else:
            item=next((i for i in before if i['uid']==uid),None)
            if item is None or item['template'] not in TICKETS or item['group']!=4 or item.get('sealed'):
                raise ValueError('Owned usable secret sweep ticket required')
            require_current(item,now=now);require_unlocked(item,now=now)
            if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(99,):
                raise ValueError('Secret sweep level99 required')
            cleared={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(owner,))}
            choices=[mid for mid in STAGES[stage-1] if mid in cleared]
            if not choices:raise ValueError('Secret sweep requires this character to have cleared the selected stage')
            dungeon=choices[0]
            qualify(db,dungeon)
            value,_=policy();row=value['maps'][str(dungeon)]
            if row['stage']!=stage:raise ValueError('Secret sweep configured stage mismatch')
            _ensure(db);used=weekly_used(db,account,now)
            coupon=_coupon(db,owner) if used==value['weekly_count'] else None
            if used==value['weekly_count'] and coupon is None:
                raise ValueError('Secret weekly quota exhausted; extra reward ticket required')
            positions=[(item['group'],item['slot'])]
            if item['count']==1:remove(db,owner,item)
            else:db.execute('UPDATE inventory_items SET count=count-1 WHERE uid=? AND owner=?',(uid,owner))
            if coupon is not None:
                if coupon['count']!=1 or coupon['metadata']!=0:raise ValueError('Secret reward ticket identity')
                positions.append((coupon['group'],coupon['slot']));remove(db,owner,coupon)
            else:
                db.execute('INSERT INTO secret_reward_weeks VALUES(?,?,1) ON CONFLICT(account_id,week) DO UPDATE SET used=used+1',
                           (account,_week(now)))
            run=str(uuid.uuid5(uuid.NAMESPACE_URL,'secret-sweep:'+operation))
            reward=rewards.grant(run,payload,row['ed'],value['experience'],lambda balance:acknowledgement(ed=balance['ed']).payload,
                          transaction=db,experience_limit=experience_limit(),resonance_source='sweep',
                          experience_dungeon=dungeon)
            announcements=reward.get('announcements',[])
            after=load_items(db,owner)
            changes=[(pos,next((i for i in after if(i['group'],i['slot'])==pos),None))for pos in positions]
            _commit(db,operation,digest,owner,0xc0f,positions,before,after)
        # C10 refreshes the sweep window immediately; install the count map first.
        messages=[notification(db,account,owner,now),acknowledgement(changes,balances(db,owner)['ed'])]
        for event in messages:encode_event(event)
        guard(db)
        return dict(events=messages,announcements=announcements)
