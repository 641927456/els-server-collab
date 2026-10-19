"""Lazy LuCiel style and active state; no item or combat-stat writes."""
import hashlib,re,sqlite3,struct,uuid
from contextlib import closing
from pathlib import Path
from els_server.storage.character_schema import character_uid
from els_server.protocol.luciel_messages import request,responses,style
from els_server.protocol.protocol_codec import encode_event

STATE='luciel_style_states';RECEIPTS='luciel_style_receipts'

def present(db,name):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def state(db,uid):
    uid=character_uid(uid)
    if not present(db,STATE):return dict(style=0,revision=0)
    row=db.execute('SELECT style,revision FROM luciel_style_states WHERE uid=?',(uid,)).fetchone()
    if row is None:return dict(style=0,revision=0)
    value,revision=row;style(value)
    if type(revision) is not int or not 0<=revision<2**63:raise ValueError('Invalid saved LuCiel revision')
    return dict(style=value,revision=revision)

def ensure(db):
    if not db.in_transaction:raise ValueError('LuCiel schema requires transaction')
    existing=(present(db,STATE),present(db,RECEIPTS))
    if existing[0]!=existing[1]:raise ValueError('Incomplete LuCiel schema')
    db.execute('''CREATE TABLE IF NOT EXISTS luciel_style_states (
        uid INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        style INTEGER NOT NULL CHECK(typeof(style)='integer' AND style BETWEEN 0 AND 2),
        revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0))''')
    db.execute('''CREATE TABLE IF NOT EXISTS luciel_style_receipts (
        operation_id TEXT PRIMARY KEY,
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
        request_hash TEXT NOT NULL CHECK(typeof(request_hash)='text' AND length(request_hash)=64))''')

def identity(uid,session_id,sequence):
    uid=character_uid(uid)
    if type(session_id) is not str:raise ValueError('LuCiel server connection UUID required')
    parsed=uuid.UUID(session_id)
    if parsed.version!=4 or str(parsed)!=session_id:raise ValueError('LuCiel canonical connection UUID required')
    if type(sequence) is not int or not 1<=sequence<2**32:raise ValueError('LuCiel wire sequence required')
    return uid,session_id+':luciel709:'+str(uid)+':'+str(sequence)

