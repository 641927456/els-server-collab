"""One permanent enrollment per account; ordinary quests own all five rewards."""
import hashlib,json,sqlite3,time
from contextlib import closing
from els_server.storage.sqlite_timing import write_transaction
from els_server.domain.quick_start import QUESTS,career_transition

def ensure(db):
    db.execute('CREATE TABLE IF NOT EXISTS quick_start_accounts (account INTEGER PRIMARY KEY CHECK(account>0),uid INTEGER NOT NULL UNIQUE,created_at INTEGER NOT NULL)')

def enrollment(db,account):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='quick_start_accounts'").fetchone():return None
    row=db.execute('SELECT uid FROM quick_start_accounts WHERE account=?',(account,)).fetchone()
    return row[0] if row else None

def participant(db,uid,account=None):
    if account is None:
        row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
        if row is None:return False
        account=row[0]
    return enrollment(db,account)==uid

def enroll(db,uid,account,now):
    ensure(db)
    if enrollment(db,account) is not None:raise ValueError('Quick Start account already enrolled')
    db.execute('INSERT INTO quick_start_accounts VALUES (?,?,?)',(account,uid,now))
    from els_server.storage.seal_quests import ensure as quest_ensure
    quest_ensure(db)
    accept_next(db,uid,now)

def accept_next(db,uid,now):
    if not participant(db,uid):return ()
    from els_server.domain.seal_quests import quest_catalog,require_eligible,target,ACTIVE_QUEST_LIMIT
    from els_server.storage.seal_quests import load_character
    from els_server.storage.inventory_state import load_items
    done={r[0]for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))}
    qid=next((q for q in QUESTS if q not in done),None)
    if qid is None or db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=?',(uid,qid)).fetchone():return ()
    if db.execute('SELECT count(*) FROM character_quests WHERE owner=?',(uid,)).fetchone()[0]>=ACTIVE_QUEST_LIMIT:
        raise ValueError('Quick Start quest capacity')
    quest=quest_catalog().quest(qid);character=load_character(db,uid)
    require_eligible(character,quest,done,load_items(db,uid))
    counts={s['m_iID']:0 for s in quest_catalog().objectives(qid)}
    db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,qid,now,now,json.dumps(counts,sort_keys=True)))
    return (qid,)

def change_career(path,uid,account,target,operation,prepare,encode):
    from els_server.storage.careers import _apply_transition
    from els_server.storage.seal_quests import completed_ids,load_character
    digest=hashlib.sha256(json.dumps([account,uid,target]).encode()).hexdigest()
    with closing(sqlite3.connect(path,timeout=10))as db,write_transaction(db):
        prepare(db)
        if not participant(db,uid,account):raise ValueError('Quick Start career participant')
        db.execute('CREATE TABLE IF NOT EXISTS quick_start_career_receipts(operation TEXT PRIMARY KEY,request_hash TEXT NOT NULL)')
        old=db.execute('SELECT request_hash FROM quick_start_career_receipts WHERE operation=?',(operation,)).fetchone()
        if old and old!=(digest,):raise ValueError('Conflicting Quick Start career retry')
        before=load_character(db,uid,account)
        retired=[]
        if old:after=before
        else:
            _,after=_apply_transition(db,uid,lambda c:career_transition(c,target,completed_ids(db,uid)))
            from els_server.domain.character_rules import CLASSES
            if CLASSES[after['unit_class']]['stage']==3 and CLASSES[before['unit_class']]['stage']!=3:
                from els_server.domain.quick_start import catalog
                # The native event explicitly skips these Epic IDs. This is
                # completion without ED/EXP/items, within the career writer.
                now=int(time.time())
                for qid in catalog()['clear_epic_quests']:
                    db.execute('DELETE FROM character_quests WHERE owner=? AND quest=?',(uid,qid))
                    if db.execute('INSERT OR IGNORE INTO completed_quests VALUES (?,?,?,?)',
                        (uid,qid,now,json.dumps({'quick_start_skip':True}))).rowcount:retired.append(qid)
            db.execute('INSERT INTO quick_start_career_receipts VALUES (?,?)',(operation,digest))
        events=encode(db,before,after,bool(old),retired)
        prepare(db)
        return events
