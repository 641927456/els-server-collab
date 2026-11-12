"""Persist the admitted challenge/free-practice result, without rewards.

Challenge policy: AP/ED/EXP zero, no rating or official record changes.
Completed opposing challenge rounds advance only their native mentor tasks.
Free-channel practice changes neither mentor tasks nor official records.
The existing native round owns death, timeout HP comparison and departure.
"""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
from els_server.domain import pvp_actor
from els_server.domain.pvp_round import DeathResult
from els_server.protocol.protocol_codec import encode_event,decode_event
from els_server.storage.item_actor import require_active_character

POLICY='town-guild-challenge-result-only-20261105'
TABLE='native_duel_results'


def _json(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'))


def settle(rounds,actor,*,encode):
    result=rounds.result(actor)
    if(type(result)is not DeathResult or result.room.kind not in('challenge','practice')
       or result.members!=result.room.members or len(result.members)!=2
       or result.reason not in('kill','timeout','leave')
       or type(result.elapsed)is not int or not 0<=result.elapsed<=300
       or result.killer is not None and result.killer not in result.members
       or result.victim is not None and result.victim not in result.members
       or result.reason=='kill'and(result.victim is result.killer or set(result.members)!={result.victim,result.killer})
       or result.reason=='leave'and result.leaver not in result.members):
        raise ValueError('Duel original sealed challenge required')
    members=result.members
    if(len({m.account.uid for m in members})!=2
       or len({m.account.account_id for m in members})!=2):
        raise ValueError('Duel distinct real owners required')
    paths={Path(m.account.store.path).resolve()for m in members}
    if len(paths)!=1:raise ValueError('Duel shared actor database required')
    guards=tuple(pvp_actor.capture(rounds.world,m)for m in members)
    signature=rounds._signature(result.room,rounds.rounds[result.seed])
    kind=result.room.kind
    def guard():
        for member,check in zip(members,guards):
            check()
            if rounds.result(member)is not result:raise ValueError('Duel result generation changed')
        if(result.room.kind!=kind
           or rounds._signature(result.room,rounds.rounds.get(result.seed))!=signature):
            raise ValueError('Duel original round changed')
    proof=dict(policy=POLICY if kind=='challenge'else'free-practice-result-only-20261112',seed=result.seed,room=result.room.identity,map=result.room.map_id,
        elapsed=result.elapsed,reason=result.reason,
        members=[dict(uid=m.account.uid,account=m.account.account_id,
            invitation=next(t.generation for t in result.room.tickets if t.session is m))for m in members],
        killer=None if result.killer is None else result.killer.account.uid,
        victim=None if result.victim is None else result.victim.account.uid,
        leaver=None if result.leaver is None else result.leaver.account.uid,
        reports=[dict(uid=m.account.uid,raw=value.raw.hex())for m,value in result.reports])
    if kind=='practice':proof['seconds']=result.room.seconds
    digest=hashlib.sha256(_json(proof).encode()).hexdigest()
    with closing(sqlite3.connect(next(iter(paths)),timeout=10))as db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        try:
            guard()
            for m in members:
                require_active_character(db,m.account.uid)
                if db.execute('SELECT account_id FROM character_owners WHERE uid=?',(m.account.uid,)).fetchone()!=(m.account.account_id,):
                    raise ValueError('Duel saved owner changed')
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone()
            old=None if not exists else db.execute('SELECT proof_hash,result_json FROM native_duel_results WHERE seed=?',(result.seed,)).fetchone()
            if old is not None:
                if old[0]!=digest:raise ValueError('Duel conflicting result receipt')
                receipt=json.loads(old[1])
                events={m:tuple(decode_event(bytes.fromhex(raw))for raw in receipt['events'][str(m.account.uid)])for m in members}
                for group in events.values():
                    for event in group:encode_event(event)
                guard();db.rollback()
                return events,receipt,True
            rows=[]
            for m in members:
                balance=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(m.account.uid,)).fetchone()
                if balance is None or any(type(n)is not int or not 0<=n<2**63 for n in balance):
                    raise ValueError('Duel existing reward balance required')
                rows.append(dict(uid=m.account.uid,account=m.account.account_id,
                    win=m is result.killer,rating_delta=0,ap_delta=0,awarded_exp=0,
                    balances=dict(zip(('ed','experience','revision'),balance))))
            events=encode(db,result,tuple(rows))
            if type(events)is not dict or set(events)!=set(members):raise ValueError('Duel both complete native replies required')
            if kind=='challenge'and result.reason in('kill','timeout'):
                from els_server.domain.mentor_play import opponents
                from els_server.storage.mentor_quests import record as mentor_record
                fact=opponents(db,members)
                if fact is not None:
                    def mentor_guard(writer):guard();return True
                    activity=dict(kind='duel',winner=None if result.killer is None else result.killer.account.uid)
                    for member in members:
                        events[member]=tuple(events[member])+tuple(mentor_record(db,member.account.uid,
                            result.seed+':mentor-duel',fact,activity,mentor_guard))
            encoded={}
            for m,row in zip(members,rows):
                events[m]=tuple(events[m])
                if sum(e.event_id==0x201 and e.kind==0xc2 for e in events[m])!=1:
                    raise ValueError('Duel one original C2 per actor required')
                encoded[str(m.account.uid)]=[encode_event(e).hex()for e in events[m]]
                if db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(m.account.uid,)).fetchone()!=tuple(row['balances'][k]for k in('ed','experience','revision')):
                    raise ValueError('Duel encoder changed reward balances')
            receipt=json.loads(_json(dict(proof=proof,rows=rows,events=encoded)))
            db.execute('CREATE TABLE IF NOT EXISTS native_duel_results(seed TEXT PRIMARY KEY,proof_hash TEXT NOT NULL,result_json TEXT NOT NULL)')
            db.execute('INSERT INTO native_duel_results VALUES(?,?,?)',(result.seed,digest,_json(receipt)))
            guard();db.commit()
            return events,receipt,False
        except BaseException:
            db.rollback();raise
