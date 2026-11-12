"""Real owned inventory and native flow; admission callback is a test seam."""
import bootstrap as env
env.W=env.HERE
import test_trade_state as fixtures
from contextlib import closing
from types import SimpleNamespace
import json,sqlite3,struct,unittest
from els_server.domain.player_trade_flow import PlayerTrades
from els_server.domain.local_session import LocalAccount,SessionOrderError
from els_server.storage.local_state import LocalState
from els_server.storage.characters import Characters
from els_server.domain.friends_world import Mailbox,FriendsWorld
from els_server.protocol.protocol_codec import Event
from els_server.protocol import player_trade_messages as wire

class Session:pass

class TradeFlowTests(unittest.TestCase):
    tearDown=fixtures.ExchangeTests.tearDown
    items=fixtures.ExchangeTests.items
    money=fixtures.ExchangeTests.money
    dump=fixtures.ExchangeTests.dump
    def setUp(self):
        fixtures.ExchangeTests.setUp(self)
        self.world=SimpleNamespace(members={},dungeons=SimpleNamespace(room=lambda s:None))
        self.world.send=lambda s,e:FriendsWorld.send(self.world,s,e)
        self.app=SimpleNamespace(world=self.world,playing={},accounts={},registry=SimpleNamespace(enabled=lambda a:True))
        self.sessions=[];self.seq=0
        for account,uid in enumerate(self.owners,1):
            local=LocalAccount(LocalState(self.path,uid),account_id=account)
            local.enable_characters(characters=Characters(self.path,account))
            s=Session();s.application=self.app;s.account=local;s.released=False;s.role='game';s.phase='town_ready'
            s.client_build='dx11_260923';s.item_test=True;s.completed={0x28};s.identity={'id':account}
            s.shop_session_id='owned-flow-session-'+str(account);s.active_map=20001;s.mailbox=Mailbox()
            s.dungeon_return_pending=False;s.town_warp_transition=None;s.social_overflow=False
            self.app.playing[account]=s;self.app.accounts[account]=local;self.world.members[s]=(1,20001)
            self.sessions.append(s)
        self.sa,self.sb=self.sessions
        self.flow=PlayerTrades(self.world)
    def action(self,s,kind,payload=b'',success=True):
        self.seq+=1;out=self.flow.request(s,Event(0x202,kind=kind,payload=payload),self.seq)
        if kind!=0x177:
            ack=next(e for e in out if e.kind==kind+1)
            self.assertEqual(ack.payload[:4]==bytes(4),success,(hex(kind),[e.payload.hex()for e in out]))
        return out
    def open(self):
        self.action(self.sa,0x174,struct.pack('>Q',self.b))
        self.assertEqual([e.kind for e in self.sb.mailbox.drain()],[0x176])
        out=self.action(self.sb,0x177,struct.pack('>QBi',self.a,1,0))
        self.assertEqual([e.kind for e in out],[0x179,0x17d])
        self.assertEqual([e.kind for e in self.sa.mailbox.drain()],[0x179,0x17e])
    def quoted(self):
        self.open()
        gear=next(i for i in self.items(self.a)if i['template']==30154)
        self.action(self.sa,0x17f,struct.pack('>QiB',gear['uid'],1,0))
        self.action(self.sa,0x182,struct.pack('>Q',101));self.action(self.sb,0x182,struct.pack('>Q',20))
        self.action(self.sa,0x185);self.action(self.sb,0x185)
        return gear
    def test_two_registration_and_approval_steps_precede_actual_exchange(self):
        gear=self.quoted();before=self.dump()
        self.action(self.sa,0x188);self.assertEqual(before,self.dump())
        out=self.action(self.sb,0x188)
        self.assertIn(0x18b,[e.kind for e in out]);self.assertFalse(self.flow.by_session)
        self.assertEqual((self.money(self.a)['ed'],self.money(self.b)['ed']),(4918,5076))
        self.assertEqual(next(i for i in self.items(self.b)if i['uid']==gear['uid'])['enhancement'],8)
        self.assertIn(0x18b,[e.kind for e in self.sa.mailbox.drain()])
        before=self.dump();self.action(self.sb,0x188,success=False);self.assertEqual(before,self.dump())
    def test_own_registered_offer_is_frozen_and_peer_edit_resets_confirmation(self):
        self.open();self.action(self.sa,0x185)
        room=self.flow.by_session[self.sa]
        self.action(self.sa,0x182,struct.pack('>Q',1),success=False)
        self.assertEqual(room['registered'],{self.a})
        self.action(self.sb,0x182,struct.pack('>Q',1))
        self.assertEqual(room['registered'],set())
        notices=[e for e in self.sa.mailbox.drain()if e.kind==0x184]
        self.assertEqual(notices[-1].payload[-18:],struct.pack('>Q?Q?',self.a,False,self.b,False))
        before=self.dump();self.action(self.sb,0x188,success=False)
        self.assertEqual(before,self.dump());self.assertFalse(self.flow.by_session)
    def test_duplicate_item_is_not_appended_and_remove_uses_owned_offer(self):
        self.open();item=next(i for i in self.items(self.a)if i['template']==500040)
        body=struct.pack('>QiB',item['uid'],3,0)
        self.action(self.sa,0x17f,body);self.action(self.sa,0x17f,body,success=False)
        self.assertEqual(len(self.flow.by_session[self.sa]['offers'][self.a]['items']),1)
        self.action(self.sa,0x17f,struct.pack('>QiB',item['uid'],-100,1))
        self.action(self.sa,0x17f,struct.pack('>QiB',item['uid'],0,1),success=False)
        self.assertFalse(self.flow.by_session[self.sa]['offers'][self.a]['items'])
    def test_cancel_and_scene_change_release_both_reservations_without_economy(self):
        self.open();before=self.dump()
        self.action(self.sa,0x17a,struct.pack('>i',0x72))
        self.assertFalse(self.flow.by_session);self.assertEqual(before,self.dump())
        self.assertEqual([e.kind for e in self.sa.mailbox.drain()],[0x17c])
        self.assertEqual([e.kind for e in self.sb.mailbox.drain()],[0x17c])
        self.open();self.sb.phase='channels_ready';self.flow.synchronize(self.sb)
        self.assertFalse(self.flow.by_session);self.assertEqual(before,self.dump())
        self.assertIn(0x17c,[e.kind for e in self.sa.mailbox.drain()])
    def test_qualification_busy_and_forged_recipient_do_not_authorize_trade(self):
        self.sb.phase='channels_ready';self.action(self.sa,0x174,struct.pack('>Q',self.b),success=False)
        self.assertFalse(self.flow.by_session)
        self.sb.phase='town_ready';self.action(self.sa,0x174,struct.pack('>Q',self.b))
        self.action(self.sb,0x174,struct.pack('>Q',self.a),success=False)
        out=self.action(self.sa,0x177,struct.pack('>QBi',self.a,1,0))
        self.assertEqual(out[0].kind,0x178)
        self.assertEqual(self.flow.by_session[self.sa]['phase'],'invited')
        self.action(self.sb,0x177,struct.pack('>QBi',self.a,0,0))
        self.assertFalse(self.flow.by_session)
    def test_full_mailbox_preparation_rolls_back_both_economic_updates(self):
        self.quoted();self.action(self.sa,0x188);before=self.dump()
        self.sa.mailbox.drain()
        for _ in range(256):self.sa.mailbox.append(Event(0x201,kind=0x48f,payload=b'x'))
        self.action(self.sb,0x188,success=False)
        self.assertEqual(before,self.dump());self.assertFalse(self.flow.by_session)
        self.assertTrue(self.sa.social_overflow)
    def test_late_peer_generation_change_rolls_back_and_never_publishes_success(self):
        self.quoted();self.action(self.sa,0x188);self.sa.mailbox.drain();before=self.dump()
        completed=wire.completed
        def change(ed,changes):
            event=completed(ed,changes);self.sa.shop_session_id='new-generation';return event
        wire.completed=change
        try:out=self.action(self.sb,0x188,success=False)
        finally:wire.completed=completed
        self.assertEqual(before,self.dump());self.assertFalse(self.flow.by_session)
        self.assertNotIn(0x18b,[e.kind for e in out]+[e.kind for e in self.sa.mailbox.drain()])
    def test_item_removed_after_registration_cannot_settle(self):
        gear=self.quoted()
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE inventory_items SET template=30155 WHERE uid=?',(gear['uid'],))
        before=self.dump();self.action(self.sa,0x188,success=False)
        self.assertEqual(before,self.dump());self.assertFalse(self.flow.by_session)
    def test_offer_change_during_response_preparation_rolls_back(self):
        self.quoted();self.action(self.sa,0x188);before=self.dump()
        room=self.flow.by_session[self.sa];completed=wire.completed
        def change(ed,changes):
            event=completed(ed,changes);room['offers'][self.a]['ed']+=1;return event
        wire.completed=change
        try:self.action(self.sb,0x188,success=False)
        finally:wire.completed=completed
        self.assertEqual(before,self.dump());self.assertFalse(self.flow.by_session)
    def test_current_native_ten_slot_bound_also_applies_to_storage(self):
        from els_server.storage.inventory_state import grant_items
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES
        from els_server.storage.item_seals import assign
        from els_server.storage import player_trade_state as state
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            rows=grant_items(db,[dict(template=30154,metadata=VERIFIED_TEMPLATES[30154],group=1,quantity=10)],self.a)
            for item in rows:assign(db,self.a,item['uid'],True,2)
        self.open()
        rows=[i for i in self.items(self.a)if i['template']==30154]
        self.assertEqual(len(rows),11)
        for item in rows[:10]:self.action(self.sa,0x17f,struct.pack('>QiB',item['uid'],1,0))
        self.action(self.sa,0x17f,struct.pack('>QiB',rows[10]['uid'],1,0),success=False)
        self.assertEqual(len(self.flow.by_session[self.sa]['offers'][self.a]['items']),10)
        before=self.dump()
        agreement=dict(id=1,participants=[dict(owner=self.a,account=1,generation='a',ed=0,items=[dict(item=i,quantity=1)for i in rows]),
            dict(owner=self.b,account=2,generation='b',ed=0,items=[])])
        with self.assertRaises(ValueError):state.perform(self.path,agreement,'owned-ten-slots',lambda db,now:None,lambda *args:None)
        self.assertEqual(before,self.dump())
    def test_expired_invitation_releases_both_peers_and_late_consent_fails(self):
        self.action(self.sa,0x174,struct.pack('>Q',self.b));before=self.dump()
        self.flow.by_session[self.sa]['expires']=0
        self.flow.periodic(self.sb)
        self.assertFalse(self.flow.by_session);self.assertEqual(before,self.dump())
        self.sa.mailbox.drain();self.sb.mailbox.drain()
        out=self.action(self.sb,0x177,struct.pack('>QBi',self.a,1,0))
        self.assertEqual(out[0].kind,0x178);self.assertEqual(before,self.dump())
        self.open()

    def test_timeout_does_not_notify_a_replaced_character_generation(self):
        self.action(self.sa,0x174,struct.pack('>Q',self.b))
        self.sa.mailbox.drain();self.sb.mailbox.drain()
        self.sa.shop_session_id='replacement-generation'
        self.flow.by_session[self.sb]['expires']=0
        self.flow.periodic(self.sb)
        self.assertFalse(self.flow.by_session)
        self.assertEqual(self.sa.mailbox.drain(),[])
        self.assertEqual([e.kind for e in self.sb.mailbox.drain()],[0x178])

    def test_worker_targets_include_peer_before_invite_and_while_reserved(self):
        event=Event(0x202,kind=0x174,payload=struct.pack('>Q',self.b))
        def handle():pass
        self.assertEqual(self.flow.targets(self.sa,handle,(event,)),(self.sb,))
        self.action(self.sa,0x174,event.payload)
        self.assertEqual(set(self.flow.targets(self.sb,lambda:None,())),set(self.sessions))

if __name__=='__main__':
    result=unittest.main(exit=False).result
    value=dict(ok=result.wasSuccessful(),tests=result.testsRun,failures=[(str(t),d)for t,d in result.failures],errors=[(str(t),d)for t,d in result.errors],
        production_database_access=False,natural_GUI=False,
        scope='Native world-flow and real owned SQL; approved no level/wait admission; separate authenticated TLS dispatcher verification')
    target=env.W/'flow-tests.json'
    if target.exists():target=target.with_stem(target.stem+'-'+str(__import__('time').time_ns()))
    target.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf8');raise SystemExit(0 if value['ok']else 1)
