from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,json,sqlite3,struct,sys,tempfile,unittest
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B)]
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.local_state import LocalState
from els_server.domain.local_session import LocalAccount
from els_server.storage.accounts import Accounts
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items
from els_server.domain.reward_rules import item_plan
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage.mount_growth import read
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import wstring


class Flow(unittest.TestCase):
    def setUp(self):
        (W/'tmp').mkdir(exist_ok=True);self.tmp=tempfile.TemporaryDirectory(dir=W/'tmp');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'races.sqlite3';a=LocalAccount(LocalState(self.path));a.enable_characters();a.enable_rewards();a.get_inventory_snapshot()
        config=ServerConfig(mode='friends',state_file=self.path,accounts_file=Path(self.tmp.name)/'accounts.sqlite3',tls_cert=Path(self.tmp.name)/'cert',tls_key=Path(self.tmp.name)/'key')
        self.app=Application(config);self.addCleanup(self.app.close);self.app.registry=Accounts(config.accounts_file)
        self.members=[];self.mounts={};self.sequence=800
        for i in range(6):
            identity=self.app.registry.create('racer'+str(i));identity={k:v for k,v in identity.items()if k!='token'}
            role=Characters(self.path,identity['id']).create('Elrider'+str(i),1,'racer-'+str(i));owner=role['uid']
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
                item=grant_items(db,[item_plan(550431,1)],owner)[0]
            activate(self.path,owner,0x432,struct.pack('>Q',item['uid']),'activate-'+str(i),account_id=identity['id'])
            self.mounts[owner]=next(p for p in snapshot(self.path,owner)['companions']if p['kind']=='mount')
            s=asyncio.run(self.app.session(identity=identity));s.role='game';s.phase='town_ready';s.completed.update((0x28,0x225,0x227))
            self.app.playing[identity['id']]=s;s.pending_map=s.active_map=s.account.get_location()['map'];self.call(self.app.world.synchronize,s)
            self.members.append(s)
        for s in self.members:s.mailbox.drain()
        self.racing=self.app.world.racing

    def send(self,s,kind,payload=b''):
        self.sequence+=1
        return self.call(s.handle,Event(0x202,kind=kind,payload=payload),self.sequence)

    def call(self,function,*args):return asyncio.run(self.app.call(function,*args))

    def select(self,s):
        uid=self.mounts[s.account.uid]['uid']
        response=self.send(s,0xa89,struct.pack('>Q',uid));self.assertEqual(next(e for e in response if e.kind==0xa8a).payload[:4],bytes(4))
        response=self.send(s,0xa8b,struct.pack('>QB',uid,1));self.assertEqual(next(e for e in response if e.kind==0xa8c).payload[:4],bytes(4))

    def invite(self,leader,target):
        body=struct.pack('>Q',target.account.uid)+wstring(target.account.character()['name'])+struct.pack('>iBi',0,1,150060)+bytes(6)+wstring('')+bytes(15)
        answer=self.send(leader,0x136,body);self.assertEqual(answer[0].payload[:4],bytes(4));target.mailbox.drain()
        answer=self.send(target,0x139,struct.pack('>QQBiBQ',leader.account.uid,0,1,0,0,0));self.assertEqual(answer[0].payload[:4],bytes(4))

    def entry(self,s,mode):
        response=self.send(s,0x7d4,struct.pack('>ii',mode,150060));self.assertEqual(response[0].payload,struct.pack('>ii',0,mode))
        body=struct.pack('>I',1)+bytes(19)
        response=self.send(s,0x382 if mode==1 else 0x37f,body)
        for event in response:
            if event.kind==0x14a:self.native_admission=event.payload
        return response

    def load(self,members):
        for s in members:self.send(s,0x91,struct.pack('>ii',100,0))
        room=self.racing.room(members[0]);self.assertEqual(room.phase,'active')
        for s in members:self.assertEqual(s.phase,'racing_active')
        return room

    def finish_payload(self,room):
        rows=room.data['standings']
        return struct.pack('>I',len(rows))+b''.join(struct.pack('>Qiff',r['uid'],len(rows)+1-r['rank'],r['time'],r['max_speed'])for r in sorted(rows,key=lambda r:r['uid']))+struct.pack('>f',max(r['time']for r in rows))

    def test_party_three_real_entry_loading_finish_replay_and_return(self):
        group=self.members[:3];leader=group[0]
        for s in group:self.select(s)
        for s in group[1:]:self.invite(leader,s)
        self.entry(leader,1);room=self.racing.room(leader)
        self.assertTrue(all(self.racing.room(s)is room for s in group));self.assertEqual(len(room.members),3)
        self.assertEqual(self.call(self.app.world.dungeons.manifest,self.app,leader.account.account_id)['epoch'],room.seed)
        room=self.load(group);payload=self.finish_payload(room)
        failed=self.send(leader,0xa86,payload);self.assertEqual(failed[0].payload,struct.pack('>i',-1))
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT SUM(settled)FROM mount_race_results').fetchone()[0],0)
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=room.started+130),patch('els_server.storage.mount_state.time.time',return_value=room.data['started']+130):
            answer=self.send(leader,0xa86,payload)
            self.assertIn(0xa88,[e.kind for e in answer]);self.assertEqual(room.phase,'result')
            self.send(leader,0xa86,payload)
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('SELECT SUM(settled)FROM mount_race_results').fetchone()[0],3)
            for s in group:
                expected=room.data['awards'][str(s.account.uid)]['profile']['experience']
                self.assertEqual(read(db,s.account.uid,self.mounts[s.account.uid]['uid'])['experience'],expected)
        result=self.send(leader,0x67,struct.pack('>i',0x72)+bytes(96));self.assertIn(0x68,[e.kind for e in result]);self.assertEqual(leader.phase,'map_loading')

    def test_six_matching_auto_start_and_waiting_locks(self):
        for s in self.members:self.select(s)
        for s in self.members[:5]:self.entry(s,2)
        first=self.members[0];before=first.account.get_inventory_snapshot()
        self.assertEqual(self.send(first,0xa8b,struct.pack('>QB',self.mounts[first.account.uid]['uid'],0)),[])
        self.assertEqual(self.send(first,0x104,bytes(11)),[]);self.assertEqual(first.account.get_inventory_snapshot(),before)
        self.entry(self.members[5],2);room=self.racing.room(first)
        self.assertEqual(len(room.members),6);self.assertFalse(self.racing.queue)
        self.load(self.members)
        (W/'native-inputs.json').write_text(json.dumps(dict(plans=room.data['plans'],data=room.data,mount=self.mounts[first.account.uid],mounts=self.mounts,admission=self.native_admission.hex())),encoding='utf8')

    def settle(self,room,leader):
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=room.started+130),patch('els_server.storage.mount_state.time.time',return_value=room.data['started']+130):
            return self.send(leader,0xa86,self.finish_payload(room))

    def test_six_party_direct_native_start_and_random_rejection(self):
        for s in self.members:self.select(s)
        leader=self.members[0]
        for s in self.members[1:]:self.invite(leader,s)
        response=self.send(leader,0x7d4,struct.pack('>ii',2,150060));self.assertNotEqual(response[0].payload[:4],bytes(4))
        response=self.send(self.members[1],0x382,struct.pack('>I',1)+bytes(19));self.assertNotEqual(response[0].payload[:4],bytes(4))
        response=self.send(leader,0x382,struct.pack('>I',1)+bytes(19));self.assertEqual(response[0].payload[:4],bytes(4))
        room=self.racing.room(leader);self.assertEqual(len(room.members),6);self.load(self.members)

    def test_disconnect_original_mount_dnf_other_players_finish_and_leave(self):
        group=self.members[:3];leader,other=group[:2]
        for s in group:self.select(s)
        for s in group[1:]:self.invite(leader,s)
        self.entry(leader,1);room=self.load(group)
        self.call(self.racing.relay_lost,other)
        self.assertIsNone(self.racing.room(other));self.assertTrue(other.coop_error)
        self.assertIn(0xa88,[e.kind for e in self.settle(room,leader)])
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(read(db,other.account.uid,self.mounts[other.account.uid]['uid'])['experience'],0)
            self.assertEqual(db.execute('SELECT disconnected,settled FROM mount_race_results WHERE owner=?',(other.account.uid,)).fetchone(),(1,1))
            self.assertIsNone(db.execute('SELECT 1 FROM mount_race_busy WHERE owner=?',(other.account.uid,)).fetchone())
            self.assertEqual(db.execute('SELECT stamina FROM mount_runtime WHERE uid=?',(self.mounts[other.account.uid]['uid'],)).fetchone()[0],60)

    def test_real_race_experience_levels_up_on_second_race(self):
        group=self.members[:3];leader=group[0]
        for s in group:self.select(s)
        for s in group[1:]:self.invite(leader,s)
        from els_server.domain import mount_racing_plan
        original=mount_racing_plan.draw
        # Fix only the server RNG; no growth is injected into the save.
        for run in range(2):
            with patch.object(mount_racing_plan,'draw',side_effect=lambda profile,lane,randbelow:original(profile,lane,lambda n:0)):
                self.entry(leader,1);room=self.load(group)
            self.assertEqual(room.data['standings'][0]['uid'],leader.account.uid)
            self.settle(room,leader)
            with closing(sqlite3.connect(self.path))as db:
                growth=read(db,leader.account.uid,self.mounts[leader.account.uid]['uid'])
                self.assertEqual(growth['experience'],120*(run+1));self.assertEqual(growth['level'],run+1)
                self.assertEqual(sum(growth['stats'].values()),2*run)
            for s in group:
                self.send(s,0x67,struct.pack('>i',0x72)+bytes(96))
                # Complete the test-owned town transition through the same
                # world membership boundary used by ordinary dungeon returns.
                s.phase='town_ready';s.dungeon_return_pending=False;s.active_map=s.pending_map=s.account.get_location()['map'];self.call(self.app.world.synchronize,s)
            if run==0:
                with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE mount_runtime SET stamina=120')

    def test_partial_decline_and_expiry_clear_all_original_peers(self):
        group=self.members[:3]
        for s in group:self.select(s);self.entry(s,2)
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=self.racing.partial_since+6):self.call(self.racing.periodic,group[0])
        for s in group:s.mailbox.drain()
        response=self.send(group[1],0x389,b'\0\1')
        self.assertFalse(self.racing.offers)
        for s in group:self.assertIn(0x387,[e.kind for e in s.mailbox.drain()]+([e.kind for e in response]if s is group[1]else[]))
        for s in group:self.entry(s,2)
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=self.racing.partial_since+6):self.call(self.racing.periodic,group[0])
        deadline=self.racing.offers[group[0]].deadline
        for s in group:s.mailbox.drain()
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=deadline+1):self.call(self.racing.periodic,group[0])
        self.assertFalse(self.racing.offers)
        for s in group:self.assertIn(0x387,[e.kind for e in s.mailbox.drain()])

    def test_server_clock_finishes_after_early_native_report_without_retransmit(self):
        group=self.members[:3];leader=group[0]
        for s in group:self.select(s)
        for s in group[1:]:self.invite(leader,s)
        self.entry(leader,1);room=self.load(group)
        self.assertEqual(self.send(leader,0xa86,self.finish_payload(room))[0].payload,struct.pack('>i',-1))
        for s in group:s.mailbox.drain()
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=room.started+130),patch('els_server.storage.mount_state.time.time',return_value=room.data['started']+130):
            self.call(self.racing.periodic,leader)
            self.assertEqual(room.phase,'result')
            with closing(sqlite3.connect(self.path))as db:before=db.execute('SELECT * FROM mount_race_results').fetchall()
            for s in group:self.assertIn(0xa88,[e.kind for e in s.mailbox.drain()]);self.call(self.racing.periodic,s)
            with closing(sqlite3.connect(self.path))as db:self.assertEqual(db.execute('SELECT * FROM mount_race_results').fetchall(),before)

    def test_partial_matching_native_confirmation_and_cancel(self):
        group=self.members[:3]
        for s in group:self.select(s);self.entry(s,2)
        start=self.racing.partial_since
        with patch('els_server.domain.friends_racing.time.monotonic',return_value=start+6):self.call(self.racing.periodic,group[0])
        offer=self.racing.offers[group[0]];self.assertEqual(offer.members,tuple(group))
        for s in group:
            self.assertIn(0x388,[e.kind for e in s.mailbox.drain()])
            self.send(s,0x389,b'\1\1')
        self.assertEqual(len(self.racing.room(group[0]).members),3)
        s=self.members[3];self.select(s);self.entry(s,2);self.send(s,0x385,bytes(8));self.assertNotIn(s,self.racing.queue)


if __name__=='__main__':unittest.main(verbosity=2)
