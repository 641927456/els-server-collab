"""Current-build request direction guard; private TLS and controlled legacy handler."""
from pathlib import Path
import asyncio,hashlib,importlib,json,sqlite3,struct,sys,time,unittest
from contextlib import closing
from types import MethodType
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
m=importlib.import_module('test_friends_server')
async def send(self,kind,payload=b'',event_id=0x202):
 self.writer.write(m.encode_frame(m.encode_event(m.Event(event_id,kind=kind,payload=payload,performers=(0,)if kind in(0x28,0xad,0xb6f)else())),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
class LegacyGuardTLS(unittest.IsolatedAsyncioTestCase):
 asyncSetUp=m.FriendsTests.asyncSetUp
 asyncTearDown=m.FriendsTests.asyncTearDown
 bridge=m.FriendsTests.bridge
 async def peer(self,account):
  peer=await m.FriendsTests.peer(self,account)
  peer.send=MethodType(send,peer)
  return peer
 def sql_snapshot(self):
  rows=[]
  for path in(self.config.state_file,self.config.accounts_file):
   with closing(sqlite3.connect(path))as db:
    db.execute('BEGIN');tables=db.execute("SELECT name,sql FROM sqlite_master WHERE type='table'AND name NOT LIKE'sqlite_%'ORDER BY name").fetchall()
    for name,schema in tables:rows.append((path.name,name,schema,sorted(map(repr,db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()))))
    db.commit()
  return hashlib.sha256(repr(rows).encode('utf8')).hexdigest()
 async def selected(self):
  peer=await self.peer(self.alice);await peer.roster();uid=self.app.accounts[self.alice['id']].uid
  await peer.send(0x490);await peer.until(0x491);await peer.send(0x28,struct.pack('>Q',uid));await peer.until(0x29)
  await peer.send(0x48d);await peer.until(0x48f);session=self.app.playing[self.alice['id']]
  self.assertEqual(session.phase,'player_initialized');return peer,session
 async def test_DX11_rejects_old_request_without_ACK_or_state_save_changes(self):
  peer,session=await self.selected();before=self.sql_snapshot();phase=session.phase;completed=set(session.completed)
  await peer.send(0xb6f)
  with self.assertRaises(asyncio.IncompleteReadError):await peer.until(0xb70)
  self.assertEqual(session.phase,phase);self.assertEqual(session.completed,completed);self.assertEqual(self.sql_snapshot(),before)
  self.assertTrue(any(e.get('event')=='protocol_error'and e.get('error')=='Legacy auxiliary request is not valid for DX11'for e in self.events))
 async def test_legacy_controlled_original_contract_retained(self):
  peer,session=await self.selected();before=self.sql_snapshot();phase=session.phase;completed=set(session.completed);build=session.client_build
  try:
   session.client_build='legacy';reply=session._handle(m.Event(0x202,kind=0xb6f),17)
  finally:session.client_build=build
  self.assertEqual(len(reply),1);self.assertEqual(reply[0].kind,0xb70);self.assertEqual(reply[0].payload,struct.pack('>i3I',0,0,0,0))
  self.assertEqual(session.phase,phase);self.assertEqual(session.completed,completed);self.assertEqual(self.sql_snapshot(),before)

if __name__=='__main__':unittest.main()
