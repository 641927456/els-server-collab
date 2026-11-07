"""Item option vectors follow complete instances across persistent containers."""
import json
from els_server.domain.sage_sockets import validate
def ensure(db):
 db.execute('''CREATE TABLE IF NOT EXISTS equipment_options (
  item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
  groups_json TEXT NOT NULL)''')
def attach(db,items,owner):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='equipment_options'").fetchone():return
 owned={i['uid']:i for i in items}
 for uid,raw in db.execute('SELECT o.item_uid,o.groups_json FROM equipment_options o JOIN inventory_items i ON i.uid=o.item_uid WHERE i.owner=?',(owner,)):
  if uid in owned:owned[uid]['option_groups']=validate(owned[uid]['template'],json.loads(raw))
def replace(db,owner,uid,expected,updated):
 if not db.in_transaction:raise ValueError('Option update requires transaction')
 row=db.execute('SELECT template,count FROM inventory_items WHERE uid=? AND owner=?',(uid,owner)).fetchone()
 if row is None or row[1]!=1:raise ValueError('Owned single socket equipment required')
 expected=validate(row[0],expected);updated=validate(row[0],updated);ensure(db)
 old=db.execute('SELECT groups_json FROM equipment_options WHERE item_uid=?',(uid,)).fetchone()
 if (json.loads(old[0]) if old else {})!=expected:raise ValueError('Stale socket attributes')
 if updated:db.execute('INSERT INTO equipment_options VALUES (?,?) ON CONFLICT(item_uid) DO UPDATE SET groups_json=excluded.groups_json',(uid,json.dumps(updated,sort_keys=True)))
 else:db.execute('DELETE FROM equipment_options WHERE item_uid=?',(uid,))
