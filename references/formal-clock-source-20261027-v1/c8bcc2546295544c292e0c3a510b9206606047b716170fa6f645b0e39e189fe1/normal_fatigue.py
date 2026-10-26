"""Character ordinary fatigue. Every mutation belongs to an existing SQL writer.

No migration reads life stamina or infers unknown old progress. First admission
uses the separately approved full4800 initialization; daily boundary is CN10AM.
Original-operation facts survive a rollback of code and never restore a DB.
"""
from pathlib import Path
import hashlib,json,sqlite3,time
from els_server.protocol.normal_fatigue_messages import notification
from els_server.protocol.protocol_codec import encode_event

MAXIMUM=4800
STATE_SQL='CREATE TABLE normal_fatigue_state(owner INTEGER PRIMARY KEY REFERENCES characters(uid),day INTEGER NOT NULL,current INTEGER NOT NULL CHECK(current BETWEEN 0 AND 4800),revision INTEGER NOT NULL CHECK(revision>0),observed_at INTEGER NOT NULL CHECK(observed_at>0))'
OPERATIONS_SQL='CREATE TABLE normal_fatigue_operations(operation TEXT PRIMARY KEY,owner INTEGER NOT NULL REFERENCES characters(uid),kind TEXT NOT NULL,context_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL,day INTEGER NOT NULL,effective_amount INTEGER NOT NULL,before_value INTEGER NOT NULL,after_value INTEGER NOT NULL,observed_at INTEGER NOT NULL,prior_state_json TEXT NOT NULL)'

def _exists(db,name):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone())

def _clock(now=None):
    value=int(time.time())if now is None else now
    if type(value)is not int or not 1<=value<2**63:
        raise ValueError('Ordinary fatigue clock')
    return value

def _day(now):return(now-7200)//86400  # UTC+8 10:00 == UTC02:00.

def _actor(db,owner,account):
    from els_server.storage.profession_state import require_owner
    from els_server.storage.item_actor import require_active_character
    require_owner(db,owner,account);require_active_character(db,owner)

def _saved(db,owner):
    if not _exists(db,'normal_fatigue_state'):return None
    row=db.execute('SELECT owner,day,current,revision,observed_at FROM normal_fatigue_state WHERE owner=?',(owner,)).fetchone()
    if row is None:return None
    if(any(type(v)is not int for v in row)or row[0]!=owner or not 0<=row[2]<=MAXIMUM
       or not 0<row[3]<2**63 or row[4]<=0 or row[1]!=_day(row[4])):
        raise ValueError('Ordinary fatigue saved state')
    return dict(zip(('owner','day','current','revision','observed_at'),row))

def snapshot(db,owner,account,*,now=None):
    from els_server.storage.profession_state import require_owner
    require_owner(db,owner,account);clock=_clock(now);saved=_saved(db,owner)
    if saved is None:return dict(owner=owner,maximum=MAXIMUM,current=MAXIMUM,day=_day(clock),revision=0)
    # A backwards wall clock cannot create a second daily refill.
    day=max(_day(clock),saved['day'])
    return dict(owner=owner,maximum=MAXIMUM,current=MAXIMUM if day>saved['day']else saved['current'],day=day,revision=saved['revision'])

def _writer(db,path):
    if not isinstance(db,sqlite3.Connection)or not db.in_transaction:
        raise ValueError('Ordinary fatigue requires original active writer')
    attached=db.execute('PRAGMA database_list').fetchall();main=[r for r in attached if r[1]=='main']
    if len(main)!=1 or Path(main[0][2]).resolve()!=Path(path).resolve()or any(r[1]not in('main','temp')for r in attached):
        raise ValueError('Ordinary fatigue writer/save mismatch')

