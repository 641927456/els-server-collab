"""Explicit, owned old-starter location recovery; never a progress migration."""
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
import hashlib,json,math,re,shutil,sqlite3,time,uuid

SCHEMA="CREATE TABLE IF NOT EXISTS tutorial_recovery_receipts (account_id INTEGER NOT NULL CHECK(account_id>0), operation_id TEXT NOT NULL CHECK(length(operation_id)=36 AND operation_id GLOB '????????-????-4???-[89ab]???-????????????' AND length(replace(operation_id,'-',''))=32 AND replace(operation_id,'-','') NOT GLOB '*[^0-9a-f]*'), owner INTEGER NOT NULL REFERENCES character_owners(uid), request_hash TEXT NOT NULL CHECK(length(request_hash)=64 AND request_hash NOT GLOB '*[^0-9a-f]*'), before_location TEXT NOT NULL CHECK(length(before_location) BETWEEN 1 AND 1024), target_town INTEGER NOT NULL CHECK(target_town IN (20011,20012,20014)), backup_name TEXT NOT NULL CHECK(length(backup_name) BETWEEN 1 AND 100), PRIMARY KEY(account_id,operation_id))"
MAX_BACKUP=268435456
LOCATION=('uid','town','board','progress','x','y','z','revision')
FACTS=(('characters','uid'),('location','uid'),('character_quests','owner'),('completed_quests','owner'),
       ('inventory_items','owner'),('reward_balances','uid'),('skill_slots','uid'),('character_artifacts','uid'))

class RecoveryError(ValueError):pass

def bounded_json(document):
    body=json.dumps(document,separators=(',',':')).encode('utf8')
    if not 1<=len(body)<=2048:raise RecoveryError('recovery_unavailable')
    return document

def table(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() is not None

def readonly(path):
    path=Path(path).resolve()
    if not path.is_file():raise RecoveryError('recovery_unavailable')
    return sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.25)

def identity(uid,account_id):
    if type(uid) is not int or not 1001<=uid<=2**53-1 or type(account_id) is not int or not 1<=account_id<2**63:
        raise RecoveryError('invalid_request')

def validate_request(uid,version,operation_id,account_id):
    identity(uid,account_id)
    if not isinstance(version,str) or not re.fullmatch('[0-9a-f]{64}',version):raise RecoveryError('invalid_request')
    try:parsed=uuid.UUID(operation_id) if isinstance(operation_id,str) else None
    except (ValueError,AttributeError):parsed=None
    if parsed is None or str(parsed)!=operation_id or parsed.version!=4 or parsed.variant!=uuid.RFC_4122:raise RecoveryError('invalid_request')
    return hashlib.sha256(json.dumps([account_id,uid,version,operation_id],separators=(',',':')).encode()).hexdigest()

def owned(db,uid,account_id):
    identity(uid,account_id)
    if not all(table(db,t) for t in ('characters','character_owners','location')):raise RecoveryError('recovery_unavailable')
    owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
    if owner is None or tuple(owner)!=(account_id,):raise RecoveryError('recovery_unavailable')

def location(db,uid):
    from els_server.storage.local_state import validate_location
    row=db.execute('SELECT uid,town,board,progress,x,y,z,revision FROM location WHERE uid=?',(uid,)).fetchone()
    if row is None or any(type(row[i]) is not int for i in (0,1,2,3,7)) or row[7]<0:raise RecoveryError('recovery_unavailable')
    validate_location(row[1],row[2],row[3],row[4:7])
    return dict(zip(LOCATION,row))

