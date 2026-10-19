"""Prospective static-kill title ledger; immutable event identity and atomic DTO."""
from contextlib import closing
import hashlib,json,sqlite3,time,uuid
from els_server.storage import titles,title_counts

def validate(context,proof):
    fields={'run','dungeon','stage','part','visits','key','npc','graph'}
    if not isinstance(context,dict) or set(context)!=fields:raise ValueError('Title death context')
    if str(uuid.UUID(context['run']))!=context['run']:raise ValueError('Title death run')
    if any(type(context[k]) is not int or not 0<=context[k]<=2147483647 for k in ('dungeon','stage','part','visits','key','npc')) or not context['dungeon'] or not context['npc'] or not context['visits']:raise ValueError('Title death bounds')
    if not isinstance(context['graph'],str) or len(context['graph'])!=64 or bytes.fromhex(context['graph']).hex()!=context['graph']:raise ValueError('Title graph hash')
    if not isinstance(proof,bytes) or not 1<=len(proof)<=8192:raise ValueError('Title death proof')

def matches(o,context):
    return getattr(o,'kind',8)==2 and context['npc'] in o.npcs and (not o.maps or context['dungeon'] in o.maps)

def record(path,uid,context,proof,*,now=None):
    validate(context,proof)
    # This API is called only by the accepted-death observer, not a client
    # title request. No kill requests or arbitrary template reports are added.
    identity={k:context[k] for k in ('run','stage','part','visits','key')}
    identity['owner']=uid
    key=hashlib.sha256(json.dumps(identity,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    digest=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()+b':'+proof).hexdigest()
    now=int(time.time()) if now is None else now
    if type(now) is not int or not 0<=now<2**40:raise ValueError('Title event clock')
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('BEGIN IMMEDIATE');character=titles.character(db,uid)
        if titles.exists(db,'title_kill_receipts'):
            old=db.execute('SELECT owner,request_sha256 FROM title_kill_receipts WHERE event_id=?',(key,)).fetchone()
            if old:
                if old!=(uid,digest):raise ValueError('Conflicting title death retry')
                return dict(replayed=True,awarded=())
        if not any(matches(o,context) for r in title_counts.rules() for o in r.objectives):return dict(replayed=False,awarded=())
        awarded=title_counts.advance(db,character,now,lambda o:matches(o,context))
        # Record even a level-ineligible kill. Replaying that event after a
        # later unlock cannot manufacture a prospective title count.
        db.execute('CREATE TABLE IF NOT EXISTS title_kill_receipts(event_id TEXT PRIMARY KEY,owner INTEGER NOT NULL,request_sha256 TEXT NOT NULL)')
        db.execute('INSERT INTO title_kill_receipts VALUES (?,?,?)',(key,uid,digest))
        return dict(replayed=False,awarded=awarded)
