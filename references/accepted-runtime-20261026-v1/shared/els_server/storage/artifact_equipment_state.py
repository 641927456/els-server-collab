"""Native Artifact spirit-slot expansion flag, following complete item instances."""
from els_server.domain.artifact_progression import slots
def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS artifact_equipment_state (item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED, socket_open INTEGER NOT NULL CHECK(socket_open IN (0,1)))')
def attach(db,items,owner):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_equipment_state'").fetchone():return
 owned={i['uid']:i for i in items}
 for uid,value in db.execute('SELECT s.item_uid,s.socket_open FROM artifact_equipment_state s JOIN inventory_items i ON i.uid=s.item_uid WHERE i.owner=?',(owner,)):
  if uid in owned:owned[uid]['artifact_socket_open']=bool(value)
def replace(db,owner,uid,expected,updated):
 if not db.in_transaction or type(expected) is not bool or type(updated) is not bool:raise ValueError('Artifact slot transaction/flag')
 row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
 if row is None or not slots(row[0]) or row[1]!=1:raise ValueError('Owned Artifact equipment required')
 ensure(db);old=db.execute('SELECT socket_open FROM artifact_equipment_state WHERE item_uid=?',(uid,)).fetchone()
 if bool(old[0] if old else 0)!=expected:raise ValueError('Stale Artifact spirit-slot state')
 if updated:db.execute('INSERT INTO artifact_equipment_state VALUES (?,1) ON CONFLICT(item_uid) DO UPDATE SET socket_open=1',(uid,))
 else:db.execute('DELETE FROM artifact_equipment_state WHERE item_uid=?',(uid,))