def _apply(db,path,owner,account,operation,kind,context,policy_sha256,amount,*,prepare,now=None):
    """Private primitive: callers supply a source-qualified amount and guard.

    Runtime callers must bind their current actor/run or owned source inside
    prepare(db), before and after encoding. This is never a network grant API.
    """
    _writer(db,path);_actor(db,owner,account);prepare(db)
    if(type(operation)is not str or not 1<=len(operation)<=240 or kind not in('stage','potion','level','reset')
       or type(context)is not dict or type(amount)is not int or not 0<=amount<=MAXIMUM
       or type(policy_sha256)is not str or len(policy_sha256)!=64):
        raise ValueError('Ordinary fatigue operation shape')
    bytes.fromhex(policy_sha256)
    digest=hashlib.sha256(json.dumps(context,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if _exists(db,'normal_fatigue_operations'):
        old=db.execute('SELECT owner,kind,context_sha256 FROM normal_fatigue_operations WHERE operation=?',(operation,)).fetchone()
        if old is not None:
            if old!=(owner,kind,digest):raise ValueError('Conflicting ordinary fatigue retry')
            state=snapshot(db,owner,account,now=now);event=notification(state['current']);encode_event(event);prepare(db)
            return dict(replayed=True,state=state,notification=event)
    clock=_clock(now);prior=_saved(db,owner)
    if prior is not None:clock=max(clock,prior['observed_at'])
    current=snapshot(db,owner,account,now=clock);before=current['current']
    if kind=='stage':after=max(0,before-amount);effective=before-after
    elif kind=='potion':
        if before==MAXIMUM or amount<=0:raise ValueError('Ordinary fatigue already full')
        after=min(MAXIMUM,before+amount);effective=after-before
    else:
        if amount!=MAXIMUM:raise ValueError('Native full-refill source required')
        after=MAXIMUM;effective=after-before
    revision=(prior['revision']if prior else 0)+1
    if revision>=2**63:raise ValueError('Ordinary fatigue revision overflow')
    state=dict(owner=owner,maximum=MAXIMUM,current=after,day=_day(clock),revision=revision)
    event=notification(after);encode_event(event);prepare(db)
    db.execute(STATE_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    db.execute(OPERATIONS_SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
    if prior is None:
        db.execute('INSERT INTO normal_fatigue_state VALUES(?,?,?,?,?)',(owner,state['day'],after,revision,clock))
    elif db.execute('UPDATE normal_fatigue_state SET day=?,current=?,revision=?,observed_at=? WHERE owner=? AND revision=?',(state['day'],after,revision,clock,owner,prior['revision'])).rowcount!=1:
        raise ValueError('Ordinary fatigue state changed')
    db.execute('INSERT INTO normal_fatigue_operations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(operation,owner,kind,digest,policy_sha256,state['day'],effective,before,after,clock,json.dumps(prior,sort_keys=True)))
    _actor(db,owner,account);prepare(db)
    return dict(replayed=False,state=state,notification=event)

def level_up(db,path,owner,account,operation,proof_sha256,old_level,new_level):
    """Called by RewardState only after its actual level UPDATE affected a row.

    Its original reward receipt owns both changes and encoding/rollback. An
    existing reward replay returns before this hook; it cannot refill again.
    """
    from els_server.domain.normal_fatigue_rules import enabled,policy
    if not enabled():return None
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if row is None:return None  # Original anonymous legacy reward store.
    if account is not None and account!=row[0]:raise ValueError('Fatigue level reward owner')
    if type(old_level)is not int or type(new_level)is not int or not 1<=old_level<new_level<=99:raise ValueError('Fatigue actual ordinary level increase')
    account=row[0]
    def prepare(writer):
        _writer(writer,path);_actor(writer,owner,account)
        if writer.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()!=(new_level,):raise ValueError('Fatigue changed original reward level')
    return _apply(db,path,owner,account,'fatigue-level:'+operation,'level',dict(reward=operation,owner=owner,proof_sha256=proof_sha256,old_level=old_level,new_level=new_level),policy()['sha256'],MAXIMUM,prepare=prepare)
