"""Owned loopback TLS, two real accounts, qualified Eve roles and native frames."""
from pathlib import Path
import asyncio,hashlib,importlib.util,io,json,struct,sys,tempfile,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;R=ROOT/'analysis/pr771-firstbatch-20261103-v1/runtime'
G=ROOT/'analysis/pr771-firstbatch-20261103-v1/git'
sys.path[:0]=[str(R),str(G),str(ROOT),str(G/'tests')]
import els_server
assert Path(els_server.__file__).is_relative_to(R)
import test_friends_server as native
assert Path(native.__file__)==G/'tests/test_friends_server.py'
from els_server.storage.characters import Characters
from els_server.domain.summon_rules import player_summon_templates
from els_server.domain.dungeon_population import population
from els_server.domain.dungeon_npcs import encode_npc
from els_server.protocol.protocol_codec import decode_event,decode_frame

class ObservedPeer(native.Peer):
    async def until(self,kind):
        if not hasattr(self,'observed'):self.observed=[]
        async with asyncio.timeout(8):
            for _ in range(80):
                frame=decode_frame(await native.read_wire(self.reader),self.keys,expected_sequence=self.incoming)
                self.incoming+=1;event=decode_event(frame.plaintext);self.observed.append(event)
                if event.kind==kind:return event
        raise AssertionError('Expected response missing '+hex(kind))

def summon(uid):
    p=ROOT/'analysis/skills-clear-20261015/sentry-request.json'
    dto=bytearray.fromhex(json.loads(p.read_bytes())['dto']);struct.pack_into('<Q',dto,0x6d,uid)
    return struct.pack('>I',1)+encode_npc(dto,0)

def expiry(key,uid):
    return (struct.pack('>iBQQ6fBf',key,255,2**64-1,2**64-1,*([0.]*6),1,500.)
        +struct.pack('>IIQBQIQ',0,1,uid,0,0,0,0))

class SentryTLS(unittest.IsolatedAsyncioTestCase):
    asyncSetUp=native.FriendsTests.asyncSetUp
    async def asyncTearDown(self):
        errors=[{k:v for k,v in e.items()if k in ('event','connection','error','sequence','kind','before','after')}
            for e in self.events if e['event']in ('worker_error','protocol_error','connection_task_error','business_phase')]
        (W/'tls-diagnostic.json').write_bytes((json.dumps(errors,indent=2)+'\n').encode())
        if any(e['event']!='business_phase'for e in errors):print(json.dumps(errors))
        await native.FriendsTests.asyncTearDown(self)
    bridge=native.FriendsTests.bridge
    coop_pair=native.FriendsTests.coop_pair
    coop_start=native.FriendsTests.coop_start
    coop_load=native.FriendsTests.coop_load
    async def peer(self,account):
        identity=self.app.registry.authenticate(account['name'],account['token'])
        roster=Characters(self.config.state_file,identity['id'])
        if not roster.list():roster.create('Player'+str(identity['id']),5,'owned-eve:'+str(identity['id']))
        peer=await ObservedPeer.open(self.bridge(account));self.peers.append(peer);return peer

    async def test_owner_summon_survives_shared_stage_and_expires_over_tls(self):
        alice,bob,a,b=await self.coop_pair();await self.coop_start(alice,bob);await self.coop_load(alice,bob)
        sessions=tuple(self.app.playing.values());owner=next(s for s in sessions if s.account.uid==b)
        leader=next(s for s in sessions if s.account.uid==a);room=self.app.world.dungeons.room(owner)
        self.assertIn(384,player_summon_templates(owner.account.character()))
        await bob.send(0x2ce,summon(b));self.assertEqual((await bob.until(0x2cf)).payload,bytes(4))
        created=await asyncio.gather(alice.until(0x2d0),bob.until(0x2d0))
        self.assertEqual(created[0].payload,created[1].payload);key=next(iter(owner.summon_keys))
        self.assertEqual(room.shared_actors.owners[key][2],b)
        starts={peer:len(peer.observed)for peer in (alice,bob)}
        p=population(0,hp_context=getattr(leader,'_c1_hp_context',None))
        order=[n for n in p['npcs']if n['key']!=p['clear_key']]+[p['npcs'][p['clear_key']]]
        for npc in order:
            body=(struct.pack('>iBQQ6fBf',npc['key'],0,a,b,0.,0.,0.,1.,2.,3.,0,npc['hp'])
                +struct.pack('>IQf',1,b,1.)+struct.pack('>IQB',1,b,1)+bytes(8)+bytes(4)+struct.pack('>Q',b))
            await alice.send(0xad,body);await alice.until(0xae);await bob.until(0xaf)
        self.assertTrue(all(s.part_end_notified for s in sessions))
        for peer in (alice,bob):await peer.send(0xbb,b'\0');await peer.until(0xbc)
        stages=await asyncio.gather(alice.until(0xb2),bob.until(0xb2))
        self.assertEqual(stages[0].payload,stages[1].payload);self.assertEqual(room.phase,'substage')
        self.assertTrue(all(s.summon_keys=={key}and not s.dungeon_substage_synced for s in sessions))
        before={s.account.uid:dict(s.account.get_reward_balances())for s in sessions}
        drop_counts={s:len(s.world_drops)for s in sessions}
        await alice.send(0xad,expiry(key,b))
        await bob.send(0xad,expiry(key,b));await bob.until(0xae);await alice.until(0xaf)
        self.assertTrue(all(set(s.summon_deaths)=={key}and not s.defeated_npcs for s in sessions))
        await self.coop_load(alice,bob)
        await bob.send(0xad,expiry(key,b));await bob.until(0xae)
        self.assertEqual(before,{s.account.uid:dict(s.account.get_reward_balances())for s in sessions})
        self.assertEqual(drop_counts,{s:len(s.world_drops)for s in sessions})
        self.assertTrue(all(not s.defeated_npcs and not s.part_end_notified for s in sessions))
        for peer in (alice,bob):self.assertNotIn(0x2d0,[e.kind for e in peer.observed[starts[peer]:]])
        self.assertEqual(sum(e.kind==0xaf and struct.unpack_from('>i',e.payload)[0]==key
            for e in alice.observed[starts[alice]:]),1)
        self.assertTrue(all(s.account.character()['unit_type']==5 for s in sessions))

if __name__=='__main__':
    (W/'tmp').mkdir(exist_ok=True);tempfile.tempdir=str(W/'tmp')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(SentryTLS);stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    paths=[Path(m.__file__)for n,m in sys.modules.copy().items()if n.startswith('els_server')and getattr(m,'__file__',None)]
    assert all(p.is_relative_to(R)for p in paths)
    out=dict(ok=result.wasSuccessful(),tests=result.testsRun,skipped=len(result.skipped),
        source_hashes={str(p.relative_to(R)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()for p in paths if p.suffix=='.py'},
        test_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),runtime_import_paths_verified=True,
        helper_sha256=hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        transport='real TLS/native frames over owned loopback listener',mocked_gameplay_qualification=False,
        natural_GUI=False,live_player_process=False,installed=False,
        failures=[dict(test=str(t),trace=s)for t,s in result.errors+result.failures])
    target=W/'sentry-tls-result.json';i=1
    while target.exists():target=W/f'sentry-tls-result-{i}.json';i+=1
    target.write_bytes((json.dumps(out,indent=2)+'\n').encode());print(stream.getvalue());print(json.dumps({k:v for k,v in out.items()if k not in('failures','source_hashes')}))
    raise SystemExit(not result.wasSuccessful())
