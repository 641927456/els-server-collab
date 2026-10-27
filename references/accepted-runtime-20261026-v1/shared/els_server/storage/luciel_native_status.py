"""Bounded latest38E cursor and atomic active state, independent of other stats."""
import hashlib,re,sqlite3,struct,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid
from els_server.storage.luciel_state import active_state,state,present,ensure_active

CURSORS='luciel_status_cursors'


def ensure(db):
    if not db.in_transaction:raise ValueError('LuCiel status transaction required')
    db.execute('''CREATE TABLE IF NOT EXISTS luciel_status_cursors (
        uid INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        session_id TEXT NOT NULL,
        epoch TEXT NOT NULL,
        sequence INTEGER NOT NULL CHECK(typeof(sequence)='integer' AND sequence BETWEEN 1 AND 4294967295),
        request_hash TEXT NOT NULL CHECK(typeof(request_hash)='text' AND length(request_hash)=64 AND request_hash NOT GLOB '*[^0-9a-f]*'))''')


def canonical(value,versions):
    if type(value) is not str:raise ValueError('LuCiel status identity')
    parsed=uuid.UUID(value)
    if str(parsed)!=value or parsed.version not in versions:raise ValueError('LuCiel status generation')


def perform(path,uid,payload,*,account_id,session_id,epoch,sequence,validate,prepare,kind=0x38e):
    if kind==0x38e:
        from els_server.protocol.luciel_status_messages import request
    elif kind==0x67:
        from els_server.protocol.luciel_end_messages import request
    else:raise ValueError('LuCiel unsupported status kind')
    active=request(payload);uid=character_uid(uid)
    canonical(session_id,(4,));canonical(epoch,(4,5))
    if type(account_id) is not int or account_id<1:raise ValueError('LuCiel status account')
    if type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('LuCiel status sequence')
    digest=hashlib.sha256(struct.pack('>QH',uid,kind)+payload).hexdigest()
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        actor=db.execute('SELECT c.unit_type,c.unit_class,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
        if actor is None or actor[0]!=10 or actor[2]!=account_id:raise ValueError('LuCiel status current owner')
        from els_server.game_data import client_data
        if client_data().unit(actor[1])['unitType']!=10:raise ValueError('LuCiel status class family')
        current=active_state(db,uid);preference=state(db,uid)
        cursor=db.execute('SELECT session_id,epoch,sequence,request_hash FROM luciel_status_cursors WHERE uid=?',(uid,)).fetchone() if present(db,CURSORS) else None
        if cursor is not None:
            old_session,old_epoch,old_sequence,old_hash=cursor
            canonical(old_session,(4,));canonical(old_epoch,(4,5))
            if type(old_sequence) is not int or not 1<=old_sequence<2**32 or type(old_hash) is not str or re.fullmatch('[0-9a-f]{64}',old_hash) is None:raise ValueError('LuCiel invalid saved status cursor')
            if old_session==session_id and sequence<=old_sequence:
                if sequence==old_sequence and (old_hash!=digest or old_epoch!=epoch):raise ValueError('LuCiel conflicting status retry')
                validate()
                return dict(changed=False,prepared=None,active_unit=current['active_unit'],stale_or_retry=True)
        changed=active!=current['active_unit'];revision=current['revision']+int(changed)
        if revision>=2**63:raise ValueError('LuCiel active revision overflow')
        publication=prepare(dict(events=[],active_unit=active,style=preference['style'])) if changed else None
        validate()
        ensure_active(db);ensure(db)
        if changed:
            db.execute('INSERT INTO luciel_active_states(uid,active_unit,revision) VALUES(?,?,?) ON CONFLICT(uid) DO UPDATE SET active_unit=excluded.active_unit,revision=excluded.revision',(uid,active,revision))
        db.execute('INSERT INTO luciel_status_cursors(uid,session_id,epoch,sequence,request_hash) VALUES(?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET session_id=excluded.session_id,epoch=excluded.epoch,sequence=excluded.sequence,request_hash=excluded.request_hash',(uid,session_id,epoch,sequence,digest))
        validate()
        return dict(changed=changed,prepared=publication,active_unit=active,stale_or_retry=False)
