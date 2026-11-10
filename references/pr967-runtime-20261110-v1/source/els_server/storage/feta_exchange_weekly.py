"""Authorized Feta account/product weeks; native quantities and max counts."""
from datetime import datetime,timezone,timedelta
TABLE='feta_exchange_weekly'
USAGE='feta_exchange_weekly_usage'
MAXIMUM={710313:1,710193:1,30880:4,119328:1,119216:1}
REFERENCE=int(datetime(2026,1,7,10,tzinfo=timezone(timedelta(hours=8))).timestamp())

def week_at(now):
 if type(now)is not int or not 0<=now<2**40:raise ValueError('Feta week clock')
 return (now-REFERENCE)//604800

def exists(db,name):return db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(name,)).fetchone()is not None

def ensure(db):
 if not db.in_transaction:raise ValueError('Feta limits require original transaction')
 db.execute('''CREATE TABLE IF NOT EXISTS feta_exchange_weekly(account_id INTEGER NOT NULL,product INTEGER NOT NULL,week INTEGER NOT NULL,used INTEGER NOT NULL CHECK(used>0),PRIMARY KEY(account_id,product,week))''')
 db.execute('''CREATE TABLE IF NOT EXISTS feta_exchange_weekly_usage(operation TEXT PRIMARY KEY,account_id INTEGER NOT NULL,owner INTEGER NOT NULL,product INTEGER NOT NULL,week INTEGER NOT NULL)''')

def used(db,account,product,now):
 if type(account)is not int or not 1<=account<2**63 or product not in MAXIMUM:raise ValueError('Feta weekly account/product')
 if not exists(db,TABLE):return 0
 row=db.execute('SELECT used FROM feta_exchange_weekly WHERE account_id=?AND product=?AND week=?',(account,product,week_at(now))).fetchone()
 if row is None:return 0
 if type(row[0])is not int or not 0<row[0]<=MAXIMUM[product]:raise ValueError('Feta corrupt weekly count')
 return row[0]

def reserve(db,account,owner,row,operation,now):
 if row['index']not in(686,687,688,689,690)or row['source']!=119317:raise ValueError('Feta finite weekly rows')
 ensure(db);week=week_at(now);product=row['destination'];n=used(db,account,product,now)
 if db.execute('SELECT 1 FROM feta_exchange_weekly WHERE account_id=?AND week>?LIMIT 1',(account,week)).fetchone():raise ValueError('Feta future week ledger')
 if n>=MAXIMUM[product]:raise ValueError('Feta account product weekly limit reached')
 db.execute('INSERT INTO feta_exchange_weekly VALUES(?,?,?,1)ON CONFLICT(account_id,product,week)DO UPDATE SET used=used+1',(account,product,week))
 db.execute('INSERT INTO feta_exchange_weekly_usage VALUES(?,?,?,?,?)',(operation,account,owner,product,week))
 return dict(account=account,owner=owner,product=product,week=week,used=n+1)

def receipt(db,account,owner,row,operation):
 if row['index']<686:return
 if not exists(db,TABLE)or not exists(db,USAGE):raise ValueError('Feta weekly paired history missing')
 record=db.execute('SELECT account_id,owner,product,week FROM feta_exchange_weekly_usage WHERE operation=?',(operation,)).fetchone()
 if record is None or record[:3]!=(account,owner,row['destination']):raise ValueError('Feta weekly paired history conflict')
 n=db.execute('SELECT used FROM feta_exchange_weekly WHERE account_id=?AND product=?AND week=?',(account,row['destination'],record[3])).fetchone()
 if n is None or type(n[0])is not int or not 1<=n[0]<=MAXIMUM[row['destination']]:raise ValueError('Feta weekly historical count mismatch')
