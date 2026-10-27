"""Character-owned stamina, ride clocks and atomic native summon operations."""
import hashlib,json,sqlite3,struct,time
from contextlib import closing
from els_server.domain.mount_rules import template,catalog,advance
from els_server.protocol import mount_messages as wire
from els_server.storage.character_schema import character_uid

def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS mount_runtime (uid INTEGER PRIMARY KEY,owner INTEGER NOT NULL,stamina REAL NOT NULL,accounted_at INTEGER NOT NULL,ridden INTEGER NOT NULL CHECK(ridden IN (0,1)))')
 db.execute('CREATE TABLE IF NOT EXISTS mount_operations (owner INTEGER NOT NULL,operation TEXT NOT NULL,digest TEXT NOT NULL,uid INTEGER NOT NULL,PRIMARY KEY(owner,operation))')

def timestamp(now=None):
 value=int(time.time()) if now is None else now
 if type(value) is not int or not 0<=value<2**63:raise ValueError('Invalid mount clock')
 return value

def owned(db,owner,uid):
 row=db.execute("SELECT uid,owner,kind,unit,name,source_item FROM companions WHERE uid=? AND owner=? AND kind='mount'",(uid,owner)).fetchone()
 if row is None:raise ValueError('Owned mount required')
 return dict(zip(('uid','owner','kind','unit','name','source_item'),row))

def settle(db,owner,mount,now):
 rule=template(mount['unit']);row=db.execute('SELECT owner,stamina,accounted_at,ridden FROM mount_runtime WHERE uid=?',(mount['uid'],)).fetchone()
 if row is None:
  row=(owner,float(rule['max_stamina']),now,0)
  db.execute('INSERT INTO mount_runtime VALUES (?,?,?,?,?)',(mount['uid'],*row))
 if row[0]!=owner:raise ValueError('Mount runtime owner mismatch')
 # A backwards wall clock cannot re-credit elapsed time on a later retry.
 checked=max(now,row[2]);stamina=advance(mount['unit'],row[1],checked-row[2],bool(row[3]))
 db.execute('UPDATE mount_runtime SET stamina=?,accounted_at=? WHERE uid=? AND owner=?',(stamina,checked,mount['uid'],owner))
 return dict(mount,stamina=stamina,accounted_at=checked,ridden=bool(row[3]))

def attach(db,owner,companions,*,now=None):
 mounts=[p for p in companions if p['kind']=='mount']
 if not mounts:return
 ensure(db);now=timestamp(now)
 for mount in mounts:mount.update(settle(db,owner,mount,now))

def login(db,owner,*,now=None):
 """Re-login starts on foot; crash recovery resumes from committed state."""
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_runtime'").fetchone():return
 # Normal disconnect has already charged the last ridden interval. After a
 # process crash only committed stamina is known; never charge offline riding.
 db.execute('UPDATE mount_runtime SET ridden=0 WHERE owner=?',(owner,))

def tick(path,owner,*,now=None,disconnect=False):
 owner=character_uid(owner);now=timestamp(now)
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_runtime'").fetchone():return []
  # A previously touched but currently unmounted character has no clock
  # to settle. Release the read snapshot before a real mounted-state write.
  db.execute('BEGIN')
  row=db.execute('SELECT mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone()
  if not row or not row[0] or not row[1]:return []
  db.rollback()
  db.execute('BEGIN IMMEDIATE');row=db.execute('SELECT mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone()
  if not row or not row[0] or not row[1]:return []
  mount=settle(db,owner,owned(db,owner,row[0]),now)
  if disconnect or mount['stamina']==0:
   mount['ridden']=False
   db.execute('UPDATE mount_runtime SET ridden=0 WHERE uid=? AND owner=?',(mount['uid'],owner))
   db.execute('UPDATE companion_active SET mount=0,mounted=0 WHERE owner=?',(owner,))
   # Encode before commit. Failure leaves the ride clock and state unchanged.
   return [wire.dismounted(0,mount['uid'],mount)]
  return []

def handle(path,owner,kind,payload,operation,*,now=None):
 owner=character_uid(owner);now=timestamp(now)
 if kind not in (0x42c,0x42f) or not isinstance(operation,str) or not 1<=len(operation)<=160:raise ValueError('Invalid mount operation')
 if (kind==0x42c and (len(payload)!=9 or payload[8]>1)) or (kind==0x42f and (len(payload)!=12 or payload[8:]!=bytes(4))):raise ValueError('Invalid riding request')
 uid=struct.unpack_from('>Q',payload)[0]
 if not 0<uid<2**63:raise ValueError('Invalid mount UID')
 digest=hashlib.sha256(struct.pack('>I',kind)+payload).hexdigest()
 from els_server.storage.companion_state import ensure as companions
 with closing(sqlite3.connect(path,timeout=10)) as db,db:
  db.execute('BEGIN IMMEDIATE');companions(db);ensure(db)
  mount=settle(db,owner,owned(db,owner,uid),now)
  active=db.execute('SELECT mount,mounted FROM companion_active WHERE owner=?',(owner,)).fetchone() or (0,0)
  previous=db.execute('SELECT digest,uid FROM mount_operations WHERE owner=? AND operation=?',(owner,operation)).fetchone()
  if previous:
   if previous!=(digest,uid):raise ValueError('Conflicting riding retry')
   if kind==0x42c and active!=(uid,1):raise ValueError('Stale riding retry')
   if kind==0x42f and (active!=(0,0) or mount['ridden']):raise ValueError('Stale dismount retry')
   return wire.summoned(0,mount) if kind==0x42c else wire.dismounted(0,uid,mount)
  if kind==0x42c:
   if mount['stamina']<=0 or (active!=(uid,1) and mount['stamina']<catalog()['enable_stamina']):raise ValueError('Mount is exhausted')
   if active[0] and active[0]!=uid and active[1]:
    settle(db,owner,owned(db,owner,active[0]),now)
    db.execute('UPDATE mount_runtime SET ridden=0 WHERE uid=? AND owner=?',(active[0],owner))
   mount['ridden']=True
   db.execute('INSERT INTO companion_active(owner,mount,mounted) VALUES (?,?,1) ON CONFLICT(owner) DO UPDATE SET mount=excluded.mount,mounted=1',(owner,uid))
   answer=wire.summoned(0,mount)
  else:
   if active!=(uid,1) and not (active==(0,0) and not mount['ridden']):raise ValueError('Currently ridden mount required')
   mount['ridden']=False
   db.execute('UPDATE companion_active SET mount=0,mounted=0 WHERE owner=?',(owner,))
   answer=wire.dismounted(0,uid,mount)
  db.execute('UPDATE mount_runtime SET ridden=? WHERE uid=? AND owner=?',(int(mount['ridden']),uid,owner))
  db.execute('INSERT INTO mount_operations VALUES (?,?,?,?)',(owner,operation,digest,uid))
  return answer
