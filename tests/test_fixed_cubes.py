"""Fixed rewards, unknown boxes, transactional retries and inventory failures."""
import sqlite3,struct
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from tests import test_npc_sale as fixture
from els_server.domain.fixed_cubes import catalog
from els_server.domain.local_session import LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.fixed_cubes import open_cube


def payload(uid,choices=(),option=0):
    return struct.pack('>QBBBI',uid,0,0,0,len(choices))+b''.join(struct.pack('>i',i) for i in choices)+struct.pack('>i',option)


class CubeTests(fixture.SaleTests):
    def use(self,item,operation='open'):
        return open_cube(self.path,1001,item['template'],payload(item['uid']),operation)

    def test_native_catalog_is_unambiguous_and_excludes_conflicting_historical_text(self):
        self.assertEqual(len(catalog()),49)
        self.assertEqual((catalog()[130172]['reward'],catalog()[130172]['quantity']),(130047,20))
        # Native title says 10 but text says 20 and carries an old deletion date.
        self.assertNotIn(131582,catalog())
        # Several distinct item IDs share the untagged full-potion name.
        self.assertNotIn(135665,catalog())

    def test_open_shard_cube_does_not_charge_or_change_money(self):
        item=self.grant(130172);money=self.money();events=self.use(item)
        self.assertEqual([e.kind for e in events],[0xad8,0x197]);self.assertEqual(self.money(),money)
        self.assertNotIn(item['uid'],{i['uid'] for i in self.items()})
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==130047),20)
        self.assertEqual(struct.unpack_from('>ii',events[-1].payload,16),(130047,20))

    def test_partial_cube_stack_consumes_one_and_keeps_original_uid(self):
        item=self.grant(130172,3);self.use(item)
        self.assertEqual(next(i['count'] for i in self.items() if i['uid']==item['uid']),2)
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==130047),20)

    def test_large_native_quantity_splits_into_real_stack_limits(self):
        item=self.grant(980050);events=self.use(item)
        stacks=[i for i in self.items() if i['template']==78360]
        self.assertEqual(sum(i['count'] for i in stacks),300)
        self.assertTrue(all(1<=i['count']<=99 for i in stacks))
        self.assertEqual(len(stacks),4);self.assertEqual(struct.unpack_from('>I',events[0].payload)[0],5)

    def test_bag_full_rolls_back_cube_revision_reward_and_uid_allocation(self):
        item=self.grant(130172,2);before=self.dump()
        with patch('els_server.storage.bag_capacity.allowances',return_value={g:1 for g in (1,2,3,4,5,6,7,21,27,11)}):
            with self.assertRaises(ValueError):self.use(item)
        self.assertEqual(self.dump(),before)

    def test_retry_has_no_second_reward_popup_and_uses_current_slot(self):
        item=self.grant(130172);self.use(item);replacement=self.grant(130173)
        before=self.dump();events=self.use(item)
        self.assertTrue(all(e.kind!=0xad8 for e in events))
        self.assertEqual(struct.unpack_from('>I',events[-1].payload,12)[0],0)
        self.assertEqual(self.dump(),before)
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==130047),20)
        self.assertIn(replacement['uid'],{i['uid'] for i in self.items()})

    def test_wrong_owner_preview_template_unknown_cube_and_choices_preserve_save(self):
        item=self.grant(130172)
        for owner,t,p in ((self.other,130172,payload(item['uid'])),(1001,130173,payload(item['uid'])),
                (1001,131582,payload(item['uid'])),(1001,130172,payload(item['uid'],(130048,))),
                (1001,130172,payload(item['uid'],option=99))):
            before=self.dump()
            with self.assertRaises(ValueError):open_cube(self.path,owner,t,p,'bad')
            self.assertEqual(self.dump(),before)

    def test_expired_cube_and_encoder_failure_are_atomic(self):
        item=self.grant(130172);before=self.dump()
        with patch('els_server.storage.fixed_cubes.result',side_effect=ValueError('wire')):
            with self.assertRaises(ValueError):self.use(item)
        self.assertEqual(self.dump(),before)
        from els_server.storage.item_expiration import assign
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,1001,item['uid'],1000000000)
        before=self.dump()
        with self.assertRaises(ValueError):self.use(item)
        self.assertEqual(self.dump(),before)

    def test_duplicate_concurrent_use_commits_one_outcome(self):
        item=self.grant(130172)
        with ThreadPoolExecutor(2) as pool:list(pool.map(lambda _:self.use(item),range(2)))
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==130047),20)
        with self.assertRaises(ValueError):self.use(item,'new-transaction')

    def test_fixed_preview_and_use_are_independent_of_ice_feature(self):
        item=self.grant(130172)
        args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s=LocalSession(self.account,**args);s.role='game';s.phase='town_ready'
        use=Event(0x202,kind=0x196,payload=payload(item['uid']))
        preview=Event(0x202,kind=0x559,payload=struct.pack('>iIiBB',130172,1,0,0,0))
        self.assertEqual(s.handle(preview,2)[0].kind,0x55a)
        events=s.handle(use,3);self.assertEqual([e.kind for e in events],[0xad8,0x197])
        unknown=Event(0x202,kind=0x559,payload=struct.pack('>iIiBB',131582,1,0,0,0))
        self.assertEqual(struct.unpack_from('>i',s.handle(unknown,4)[0].payload)[0],-1)
        self.assertIsNone(s.fixed_cube_preview_template);self.assertFalse(s.ice_preview_ready)

    def test_direct_native_use_and_retry_without_a_preview(self):
        item=self.grant(130172)
        args=dict(enter_town=True,enter_dungeon=True,client_build='dx11_260923',npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,reward_test=True,item_test=True)
        s=LocalSession(self.account,**args);s.role='game';s.phase='town_ready'
        event=Event(0x202,kind=0x196,payload=payload(item['uid']))
        self.assertEqual([e.kind for e in s.handle(event,1)],[0xad8,0x197])
        before=self.dump();self.assertEqual(s.handle(event,1)[-1].kind,0x197);self.assertEqual(self.dump(),before)

    def test_selected_contents_match_original_id_and_count(self):
        item=self.grant(306015)
        events=open_cube(self.path,1001,306015,payload(item['uid'],(300948,)),'select')
        self.assertEqual(struct.unpack_from('>ii',events[-1].payload,16),(300948,5))
        self.assertEqual(sum(i['count'] for i in self.items() if i['template']==300948),5)
        self.assertFalse(any(i['template']==305676 for i in self.items()))
        before=self.dump();retry=open_cube(self.path,1001,306015,payload(item['uid'],(300948,)),'select')
        self.assertEqual(struct.unpack_from('>I',retry[-1].payload,12)[0],0);self.assertEqual(self.dump(),before)

    def test_empty_forged_multiple_and_changed_selection_preserve_cube(self):
        item=self.grant(720044)
        for choices in ((),(701000,),(980038,980039)):
            before=self.dump()
            with self.assertRaises(ValueError):open_cube(self.path,1001,720044,payload(item['uid'],choices),'select')
            self.assertEqual(self.dump(),before)
        open_cube(self.path,1001,720044,payload(item['uid'],(980038,)),'select')
        before=self.dump()
        with self.assertRaises(ValueError):open_cube(self.path,1001,720044,payload(item['uid'],(980039,)),'select')
        self.assertEqual(self.dump(),before)


for _name in list(vars(fixture.SaleTests)):
    if _name.startswith('test_') and _name not in vars(CubeTests):setattr(CubeTests,_name,None)
