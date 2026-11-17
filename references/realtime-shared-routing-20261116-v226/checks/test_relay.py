"""RAM-only real relay receive loop; no listeners, accounts or player writes."""
import asyncio,importlib.util,json,struct,sys,time,unittest,uuid
from pathlib import Path
from types import SimpleNamespace as NS
ROOT=Path(__file__).resolve().parents[1]
import argparse
parser=argparse.ArgumentParser(add_help=False)
parser.add_argument('--runtime',type=Path,required=True)
options,rest=parser.parse_known_args()
sys.argv[1:]=rest
SRC=options.runtime.resolve(strict=True)
sys.path[:0]=[str(SRC),str(SRC/'vendor')]
BASELINE='--baseline' in sys.argv
if BASELINE:sys.argv.remove('--baseline')
def load(name):
    p=(SRC if BASELINE else ROOT/'source')/Path(*name.split('.')).with_suffix('.py')
    spec=importlib.util.spec_from_file_location(name,p);module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module;spec.loader.exec_module(module);return module
rt=load('els_server.realtime');relay=load('els_server.friends_relay')
EPOCH=str(uuid.uuid4())
class Writer:
    def __init__(self):self.data=[]
    def write(self,data):self.data.append(data)
    async def drain(self):pass
def frame(reader,payload):reader.feed_data(struct.pack('>I',len(payload))+payload)

class Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        async def call(function,*args):return function(*args)
        self.logs=[]
        self.app=NS(realtime=NS(view=rt.View({}, {(1,EPOCH,1002):(2,1001)}, {}, {1:(1,2),2:(1,2)}, {1:'session1',2:'session2'}, {}, frozenset())),
            registry=NS(list=lambda:[{'id':i,'enabled':True}for i in (1,2)]),playing={},
            world=NS(dungeons=NS(relay_lost=lambda *a:None),pvp=NS(support_lost=lambda *a:None)),call=call)
        self.access=rt.RealtimeAccess(self.app,lambda *a,**k:None)
        self.access.enabled=frozenset((1,2));self.access.checked=time.monotonic()-1
        self.server=relay.RelayServer(self.app,lambda event,**kw:self.logs.append((event,kw)))
        self.server.realtime=self.access;self.target=relay.PacketQueue();self.server.endpoints[2]=self.target
        self.reader=asyncio.StreamReader();self.writer=Writer()
        self.task=asyncio.create_task(self.server.serve(self.reader,self.writer,{'id':1},control=True))
        await asyncio.sleep(0)
    async def asyncTearDown(self):
        self.task.cancel();await asyncio.gather(self.task,return_exceptions=True);await self.access.close()
    async def refresh(self,enabled=(1,2)):
        self.app.registry.list=lambda:[{'id':i,'enabled':i in enabled}for i in (1,2)]
        await self.access.refresh()
    async def send(self,data=b'opaque-hit',epoch=EPOCH,target=1002):
        frame(self.reader,relay.data_packet(epoch,target,data));await asyncio.sleep(.02)
    async def test_stale_snapshot_preserves_current_frame_once(self):
        await self.send();self.assertTrue(self.target.queue.empty())
        await self.refresh();await asyncio.sleep(.02)
        self.assertEqual(self.target.queue.qsize(),1,'old receive loop silently loses this frame')
        self.assertEqual(relay.read_data(await self.target.get()),(EPOCH,1001,b'opaque-hit'))
    async def test_disabled_target_during_wait_is_not_forwarded(self):
        await self.send();await self.refresh(enabled=(1,));await asyncio.sleep(.02)
        self.assertTrue(self.target.queue.empty())
    async def test_changed_room_during_wait_does_not_replay(self):
        await self.send();self.app.realtime.view.routes.clear();await self.refresh();await asyncio.sleep(.02)
        self.assertTrue(self.target.queue.empty())
    async def test_changed_session_during_wait_does_not_forward(self):
        await self.send();self.app.realtime.view.bindings[1]='new-session';await self.refresh();await asyncio.sleep(.02)
        self.assertTrue(self.target.queue.empty())
    async def test_fresh_packets_preserve_order_and_sender_identity(self):
        await self.refresh()
        for i in range(20):frame(self.reader,relay.data_packet(EPOCH,1002,bytes((i,))))
        await asyncio.sleep(.03)
        self.assertEqual(self.target.queue.qsize(),20)
        self.assertEqual([relay.read_data(await self.target.get())for _ in range(20)],[(EPOCH,1001,bytes((i,)))for i in range(20)])
    async def test_overflow_fails_destination_only(self):
        await self.refresh()
        for _ in range(128):self.target.put(b'full')
        await self.send();self.assertTrue(self.target.failed.is_set());self.assertFalse(self.task.done())
    async def test_unknown_target_and_epoch_rejected(self):
        await self.refresh();await self.send(target=9999);await self.send(epoch=str(uuid.uuid4()))
        self.assertTrue(self.target.queue.empty())
    async def test_close_reports_metadata_without_datagram(self):
        await self.refresh();await self.send(data=b'PRIVATE-COMBAT-PAYLOAD')
        frame(self.reader,b'\6');await asyncio.wait_for(self.task,1)
        records=[kw for e,kw in self.logs if e=='relay_traffic']
        self.assertEqual(len(records),1);self.assertEqual(records[0]['counts']['queued'],1)
        self.assertEqual(records[0]['queued_by_target'],{2:1})
        self.assertNotIn('PRIVATE-COMBAT-PAYLOAD',json.dumps(self.logs))
    async def test_reader_failure_wakes_waiter_and_denies(self):
        if BASELINE:self.skipTest('new wait method')
        async def failed():raise OSError('registry unavailable')
        self.access.task=asyncio.create_task(failed());await asyncio.sleep(0)
        self.access.updated.set()
        await self.access.wait_current(1)
        self.assertEqual(self.access.denial(1,self.app.realtime.view),'registry_reader_failed')
        self.assertIsNone(self.access.route(1,EPOCH,1002))
    async def legacy_after_worker(self,change_room):
        await self.refresh();v=self.app.realtime.view
        self.app.realtime.view=rt.View(v.manifests,v.routes,v.clocks,v.required,v.bindings,v.auxiliary,frozenset((1,2)))
        self.app.world.dungeons.manifest=lambda *args:None
        called=0
        def target(*args):
            nonlocal called
            called+=1
            if called==1:self.access.checked=time.monotonic()-1;return (2,1001)
            return None if change_room else (2,1001)
        self.app.world.dungeons.relay_target=target
        await self.send();self.assertTrue(self.target.queue.empty())
        await self.refresh();await asyncio.sleep(.03)
        self.assertEqual(called,2)
        self.assertEqual(self.target.queue.qsize(),0 if change_room else 1)
    async def test_two_stale_phases_share_one_deadline(self):
        if BASELINE:self.skipTest('new wait budget')
        start=asyncio.Event()
        legacy_call=asyncio.Event()
        original=self.access.wait_current
        async def wait_current(account):
            start.set()
            return await original(account)
        self.access.wait_current=wait_current
        v=self.app.realtime.view
        self.app.realtime.view=rt.View(v.manifests,v.routes,v.clocks,v.required,v.bindings,v.auxiliary,frozenset((1,2)))
        self.app.world.dungeons.manifest=lambda *args:None
        def target(*args):
            self.access.checked=time.monotonic()-1
            legacy_call.set()
            return (2,1001)
        self.app.world.dungeons.relay_target=target
        from unittest.mock import patch
        with patch.object(relay,'AUTHORIZATION_WAIT_TIMEOUT',.50):
            frame(self.reader,relay.data_packet(EPOCH,1002,b'opaque'))
            await asyncio.wait_for(start.wait(),1)
            await asyncio.sleep(.30)
            await self.refresh()
            await asyncio.wait_for(legacy_call.wait(),1)
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(self.task),.35)
            self.assertTrue(self.task.done(),'a second per-phase delay extends the frame budget')
            self.assertTrue(self.target.queue.empty())
            self.assertEqual(sum(event=='relay_authorization_timeout' for event,_ in self.logs),1)
            self.assertEqual(sum(row['counts'].get('authorization_timeouts',0)
                                 for event,row in self.logs if event=='relay_traffic'),1)

    async def test_legacy_route_rechecks_epoch_after_auth_wait(self):
        await self.legacy_after_worker(True)
    async def test_legacy_route_survives_auth_wait_without_replay(self):
        await self.legacy_after_worker(False)

if __name__=='__main__':unittest.main(verbosity=2)
