"""Prospective static-kill title ledger; immutable event identity and atomic DTO."""
from contextlib import closing
import hashlib,json,sqlite3,time,uuid
from els_server.storage import titles,title_counts
from pathlib import Path
from els_server.storage.read_scope import canonical_path

def validate(context,proof):
    fields={'run','dungeon','stage','part','visits','key','npc','graph'}
    if not isinstance(context,dict) or set(context)!=fields:raise ValueError('Title death context')
    if str(uuid.UUID(context['run']))!=context['run']:raise ValueError('Title death run')
    if any(type(context[k]) is not int or not 0<=context[k]<=2147483647 for k in ('dungeon','stage','part','visits','key','npc')) or not context['dungeon'] or not context['npc'] or not context['visits']:raise ValueError('Title death bounds')
    if not isinstance(context['graph'],str) or len(context['graph'])!=64 or bytes.fromhex(context['graph']).hex()!=context['graph']:raise ValueError('Title graph hash')
    if not isinstance(proof,bytes) or not 1<=len(proof)<=8192:raise ValueError('Title death proof')

def matches(o,context):
    return getattr(o,'kind',8)==2 and context['npc'] in o.npcs and (not o.maps or context['dungeon'] in o.maps)

def _inputs(uid,context,proof,now):
    validate(context,proof)
    # This API is called only by the accepted-death observer, not a client
    # title request. No kill requests or arbitrary template reports are added.
    identity={k:context[k] for k in ('run','stage','part','visits','key')}
    identity['owner']=uid
    key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    digest=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()+b':'+proof).hexdigest()
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 0<=now<2**40:raise ValueError('Title event clock')
    return key,digest,now

def _record(db,uid,context,key,digest,now):
    character=titles.character(db,uid)
    if titles.exists(db,'title_kill_receipts'):
        old=db.execute('SELECT owner,request_sha256 FROM title_kill_receipts WHERE event_id=?',(key,)).fetchone()
        if old:
            if old!=(uid,digest):raise ValueError('Conflicting title death retry')
            return dict(replayed=True,awarded=())
    if not any(matches(o,context) for r in title_counts.rules() for o in r.objectives):return dict(replayed=False,awarded=())
    awarded=title_counts.advance(db,character,now,lambda o:matches(o,context))
    db.execute('CREATE TABLE IF NOT EXISTS title_kill_receipts(event_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,request_sha256 TEXT NOT NULL)')
    db.execute('INSERT INTO title_kill_receipts VALUES (?,?,?)',(key,uid,digest))
    return dict(replayed=False,awarded=awarded)

def record_in_transaction(db,path,uid,context,proof,*,now=None):
    # The accepted-death caller already owns its source/actor and writer.
    # This helper cannot commit or roll back another operation.
    if not db.in_transaction:raise ValueError('Title kill requires caller writer')
    main=next(row[2]for row in db.execute('PRAGMA database_list')if row[1]=='main')
    if canonical_path(main)!=canonical_path(path):raise ValueError('Title kill writer database')
    key,digest,now=_inputs(uid,context,proof,now)
    return _record(db,uid,context,key,digest,now)

def record(path,uid,context,proof,*,now=None):
    key,digest,now=_inputs(uid,context,proof,now)
    with closing(sqlite3.connect(path,timeout=10)) as db,write_transaction(db):
        return _record(db,uid,context,key,digest,now)

from els_server.storage.sqlite_timing import write_transaction
