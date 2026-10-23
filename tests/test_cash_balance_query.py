"""Temporary SQL and actual pinned loopback TLS; no production accounts or network."""
from pathlib import Path
import asyncio,hashlib,importlib,json,sqlite3,struct,sys,time,unittest
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
m=importlib.import_module('test_friends_server')
async def send(self,kind,payload=b'',event_id=0x202):
 self.writer.write(m.encode_frame(m.encode_event(m.Event(event_id,kind=kind,payload=payload,performers=(0,)if kind in(0x28,0xad,0x1b2)else())),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
m.Peer.send=send
class CashTLS(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=m.FriendsTests.asyncSetUp
 asyncTearDown=m.FriendsTests.asyncTearDown
 peer=m.FriendsTests.peer
 bridge=m.FriendsTests.bridge
 async def barrier(self,peer):
  await peer.send(0x48d);events=[]
  for _ in range(60):
   frame=m.decode_frame(await m.read_wire(peer.reader),peer.keys,expected_sequence=peer.incoming);peer.incoming+=1;e=m.decode_event(frame.plaintext)
   if e.kind==0x48f:return events
   events.append(e)
  raise AssertionError('metadata barrier bound')
 def sql_snapshot(self):
  with closing(sqlite3.connect(self.config.state_file))as db:
   db.execute('BEGIN');tables=db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'AND name NOT LIKE'sqlite_%'ORDER BY name").fetchall();rows=[]
   for name,schema in tables:
    contents=sorted(map(repr,db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()));rows.append((name,schema,contents))
   db.commit()
  return hashlib.sha256(repr(rows).encode('utf8')).hexdigest()
 async def selected(self,account):
  peer=await self.peer(account);await peer.roster();uid=self.app.accounts[account['id']].uid
  await peer.send(0x490);await peer.until(0x491);await peer.send(0x28,struct.pack('>Q',uid));await peer.until(0x29);await self.barrier(peer)
  session=self.app.playing[account['id']];self.assertEqual(session.phase,'player_initialized');self.assertEqual(session.client_build,'dx11_260923')
  return peer,session
 def seed_ed(self,session,ed):
  session.account.get_inventory_snapshot()
  with closing(sqlite3.connect(self.config.state_file))as db,db:
   self.assertEqual(db.execute('UPDATE reward_balances SET ed=? WHERE uid=?',(ed,session.account.uid)).rowcount,1)
  self.assertEqual(session.account.get_reward_balances()['ed'],ed)
 async def assert_zero(self,peer,session):
  before=self.sql_snapshot();phase=session.phase;completed=set(session.completed)
  await peer.send(0x1b2);reply=await peer.until(0x1b3)
  self.assertEqual(len(reply.payload),29);self.assertEqual(struct.unpack('>iIBi4I',reply.payload),(0,0,0,-1,0,0,0,0))
  await self.barrier(peer);self.assertEqual(self.sql_snapshot(),before);self.assertEqual(session.phase,phase);self.assertEqual(session.completed,completed)
  return reply.payload
 async def test_native_empty_balance_is_separate_from_ED_and_cold_reconnect(self):
  alice,sa=await self.selected(self.alice);self.seed_ed(sa,111111);first=await self.assert_zero(alice,sa);self.assertEqual(await self.assert_zero(alice,sa),first)
  bob,sb=await self.selected(self.bob);self.seed_ed(sb,222222);self.assertEqual(await self.assert_zero(bob,sb),first)
  self.assertEqual(sa.account.get_reward_balances()['ed'],111111);self.assertEqual(sb.account.get_reward_balances()['ed'],222222)
  await alice.close();self.peers.remove(alice);await asyncio.sleep(.1)
  again,sc=await self.selected(self.alice);self.assertEqual(sc.account.get_reward_balances()['ed'],111111);self.assertEqual(await self.assert_zero(again,sc),first)
 async def test_nonempty_foreign_UID_body_rejected_without_writes(self):
  peer,session=await self.selected(self.alice);self.seed_ed(session,12345);before=self.sql_snapshot();phase=session.phase;completed=set(session.completed)
  await peer.send(0x1b2,struct.pack('>Q',0x1122334455667788))
  with self.assertRaises(asyncio.IncompleteReadError):await peer.until(0x1b3)
  self.assertEqual(session.phase,phase);self.assertEqual(session.completed,completed);self.assertEqual(self.sql_snapshot(),before)
  self.assertTrue(any(row.get('event')=='protocol_error'and row.get('error')=='Cash balance query has no request body'for row in self.events))

if __name__=='__main__':unittest.main()