def perform(path,uid,payload,*,account_id,session_id,sequence,encode=None,prepare=None,validate=None):
    value=request(payload);uid,operation=identity(uid,session_id,sequence)
    if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('LuCiel real account required')
    digest=hashlib.sha256(struct.pack('>QH',uid,0x709)+payload).hexdigest()
    encoder=encode_event if encode is None else encode
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        if validate is not None:validate()
        row=db.execute('SELECT c.unit_type,c.unit_class,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
        if row is None or row[0]!=10 or row[2]!=account_id:raise ValueError('LuCiel current owned character required')
        from els_server.game_data import client_data
        if client_data().unit(row[1])['unitType']!=10:raise ValueError('LuCiel class identity mismatch')
        current=state(db,uid)
        old=db.execute('SELECT owner,request_hash FROM luciel_style_receipts WHERE operation_id=?',(operation,)).fetchone() if present(db,RECEIPTS) else None
        if old is not None:
            owner,saved_hash=old
            if type(owner) is not int or type(saved_hash) is not str or re.fullmatch('[0-9a-f]{64}',saved_hash) is None:raise ValueError('Invalid LuCiel receipt')
            if owner!=uid or saved_hash!=digest:raise ValueError('Conflicting LuCiel sequence retry')
            reply=responses(uid,current['style'])
            for event in reply:encoder(event)
            if prepare is not None:prepare(reply)
            if validate is not None:validate()
            return reply
        updated=dict(style=value,revision=current['revision']+int(value!=current['style']))
        if updated['revision']>=2**63:raise ValueError('LuCiel revision overflow')
        reply=responses(uid,updated['style'])
        # All fallible publication preparation precedes the first lazy DDL/write.
        for event in reply:encoder(event)
        if prepare is not None:prepare(reply)
        if validate is not None:validate()
        ensure(db)
        db.execute('INSERT INTO luciel_style_states VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET style=excluded.style,revision=excluded.revision',(uid,updated['style'],updated['revision']))
        db.execute('INSERT INTO luciel_style_receipts VALUES (?,?,?)',(operation,uid,digest))
        if validate is not None:validate()
        return reply


ACTIVE_STATE='luciel_active_states';ACTIVE_RECEIPTS='luciel_active_receipts'

def active_state(db,uid):
    from els_server.protocol.luciel_messages import active
    uid=character_uid(uid)
    existing=(present(db,ACTIVE_STATE),present(db,ACTIVE_RECEIPTS))
    if existing[0]!=existing[1]:raise ValueError('Incomplete LuCiel active schema')
    if not existing[0]:return dict(active_unit=0,revision=0)
    row=db.execute('SELECT active_unit,revision FROM luciel_active_states WHERE uid=?',(uid,)).fetchone()
    if row is None:return dict(active_unit=0,revision=0)
    value,revision=row;active(value)
    if type(revision) is not int or not 0<=revision<2**63:raise ValueError('Invalid saved LuCiel active revision')
    return dict(active_unit=value,revision=revision)

def ensure_active(db):
    if not db.in_transaction:raise ValueError('LuCiel active schema requires transaction')
    existing=(present(db,ACTIVE_STATE),present(db,ACTIVE_RECEIPTS))
    if existing[0]!=existing[1]:raise ValueError('Incomplete LuCiel active schema')
    db.execute("CREATE TABLE IF NOT EXISTS luciel_active_states (uid INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED, active_unit INTEGER NOT NULL CHECK(typeof(active_unit)='integer' AND active_unit BETWEEN 0 AND 1), revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0))")
    db.execute("CREATE TABLE IF NOT EXISTS luciel_active_receipts (operation_id TEXT PRIMARY KEY, owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED, request_hash TEXT NOT NULL CHECK(typeof(request_hash)='text' AND length(request_hash)=64 AND request_hash NOT GLOB '*[^0-9a-f]*'))")

def perform_active(path,uid,kind,payload,*,account_id,session_id,sequence,prepare,validate,encode=None):
    """Return prepared publication only after SQLite has committed successfully."""
    from els_server.protocol.luciel_messages import active_request,active_response,ACTIVE_REPLIES
    value=active_request(payload);uid,_=identity(uid,session_id,sequence)
    if type(kind) is not int or kind not in ACTIVE_REPLIES:raise ValueError('LuCiel active request kind')
    if type(account_id) is not int or not 1<=account_id<2**63:raise ValueError('LuCiel active account')
    operation=session_id+':luciel-active:'+str(uid)+':'+str(kind)+':'+str(sequence)
    digest=hashlib.sha256(struct.pack('>QH',uid,kind)+payload).hexdigest()
    encoder=encode_event if encode is None else encode
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        row=db.execute('SELECT c.unit_type,c.unit_class,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
        if row is None or row[0]!=10 or row[2]!=account_id:raise ValueError('LuCiel current active owner')
        from els_server.game_data import client_data
        if client_data().unit(row[1])['unitType']!=10:raise ValueError('LuCiel active class mismatch')
        current=active_state(db,uid);current_style=state(db,uid)['style']
        old=db.execute('SELECT owner,request_hash FROM luciel_active_receipts WHERE operation_id=?',(operation,)).fetchone() if present(db,ACTIVE_RECEIPTS) else None
        if old is not None:
            owner,saved_hash=old
            if type(owner) is not int or type(saved_hash) is not str or re.fullmatch('[0-9a-f]{64}',saved_hash) is None:raise ValueError('Malformed LuCiel active receipt')
            if owner!=uid or saved_hash!=digest:raise ValueError('Conflicting LuCiel active sequence')
            updated=current
        else:
            updated=dict(active_unit=value,revision=current['revision']+int(value!=current['active_unit']))
            if updated['revision']>=2**63:raise ValueError('LuCiel active revision overflow')
        events=[active_response(kind,uid,updated['active_unit'])]
        for event in events:encoder(event)
        if old is None:
            ensure_active(db)
            db.execute('INSERT INTO luciel_active_states VALUES (?,?,?) ON CONFLICT(uid) DO UPDATE SET active_unit=excluded.active_unit,revision=excluded.revision',(uid,updated['active_unit'],updated['revision']))
            db.execute('INSERT INTO luciel_active_receipts VALUES (?,?,?)',(operation,uid,digest))
        result=dict(events=events,active_unit=updated['active_unit'],style=current_style,revision=updated['revision'],retry=old is not None)
        result['prepared']=prepare(result)
        validate()
        return result
