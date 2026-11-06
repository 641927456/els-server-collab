"""Experimental mount level/exp rows; stamina stays in mount_runtime."""
SLOTS=('h','q')
def ensure(db):
 db.execute('CREATE TABLE IF NOT EXISTS mount_progress (uid INTEGER PRIMARY KEY,level INTEGER NOT NULL DEFAULT 0,exp INTEGER NOT NULL DEFAULT 0,slot TEXT NOT NULL DEFAULT \'h\')')
 if 'slot' not in [row[1] for row in db.execute('PRAGMA table_info(mount_progress)')]:
  db.execute("ALTER TABLE mount_progress ADD COLUMN slot TEXT NOT NULL DEFAULT 'h'")

def load(db,uid):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_progress'").fetchone():return {'level':0,'exp':0,'slot':'h'}
 try:row=db.execute('SELECT level,exp,slot FROM mount_progress WHERE uid=?',(uid,)).fetchone()
 except Exception:row=db.execute('SELECT level,exp FROM mount_progress WHERE uid=?',(uid,)).fetchone()
 if not row:return {'level':0,'exp':0,'slot':'h'}
 return {'level':row[0],'exp':row[1],'slot':row[2]} if len(row)>2 else {'level':row[0],'exp':row[1],'slot':'h'}

def set_level(db,uid,level,exp=0,slot='h'):
 if type(uid) is not int or not 0<uid<2**63:raise ValueError('Invalid mount UID')
 if type(level) is not int or type(exp) is not int or level<0 or exp<0:raise ValueError('Invalid mount progress')
 if slot not in SLOTS:raise ValueError('Invalid mount level slot')
 ensure(db)
 db.execute('INSERT INTO mount_progress(uid,level,exp,slot) VALUES (?,?,?,?) ON CONFLICT(uid) DO UPDATE SET level=excluded.level,exp=excluded.exp,slot=excluded.slot',(uid,level,exp,slot))

def clear(db,uid):
 if not db.execute("SELECT 1 FROM sqlite_master WHERE name='mount_progress'").fetchone():return
 db.execute('DELETE FROM mount_progress WHERE uid=?',(uid,))
