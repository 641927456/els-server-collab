"""Portable self-world transactions; no absolute overlay or client."""
import sqlite3,tempfile,json,struct,time,unittest,hashlib
from pathlib import Path
from contextlib import closing
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
from els_server.storage import world_elixirs as store
from els_server.protocol import world_buff_messages as wire
ROWS=[]
NOW=int(time.time())

def req(uid,extra=1):return struct.pack('>QQiiIB',uid,extra,0,0,0,0)

class Elixir(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='elixir-private-');self.addCleanup(self.tmp.cleanup);self.path=Path(self.tmp.name)/'game.sqlite3'
  self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
  self.foreign=Characters(self.path,2).create('OtherElix',1,'foreign')['uid']
  with closing(sqlite3.connect(self.path))as db,db:
   self.items={t:grant_items(db,[dict(template=t,metadata=2,group=4,quantity=5)],1001)[0]for t in(710206,710207,710210)}
 def dump(self):
  with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())
 def prepare(self,db,state,items):return[wire.snapshot(1001,state['rows'])]
 def use(self,t,op,extra=1,now=NOW,prepare=None,account=1):return store.use(self.path,1001,account,req(self.items[t]['uid'],extra),op,prepare or self.prepare,now=now)
 def count(self,t):
  with closing(sqlite3.connect(self.path))as db:return db.execute('SELECT count FROM inventory_items WHERE uid=?',(self.items[t]['uid'],)).fetchone()[0]
 def test_source_group_confirmation_refresh_retry_and_deadline(self):
  self.assertTrue(all(TEMPLATE_MAX_STACKS[t]==99 for t in self.items))
  before=self.dump();state=store.snapshot(self.path,1001,1,now=NOW);self.assertEqual(state['revision'],0);self.assertEqual(before,self.dump())
  first=self.use(710206,'first');self.assertEqual([e.kind for e in first['events']],[0x21a,0x3a2]);self.assertEqual(self.count(710206),4)
  self.assertEqual(len(first['events'][1].payload),79)
  before=self.dump();confirm=self.use(710207,'confirm-probe');self.assertEqual(struct.unpack_from('>i',confirm['events'][0].payload)[0],403);self.assertEqual(len(confirm['events'][0].payload),36);self.assertEqual(before,self.dump())
  second=self.use(710207,'confirm-use',0,NOW+5);self.assertEqual(self.count(710207),4);self.assertEqual([r['template']for r in second['state']['rows']],[710207]);self.assertEqual(second['state']['rows'][0]['end'],NOW+1805)
  refreshed=self.use(710207,'refresh',0,NOW+8);self.assertEqual(self.count(710207),3);self.assertEqual(refreshed['state']['rows'][0]['end'],NOW+1808)
  # Old reply refreshes CURRENT UID/positions and current buff, never old state.
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE inventory_items SET slot=10 WHERE uid=?',(self.items[710206]['uid'],))
  before=self.dump();retry=self.use(710206,'first',now=NOW+10);self.assertTrue(retry['replayed']);self.assertEqual(before,self.dump());self.assertEqual(retry['state']['rows'][0]['template'],710207);self.assertEqual(struct.unpack_from('>I',retry['events'][0].payload,4)[0],2)
  cold=LocalAccount(LocalState(self.path));cold.enable_characters();saved=store.snapshot(self.path,1001,1,now=NOW+100);self.assertEqual(saved['rows'][0]['end'],NOW+1808)
  self.assertEqual(store.snapshot(self.path,1001,1,now=NOW+1808)['rows'],[])
  expired=store.expire(self.path,1001,1,self.prepare,now=NOW+1808);self.assertEqual(expired['events'][0].payload,bytes(4));self.assertEqual(expired['state']['revision'],4)
  before=self.dump();self.assertIsNone(store.expire(self.path,1001,1,self.prepare,now=NOW+1900));self.assertEqual(before,self.dump())
  replay=self.use(710206,'first',now=NOW+1900);self.assertEqual(replay['state']['rows'],[]);self.assertEqual(self.count(710206),4)
  with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
  ROWS.append(dict(case='original-source-three-single-group403-confirm-refresh-cold-retry-expire',passed=True,deadline_reset_only_by_fresh_consumption=True,retry_refreshes_current_UID=True,unsupported_other_buffs_touched=False))
 def test_failures_are_atomic_and_current_actor_before_receipt(self):
  before=self.dump()
  def bad(db,state,items):raise ValueError('controlled prepare failure')
  with self.assertRaisesRegex(ValueError,'prepare failure'):self.use(710206,'encode-fail',prepare=bad)
  self.assertEqual(before,self.dump())
  with self.assertRaisesRegex(ValueError,'ownership'):self.use(710206,'foreign',account=2)
  self.assertEqual(before,self.dump())
  for extra in(2,2**64-1):
   with self.assertRaises(ValueError):self.use(710206,'bad-extra-'+str(extra),extra)
   self.assertEqual(before,self.dump())
  first=self.use(710206,'committed')
  from els_server.storage.character_selection import save
  from els_server.storage.character_lifecycle import change
  save(self.path,1,[],[1001]);change(self.path,1,1001,'schedule')
  for op in('new-pending','committed'):
   before=self.dump()
   with self.assertRaisesRegex(ValueError,'Unavailable'):self.use(710206,op)
   self.assertEqual(before,self.dump())
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE character_lifecycle SET requested_at=0,finalized_at=? WHERE uid=1001',(NOW,))
  before=self.dump()
  with self.assertRaisesRegex(ValueError,'Unavailable'):self.use(710206,'committed')
  self.assertEqual(before,self.dump())
  ROWS.append(dict(case='SQL-and-preflight-rollback-owner-fields-pending-finalized-old-receipt',passed=True))
 def test_legacy_schema_source_qualified_rows_and_codec_layout(self):
  with closing(sqlite3.connect(self.path))as db,db:db.execute('DROP TABLE character_lifecycle')
  before=self.dump();store.snapshot(self.path,1001,1,now=NOW);self.assertEqual(before,self.dump())
  first=self.use(710210,'legacy');self.assertEqual(first['state']['rows'][0]['template'],710210)
  row=first['state']['rows'][0];p=wire.snapshot(1001,[row],profiles=(struct.pack('>7f',*range(1,8)),struct.pack('>7f',*range(11,18)))).payload
  self.assertEqual(struct.unpack_from('>QI',p),(1001,1));self.assertEqual(struct.unpack_from('>IIi',p,12),(0,0,400));self.assertEqual(p[-56:-28],struct.pack('>7f',*range(1,8)));self.assertEqual(p[-28:],struct.pack('>7f',*range(11,18)))
  self.assertEqual(struct.unpack_from('>QQ',p,71),(NOW,NOW+1800))
  # Corrupt/foreign unbacked state cannot authorize a buff or consume another.
  with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE world_elixir_state SET source_uid=999999 WHERE owner=1001')
  before=self.dump()
  with self.assertRaisesRegex(ValueError,'receipt missing'):store.snapshot(self.path,1001,1,now=NOW)
  self.assertEqual(before,self.dump())
  ROWS.append(dict(case='optional-lifecycle-absent-read-only-current-codec-source-row-rejection',passed=True))

if __name__=='__main__':unittest.main()
