"""Real private TLS transport tests. No game, production credentials or saves."""
from pathlib import Path
import asyncio,hashlib,importlib.util,json,socket,ssl,sys,tempfile,unittest
from unittest.mock import AsyncMock,patch
from types import SimpleNamespace
import time as real_time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from els_server.friends_bridge import Bridge,BridgeConfig
import els_server.friends_bridge as module
from els_server.friends_wire import read_json,write_json
from tools.create_friends_certificate import create

def free_port():
 with socket.socket()as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class TransportTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.pin=create(self.root,'127.0.0.1')
  ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(self.root/'server-cert.pem',self.root/'server-key.pem')
  self.connections=0;self.auth=[];self.frames=[];self.tasks=set();self.writers=set();self.events=[];self.bridges=[];self.probe=free_port()
  self.welcome=b'unchanged-native-welcome';self.reject_auth=False;self.disconnect=False
  def accept(reader,writer):
   task=asyncio.create_task(self.handle(reader,writer));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
  self.server=await asyncio.start_server(accept,'127.0.0.1',0,ssl=ctx);self.port=self.server.sockets[0].getsockname()[1]
 async def handle(self,reader,writer):
  self.connections+=1;self.writers.add(writer)
  try:
   auth=await read_json(reader);self.auth.append(auth)
   await write_json(writer,{'ok':not self.reject_auth,'account_id':2,'probe_port':self.probe,'relay_version':0})
   if self.reject_auth:return
   writer.write(self.welcome);await writer.drain()
   while data:=await reader.read(65536):
    self.frames.append(data)
    if self.disconnect:return
    writer.write(data);await writer.drain()
  except (ConnectionError,OSError,asyncio.IncompleteReadError):pass
  finally:
   writer.close()
   try:await writer.wait_closed()
   except (ConnectionError,OSError):pass
   self.writers.discard(writer)
 def bridge(self,**overrides):
  values=dict(host='127.0.0.1',port=self.port,name='private_test',token='x'*43,certificate_sha256=self.pin,local_port=free_port(),probe_port=self.probe);values.update(overrides)
  b=Bridge(BridgeConfig(**values),lambda e,**kw:self.events.append(dict(event=e,**kw)));self.bridges.append(b);return b
 async def native(self,b):return await asyncio.open_connection('127.0.0.1',b.config.local_port)
 async def asyncTearDown(self):
  for b in self.bridges:await b.close()
  for w in list(self.writers):w.close()
  self.server.close();await self.server.wait_closed()
  if self.tasks:await asyncio.wait_for(asyncio.gather(*self.tasks,return_exceptions=True),3)
  encoded=json.dumps(self.events);self.assertNotIn('x'*43,encoded);self.assertNotIn('private_test',encoded)
  self.tmp.cleanup()
 async def test_first_native_reuses_verified_preflight_when_new_connect_would_timeout(self):
  b=self.bridge();await b.start();b.remote=AsyncMock(side_effect=TimeoutError('private transient'))
  r,w=await self.native(b)
  try:
   self.assertEqual(await asyncio.wait_for(r.readexactly(len(self.welcome)),1),self.welcome)
   w.write(b'one-native-request');await w.drain();self.assertEqual(await r.readexactly(18),b'one-native-request')
   b.remote.assert_not_called();self.assertEqual(self.connections,1)
  finally:w.close();await w.wait_closed()
 async def test_delayed_native_claim_after_measured_startup_still_reuses_preflight(self):
  b=self.bridge();await b.start();self.assertEqual(module.RESERVED_NATIVE_TTL,120.0)
  now=real_time.monotonic
  b.remote=AsyncMock(side_effect=TimeoutError('fresh connection must not be opened'))
  with patch.object(module,'time',SimpleNamespace(monotonic=lambda:now()+45)):
   r,w=await b.native_remote()
  try:
   self.assertEqual(await r.readexactly(len(self.welcome)),self.welcome)
   b.remote.assert_not_called();self.assertEqual(self.connections,1)
  finally:await b._close_writer(w)
 async def test_expired_preflight_is_closed_and_new_connection_authenticated(self):
  with patch.object(module,'RESERVED_NATIVE_TTL',.03):
   b=self.bridge();await b.start();await asyncio.sleep(.08);self.assertIsNone(b.reserved_native)
   r,w=await self.native(b)
   try:self.assertEqual(await r.readexactly(len(self.welcome)),self.welcome);self.assertEqual(self.connections,2)
   finally:w.close();await w.wait_closed()
 async def test_pin_failure_sends_no_credentials_and_is_not_retried(self):
  b=self.bridge(certificate_sha256='0'*64)
  with self.assertRaisesRegex(ValueError,'fingerprint'):await b.start()
  self.assertFalse(self.auth);self.assertIsNone(b.reserved_native)
 async def test_authentication_rejection_is_not_retried(self):
  self.reject_auth=True;b=self.bridge()
  with self.assertRaisesRegex(ValueError,'authentication'):await b.start()
  self.assertEqual(len(self.auth),1);self.assertEqual(self.events[-1]['stage'],'authentication_reply')
 async def test_quick_transient_retry_only_before_forwarding(self):
  b=self.bridge();original=b.remote;b.remote=AsyncMock(side_effect=[OSError('private reset'),await original()])
  r,w=await b.native_remote()
  try:self.assertEqual(await r.readexactly(len(self.welcome)),self.welcome);self.assertEqual(b.remote.await_count,2);self.assertFalse(self.frames)
  finally:await b._close_writer(w)
 async def test_no_retry_after_forwarded_native_request(self):
  self.disconnect=True;b=self.bridge();await b.start();original=b.remote;b.remote=AsyncMock(wraps=original)
  r,w=await self.native(b)
  try:
   self.assertEqual(await r.readexactly(len(self.welcome)),self.welcome);w.write(b'single-economic-request');await w.drain()
   self.assertEqual(await asyncio.wait_for(r.read(),2),b'');self.assertEqual(self.frames,[b'single-economic-request']);b.remote.assert_not_called()
  finally:w.close();await w.wait_closed()
 async def test_connect_timeout_phase_logged_without_credentials(self):
  b=self.bridge()
  with patch.object(module.asyncio,'open_connection',AsyncMock(side_effect=TimeoutError('private timeout'))):
   with self.assertRaises(TimeoutError):await b.remote()
  self.assertEqual(self.events[-1]['stage'],'connect_tls');self.assertEqual(self.events[-1]['reason'],'TimeoutError')
 async def test_unused_preflight_closed_on_owner_shutdown(self):
  b=self.bridge();await b.start();await b.close();await asyncio.sleep(.03)
  self.assertIsNone(b.reserved_native);self.assertFalse(self.writers)

if __name__=='__main__':unittest.main(verbosity=2)