def inspect(db,uid,account_id):
    """Pure reads, including on old schemas; do not call any ensure/constructor."""
    owned(db,uid,account_id)
    from els_server.storage.characters import Characters,validate_name
    from els_server.domain.character_rules import validate_career_state
    from els_server.domain.tutorial_quests import starter
    from els_server.domain.seal_quests import quest_catalog,require_eligible
    raw=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
    if raw is None or raw[5] not in (0,1) or raw[6] not in (0,1):raise RecoveryError('recovery_unavailable')
    character=Characters._row(raw);validate_name(character['name']);character['artifact']=None
    if table(db,'character_artifacts'):
        artifact=db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=?',(uid,)).fetchone()
        if artifact:
            character['artifact']=dict(zip(('template','evolution','level','experience','potentials'),artifact));character['artifact']['potentials']=json.loads(artifact[4])
    validate_career_state(character);old=location(db,uid)
    if character['unit_type'] not in (13,14,15) or old['town']!=20000:raise RecoveryError('recovery_unavailable')
    catalog=quest_catalog();active=[];completed=[]
    if table(db,'character_quests'):active=[r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))]
    if table(db,'completed_quests'):completed=[r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))]
    if len(active)>=30 or any(q not in catalog.quests or catalog.quest(q)['m_eQuestType']==5 for q in active+completed):raise RecoveryError('recovery_unavailable')
    quest,target=starter(character['unit_type'])
    items=[dict(template=r[0],count=r[1]) for r in db.execute('SELECT template,count FROM inventory_items WHERE owner=? ORDER BY uid',(uid,))] if table(db,'inventory_items') else []
    require_eligible(character,quest,set(completed),items,location=('town',target))
    facts=[['owner',account_id,uid],['starter',quest,target]]
    for name,key in FACTS:
        exists=table(db,name)
        rows=db.execute('SELECT * FROM '+name+' WHERE '+key+'=? ORDER BY 1',(uid,)).fetchall() if exists else []
        facts.append([name,exists,[tuple(r) for r in rows]])
    version=hashlib.sha256(repr(facts).encode('utf8')).hexdigest()
    descriptor=dict(uid=uid,name=character['name'],unit_type=character['unit_type'],from_town=20000,target_town=target,version=version)
    return descriptor,old

def optional_descriptor(db,uid,account_id=1):
    try:return inspect(db,uid,account_id)[0]
    except (ValueError,sqlite3.Error,KeyError,TypeError):return None

def preview(path,account_id,offset):
    if type(offset) is not int or not 0<=offset<=100000:raise RecoveryError('invalid_request')
    with closing(readonly(path)) as db:
        db.execute('BEGIN')
        if not table(db,'character_owners'):return bounded_json(dict(ok=True,characters=[],next_offset=None))
        ids=[r[0] for r in db.execute('SELECT uid FROM character_owners WHERE account_id=? ORDER BY uid LIMIT 5 OFFSET ?',(account_id,offset))]
        rows=[d for uid in ids[:4] if (d:=optional_descriptor(db,uid,account_id)) is not None]
        return bounded_json(dict(ok=True,characters=rows,next_offset=offset+4 if len(ids)>4 else None))

def receipt_reply(db,uid,account_id,operation_id,digest):
    owned(db,uid,account_id)
    if not table(db,'tutorial_recovery_receipts'):return None
    row=db.execute('SELECT owner,request_hash,before_location,target_town,backup_name FROM tutorial_recovery_receipts WHERE account_id=? AND operation_id=?',(account_id,operation_id)).fetchone()
    if row is None:return None
    if row[:2]!=(uid,digest):raise RecoveryError('recovery_conflict')
    old=json.loads(row[2])
    if set(old)!=set(LOCATION) or old['uid']!=uid or old['town']!=20000 or row[3] not in (20011,20012,20014):raise RecoveryError('recovery_unavailable')
    if not isinstance(row[4],str) or not 1<=len(row[4])<=100 or Path(row[4]).name!=row[4] or '/' in row[4] or '\\' in row[4]:raise RecoveryError('recovery_unavailable')
    return bounded_json(dict(ok=True,uid=uid,from_town=20000,target_town=row[3],current_town=location(db,uid)['town'],replayed=True,backup=row[4]))

@dataclass(frozen=True)
class PreparationTicket:
    state_path:Path
    backups_path:Path
    account_id:int
    uid:int
    operation_id:str
    version:str
    request_hash:str
    original_location:tuple
    cache_generation:object
    prepared_monotonic:float
    deadline_monotonic:float
    stop:object

def prepare(path,account_id,uid,version,operation_id,cache_generation,stop,backups_path=None):
    digest=validate_request(uid,version,operation_id,account_id);now=time.monotonic();path=Path(path).resolve()
    with closing(readonly(path)) as db:
        db.execute('BEGIN');old=receipt_reply(db,uid,account_id,operation_id,digest)
        if old is not None:return old
        descriptor,oldloc=inspect(db,uid,account_id)
        if descriptor['version']!=version:raise RecoveryError('recovery_stale')
    return PreparationTicket(path,Path(backups_path) if backups_path else path.parent/'backups/tutorial-recovery',account_id,uid,operation_id,version,digest,
                             tuple(oldloc[k] for k in LOCATION),cache_generation,now,now+15,stop)

