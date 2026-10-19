"""Progress follows the UID and bank instance; each business write is atomic."""
from els_server.domain.enhancement_progress import validate
TABLE='equipment_enhancement_progress'
def exists(db):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(TABLE,)).fetchone())
def attach(db,items,owner):
 if not exists(db):return items
 owned={i['uid']:i for i in items}
 for uid,gauge,points in db.execute('''SELECT p.item_uid,p.gauge,p.guarantee FROM equipment_enhancement_progress p JOIN inventory_items i ON i.uid=p.item_uid WHERE i.owner=?''',(owner,)):
  if uid in owned:
   item=owned[uid]
   if gauge:item['enhancement_gauge']=gauge
   if points:item['enhancement_guarantee']=points
   validate(item)
 return items
def replace(db,owner,item,gauge,points):
 if not db.in_transaction:raise ValueError('Enhancement progress requires transaction')
 row=db.execute('SELECT template,count FROM inventory_items WHERE owner=? AND uid=?',(owner,item['uid'])).fetchone()
 if row!=(item['template'],1):raise ValueError('Owned single equipment progress required')
 validate(dict(item,enhancement_gauge=gauge,enhancement_guarantee=points))
 present=exists(db)
 if gauge or points:
  db.execute('''CREATE TABLE IF NOT EXISTS equipment_enhancement_progress (
   item_uid INTEGER PRIMARY KEY REFERENCES inventory_items(uid) DEFERRABLE INITIALLY DEFERRED,
   gauge INTEGER NOT NULL CHECK(gauge BETWEEN 0 AND 270),guarantee INTEGER NOT NULL CHECK(guarantee BETWEEN 0 AND 20))''')
  db.execute('''INSERT INTO equipment_enhancement_progress VALUES (?,?,?) ON CONFLICT(item_uid) DO UPDATE SET gauge=excluded.gauge,guarantee=excluded.guarantee''',(item['uid'],gauge,points))
 elif present:db.execute('DELETE FROM equipment_enhancement_progress WHERE item_uid=?',(item['uid'],))
