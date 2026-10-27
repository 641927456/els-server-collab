import asyncio,hashlib,sqlite3,struct,unittest
from contextlib import closing
from unittest.mock import patch
import test_friends_server as native
from els_server.friends_bridge import Bridge,BridgeConfig as ActualBridgeConfig
from els_server.protocol.protocol_codec import BOOTSTRAP_KEYS,Event,encode_event,encode_frame,decode_event,decode_frame,read_welcome
from els_server.protocol.local_messages import wstring
from els_server.performance import worker_timing

class Peer:
    @classmethod
    async def open(cls,identity,pin,host):
        self=cls();self.bridge=Bridge(BridgeConfig(host,19400,identity['name'],identity['token'],pin))
        self.reader,self.writer=await self.bridge.remote();self.outgoing=1;self.incoming=2;self.last_initialization=None
        self.spi,self.keys=read_welcome(decode_event(decode_frame(await self.frame(),BOOTSTRAP_KEYS).plaintext))
        return self
    async def frame(self):
        async with asyncio.timeout(15):
            header=await self.reader.readexactly(8);length=struct.unpack_from('<I',header)[0]
            assert 40<=length<=1024*1024
            return header+await self.reader.readexactly(length-8)
    async def send(self,kind,payload=b''):
        event=Event(0x202,kind=kind,payload=payload,performers=(0,)if kind in(0x28,0x48b,0x489,0x7d0)else())
        self.writer.write(encode_frame(encode_event(event),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1
        await self.writer.drain()
    async def until(self,kind):
        for _ in range(160):
            frame=decode_frame(await self.frame(),self.keys,expected_sequence=self.incoming);self.incoming+=1
            event=decode_event(frame.plaintext)
            if event.kind==0x2a:self.last_initialization=event
            if event.kind==kind:return event
        raise AssertionError('Expected bounded protocol response missing')
    async def roster(self):
        for request,response in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
            await self.send(request);await self.until(response)
    async def enter(self,uid):
        native=None
        for request,response,payload in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uid)),
                (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
                (0x225,0x226,struct.pack('>iB',20000,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
            await self.send(request,payload);await self.until(response)
            if request==0x28:
                native=self.last_initialization
                if native is None:native=await self.until(0x2a)
                assert len(native.payload)>200 and struct.pack('>Q',uid)in native.payload
        return {'kind':0x2a,'size':len(native.payload),'sha256':hashlib.sha256(native.payload).hexdigest()}
    async def burst(self):
        for _ in range(128):await self.send(0x7d0,bytes(9))
        await self.send(0x213);await self.until(0x214)
    async def close(self):
        self.writer.close()
        try:await self.writer.wait_closed()
        finally:await self.bridge.close()


class SelectionBusinessTLS(native.FriendsTests):
    async def test_live_market_projection_does_not_reserve_writer_or_write(self):
        global BridgeConfig
        BridgeConfig=lambda host,port,name,token,pin:ActualBridgeConfig(host,self.port,name,token,pin)
        peer=await Peer.open(self.alice,self.pin,'127.0.0.1')
        try:
            await peer.roster()
            await peer.send(0x489,wstring('QBusiness')+struct.pack('>iiBBI',1,1,0,0,0))
            self.assertEqual((await peer.until(0x25)).payload[:4],bytes(4))
            from els_server.storage.characters import Characters
            uid=Characters(self.config.state_file,self.alice['id']).list()[0]['uid']
            await peer.enter(uid)
            session=self.app.playing[self.alice['id']]
            def project():
                from els_server.domain.black_market_flow import transact
                from els_server.storage.read_scope import committed_reads
                connect=sqlite3.connect;traces=[];sample=dict(registry_ms=0.,registry_checks=0,projection_ms=0.,projection_loads=0,projection_hits=0)
                def traced(*a,**kw):
                    db=connect(*a,**kw);db.set_trace_callback(traces.append);return db
                with closing(connect(self.config.state_file,timeout=.05))as blocker:
                    blocker.execute('BEGIN IMMEDIATE')
                    session._black_market_snapshot=None
                    with patch('sqlite3.connect',traced),worker_timing(sample),committed_reads():reply=transact(session)
                    self.assertTrue(reply);self.assertFalse(any('BEGIN IMMEDIATE' in q.upper()for q in traces))
                    self.assertFalse(any(q.lstrip().upper().startswith(('INSERT','UPDATE','DELETE','CREATE'))for q in traces))
                    self.assertEqual(sample.get('sql_begin_wait_ms',0),0)
                return True
            self.assertTrue(await asyncio.wait_for(self.app.call(project),2))
            self.assertFalse(any(e['event']=='worker_error'for e in self.events))
        finally:await peer.close()

def load_tests(loader,tests,pattern):
    return unittest.TestSuite([SelectionBusinessTLS('test_live_market_projection_does_not_reserve_writer_or_write')])
