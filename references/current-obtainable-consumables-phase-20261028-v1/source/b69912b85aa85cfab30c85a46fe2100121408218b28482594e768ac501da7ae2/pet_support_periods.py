"""Current owned timed pet support; original seconds fields and local renewal rule."""
import datetime,hashlib,sqlite3,time
from contextlib import closing

TABLE='pet_support_periods'
SQL='''CREATE TABLE pet_support_periods (
 owner INTEGER NOT NULL REFERENCES characters(uid),kind TEXT NOT NULL CHECK(kind IN ('automatic','pickup')),
 target INTEGER NOT NULL CHECK(target>=0),deadline INTEGER NOT NULL CHECK(deadline>0 AND deadline<2493043200),
 source_operation TEXT NOT NULL,notified INTEGER NOT NULL DEFAULT 0 CHECK(notified IN (0,1)),
 CHECK((kind='automatic' AND target=0) OR(kind='pickup' AND target>0)),PRIMARY KEY(owner,kind,target))'''
# FEC270 and native pickup handling classify valid years before2049 as limited.
# Refuse extension beyond that original representable limited range, no debit.
LIMITED_END=2493043200
from els_server.domain.item_expiration import CLIENT_ZONE
assert LIMITED_END==int(datetime.datetime(2049,1,1,tzinfo=CLIENT_ZONE).timestamp())
PRODUCTS={300640:('automatic',15*86400),300643:('pickup',15*86400),300644:('pickup',30*86400),500867:('pickup',15*86400)}
POLICY='human-approved-pet-renew-max-current-or-now-20261028-v1'
ITEM_SHA={300640: '3508eb1ce22f770388d25f9e9aa1e1ffcc5600df604f9772ea6e9cdb18da0b22', 300643: '5b43130867af98f4007d9d7b987d13a6849723f835e83b3b7288699d9e96972b', 300644: '997591ca184bd4d3e6c65f53895c8c24d31626eeb7c554f3e3eeaa78deb3b6f6', 500867: '16c0618bf890172a9146372305e52d199036b3949d59754697b9dd946572a0b6'}

def validate_product(template):
 from els_server.game_data import client_data
 if template not in PRODUCTS or hashlib.sha256(client_data().item(template)['record']).hexdigest()!=ITEM_SHA[template]:raise ValueError('Exact original timed pet support product')
 return PRODUCTS[template]

def epoch(now=None):
 value=int(time.time())if now is None else now
 if type(value)is not int or not 0<=value<LIMITED_END:raise ValueError('Timed pet support clock')
 return value

def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(TABLE,)).fetchone())

def period(db,owner,kind,target):
 if not exists(db):return None
 row=db.execute('SELECT deadline FROM pet_support_periods WHERE owner=?AND kind=?AND target=?',(owner,kind,target)).fetchone()
 if row is None:return None
 if type(row[0])is not int or not 0<row[0]<LIMITED_END:raise ValueError('Stored timed pet deadline')
 return row[0]

def active(deadline,now=None):return deadline is None or epoch(now)<=deadline

def renew(db,owner,kind,target,seconds,operation,*,now=None):
 if not db.in_transaction or kind not in('automatic','pickup')or seconds not in(15*86400,30*86400):raise ValueError('Timed pet original writer')
 now=epoch(now);old=period(db,owner,kind,target);deadline=max(now,old or now)+seconds
 if deadline>=LIMITED_END:raise ValueError('Timed pet native limited-date range')
 db.execute(SQL.replace('CREATE TABLE ','CREATE TABLE IF NOT EXISTS ',1))
 db.execute('INSERT INTO pet_support_periods VALUES(?,?,?,?,?,0) ON CONFLICT(owner,kind,target) DO UPDATE SET deadline=excluded.deadline,source_operation=excluded.source_operation,notified=0',(owner,kind,target,deadline,operation))
 return deadline

def permanent(db,owner,kind,target):
 if not db.in_transaction:raise ValueError('Permanent pet original writer')
 if exists(db):db.execute('DELETE FROM pet_support_periods WHERE owner=?AND kind=?AND target=?',(owner,kind,target))

def expire(path,owner,*,now=None):
 now=epoch(now)
 with closing(sqlite3.connect(path,timeout=10))as db:
  if not exists(db)or not db.execute('SELECT 1 FROM pet_support_periods WHERE owner=?AND deadline<?AND notified=0 LIMIT 1',(owner,now)).fetchone():return []
  with db:
   db.execute('BEGIN IMMEDIATE')
   from els_server.storage.item_actor import require_active_character
   require_active_character(db,owner)
   due=db.execute('SELECT kind,target,deadline FROM pet_support_periods WHERE owner=?AND deadline<?AND notified=0 ORDER BY kind,target',(owner,now)).fetchall()
   from els_server.storage.pet_support import automatic,owned_pet
   from els_server.protocol import pet_support_messages as wire
   from els_server.protocol.protocol_codec import encode_event
   events=[]
   for kind,target,deadline in due:
    from els_server.storage.boosting_2026_limited_pet import ExpiredLimitedPet
    try:events.append(wire.settings(automatic(db,owner,now=now),0xb3b)if kind=='automatic'else wire.pet_update(owned_pet(db,owner,target,now=now)))
    except ExpiredLimitedPet:pass # Pet's own earlier expiry already removes its permission.
   for event in events:encode_event(event)
   for kind,target,deadline in due:db.execute('UPDATE pet_support_periods SET notified=1 WHERE owner=?AND kind=?AND target=?AND deadline=?',(owner,kind,target,deadline))
   return events
