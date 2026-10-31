"""Shared item tasks: collections, mixed objectives and native raid settlement."""
import json
import sqlite3
import struct
import unittest
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_weapon_growth as fixture
from els_server.domain import weapon_growth as rules,weapon_growth_flow as flow
from els_server.protocol import weapon_growth_messages as wire
from els_server.protocol.protocol_codec import Event
from els_server.storage import weapon_growth as store
from els_server.game_data import client_data


class WeaponGrowthFamilyTests(unittest.TestCase):
    setUp=fixture.WeaponGrowthTests.setUp
    items=fixture.WeaponGrowthTests.items
    snapshot=fixture.WeaponGrowthTests.snapshot
    dump=fixture.WeaponGrowthTests.dump
    receipt=fixture.WeaponGrowthTests.receipt
    claim=fixture.WeaponGrowthTests.claim

    def weapon(self,template,stage=0):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE inventory_items SET template=?,metadata=? WHERE uid=?',
                       (template,client_data().item(template)['metadata'],self.item_uid))
            if stage:
                from els_server.storage.equipment_options import replace
                replace(db,1001,self.item_uid,{}, {'17':rules.quest(stage-1,template)['options']})

    def material(self,template,count,slot=0,uid=1003000):
        from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
                       (uid,1001,template,client_data().item(template)['metadata'],count,TEMPLATE_BAG_GROUPS[template],slot))

    def clear(self,dungeon,no_deaths=False):
        run,proof=self.receipt(dungeon)
        return store.record_clear(self.path,1001,1,self.item_uid,run,dungeon,proof,no_deaths=no_deaths)

    def test_all_families_initialize_and_admit_only_actual_native_quests(self):
        for template,qid in [(136062,1),(136120,6),(136182,11)]:
            self.weapon(template)
            self.assertEqual(self.snapshot()['item_active'][0]['id'],qid)
            self.assertEqual(wire.request(struct.pack('>iQB',qid,self.item_uid,0))[0],qid)
        for qid in (0,17,99):
            with self.assertRaises(ValueError):wire.request(struct.pack('>iQB',qid,self.item_uid,1))

    def test_complete_abyss_and_mortal_chains_have_family_specific_rewards(self):
        for template in (136120,136182):
            self.weapon(template)
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('DELETE FROM weapon_growth_progress') if store._exists(db,'weapon_growth_progress') else None
                db.execute('DELETE FROM equipment_options WHERE item_uid=?',(self.item_uid,)) if store._exists(db,'equipment_options') else None
            for stage,q in enumerate(rules.chain(template)['quests'],1):
                for g in q['objectives']:
                    if g['kind']=='collect':
                        self.material(g['template'],g['target'])
                    else:
                        for _ in range(g['target']):self.clear(g['dungeons'][0],no_deaths=g['kind']=='no_deaths')
                result=self.claim(q['id'],'family-'+str(q['id']))
                self.assertEqual(result['updated']['option_groups']['17'],q['options'])
                self.assertEqual(len(self.snapshot()['item_completed']),stage)
                self.assertEqual(rules.stage(next(i for i in self.items() if i['uid']==self.item_uid)),stage)
                self.assertFalse(any(i['template'] in (136113,136114,136181) for i in self.items()))
            self.assertEqual(self.snapshot()['item_active'],[])

    def test_collection_uses_current_owned_unlocked_unexpired_counts(self):
        self.weapon(136120,3);self.material(136113,5);self.material(136113,6,1,1003001)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{9:9})
        from els_server.storage.item_locks import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,1003001,2**62)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{9:5})
        before=self.dump()
        with self.assertRaises(ValueError):self.claim(9)
        self.assertEqual(self.dump(),before)
        from els_server.storage.item_expiration import assign as expire
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');expire(db,1001,1003000,100000000)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{9:0})

    def test_mixed_objectives_require_clear_and_materials(self):
        self.weapon(136182,3);self.material(136181,120)
        with self.assertRaises(ValueError):self.claim(14)
        for _ in range(20):self.clear(35560)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{14:20,18:120})
        with closing(sqlite3.connect(self.path)) as db,db:db.execute('UPDATE inventory_items SET count=119 WHERE uid=1003000')
        before=self.dump()
        with self.assertRaises(ValueError):self.claim(14)
        self.assertEqual(self.dump(),before)

    def test_material_consumption_and_reward_rollback_on_encoding_failure(self):
        self.weapon(136120,3);self.material(136113,4);self.material(136113,7,1,1003001)
        before=self.dump()
        def fail(result):raise ValueError('encoder stopped')
        with self.assertRaisesRegex(ValueError,'encoder stopped'):self.claim(9,encode=fail)
        self.assertEqual(self.dump(),before)
        result=self.claim(9)
        self.assertEqual([i['count'] for i in self.items() if i['template']==136113],[2])
        self.assertEqual(result['consumed'][0],((5,0),None))
        self.assertEqual(result['consumed'][1][1]['count'],2)

    def test_collection_replay_emits_current_reused_slot_without_consuming_again(self):
        self.weapon(136120,3);self.material(136113,9)
        self.claim(9)
        self.material(136114,4,uid=1003001)
        before=self.dump();replay=self.claim(9)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['consumed'][0][1]['template'],136114)
        self.assertEqual(self.dump(),before)

    def test_no_death_maps_are_independent_and_missing_evidence_cannot_qualify(self):
        self.weapon(136182,5)
        self.assertFalse(self.clear(35560)['changed'])
        self.clear(35560,True);self.clear(35560,True)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{20:2,16:0})
        before=self.dump()
        with self.assertRaises(ValueError):self.claim(16)
        self.assertEqual(self.dump(),before)
        self.clear(35590,True);self.clear(35590,True)
        self.claim(16)
        self.assertEqual([r['id'] for r in self.snapshot()['item_completed']],list(range(11,17)))

    def test_v1_scalar_progress_is_read_without_write_and_migrates_once(self):
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('CREATE TABLE weapon_growth_progress(item_uid INTEGER PRIMARY KEY,stage INTEGER NOT NULL,count INTEGER NOT NULL,completed_json TEXT NOT NULL)')
            db.execute('INSERT INTO weapon_growth_progress VALUES (?,0,1,?)',(self.item_uid,'[]'))
        before=self.dump();self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{1:1})
        self.assertEqual(self.dump(),before)
        self.claim()
        with closing(sqlite3.connect(self.path)) as db,db:
            store.ensure(db);store.ensure(db)
            self.assertEqual(len([r for r in db.execute('PRAGMA table_info(weapon_growth_progress)') if r[1]=='objectives_json']),1)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{2:0})

    def test_family_rewards_cannot_be_applied_to_another_family(self):
        with self.assertRaises(ValueError):rules.options(136062,rules.quest(0,136120)['options'])
        with self.assertRaises(ValueError):rules.options(136120,rules.quest(5,136182)['options'])

    def member(self,epoch):
        return SimpleNamespace(account=self.account,dungeon_run=SimpleNamespace(run_id=epoch,identity=35560,graph={'source_sha256':'graph'}),
            _weapon_growth_run=dict(identity=(str(self.path),1001,epoch),item_uid=self.item_uid,eligible=True,recorded=False,from_start=True))

    def test_party_death_witness_survives_native_revival_and_unobserved_roster_fails(self):
        a=self.member('run');b=self.member('run')
        self.assertTrue(flow._no_deaths((a,b),'run'))
        b._raid_life_witness=dict(epoch='run',number=1,phase='alive')
        self.assertFalse(flow._no_deaths((a,b),'run'))
        del b._raid_life_witness;b._weapon_growth_run['from_start']=False
        self.assertFalse(flow._no_deaths((a,b),'run'))

    def test_actual_raid_clear_observer_uses_existing_writer_and_owner_receipt(self):
        self.weapon(136182,5)
        receipt,proof=self.receipt(35560);epoch='room-epoch-differs-from-owner-receipt'
        s=self.member(epoch);s._quest_run_levels={};s.account.account_id=1
        shadow=SimpleNamespace(clear_notified=True,reward_receipt=dict(run_id=receipt,local_rules=None))
        events=[]
        from els_server.domain.raid_economy_flow import _clear_observers
        from els_server.storage.seal_quests import load_character
        quest=SimpleNamespace(record=lambda *a,**kw:[])
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');before=load_character(db,1001,1)
            with patch('els_server.domain.quest_flow.store',return_value=quest):
                _clear_observers(db,s,shadow,before,events,lambda writer:None,(s,))
            self.assertTrue(db.in_transaction)
            self.assertEqual([e.kind for e in events],[0x96b])
            db.rollback()
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{20:0,16:0})
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            flow.settled(s,shadow,db,(s,),lambda writer:None)
        self.assertEqual(self.snapshot()['item_active'][0]['objectives'],{20:1,16:0})

    def test_live_material_refresh_reuses_collection_snapshot_and_idle_does_not_request_it(self):
        from els_server.storage.seal_quests import QuestState
        self.weapon(136120,3)
        s=SimpleNamespace(account=self.account)
        rows,state=QuestState(self.path,1001,account_id=1).collection_snapshot(include_growth=True)
        self.assertEqual(flow.collection_notices(s,state),[])
        self.assertFalse(flow.collection_requested(s,[Event(0x201,kind=0xbd)]))
        self.material(136113,9)
        rows,state=QuestState(self.path,1001,account_id=1).collection_snapshot(include_growth=True)
        self.assertEqual([e.kind for e in flow.collection_notices(s,state)],[0x96b])
        self.assertEqual(state['item_active'][0]['objectives'],{9:9})

    def test_snapshot_counts_have_each_native_objectives_own_limit(self):
        self.weapon(136182,3);self.material(136181,120)
        row=self.snapshot()['item_active'][0];data=wire.active_record(row)
        self.assertEqual(len(data),32+2*7)
        self.assertEqual(struct.unpack_from('>iHB',data,32),(14,0,0))
        self.assertEqual(struct.unpack_from('>iHB',data,39),(18,120,1))

    def test_material_readers_do_not_open_unqualified_factories(self):
        from els_server.storage.inventory_state import validate_plan
        for template in (136113,136114):
            with self.assertRaises(ValueError):validate_plan([dict(template=template,count=1)])
