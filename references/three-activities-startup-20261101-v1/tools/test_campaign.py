"""Isolated economic/restore tests; all fixtures and temporary saves stay on G:."""
from pathlib import Path
import sys,tempfile,sqlite3,struct,json,uuid,unittest,time
from contextlib import closing
from unittest.mock import patch
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT/'runtime'))
from els_server.domain import abyss_weapon_2026 as rules
from els_server.domain.local_session import LocalAccount,LocalSession
import els_server;assert Path(els_server.__file__).resolve().is_relative_to(Path(__file__).resolve().parent/'runtime'),els_server.__file__
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items,grant_items,InventoryFull
from els_server.storage.abyss_weapon_2026 import Campaign,week
from els_server.storage.abyss_weapon_boxes import open_box
from els_server.protocol.protocol_codec import Event
from els_server.domain.abyss_weapon_campaign import Flow
NOW=int(time.time())

def cube_payload(uid):return struct.pack('>QBBBIi',uid,0,0,0,0,0)
def request(kind,payload=b''):return Event(0x202,performers=(0,),kind=kind,payload=payload)

class CampaignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from els_server.domain.owned_growth_items import install
        install();rules.register()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='save-',dir=OUT);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'game.sqlite3'
        self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        with self.db()as db,db:
            db.execute('UPDATE characters SET unit_class=79,level=99,transcendence=1 WHERE uid=1001')
            Campaign(db).initialize()
        self.prepare=lambda db:None
    def db(self):return closing(sqlite3.connect(self.path,timeout=10))
    def items(self):
        with self.db()as db:return load_items(db,1001)
    def join(self):
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');return Campaign(db).join(1,1001,NOW)
    def open_weapon(self):
        self.join()
        with self.db()as db:box=Campaign(db).snapshot(1)['box_uid']
        events=open_box(self.path,1001,rules.BOX,cube_payload(box),'open',account_id=1,prepare=self.prepare)
        with self.db()as db:uid=Campaign(db).snapshot(1)['weapon_uid']
        return next(i for i in self.items()if i['uid']==uid),events
    def receipt(self,db,run,dungeon):
        db.execute('CREATE TABLE IF NOT EXISTS reward_receipts(run_id TEXT PRIMARY KEY,proof_sha256 TEXT NOT NULL,grant_json TEXT NOT NULL)')
        db.execute('INSERT INTO reward_receipts VALUES(?,?,?,?,?)',(run,'a'*64,json.dumps(dict(owner=1001,dungeon_clear=[dungeon,1])),b'fixture',json.dumps({})))
    def enough_points(self):
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');t=Campaign(db)
            for w in range(4):
                now=NOW+w*604800;t.refresh(1,1001,now)
                for _ in range(5):
                    run=str(uuid.uuid4());t.admit(1,1001,run,34130,False,now);self.receipt(db,run,34130)
                t.recover(1,1001,now);t.claim_task(1,1001,169590,now)
            self.assertEqual(t.snapshot(1)['points'],500)
    def test_join_is_account_bound_and_rolls_back_full_bag(self):
        with patch('els_server.storage.inventory_state.grant_items',side_effect=InventoryFull):pass
        with self.db()as db:
            with self.assertRaises(InventoryFull),db:
                db.execute('BEGIN IMMEDIATE')
                with patch('els_server.storage.abyss_weapon_2026.grant_items',side_effect=InventoryFull):Campaign(db).join(1,1001,NOW)
            self.assertIsNone(Campaign(db).snapshot(1))
        first=self.join();before=self.items();self.assertEqual(self.join(),[]);self.assertEqual(self.items(),before)
        self.assertEqual(len(first),1)
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):Campaign(db).join(2,1001,NOW)
            db.execute('UPDATE characters SET unit_class=1 WHERE uid=1001')
            with self.assertRaises(ValueError):Campaign(db).join(1,1001,NOW)
    def test_weapon_is_plus11_fully_grown_and_open_replay_does_not_duplicate(self):
        weapon,events=self.open_weapon();self.assertEqual(weapon['template'],720797);self.assertEqual(weapon['enhancement'],11)
        self.assertLessEqual(abs(weapon['expires_at']-NOW-90*86400),5)
        self.assertEqual(weapon['option_groups']['17'],[47720,200148,200138])
        with self.db()as db:box=Campaign(db).snapshot(1)['box_uid']
        before=self.items();open_box(self.path,1001,rules.BOX,cube_payload(box),'open',account_id=1,prepare=self.prepare)
        self.assertEqual(self.items(),before)
        from els_server.domain.paid_enhancement import quote
        from els_server.domain.decomposition_rules import quote as dismantle
        with self.assertRaises(ValueError):quote(weapon)
        with self.assertRaises(ValueError):dismantle(weapon)
    def test_clear_admission_replay_week_boundary_and_foreign_receipt(self):
        self.join()
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');t=Campaign(db);run=str(uuid.uuid4())
            t.admit(1,1001,run,34130,True,NOW);self.receipt(db,run,34130)
            t.recover(1,1001,NOW);t.recover(1,1001,NOW)
            task={r['id']:r['count']for r in t.tasks(1,1001,NOW)};self.assertEqual(task[169590][0],1)
            t.refresh(1,1001,NOW+604800);task={r['id']:r['count']for r in t.tasks(1,1001,NOW+604800)};self.assertEqual(task[169590][0],0)
            with self.assertRaises(ValueError):t.admit(1,1001,run,34130,True,NOW)
        boundary=week(NOW)+604800
        self.assertEqual(week(boundary-1),boundary-604800);self.assertEqual(week(boundary),boundary)
    def test_rewards_and_conversion_commit_once_keep_uid_and_other_options(self):
        weapon,_=self.open_weapon()
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE')
            with self.assertRaises(ValueError):Campaign(db).convert(1,1001,NOW)
        self.enough_points()
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');t=Campaign(db)
            with self.assertRaises(ValueError):t.claim_reward(1,1001,4)
            for index in range(5):
                grants=t.claim_reward(1,1001,index);self.assertEqual(len(grants),1)
                self.assertEqual(t.claim_reward(1,1001,index),[])
            converted=t.convert(1,1001,NOW)
            self.assertEqual(converted['uid'],weapon['uid']);self.assertNotIn('expires_at',converted)
            self.assertEqual(converted['enhancement'],11);self.assertEqual(converted['option_groups'],weapon['option_groups'])
            self.assertEqual(t.convert(1,1001,NOW),converted)
        with self.db()as db:self.assertEqual(Campaign(db).snapshot(1)['converted_uid'],weapon['uid'])
    def test_every_campaign_bundle_opens_with_published_quantities(self):
        for template in map(int,rules.definition()['bundles']):
            with self.db()as db,db:
                db.execute('BEGIN IMMEDIATE');item=grant_items(db,rules.plan(template,1),1001)[0]
            before={t:sum(i['count']for i in self.items()if i['template']==t)for t in rules.templates()}
            open_box(self.path,1001,template,cube_payload(item['uid']),'bundle:'+str(template),account_id=1,prepare=self.prepare)
            for row in rules.definition()['bundles'][str(template)]:self.assertEqual(sum(i['count']for i in self.items()if i['template']==row['template'])-before[row['template']],row['quantity'])
    def test_flow_preserves_other_event_entries_and_rejects_malformed_rewards(self):
        from els_server.protocol.activity_2026_entries import notice,CodeEntry,read
        s=LocalSession(self.account,client_build='dx11_260923',item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_dungeon=True)
        s.role='game';s.phase='town_ready';flow=Flow(None,clock=lambda:NOW)
        out=flow.finalize(s,[notice({678:CodeEntry(True,1,2),518:CodeEntry(True,1,2)})])
        self.assertEqual(set(read(next(e.payload for e in out if e.kind==0x4b9))),{518,580,678})
        result=flow.handle(s,request(0xc5b),1);self.assertEqual(next(e.payload for e in result if e.kind==0xc5c),bytes(4))
        out=flow.finalize(s,result);self.assertEqual(set(read(next(e.payload for e in out if e.kind==0x4b9))),{518,580,678})
        self.assertEqual(sum(e.kind==0xf0 for e in out),8)
        bad=flow.handle(s,request(0xc5d,b'\0\0\0\0'),2)
        self.assertNotEqual(bad[0].payload,bytes(4))
    def test_public_startup_installs_provider_and_preserves_existing_clock_tracking(self):
        import asyncio
        from els_server.application import Application
        from els_server.config import ServerConfig
        async def run():
            directory=Path(self.temp.name)
            config=ServerConfig(mode='friends',state_file=self.path,accounts_file=directory/'accounts.sqlite3',tls_cert=directory/'tls.crt',tls_key=directory/'tls.key',log_dir=directory/'logs')
            app=Application(config)
            try:
                await app.start()
                flow=app.activity_options(app.account)['activity2026_awards']
                self.assertIsInstance(flow,Flow);self.assertIsNotNone(flow.previous)
                self.assertIn(flow,app.activity2026_manager.flows)
                self.assertNotIn(flow.previous,app.activity2026_manager.flows)
                self.assertIs(flow.online,flow.previous.online)
            finally:app.close()
        asyncio.run(run())
    def test_native_reward_aliases_and_manual_recovery_use_existing_rules(self):
        from els_server.domain.spell_socket_rules import material,draw,validate_option
        for t,base in ((720764,136109),(720765,136110),(720766,136111),(720767,136112)):
            self.assertEqual(material(t)['pool_type'],material(base)['pool_type'])
            self.assertEqual(material(t)['socket_group'],material(base)['socket_group'])
            value=draw(t,lambda n:n-1);self.assertEqual(value,draw(base,lambda n:n-1));validate_option(t,value)
        from els_server.domain.consumables import require_usable
        for t in(710006,710250):self.assertEqual(require_usable(t,99)['id'],t)
    def test_reward_encode_failure_rolls_back_binding_and_items(self):
        s=LocalSession(self.account,client_build='dx11_260923',item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_dungeon=True)
        s.role='game';s.phase='town_ready';flow=Flow(None,clock=lambda:NOW);before=self.items()
        with patch('els_server.domain.abyss_weapon_campaign.encode_event',side_effect=RuntimeError('injected encoder failure')):
            with self.assertRaises(RuntimeError):flow.handle(s,request(0xc5b),1)
        with self.db()as db:self.assertIsNone(Campaign(db).snapshot(1))
        self.assertEqual(self.items(),before)
    def test_point_item_real_dispatch_debits_once_and_replays_last_stack(self):
        self.join()
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');item=grant_items(db,rules.plan(rules.POINT_ITEM,1),1001)[0]
        flow=Flow(None,clock=lambda:NOW)
        s=LocalSession(self.account,client_build='dx11_260923',item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_dungeon=True,activity2026_awards=flow)
        s.role='game';s.phase='town_ready'
        payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
        from els_server.domain.session_dispatch import feature_handlers
        out=feature_handlers(s,request(0x219,payload),55)
        self.assertEqual(out[0].kind,0x21a);self.assertEqual(out[0].payload[:4],bytes(4))
        again=feature_handlers(s,request(0x219,payload),55)
        self.assertEqual(again[0].payload[:4],bytes(4))
        with self.db()as db:self.assertEqual(Campaign(db).snapshot(1)['points'],10)
        self.assertNotIn(item['uid'],{i['uid']for i in self.items()})
    def test_original_f4_claim_and_cold_2b_restore_include_all_campaign_tasks(self):
        self.join()
        with self.db()as db,db:
            db.execute('BEGIN IMMEDIATE');t=Campaign(db)
            for _ in range(5):
                run=str(uuid.uuid4());t.admit(1,1001,run,34130,False,NOW);self.receipt(db,run,34130)
        flow=Flow(None,clock=lambda:NOW)
        s=LocalSession(self.account,client_build='dx11_260923',item_test=True,reward_test=True,clear_test=True,population_test=True,gate_test=True,npc_slot_test=True,enter_dungeon=True)
        s.role='game';s.phase='town_ready'
        payload=struct.pack('>iiI',169590,0,0)+bytes((0,0,1,1,0))
        out=flow.handle(s,request(0xf4,payload),2)
        self.assertEqual(next(e.payload[:4]for e in out if e.kind==0xf5),bytes(4))
        with self.db()as db:self.assertEqual(Campaign(db).snapshot(1)['points'],150)
        flow.handle(s,request(0xf4,payload),3)
        with self.db()as db:self.assertEqual(Campaign(db).snapshot(1)['points'],150)
        from els_server.protocol.quest_messages import initialization
        from els_server.protocol.boosting_2026_restore import split
        base=initialization(dict(active=[],completed=[]))
        restored=Flow(None,clock=lambda:NOW).finalize(s,[base])
        active,done,tail=split(next(e.payload for e in restored if e.kind==0x2b))
        self.assertEqual(len(active),7);self.assertEqual([q for q,r in done],[169590])

if __name__=='__main__':unittest.main(verbosity=2)
