"""Atomic per-character base-context set selections and transport receipts."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3
from els_server.protocol.avatar_set_messages import request,acknowledgement,restoration
from els_server.protocol.protocol_codec import encode_event
from els_server.storage.character_schema import character_uid
from els_server.storage.luciel_state import identity,present

STATE='avatar_set_selections';RECEIPTS='avatar_set_apply_receipts'

def snapshot(db,uid):
    character_uid(uid)
    if present(db,STATE)!=present(db,RECEIPTS):raise ValueError('Incomplete avatar schema')
    if not present(db,STATE):return 0,()
    row=db.execute('SELECT revision,document,sha256 FROM avatar_set_selections WHERE uid=?',(uid,)).fetchone()
    if row is None:return 0,()
    revision,text,digest=row
    if type(revision) is not int or not 1<=revision<2**63 or type(text) is not str or hashlib.sha256(text.encode('utf-8')).hexdigest()!=digest:
        raise ValueError('Invalid saved avatar selection')
    try:rows=tuple(tuple(r) for r in json.loads(text))
    except (TypeError,json.JSONDecodeError) as exc:raise ValueError('Invalid avatar document') from exc
    restoration(rows)  # Full structure validation; never repair corrupt state.
    return revision,rows

def owner_side(db,uid,account_id):
    from els_server.game_data import client_data
    from els_server.storage.luciel_state import active_state
    row=db.execute('SELECT c.unit_type,c.unit_class,o.account_id FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone()
    if row is None or row[2]!=account_id or client_data().unit(row[1])['unitType']!=row[0]:raise ValueError('Avatar current owner/class')
    return active_state(db,uid)['active_unit'] if row[0]==10 else 0

def restore(path,uid,account_id):
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
        owner_side(db,uid,account_id);_,rows=snapshot(db,uid)
        return [restoration(rows)] if rows else []

def apply(path,uid,payload,*,account_id,session_id,sequence,validate,encode=None,effect=None):
    from els_server.domain.avatar_sets import available,catalog
    from els_server.storage.inventory_state import load_items
    uid,operation=identity(uid,session_id,sequence);rows=request(payload)
    if type(account_id) is not int or not 0<account_id<2**63:raise ValueError('Avatar account')
    digest=hashlib.sha256(payload).hexdigest();encoder=encode_event if encode is None else encode
    with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');validate()
        side=owner_side(db,uid,account_id)
        if any(r[1]!=side for r in rows):raise ValueError('Stale avatar editing side')
        revision,prior=snapshot(db,uid)
        old=db.execute('SELECT owner,account_id,request_sha,revision FROM avatar_set_apply_receipts WHERE operation_id=?',(operation,)).fetchone() if present(db,RECEIPTS) else None
        if old is not None:
            # BFD contains only result: stale success would reapply pending UI
            # rows, so a superseded frame is rejected rather than acknowledged.
            if old!=(uid,account_id,digest,revision):raise ValueError('Conflicting/superseded avatar retry')
            answer=acknowledgement(0);encoder(answer);validate();return answer
        retained={r[3] for r in prior if r[1]==side and r[3]}
        allowed=available(load_items(db,uid),side)|retained;sets,_=catalog()
        if any(r[3] and (r[3] not in sets or r[3] not in allowed) for r in rows):raise ValueError('Avatar set is not worn or retained')
        updated=tuple(sorted(tuple(r for r in prior if r[1]!=side)+rows,key=lambda r:(r[1],r[2])))
        revision+=int(updated!=prior)
        if not 1<=revision<2**63:raise ValueError('Avatar revision overflow')
        restoration(updated)
        text=json.dumps(updated,separators=(',',':'));state_sha=hashlib.sha256(text.encode('utf-8')).hexdigest()
        answer=acknowledgement(0);encoder(answer);validate()
        db.execute('CREATE TABLE IF NOT EXISTS avatar_set_selections(uid INTEGER PRIMARY KEY REFERENCES characters(uid) ON DELETE CASCADE,revision INTEGER NOT NULL CHECK(revision>0),document TEXT NOT NULL,sha256 TEXT NOT NULL CHECK(length(sha256)=64))')
        db.execute('CREATE TABLE IF NOT EXISTS avatar_set_apply_receipts(operation_id TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,account_id INTEGER NOT NULL,request_sha TEXT NOT NULL CHECK(length(request_sha)=64),revision INTEGER NOT NULL CHECK(revision>0))')
        db.execute('INSERT INTO avatar_set_selections VALUES (?,?,?,?) ON CONFLICT(uid) DO UPDATE SET revision=excluded.revision,document=excluded.document,sha256=excluded.sha256',(uid,revision,text,state_sha))
        db.execute('INSERT INTO avatar_set_apply_receipts VALUES (?,?,?,?,?)',(operation,uid,account_id,digest,revision));validate()
        if effect is not None:effect(db,rows,side,operation)
        validate()
        return answer