def backup_ticket(ticket):
    """Independent connections, no source transaction or game-executor hold."""
    def check(status=0,remaining=0,total=0):
        if ticket.stop.is_set() or time.monotonic()>ticket.deadline_monotonic or total*page_size>MAX_BACKUP:raise RecoveryError('recovery_backup_failed')
    page_size=4096
    try:
        with closing(readonly(ticket.state_path)) as source:
            source.execute('PRAGMA busy_timeout=250');page_size=source.execute('PRAGMA page_size').fetchone()[0]
            estimate=source.execute('PRAGMA page_count').fetchone()[0]*page_size
            if estimate>MAX_BACKUP:raise RecoveryError('recovery_backup_failed')
            ticket.backups_path.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(ticket.backups_path).free<2*estimate+16777216:raise RecoveryError('recovery_backup_failed')
            check();dest=ticket.backups_path/('recovery-'+ticket.operation_id+'-'+str(uuid.uuid4())+'.sqlite3')
            with dest.open('xb'):pass
            with closing(sqlite3.connect(dest,timeout=.25)) as target:
                target.execute('PRAGMA busy_timeout=250');target.set_progress_handler(lambda:int(ticket.stop.is_set() or time.monotonic()>ticket.deadline_monotonic),1000)
                source.backup(target,pages=256,progress=check,sleep=.02);check()
                if target.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:raise RecoveryError('recovery_backup_failed')
            if dest.stat().st_size>MAX_BACKUP:raise RecoveryError('recovery_backup_failed')
            return dest.name
    except (OSError,sqlite3.Error,RecoveryError):raise RecoveryError('recovery_backup_failed') from None

def apply_location(db,uid,target,old):
    if old['uid']!=uid or old['town']!=20000 or target not in (20011,20012,20014):raise RecoveryError('recovery_unavailable')
    changed=db.execute('UPDATE location SET town=?,board=0,progress=0,x=0,y=0,z=0,revision=revision+1 WHERE uid=? AND revision=? AND town=20000',(target,uid,old['revision']))
    if changed.rowcount!=1:raise RecoveryError('recovery_stale')

def finish(ticket,backup_name,guard):
    if time.monotonic()-ticket.prepared_monotonic>30 or ticket.stop.is_set():raise RecoveryError('recovery_stale')
    with closing(sqlite3.connect(ticket.state_path,timeout=.25)) as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('PRAGMA busy_timeout=250');db.execute('BEGIN IMMEDIATE');guard()
        replay=receipt_reply(db,ticket.uid,ticket.account_id,ticket.operation_id,ticket.request_hash)
        if replay is not None:return replay
        descriptor,old=inspect(db,ticket.uid,ticket.account_id)
        if descriptor['version']!=ticket.version or tuple(old[k] for k in LOCATION)!=ticket.original_location:raise RecoveryError('recovery_stale')
        reply=dict(ok=True,uid=ticket.uid,from_town=20000,target_town=descriptor['target_town'],current_town=descriptor['target_town'],replayed=False,backup=backup_name)
        bounded_json(reply);original=json.dumps(old,separators=(',',':'))
        if not 1<=len(original)<=1024:raise RecoveryError('recovery_unavailable')
        apply_location(db,ticket.uid,descriptor['target_town'],old)
        db.execute(SCHEMA)
        db.execute('INSERT INTO tutorial_recovery_receipts VALUES (?,?,?,?,?,?,?)',(ticket.account_id,ticket.operation_id,ticket.uid,ticket.request_hash,original,descriptor['target_town'],backup_name))
        guard();bounded_json(reply)
        return reply

def current_location(path,uid,account_id):
    with closing(readonly(path)) as db:
        owned(db,uid,account_id);row=location(db,uid)
        return dict(map=row['town'],board=row['board'],progress=row['progress'],xyz=(row['x'],row['y'],row['z']),revision=row['revision'])
