"""Three owned accounts for the roster/town read-path delivery."""
from contextlib import closing
import hashlib,sqlite3

def inventory_identity(db,uids):
    rows=db.execute('SELECT * FROM inventory_items WHERE owner IN ('+','.join('?'for _ in uids)+') ORDER BY owner,uid',uids).fetchall()
    return len(rows),hashlib.sha256(repr(rows).encode()).hexdigest()

def enroll(row,index,path,operation):
    from els_server.storage.characters import Characters
    from els_server.storage.local_state import LocalState
    from els_server.storage.reward_state import RewardState
    from els_server.game_data import client_data
    from large_fixture import enlarge
    roles=Characters(path,row['account_id']);uids=[]
    unit=(1,5,10)[index]
    for number in range(8 if index==0 else 1):
        name='L200'+format(row['account_id'],'x')+str(number)
        uid=roles.create(name,unit,operation+':'+str(index)+':'+str(number))['uid'];uids.append(uid)
        RewardState(path,uid,account_id=row['account_id']);LocalState(path,uid).save(20000,0,0,(1.,2.,3.))
    with closing(sqlite3.connect(path,timeout=60))as db,db:
        db.execute('BEGIN IMMEDIATE')
        for uid in uids:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
            db.execute('UPDATE reward_balances SET ed=1000,experience=? WHERE uid=?',(client_data().thresholds[98],uid))
    if index==0:enlarge(path,uids[0])
    with closing(sqlite3.connect(path))as db:count,digest=inventory_identity(db,uids)
    row.update(uid=uids[0],unit=unit,town=20000,scenario='roster_town_reads',index=index,role_uids=uids,inventory_count=count,inventory_sha256=digest)

def cold(rows,path,*,retired=False):
    from els_server.storage.local_state import LocalState
    result=[]
    with closing(sqlite3.connect(path,timeout=60))as db:
        db.execute('PRAGMA query_only=ON')
        for row in rows:
            uids=row['role_uids']
            assert db.execute('SELECT uid FROM character_owners WHERE account_id=? ORDER BY uid',(row['account_id'],)).fetchall()==[(uid,)for uid in sorted(uids)]
            assert inventory_identity(db,uids)==(row['inventory_count'],row['inventory_sha256'])
            for uid in uids:
                assert db.execute('SELECT level FROM characters WHERE uid=?',(uid,)).fetchone()==(99,)
                assert db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()==(1000,)
                assert LocalState(path,uid).load()['map']==20000
            result.append(dict(unit=row['unit'],roles=len(uids),inventory_count=row['inventory_count'],inventory_unchanged=True,ED=1000))
    return dict(ok=True,read_only=True,retired=retired,roles=result)
