"""Prospective account clear progress in the existing reward transaction."""
import time
from els_server.storage import titles
from els_server.storage.character_schema import character_uid
from els_server.domain.title_clear_rules import rules
from els_server.domain.titles import eligible
from els_server.protocol import title_messages as wire

def _commit_simple(db,uid,dungeon):
    character_uid(uid)
    if not db.in_transaction:raise ValueError('Title clear requires caller transaction')
    if type(dungeon) is not int or dungeon<=0:raise ValueError('Title clear dungeon identity')
    from els_server.domain.dungeon_routes import route_catalog
    dungeon=route_catalog().entry_identity(dungeon)
    # Legacy protocol-only stores have no authenticated character/account.
    if not all(titles.exists(db,t) for t in ('characters','character_owners')):return ()
    if not db.execute('SELECT 1 FROM characters c JOIN character_owners o ON o.uid=c.uid WHERE c.uid=?',(uid,)).fetchone():return ()
    character=titles.character(db,uid)
    matched=[(identity,subs,tuple(sub for sub,maps in subs if dungeon in maps)) for identity,level,subs in rules()
             if character['level']>=level and eligible(character,identity)]
    matched=[r for r in matched if r[2]]
    if not matched:return ()
    now=int(time.time());titles.schema(db)
    db.execute('CREATE TABLE IF NOT EXISTS title_clear_progress (account_id INTEGER NOT NULL CHECK(account_id>0), mission INTEGER NOT NULL, submission INTEGER NOT NULL, PRIMARY KEY(account_id,mission,submission))')
    awarded=[];account=character['account_id']
    for identity,subs,affected in matched:
        if db.execute("SELECT 1 FROM title_ownership WHERE scope='account' AND subject=? AND title=?",(account,identity)).fetchone():continue
        for sub in affected:db.execute('INSERT OR IGNORE INTO title_clear_progress VALUES (?,?,?)',(account,identity,sub))
        done={r[0] for r in db.execute('SELECT submission FROM title_clear_progress WHERE account_id=? AND mission=?',(account,identity))}
        if all(sub in done for sub,maps in subs):
            db.execute('INSERT INTO title_ownership VALUES (?,?,?,?,?,?)',('account',account,identity,character['name'],now,0));awarded.append(identity)
    # Prove the ownership DTO encodes before either rewards or titles commit.
    # Existing periodic/C22 restoration publishes it after the outer commit.
    if awarded:
        response=wire.initialization(titles.snapshot(db,uid,now))
        if not isinstance(response.payload,bytes) or not 1<=len(response.payload)<=65536:raise ValueError('Title clear response bounds')
    return tuple(awarded)


def _opened_simple(db,character,owned):
    """Only source-qualified unowned Ruben missions; never overlay acquired rows."""
    acquired={row['title'] for row in owned}
    done=set(db.execute('SELECT mission,submission FROM title_clear_progress WHERE account_id=?',(character['account_id'],))) if titles.exists(db,'title_clear_progress') else set()
    result=[]
    for identity,level,subs in rules():
        if identity in acquired or character['level']<level or not eligible(character,identity):continue
        result.append(dict(mission=identity,flag=0,progress=[dict(sub=sub,count=int((identity,sub) in done),done=(identity,sub) in done) for sub,maps in subs]))
    return result


def commit(db,uid,dungeon,seconds=None):
    # Keep the already verified simple-clear behavior and old progress schema.
    # The outer RewardState receipt supplies atomicity and retry protection.
    awarded=_commit_simple(db,uid,dungeon)
    from els_server.domain.dungeon_routes import route_catalog
    from els_server.storage.title_counts import commit as commit_counts
    return awarded+commit_counts(db,uid,route_catalog().entry_identity(dungeon),int(time.time()),seconds=seconds)


def opened(db,character,owned):
    from els_server.storage.title_counts import opened as opened_counts
    return sorted(_opened_simple(db,character,owned)+opened_counts(db,character,owned),key=lambda r:r['mission'])
