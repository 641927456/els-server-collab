"""Atomic official1v1 settlement from the original admitted room's sealed result."""
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import sqlite3

from els_server.domain import pvp_actor, pvp_quests
from els_server.domain.pvp_official_1v1_policy import plan, POLICY
from els_server.domain.pvp_round import DeathResult
from els_server.protocol.protocol_codec import encode_event, decode_event
from els_server.storage import pvp_official_profiles as profiles

WRITER_ENABLED = True
TABLE = 'official_pvp_results'

def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))

def _economics(result,member,own,other,level):
    if result.reason=='leave':
        outcome='leave'if member is result.leaver else'win'if member is result.killer else'aborted'
    else:outcome='draw'if result.killer is None else'win'if member is result.killer else'loss'
    killed=result.reason=='kill'
    return plan(own,other,outcome=outcome,level=level,kills=int(killed and member is result.killer),
        maximum_damage_kills=int(killed and member is result.killer),deaths=int(killed and member is result.victim))

def settle(rounds, actor, *, encode):
    """Consume the exact sealed first-kill object; no player winner parameter.

    encode(db, result, rows) returns {session: tuple[Event,...]} including each
    C2 and full required persistence notifications. It must not publish to
    mailboxes. This leaf returns prepared events only after the single commit.
    """
    if not callable(encode):raise ValueError('PvP complete native encoder required')
    result=rounds.result(actor)
    if type(result) is not DeathResult or result.members!=result.room.members:
        raise ValueError('PvP original sealed result required')
    members=result.members
    if (len(members)!=2 or result.reason not in ('kill','timeout','leave')
        or result.killer is not None and result.killer not in members
        or result.reason=='kill' and (result.victim is result.killer or set(members)!={result.victim,result.killer})
        or result.reason=='leave' and result.leaver not in members
        or len({m.account.uid for m in members})!=2
        or len({m.account.account_id for m in members})!=2):
        raise ValueError('PvP two original distinct actors required')
    paths={Path(m.account.store.path).resolve() for m in members}
    if len(paths)!=1:raise ValueError('PvP same real SQL database required')
    guards=tuple(pvp_actor.capture(rounds.world,m) for m in members)
    signature=rounds._signature(result.room,rounds.rounds[result.seed])
    def guard():
        for m,g in zip(members,guards):
            g()
            if rounds.result(m) is not result:raise ValueError('PvP sealed result replaced')
        if rounds._signature(result.room,rounds.rounds.get(result.seed))!=signature:
            raise ValueError('PvP original round changed')
    proof=dict(policy=POLICY,seed=result.seed,room=result.room.identity,
        map=result.room.map_id,elapsed=result.elapsed,
        members=[dict(uid=m.account.uid,account=m.account.account_id,
            ticket=next(t.generation for t in result.room.tickets if t.session is m)) for m in members],
        victim=None if result.victim is None else result.victim.account.uid,
        killer=None if result.killer is None else result.killer.account.uid,reason=result.reason,
        leaver=None if result.leaver is None else result.leaver.account.uid,
        reports=[dict(uid=m.account.uid,raw=r.raw.hex()) for m,r in result.reports])
    digest=hashlib.sha256(_json(proof).encode()).hexdigest()
    with closing(sqlite3.connect(next(iter(paths)),timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        try:
            guard()
            levels=[profiles._owner(db,m.account.uid,m.account.account_id) for m in members]
            old=None if not profiles._exists(db,TABLE) else db.execute(
                'SELECT proof_hash,result_json FROM official_pvp_results WHERE seed=?',(result.seed,)).fetchone()
            if old is not None:
                if old[0]!=digest:raise ValueError('PvP conflicting result receipt')
                receipt=json.loads(old[1]);events={m:tuple(decode_event(bytes.fromhex(raw)) for raw in receipt['events'][str(m.account.uid)]) for m in members}
                for group in events.values():
                    for event in group:encode_event(event)
                guard();db.rollback()
                return events,receipt,True
            if not WRITER_ENABLED:raise ValueError('PvP result writer held pending modern result integration')
            before=[profiles.snapshot(db,m.account.uid,m.account.account_id) for m in members]
            if any(p is None for p in before):raise ValueError('PvP registered saved profile required')
            for m,saved in zip(members,before):
                ticket=next(t for t in result.room.tickets if t.session is m)
                if ticket.profile!=saved[0]:raise ValueError('PvP profile changed since original registration')
            from els_server.domain.legacy_pve_exp import experience_limit
            from els_server.game_data import client_data
            cap=experience_limit();data=client_data();rows=[]
            for i,m in enumerate(members):
                economics=_economics(result,m,before[i][0],before[1-i][0],levels[i])
                win=bool(economics.win_increment)
                balance=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(m.account.uid,)).fetchone()
                if balance is None or any(type(n) is not int or not 0<=n<2**63 for n in balance):
                    raise ValueError('PvP valid existing reward balance required')
                award=min(economics.raw_exp,max(0,cap-balance[1]));total=balance[1]+award
                if balance[2]>=2**63-1:raise ValueError('PvP balance revision overflow')
                db.execute('UPDATE reward_balances SET experience=?,revision=revision+1 WHERE uid=?',(total,m.account.uid))
                level=data.level_for_experience(total)
                if level>levels[i]:
                    db.execute('UPDATE characters SET level=?,revision=revision+1 WHERE uid=?',(level,m.account.uid))
                    from els_server.storage.normal_fatigue import level_up
                    level_up(db,next(iter(paths)),m.account.uid,m.account.account_id,'pvp:'+result.seed,digest,levels[i],level)
                db.execute('UPDATE official_pvp_profiles SET profile_json=?,revision=revision+1 WHERE uid=? AND revision=?',
                    (_json(asdict(economics.after)),m.account.uid,before[i][1]))
                changed=pvp_quests.advance(db,m.account.uid,levels[i],economics.after,win,played=bool(economics.play_increment))
                from els_server.storage.mentor45000_scope import official_win
                mentor_events=official_win(db,m.account.uid,m.account.account_id,rounds,result,lambda db:guard()) if win else []
                if mentor_events:
                    from els_server.storage.seal_quests import _state
                    from els_server.storage.inventory_state import load_items
                    changed+=tuple(r for r in _state(db,m.account.uid,load_items(db,m.account.uid))['active']if r['id']==45000)
                rows.append(dict(uid=m.account.uid,account=m.account.account_id,before=asdict(economics.before),after=asdict(economics.after),
                    revision=before[i][1]+1,raw_exp=economics.raw_exp,awarded_exp=award,
                    balances=dict(ed=balance[0],experience=total,revision=balance[2]+1),quests=changed,
                    outcome=economics.outcome,played=bool(economics.play_increment),win=win))
            guard()
            events=encode(db,result,tuple(rows))
            if type(events) is not dict or set(events)!=set(members):raise ValueError('PvP both complete response sets required')
            encoded={}
            for m in members:
                events[m]=tuple(events[m])
                if sum(e.event_id==0x201 and e.kind==0xc2 for e in events[m])!=1:
                    raise ValueError('PvP one native C2 per original actor required')
                encoded[str(m.account.uid)]=[encode_event(e).hex() for e in events[m]]
            guard()
            for i,m in enumerate(members):
                if profiles.snapshot(db,m.account.uid,m.account.account_id)!=(_economics(result,m,before[i][0],before[1-i][0],levels[i]).after,before[i][1]+1):
                    raise ValueError('PvP saved result readback')
                if db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(m.account.uid,)).fetchone()!=tuple(rows[i]['balances'][k] for k in ('ed','experience','revision')):
                    raise ValueError('PvP saved economic readback')
            # Return exactly the persisted JSON representation even on the
            # first call (objective-map integer keys become JSON strings).
            receipt=json.loads(_json(dict(proof=proof,rows=rows,events=encoded)))
            db.execute('CREATE TABLE IF NOT EXISTS official_pvp_results(seed TEXT PRIMARY KEY,proof_hash TEXT NOT NULL,result_json TEXT NOT NULL)')
            db.execute('INSERT INTO official_pvp_results VALUES(?,?,?)',(result.seed,digest,_json(receipt)))
            guard();db.commit()
            return events,receipt,False
        except BaseException:
            db.rollback();raise
