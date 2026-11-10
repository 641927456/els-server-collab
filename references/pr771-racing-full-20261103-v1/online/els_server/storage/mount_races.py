"""Durable race plans, one stamina debit and one settlement per participant."""
from contextlib import closing
import hashlib,json,math,secrets,sqlite3,uuid
from els_server.domain import mount_racing_plan as plans,mount_racing_rules as rules
from els_server.storage import mount_growth,mount_state
from els_server.storage.item_actor import require_active_character
from els_server.storage.profession_state import require_owner


def dumps(v):return json.dumps(v,sort_keys=True,separators=(',',':'))


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS mount_races (
        id TEXT PRIMARY KEY,digest TEXT NOT NULL,started INTEGER NOT NULL,
        policy TEXT NOT NULL,data TEXT NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS mount_race_results (
        race TEXT NOT NULL REFERENCES mount_races(id),owner INTEGER NOT NULL,
        account_id INTEGER NOT NULL,mount INTEGER NOT NULL,lane INTEGER NOT NULL,
        disconnected INTEGER NOT NULL DEFAULT 0,settled INTEGER NOT NULL DEFAULT 0,
        receipt TEXT,PRIMARY KEY(race,owner))''')
    db.execute('''CREATE TABLE IF NOT EXISTS mount_race_busy (
        uid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,race TEXT NOT NULL REFERENCES mount_races(id))''')


def eligible(db,owner,account_id,uid,now):
    require_active_character(db,owner);require_owner(db,owner,account_id)
    if db.execute('SELECT level FROM characters WHERE uid=?',(owner,)).fetchone()[0]<rules.policy()['minimum_character_level']:
        raise ValueError('Racing requires character level99')
    mount=mount_state.owned(db,owner,uid)
    if 'expires_at'in mount or mount['unit']>=10000:raise ValueError('Racing requires a permanent player mount')
    mount=mount_state.settle(db,owner,mount,now)
    if mount['stamina']<rules.policy()['race_stamina']:raise ValueError('Racing requires60 stamina')
    return mount


def selected(path,owner,account_id,uid,*,prepare,now=None):
    now=mount_state.timestamp(now)
    from els_server.storage.companion_state import ensure as companions
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('BEGIN IMMEDIATE');prepare(db);companions(db);mount_state.ensure(db)
        mount=eligible(db,owner,account_id,uid,now);prepare(db)
        return mount


def begin(path,race,members,*,prepare,encode,now=None,randbelow=secrets.randbelow):
    """members is the controller's fixed (character,account,mount) roster.

    No rank, experience, reward or booster parameter is accepted from the wire.
    encode runs before commit and returns the fully prepared native deliveries.
    """
    if str(uuid.UUID(race))!=race:raise ValueError('Racing identity')
    if (not 3<=len(members)<=6 or len({m[0]for m in members})!=len(members)
            or len({m[1]for m in members})!=len(members)
            or len({m[2]for m in members})!=len(members)):
        raise ValueError('Racing requires3 to6 distinct real accounts')
    now=mount_state.timestamp(now);digest=hashlib.sha256(dumps(members).encode()).hexdigest()
    from els_server.storage.companion_state import ensure as companions
    from els_server.storage.inventory_state import grant_items
    from els_server.domain.reward_rules import item_plan
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        prepare(db);companions(db);mount_state.ensure(db);ensure(db)
        old=db.execute('SELECT digest,data FROM mount_races WHERE id=?',(race,)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Conflicting racing admission')
            data=json.loads(old[1]);answer=encode(db,data);prepare(db);return data,answer
        mounts=[]
        for owner,account_id,uid in members:
            if db.execute('SELECT 1 FROM mount_race_busy WHERE owner=? OR uid=?',(owner,uid)).fetchone():
                raise ValueError('Character or mount already racing')
            mounts.append(eligible(db,owner,account_id,uid,now))
            if len(members)==6:
                # Local admission rule: both possible bonus item groups must
                # fit before drawing. Racing blocks inventory writes until exit.
                db.execute('SAVEPOINT racing_capacity')
                grant_items(db,[item_plan(714109,5),item_plan(714108,1)],owner)
                db.execute('ROLLBACK TO racing_capacity');db.execute('RELEASE racing_capacity')
        roster={owner:plans.draw(mount['racing'],lane,randbelow)
                for lane,((owner,account_id,uid),mount)in enumerate(zip(members,mounts))}
        ranked=plans.standings(roster);awards={}
        for row in ranked:
            mount=mounts[row['lane']];saved=mount['racing']
            awards[row['uid']]=rules.result(saved['experience'],saved['stats'],row['rank'],len(members),randbelow)
        data=dict(plans=roster,standings=ranked,awards=awards,started=now,
                  profiles={owner:m['racing']for(owner,account,uid),m in zip(members,mounts)})
        db.execute('INSERT INTO mount_races VALUES (?,?,?,?,?)',(race,digest,now,rules.policy()['policy'],dumps(data)))
        for lane,((owner,account_id,uid),mount)in enumerate(zip(members,mounts)):
            db.execute('INSERT INTO mount_race_results(race,owner,account_id,mount,lane) VALUES (?,?,?,?,?)',(race,owner,account_id,uid,lane))
            db.execute('INSERT INTO mount_race_busy VALUES (?,?,?)',(uid,owner,race))
            db.execute('UPDATE mount_runtime SET stamina=stamina-?,ridden=0 WHERE uid=? AND owner=?',(rules.policy()['race_stamina'],uid,owner))
            db.execute('UPDATE companion_active SET mount=0,mounted=0 WHERE owner=?',(owner,))
        # Normalize JSON keys once; first delivery and replay use the same DTO.
        data=json.loads(dumps(data));answer=encode(db,data);prepare(db)
        return data,answer


def settle(path,race,members,*,prepare,encode,now=None):
    """Commit every original participant together, with current retry views."""
    from els_server.storage.inventory_state import grant_items,load_items
    from els_server.domain.reward_rules import item_plan
    now=mount_state.timestamp(now)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');prepare(db)
        source=db.execute('SELECT started,data FROM mount_races WHERE id=?',(race,)).fetchone()
        if source is None:raise ValueError('Original racing identity required')
        data=json.loads(source[1])
        if now<source[0]+math.ceil(max(r['time']for r in data['standings'])):raise ValueError('Race has not finished')
        participants=db.execute('SELECT owner,account_id,mount,disconnected,settled,receipt FROM mount_race_results WHERE race=? ORDER BY lane',(race,)).fetchall()
        if tuple(members)!=tuple((r[0],r[1])for r in participants):raise ValueError('Original racing participant roster required')
        results={}
        for owner,account_id,uid,disconnected,settled,old_receipt in participants:
            require_owner(db,owner,account_id);mount=mount_state.owned(db,owner,uid);award=data['awards'][str(owner)]
            if not settled and not disconnected:
                require_active_character(db,owner)
                baseline=data['profiles'][str(owner)];baseline['stats']={int(k):v for k,v in baseline['stats'].items()}
                if mount_growth.read(db,owner,uid)!=baseline:raise ValueError('Racing mount growth changed before settlement')
                updated=dict(award['profile'],stats={int(k):v for k,v in award['profile']['stats'].items()})
                mount_growth.save(db,owner,uid,updated)
                reward=award['reward'];item=reward['item'];granted=[]
                if item:granted=grant_items(db,[item_plan(item['template'],item['quantity'])],owner)
                receipt=dict(experience_gained=award['experience_gained'],bonus_type=reward['bonus_type'],item=item,
                             items=granted)
                db.execute('UPDATE reward_balances SET revision=revision+1 WHERE uid=?',(owner,))
            elif not settled:receipt=dict(experience_gained=0,bonus_type=-1,item=None,items=[])
            else:receipt=json.loads(old_receipt)
            if not settled:db.execute('UPDATE mount_race_results SET settled=1,receipt=? WHERE race=? AND owner=?',(dumps(receipt),race,owner))
            if disconnected:award['reward']=dict(experience=0,bonus_type=-1,item=None)
            mount['racing']=mount_growth.read(db,owner,uid)
            items=load_items(db,owner);current={(i['group'],i['slot']):i for i in items};uids={i['uid']for i in receipt['items']}
            positions=list(dict.fromkeys([(i['group'],i['slot'])for i in receipt['items']]
                           +[(i['group'],i['slot'])for i in items if i['uid']in uids]))
            results[owner]=dict(mount=mount,receipt=receipt,changes=[(p,current.get(p))for p in positions])
        answer=encode(db,data,results);prepare(db)
        return answer


def leave(path,owner,*,now=None):
    """Release the race clock on town return/disconnect; no stamina refund."""
    now=mount_state.timestamp(now)
    with closing(sqlite3.connect(path,timeout=10))as db,db:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_race_busy'").fetchone():return
        db.execute('BEGIN IMMEDIATE')
        release(db,owner,now)


def release(db,owner,now):
    row=db.execute('SELECT uid,race FROM mount_race_busy WHERE owner=?',(owner,)).fetchone()
    if row is None:return
    mount_state.settle(db,owner,mount_state.owned(db,owner,row[0]),now)
    db.execute('UPDATE mount_race_results SET disconnected=CASE WHEN settled=0 THEN 1 ELSE disconnected END WHERE race=? AND owner=?',(row[1],owner))
    db.execute('DELETE FROM mount_race_busy WHERE owner=?',(owner,))
