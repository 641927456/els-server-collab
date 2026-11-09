"""One paid native preview; no schema creation from readers or invalidation."""
import json
TABLE='market_conversion_pending'
COLUMNS=('owner','account_id','item_uid','generation','operation','basis_json','options_json')
def present(db):
 row=db.execute('SELECT type FROM sqlite_master WHERE name=?',(TABLE,)).fetchone()
 if row is None:return False
 if row!=('table',)or tuple(x[1]for x in db.execute('PRAGMA table_info(market_conversion_pending)'))!=COLUMNS:raise ValueError('Unknown conversion pending schema')
 return True
def ensure(db):
 if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()!=(1,):raise ValueError('Conversion original writer')
 if present(db):return
 db.execute('''CREATE TABLE market_conversion_pending(
 owner INTEGER PRIMARY KEY REFERENCES characters(uid),account_id INTEGER NOT NULL,
 item_uid INTEGER NOT NULL REFERENCES inventory_items(uid) ON DELETE CASCADE DEFERRABLE INITIALLY DEFERRED,
 generation TEXT NOT NULL,operation TEXT NOT NULL UNIQUE,basis_json TEXT NOT NULL,options_json TEXT NOT NULL)''')
def get(db,owner):
 if not present(db):return None
 row=db.execute('SELECT * FROM market_conversion_pending WHERE owner=?',(owner,)).fetchone()
 return dict(zip(COLUMNS,row))if row else None
def clear(db,owner):
 if not db.in_transaction:raise ValueError('Conversion cancellation writer')
 if present(db):db.execute('DELETE FROM market_conversion_pending WHERE owner=?',(owner,))
def basis(item):return json.dumps(item,sort_keys=True,separators=(',',':'))
def put(db,owner,account,uid,generation,operation,item,options):
 ensure(db);clear(db,owner)
 db.execute('INSERT INTO market_conversion_pending VALUES(?,?,?,?,?,?,?)',(owner,account,uid,generation,operation,basis(item),json.dumps(options)))
def invalidate_moved(db,owner,before,after):
 if not present(db):return
 old={i['uid']:(i['group'],i['slot'])for i in before if isinstance(i,dict)}
 new={i['uid']:(i['group'],i['slot'])for i in after if isinstance(i,dict)}
 row=get(db,owner)
 if row and row['item_uid']in old and new.get(row['item_uid'])!=old[row['item_uid']]:clear(db,owner)
