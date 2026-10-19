"""Explicit original identified/unidentified instance flag; no read migration."""
def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS equipment_identification (item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED, identified INTEGER NOT NULL CHECK(identified IN (0,1)))')
def attach(db,items,owner):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_identification'").fetchone():return
 owned={i['uid']:i for i in items}
 for uid,value in db.execute('SELECT a.item_uid,a.identified FROM equipment_identification a JOIN inventory_items i ON i.uid=a.item_uid WHERE i.owner=?',(owner,)):
  if uid in owned:owned[uid]['identified']=bool(value)
def replace(db,owner,uid,expected,updated):
 if not db.in_transaction or type(expected) is not bool or type(updated) is not bool:raise ValueError('Identification transaction/flags')
 row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
 if not row or row[1]!=1:raise ValueError('Owned single identification item required')
 from els_server.domain.identification_ui import require_template
 require_template(row[0]);ensure(db)
 previous=db.execute('SELECT identified FROM equipment_identification WHERE item_uid=?',(uid,)).fetchone()
 if (bool(previous[0]) if previous else True)!=expected:raise ValueError('Stale identification state')
 db.execute('INSERT INTO equipment_identification VALUES (?,?) ON CONFLICT(item_uid) DO UPDATE SET identified=excluded.identified',(uid,int(updated)))
