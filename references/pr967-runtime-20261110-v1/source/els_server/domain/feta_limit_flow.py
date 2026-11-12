"""Current F actor whole6BD snapshot; read-only ledger and true weekly window."""
from contextlib import closing
from pathlib import Path
import sqlite3,time

def synchronize(s,events):
 from els_server.domain.cartridge_exchange_flow import _context
 from els_server.storage.feta_exchange_weekly import week_at
 from els_server.protocol.feta_limit_messages import snapshot_event
 if not _context(s):return events
 account=s.account;store=account.store;owner=account.uid;aid=account.account_id;nonce=s.shop_session_id
 path=Path(store.path).resolve()
 marker=(aid,owner,nonce,week_at(int(time.time())))
 if getattr(s,'_feta_limit_snapshot',None)==marker:return events
 with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=10))as db:
  db.execute('BEGIN');db.execute('SELECT name FROM sqlite_master LIMIT 1').fetchone()
  now=int(time.time());marker=(aid,owner,nonce,week_at(now));event=snapshot_event(db,aid,now)
 if(not _context(s)or s.account is not account or account.store is not store or(account.uid,account.account_id,s.shop_session_id)!=(owner,aid,nonce)or Path(store.path).resolve()!=path):raise ValueError('Feta snapshot current actor changed')
 s._feta_limit_snapshot=marker
 return events+[event]
