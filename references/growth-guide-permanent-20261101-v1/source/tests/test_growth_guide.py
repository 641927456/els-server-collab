"""Permanent original guide: real finite rewards and persisted trusted facts."""
from contextlib import closing
import json,sqlite3,struct,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from els_server.domain.growth_guide import catalog,ordinary_active_count
from els_server.domain.growth_guide_flow import handle,synchronize
from els_server.protocol.protocol_codec import Event
from els_server.protocol import activity_2026_entries as entries

class GrowthGuideTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'save.db';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        self.state=QuestState(self.path,account_id=1);self.state.snapshot()
        self.session=LocalSession(self.account,enter_town=True,client_build='dx11_260923')
        self.session.item_test=True
        self.session.role='game';self.session.phase='town_ready'
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=1001')
        self.seq=0

    def open(self):
        self.seq+=1
        return handle(self.session,Event(0x202,performers=(0,),kind=0xd0d,payload=b''),self.seq)

    def row(self,identity):return next(r for r in self.state.snapshot()['active'] if r['id']==identity)

    def claim(self,identity,operation,encode=lambda r:[]):
        request=dict(quest=identity,npc=0,flags=(0,0,1,1,0))
        return self.state.action('claim',request,operation,encode)

    def test_native_entry_and_current_ids_keep_all_other_code_entries(self):
        self.assertEqual(len(catalog()['quests']),61)
        self.assertIn('169300',catalog()['quests']);self.assertNotIn('167850',catalog()['quests'])
        original=entries.notice({518:entries.CodeEntry(True,10,20),678:entries.CodeEntry(False,30,40)})
        reply=synchronize(self.session,[original],force=True)
        rows=entries.read(next(e for e in reply if e.kind==0x4b9).payload)
        self.assertEqual(set(rows),{518,623,678});self.assertEqual(rows[623],entries.CodeEntry(True,0,0))
        self.assertEqual(next(e for e in reply if e.kind==0xcaa).payload,bytes(8)+b'\1')

    def test_normal_session_cold_finalizer_activates_the_guide(self):
        from els_server.application import Application
        from els_server.config import ServerConfig
        app=Application(ServerConfig(mode='local',profile='bootstrap',state_file=self.path));self.addCleanup(app.close);app.account=self.account
        self.session._chip_reset_local_application=app;self.session._chip_reset_local_live=True
        with patch.object(self.session,'_handle',return_value=[Event(0x201,kind=0x2a,payload=b'')]):
            reply=self.session.handle(Event(0x202,performers=(0,),kind=0x28,payload=b''),1)
        self.assertTrue(any(e.kind==0xcaa for e in reply))
        self.assertTrue(any(e.kind==0x4b9 and entries.read(e.payload)[623].enabled for e in reply))
        self.assertTrue(any(r['id']==169300 for r in self.state.snapshot()['active']))

    def test_level_reward_commits_once_and_reopens_without_calendar(self):
        self.open();self.assertEqual(self.row(169300)['objectives'],{151280:1})
        first=self.claim(169300,'claim-first')
        self.assertEqual([(r['template'],r['count']) for r in first['updates']],[(723048,1)])
        self.assertFalse(first['replayed']);second=self.claim(169300,'claim-second');self.assertTrue(second['replayed'])
        self.assertEqual(sum(i['count'] for i in self.account.get_inventory_snapshot()['items'] if i['template']==723048),1)
        self.open();self.assertIn(169300,QuestState(self.path,account_id=1).completed())
        self.assertNotIn(169300,[r['id'] for r in self.state.snapshot()['active']])

    def test_rejected_qualification_and_encode_failure_have_no_reward(self):
        self.open()
        with self.assertRaises(ValueError):self.claim(167810,'before-first-job')
        with self.assertRaisesRegex(ValueError,'encode failed'):
            self.claim(169300,'encoding-failure',lambda r:(_ for _ in ()).throw(ValueError('encode failed')))
        self.assertNotIn(169300,self.state.completed())
        self.assertFalse(any(i['template']==723048 for i in self.account.get_inventory_snapshot()['items']))

    def test_course_prerequisites_and_career_state_are_authoritative(self):
        self.open();self.assertFalse(any(r['id']==168660 for r in self.state.snapshot()['active']))
        self.assertEqual(self.row(167810)['objectives'],{47322:0})
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=10 WHERE uid=1001')
            db.execute("INSERT INTO completed_quests VALUES(1001,27540,1,'{}')")
        self.open();self.assertEqual(self.row(167810)['objectives'],{47322:1})
        self.assertEqual(self.row(168660)['objectives'],{168351:0})

    def test_real_clear_replay_and_five_clear_requirement(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute("INSERT INTO completed_quests VALUES(1001,27540,1,'{}')")
        self.open()
        for n in range(5):
            event=dict(kind='clear',dungeon=34840,level=99)
            self.state.record('clear-'+str(n),event,b'proof')
            self.state.record('clear-'+str(n),event,b'proof')
        self.assertEqual(self.row(168660)['objectives'],{168351:5})
        reward=self.claim(168660,'deep-claim')
        self.assertEqual([r['template'] for r in reward['updates']],[723028])

    def test_shared_inventory_fact_rolls_back_with_business(self):
        from els_server.storage.growth_guide import inventory_fact
        self.open();self.assertEqual(self.row(169290)['objectives'],{164902:0})
        with self.assertRaises(ValueError):
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('BEGIN IMMEDIATE');inventory_fact(db,1001,0x1c4,[],[])
                raise ValueError('business failed')
        self.assertEqual(self.row(169290)['objectives'],{164902:0})
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');inventory_fact(db,1001,0x1c4,[],[])
        self.assertEqual(self.row(169290)['objectives'],{164902:1})

    def test_guide_does_not_consume_ordinary_fifty_task_capacity(self):
        rows=[dict(id=int(q)) for q in catalog()['quests']]
        self.assertEqual(ordinary_active_count(rows),0)
        self.assertEqual(ordinary_active_count(rows+[dict(id=6980)]),1)

    def give(self,template,count=1):
        from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
        from els_server.storage.inventory_state import grant_items
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            return grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=count)],1001)[0]

    def box(self,item,operation,choices=(),now=1800000000):
        from els_server.storage.growth_guide_boxes import open_box
        payload=struct.pack('>QBBBI',item['uid'],0,0,0,len(choices))+b''.join(struct.pack('>i',t) for t in choices)+bytes(4)
        return open_box(self.path,1001,item['template'],payload,operation,now=now)

    def test_box_choice_expiration_and_retry_keep_the_original_deadline(self):
        box=self.give(720014)
        with self.assertRaises(ValueError):self.box(box,'forged-choice',(720000,))
        self.box(box,'rings')
        rings=[i for i in self.account.get_inventory_snapshot()['items'] if 720000<=i['template']<=720003]
        self.assertEqual(len(rings),4)
        self.assertEqual({i['expires_at'] for i in rings},{1800000000+14*86400})
        self.box(box,'rings',now=1800100000)
        self.assertEqual([i for i in self.account.get_inventory_snapshot()['items'] if 720000<=i['template']<=720003],rings)

    def test_fixed_factory_reforge_and_artifact_lines(self):
        box=self.give(721759);self.box(box,'rigomor')
        gear=[i for i in self.account.get_inventory_snapshot()['items'] if 716717<=i['template']<=716720]
        self.assertEqual(len(gear),4)
        self.assertTrue(all(i['enhancement']==10 and i['reforge']==[21,100,0] for i in gear))
        box=self.give(721766);self.box(box,'artifact')
        gear=[i for i in self.account.get_inventory_snapshot()['items'] if 168600<=i['template']<=168603]
        self.assertEqual(len(gear),5)
        self.assertTrue(all(i['identified'] and len(i['option_groups']['1'])==2 for i in gear))

    def test_all_current_roles_and_luciel_sides_have_complete_native_sets(self):
        from els_server.domain.growth_guide_boxes import outputs_for
        from els_server.domain.character_rules import CLASSES
        from els_server.game_data import client_data
        roles={client_data().unit(k)['unitType']:k for k,r in CLASSES.items() if r['stage']==2}
        for family,cls in roles.items():
            for active in ((0,1) if family==10 else (0,)):
                c=dict(unit_type=family,unit_class=cls,luciel_active_unit=active)
                for t,n in ((168913,17),(723049,8),(716739,1),(721771,5),(723028,1),(723046,1)):
                    with self.subTest(role=family,active=active,box=t):self.assertEqual(len(outputs_for(t,c)),n)

    def test_box_encoding_failure_rolls_back_consumption_and_factory(self):
        box=self.give(721747)
        before=self.account.get_inventory_snapshot()['items']
        with patch('els_server.storage.growth_guide_boxes.encode_event',side_effect=ValueError('encode')):
            with self.assertRaises(ValueError):self.box(box,'box-encode')
        self.assertEqual(self.account.get_inventory_snapshot()['items'],before)
        self.box(box,'box-encode')
        self.assertEqual(sum(i['count'] for i in self.account.get_inventory_snapshot()['items'] if i['template']==710250),80)

    def test_native_reactor_installation_debits_once_and_advances_only_tuning(self):
        from els_server.storage.equipment_tuning import perform
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=100 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET ed=1000000 WHERE uid=1001')
            db.execute("INSERT INTO completed_quests VALUES(1001,27550,1,'{}')")
        self.open();box=self.give(721771);self.box(box,'tenebros');box=self.give(722236);self.box(box,'reactors')
        items=self.account.get_inventory_snapshot()['items'];armor=next(i for i in items if i['template']==720598);reactor=next(i for i in items if i['template']==720753)
        payload=struct.pack('>QIiIiQBiB',armor['uid'],1,26,1,0,reactor['uid'],0,14,0)
        perform(self.path,1001,1,payload,'install-reactor',now=1800000000)
        perform(self.path,1001,1,payload,'install-reactor',now=1800000001)
        items=self.account.get_inventory_snapshot()['items'];armor=next(i for i in items if i['template']==720598)
        self.assertEqual(armor['option_groups']['26'],[100813531]);self.assertFalse(any(i['uid']==reactor['uid'] for i in items))
        self.assertEqual(self.account.get_reward_balances()['ed'],800000)
        self.assertEqual(self.row(168580)['objectives'],{168580:1})

    def test_henir_progress_keeps_the_highest_run_stage(self):
        with closing(sqlite3.connect(self.path)) as db,db:db.executemany("INSERT INTO completed_quests VALUES(1001,?,1,'{}')",[(26640,),(26650,)])
        self.open()
        for n in range(4):self.state.record('henir-one-'+str(n),dict(kind='stage_clear',dungeon=38100,level=99,henir_mode=1,henir_stage=1),b'accepted-stage')
        self.assertEqual(next(iter(self.row(168010)['objectives'].values())),1)
        self.state.record('henir-five',dict(kind='stage_clear',dungeon=38100,level=99,henir_mode=1,henir_stage=5),b'accepted-stage')
        self.assertEqual(next(iter(self.row(168010)['objectives'].values())),5)

    def test_full_consumable_bag_rolls_back_the_whole_box(self):
        from els_server.storage.inventory_state import InventoryFull
        box=self.give(721747)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('DELETE FROM inventory_items WHERE owner=1001 AND bag_group=6')
            db.executemany('INSERT INTO inventory_items VALUES(?,1001,77000,2,1,6,?)',[(1000000000+n,n) for n in range(36)])
        before=self.account.get_inventory_snapshot()['items']
        with self.assertRaises(InventoryFull):self.box(box,'bag-full')
        self.assertEqual(self.account.get_inventory_snapshot()['items'],before)

    def test_adaptation_reads_actual_equipment_and_expiration(self):
        from els_server.storage.growth_guide_stats import adaptation
        from els_server.storage.inventory_state import load_items
        from els_server.storage.seal_quests import load_character
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET unit_class=100 WHERE uid=1001')
        weapon=self.give(713199)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),0)
            db.execute('UPDATE inventory_items SET bag_group=9,slot=9 WHERE uid=?',(weapon['uid'],))
            self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),5)
            assign(db,1001,weapon['uid'],1600000000)
            self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),0)

    def test_camp_requires_continuous_six_minutes_and_restores_the_same_buff(self):
        from els_server.domain.town_rest_buffs import synchronize as camp
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute("INSERT INTO completed_quests VALUES(1001,26640,1,'{}')")
        self.account.save_location(1009,0,0,(0.,0.,0.))
        self.session.active_map=self.session.pending_map=1009;self.session.completed.update((0x225,0x227))
        self.open()
        self.assertEqual(camp(self.session,[],clock=lambda:10,wall=lambda:1800000000),[])
        self.assertEqual(camp(self.session,[],clock=lambda:369,wall=lambda:1800000359),[])
        out=camp(self.session,[],clock=lambda:370,wall=lambda:1800000360)
        self.assertEqual(out[0].kind,0x3a2);self.assertEqual(next(iter(self.row(167980)['objectives'].values())),1)
        first=out[0].payload
        self.session._town_rest_sent=None
        out=camp(self.session,[Event(0x201,kind=0x2a,payload=b'')],clock=lambda:371,wall=lambda:1800000361)
        self.assertEqual(out[-1].payload,first)

    def test_owned_capacity_voucher_works_without_campaign_and_replays_once(self):
        from els_server.storage.boosting_2026_nested_capacity import use_ticket
        from els_server.storage.bag_capacity import allowances
        box=self.give(710138);self.box(box,'capacity-box')
        ticket=next(i for i in self.account.get_inventory_snapshot()['items'] if i['template']==190589)
        with closing(sqlite3.connect(self.path)) as db:before=allowances(db,1001)[1]
        payload=struct.pack('>QQiiIB',ticket['uid'],0,0,0,0,0)
        self.assertFalse(use_ticket(self.path,1001,payload,'capacity-use')['replayed'])
        self.assertTrue(use_ticket(self.path,1001,payload,'capacity-use')['replayed'])
        with closing(sqlite3.connect(self.path)) as db:self.assertEqual(allowances(db,1001)[1],before+8)

    def test_fourteen_day_mount_activation_retry_expiry_and_rollback(self):
        from els_server.storage.companion_state import handle as activate,snapshot
        from els_server.storage.mount_state import handle as ride,tick
        box=self.give(713146);self.box(box,'mount-choice',(713152,))
        token=next(i for i in self.account.get_inventory_snapshot()['items'] if i['template']==713152)
        payload=struct.pack('>Q',token['uid']);start=1800000000;end=start+14*86400
        with patch('els_server.storage.mount_state.time.time',return_value=start):
            with patch('els_server.protocol.companion_messages.activation_ack',side_effect=ValueError('encode')):
                with self.assertRaises(ValueError):activate(self.path,1001,0x432,payload,'mount-activate')
            self.assertTrue(any(i['uid']==token['uid'] for i in self.account.get_inventory_snapshot()['items']))
            activate(self.path,1001,0x432,payload,'mount-activate')
            activate(self.path,1001,0x432,payload,'mount-activate')
            mounts=[p for p in snapshot(self.path,1001)['companions'] if p['kind']=='mount']
        self.assertEqual(len(mounts),1);self.assertEqual(mounts[0]['expires_at'],end);uid=mounts[0]['uid']
        ride(self.path,1001,0x42c,struct.pack('>QB',uid,1),'ride',now=end-1)
        self.assertEqual([e.kind for e in tick(self.path,1001,now=end)],[0x430])
        with self.assertRaisesRegex(ValueError,'expired'):ride(self.path,1001,0x42c,struct.pack('>QB',uid,1),'expired-ride',now=end)
        with patch('els_server.storage.mount_state.time.time',return_value=end):
            self.assertEqual(snapshot(self.path,1001)['companions'],[])
            self.assertNotEqual(activate(self.path,1001,0x432,payload,'mount-activate').payload[:4],bytes(4))

    def test_ariel_engraving_uses_the_same_verified_component_pool(self):
        from els_server.storage.equipment_engrave import perform
        from els_server.protocol.equipment_engrave_messages import body
        from els_server.domain.equipment_engrave_rules import canonical_material
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET unit_class=100 WHERE uid=1001')
            db.execute('UPDATE reward_balances SET ed=10000000 WHERE uid=1001')
        weapon=self.give(713199);stone=self.give(718259,2)
        self.assertEqual(canonical_material(stone['template']),136042)
        payload=body(weapon['uid'],0,0,stone['uid'],5)
        perform(self.path,1001,payload,'engrave-paid',account_id=1,now=1800000000,randbelow=lambda n:0)
        perform(self.path,1001,payload,'engrave-paid',account_id=1,now=1800000001,randbelow=lambda n:(_ for _ in ()).throw(ValueError('re-roll')))
        perform(self.path,1001,body(weapon['uid'],0,0,stone['uid'],6),'engrave-confirm',account_id=1,now=1800000001)
        saved=self.account.get_inventory_snapshot()['items']
        self.assertEqual(next(i for i in saved if i['uid']==stone['uid'])['count'],1)
        self.assertTrue(next(i for i in saved if i['uid']==weapon['uid'])['option_groups']['14'][0])
        self.assertEqual(self.account.get_reward_balances()['ed'],8400000)

    def test_artifact_medal_requires_held_unexpired_ownership(self):
        from els_server.storage.local_clear_rules import commit
        from els_server.domain.local_artifact_rules import rating
        medal=self.give(721765)
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET unit_class=79,level=99,transcendence=1,master=1 WHERE uid=1001')
            db.execute("INSERT OR REPLACE INTO character_artifacts VALUES (1001,1,1,1,0,'[0,0,0,0]')")
            assign(db,1001,medal['uid'],1800000100)
            assessment=rating(34840,60,1,10,1)
            doubled=commit(db,1001,'medal-held',assessment,100,now=1800000000)
            normal=commit(db,1001,'medal-expired',assessment,100,now=1800000101)
            self.assertTrue(doubled['eligible']);self.assertEqual(doubled['total'],2*normal['total'])

    def test_guide_recovery_and_fighting_spirit_use_native_effect_once(self):
        from els_server.storage.consumables import use
        from els_server.storage.quick_slots import save_request,encode,empty
        from els_server.domain.quick_bindings import item_binding
        from els_server.domain.consumables import ordinary
        for n,template in enumerate((710250,710006,713170,710031,710035,710010,190624)):
            with self.subTest(template=template):
                with closing(sqlite3.connect(self.path)) as db,db:db.execute('DELETE FROM inventory_items WHERE owner=1001 AND bag_group=6')
                item=self.give(template,2)
                save_request(self.path,struct.pack('>i',1)+encode({**empty(),0:item_binding(template)}))
                payload=struct.pack('>HBBB',0,0,0,0);op='guide-potion-'+str(template)
                reply=use(self.path,1001,payload,op,account_id=1,allow_apples=True,now=1800000000+n*100)
                self.assertEqual([e.kind for e in reply],[0x114,0x115])
                self.assertEqual(reply[1].payload,struct.pack('>Qi?Q?',1001,template,False,0,False))
                self.assertEqual(len(use(self.path,1001,payload,op,account_id=1,allow_apples=True,now=1800000001+n*100)),1)
                self.assertEqual(next(i for i in self.account.get_inventory_snapshot()['items'] if i['uid']==item['uid'])['count'],1)
                with self.assertRaises(ValueError):use(self.path,1001,payload,op+'-early',account_id=1,allow_apples=True,now=1800000001+n*100)
                self.assertEqual(ordinary(template)['cooldown_seconds'],30)

    def test_guide_ariel_elixir_has_the_same_saved_world_effect_and_deadline(self):
        from els_server.storage.world_elixirs import use,snapshot
        from els_server.protocol.world_buff_messages import snapshot as world
        item=self.give(710153,2);payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
        prepare=lambda db,state,items:[world(1001,state['rows'])]
        first=use(self.path,1001,1,payload,'guide-elixir',prepare,now=1800000000)
        retry=use(self.path,1001,1,payload,'guide-elixir',prepare,now=1800000100)
        self.assertFalse(first['replayed']);self.assertTrue(retry['replayed'])
        self.assertEqual(first['state']['rows'],retry['state']['rows'])
        self.assertEqual(snapshot(self.path,1001,1,now=1800000100)['rows'][0]['end'],1800001800)
        self.assertEqual(next(i for i in self.account.get_inventory_snapshot()['items'] if i['uid']==item['uid'])['count'],1)

    def test_adaptation_includes_native_collection_and_enhancement_unlocks(self):
        from els_server.storage.growth_guide_stats import adaptation
        from els_server.storage.seal_quests import load_character
        from els_server.storage.inventory_state import load_items
        from els_server.storage.el_search_collection import activate
        from els_server.storage.ep_points import credit
        from els_server.storage.equipment_enhancement import replace
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE characters SET unit_class=100 WHERE uid=1001')
        armor=self.give(720598)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE inventory_items SET bag_group=9,slot=1 WHERE uid=?',(armor['uid'],))
            self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),2)
            replace(db,1001,armor['uid'],0,11)
            self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),3)
            db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=?',(armor['group'],armor['slot'],armor['uid']))
            db.execute('UPDATE characters SET unit_type=10,unit_class=88,transcendence=1,master=1 WHERE uid=1001')
            db.execute("INSERT OR REPLACE INTO character_artifacts VALUES (1001,10,1,1,0,'[0,0,0,0]')")
            credit(db,1001,500);character=load_character(db,1001)
            activate(db,1001,1,character,1800000000)
            self.assertEqual(adaptation(db,1001,load_character(db,1001),load_items(db,1001)),1)

    def test_foreign_owner_and_invalid_native_requests_fail(self):
        with self.assertRaises(ValueError):QuestState(self.path,account_id=2).snapshot()
        reply=handle(self.session,Event(0x202,performers=(0,),kind=0xd0d,payload=b'x'),1)
        self.assertNotEqual(reply[0].payload[:4],bytes(4))
        reply=handle(self.session,Event(0x202,performers=(0,),kind=0xcad,payload=b''),2)
        self.assertNotEqual(reply[0].payload[:4],bytes(4))

if __name__=='__main__':unittest.main()
