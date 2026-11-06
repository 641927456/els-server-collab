"""Actual unified Application handlers and isolated G-drive synthetic saves."""
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
import collections
import asyncio
import json
import os
import sqlite3
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

HOME=Path(__file__).resolve().parent
BASE=Path(os.environ['ELS_FEEDBACK_TEST_RUNTIME']).resolve()
CANDIDATE=HOME/'source'
BASELINE='--baseline'in sys.argv
sys.dont_write_bytecode=True
sys.path.insert(0,str(BASE))
import els_server.domain
import els_server.storage
if not BASELINE:
    els_server.domain.__path__.insert(0,str(CANDIDATE/'els_server/domain'))
    els_server.storage.__path__.insert(0,str(CANDIDATE/'els_server/storage'))
base=SimpleNamespace(ack=lambda events,kind:next(e for e in events if e.kind==kind))
TEMP=HOME/'test-temp';TEMP.mkdir(exist_ok=True)
tempfile.tempdir=str(TEMP)
os.environ['TMP']=os.environ['TEMP']=str(TEMP)
from els_server.domain.growth_guide_boxes import outputs_for
from els_server.domain.local_session import LocalAccount
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.inventory_state import load_items
from els_server.storage.local_state import LocalState

def totals(items):
    result=collections.Counter()
    for item in items:result[item['template']]+=item['count']
    return result

class Repairs(unittest.TestCase):
    def setUp(self):
        from els_server.storage.characters import Characters
        from els_server.application import Application
        from els_server.config import ServerConfig
        self.tmp=tempfile.TemporaryDirectory(prefix='player-bugs-');self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'game.sqlite3'
        from els_server.storage.local_state import ensure_local_tables
        from els_server.storage.reward_state import ensure_reward_tables
        from els_server.storage.inventory_state import ensure_inventory
        from els_server.storage.accounts import Accounts
        registry=Accounts(Path(self.tmp.name)/'accounts.sqlite3')
        identity=registry.create('bug_owner')
        with closing(sqlite3.connect(self.path))as db,db:
            ensure_local_tables(db);ensure_reward_tables(db);ensure_inventory(db)
        roster=Characters(self.path,identity['id'])
        self.uid=roster.create('BugOwner',1,'bug-owner')['uid']
        self.other=roster.create('BugOther',5,'bug-other')['uid']
        self.root=LocalAccount(LocalState(self.path,self.uid),identity['id'],identity['name']);self.root.enable_characters()
        self.account=self.root.for_character(self.uid)
        self.account.get_inventory_snapshot();self.root.for_character(self.other).get_inventory_snapshot()
        self.app=Application(ServerConfig(state_file=self.path,accounts_file=registry.path));self.app.registry=registry
        self.app.accounts[identity['id']]=self.root
        self.loop=asyncio.new_event_loop();self.addCleanup(self.loop.close)
        self.addCleanup(self.app.close)
        self.s=self.loop.run_until_complete(self.app.session(identity={k:identity[k]for k in('id','name')}));self.s.account=self.account
        self.app.playing[identity['id']]=self.s
        self.s.role='game';self.s.phase='town_ready';self.s.active_map=20001
        self.s.completed.update((0x28,0x225,0x227));self.career(150)
        self.s.enter_town=True;self.s.pending_map=self.s.active_map
        self.s.dungeon_return_pending=False
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE location SET town=? WHERE uid=?',(self.s.active_map,self.uid))
        self.account.location=self.account.store.load()
        self.dispatch(Event(0x202,performers=(0,),kind=0x640),1)

    def dispatch(self,event,sequence):
        return self.loop.run_until_complete(self.app.call(self.s.handle,event,sequence))

    def career(self,unit_class):
        from els_server.domain.character_rules import CLASSES
        from els_server.game_data import client_data
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=99,transcendence=?,master=0 WHERE uid=?',
                (client_data().unit(unit_class)['unitType'],unit_class,int(CLASSES[unit_class]['stage']==3),self.uid))

    def items(self,uid=None):
        with closing(sqlite3.connect(self.path))as db:
            return load_items(db,self.uid if uid is None else uid)

    def snapshot(self):
        with closing(sqlite3.connect(self.path))as db:return tuple(db.iterdump())

    def seed(self,template,count):
        from els_server.game_data import client_data
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');items=load_items(db,self.uid)
            slot=next(n for n in range(36)if not any(i['group']==4 and i['slot']==n for i in items))
            uid=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
            db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(uid+1,))
            db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',(uid,self.uid,template,client_data().item(template)['metadata'],count,4,slot))
            return next(i for i in load_items(db,self.uid)if i['uid']==uid)

    def preview(self,item,sequence=90):
        return self.dispatch(Event(0x202,performers=(0,),kind=0x559,payload=struct.pack('>iIiBB',item['template'],1,0,0,0)),sequence)

    def send(self,item,count=1,choices=(),sequence=100,flags=(0,0,0)):
        payload=struct.pack('>QBBBI',item['uid'],*flags,len(choices))+b''.join(struct.pack('>i',t)for t in choices)+struct.pack('>i',count)
        return self.dispatch(Event(0x202,performers=(0,),kind=0x196,payload=payload),sequence)

    def rejected(self,item,**kwargs):
        before=self.snapshot();answer=self.send(item,**kwargs)
        self.assertNotEqual(struct.unpack_from('>i',base.ack(answer,0x197).payload)[0],0)
        self.assertEqual(self.snapshot(),before)

    def successful(self,item,count,choices,sequence):
        before=self.items();foreign=self.items(self.other);ed=self.account.get_reward_balances()['ed']
        answer=self.send(item,count,choices,sequence)
        raw=base.ack(answer,0x197).payload
        self.assertEqual(struct.unpack_from('>i',raw)[0],0)
        for event in answer:encode_event(event)
        after=self.items();delta=totals(after);delta.subtract(totals(before));delta[item['template']]+=count or 1
        saved=self.snapshot();replay=self.send(item,count,choices,sequence)
        self.assertEqual(struct.unpack_from('>i',base.ack(replay,0x197).payload)[0],0)
        self.assertEqual(self.snapshot(),saved)
        cold=LocalAccount(LocalState(self.path,self.uid),self.account.account_id);cold.enable_characters()
        self.assertEqual(cold.get_inventory_snapshot()['items'],after)
        self.assertEqual(self.items(self.other),foreign);self.assertEqual(self.account.get_reward_balances()['ed'],ed)
        n=struct.unpack_from('>I',raw,12)[0]
        displayed=collections.Counter(dict(struct.unpack_from('>ii',raw,16+8*k)for k in range(n)))
        self.assertEqual(+delta,displayed)
        return +delta

    def test_guide_bulk_normal_and_plan_splits(self):
        for index,template in enumerate((721747,721748,721750)):
            with self.subTest(template=template):
                item=self.seed(template,20)
                self.assertEqual(struct.unpack_from('>i',base.ack(self.preview(item),0x55a).payload)[0],0)
                rows=outputs_for(template,self.account.character())
                count=3 if template==721750 else 20
                delta=self.successful(item,count,(),100+index)
                self.assertEqual(delta,collections.Counter({r['template']:r['quantity']*count for r in rows}))
                remaining=next((i['count']for i in self.items()if i['uid']==item['uid']),0)
                self.assertEqual(remaining,20-count)

    def test_guide_zero_one_selection_rejections_and_atomic_failures(self):
        import els_server.storage.growth_guide_boxes as target
        item=self.seed(721747,5)
        for i,count in enumerate((-1,6,2147483647)):
            self.rejected(item,count=count,sequence=100+i)
        self.rejected(item,flags=(2,0,0),sequence=103)
        self.rejected(item,choices=(710313,),sequence=104)
        before=self.snapshot()
        with patch.object(target,'encode_event',side_effect=ValueError('controlled late encoder failure')):
            self.rejected(item,count=3,sequence=105)
        self.assertEqual(self.snapshot(),before)
        from els_server.storage.bag_capacity import allowances
        with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
        limits[6]=max((i['slot']+1 for i in self.items()if i['group']==6),default=0)
        with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
            self.rejected(item,count=3,sequence=106)
        rows=outputs_for(item['template'],self.account.character())
        for i,count in enumerate((0,1,3)):
            self.assertEqual(self.successful(item,count,(),110+i),collections.Counter({r['template']:r['quantity']*(count or 1)for r in rows}))
        choice=self.seed(720487,2)
        selected=outputs_for(choice['template'],self.account.character())[0]
        self.rejected(choice,count=2,sequence=120)
        self.assertEqual(self.successful(choice,2,(selected['template'],),121),{selected['template']:selected['quantity']*2})

    def test_kobo_apple_boxes_all_native_choices_and_rejections(self):
        for index,template in enumerate((716611,718113)):
            for i,choice in enumerate((710313,710315,710314)):
                with self.subTest(template=template,choice=choice):
                    item=self.seed(template,1)
                    preview=base.ack(self.preview(item,200+index*30+i*3),0x55a).payload
                    self.assertEqual(struct.unpack_from('>i',preview)[0],0)
                    self.assertEqual(struct.unpack_from('>iI',preview,13),(1,3))
                    for bad in ((),(710003,),(710313,710314)):
                        self.rejected(item,choices=bad,sequence=240+index*30+i*3+len(bad))
                    self.rejected(item,count=2,choices=(choice,),sequence=280+index*30+i)
                    self.assertEqual(self.successful(item,1,(choice,),300+index*30+i),{choice:50})
        # Existing approved303673 mapping remains distinct and replayable.
        item=self.seed(303673,1)
        self.rejected(item,choices=(710313,),sequence=390)
        self.assertEqual(self.successful(item,1,(710003,),391),{710003:100})

    def test_npc_dialogue_exception_does_not_disconnect(self):
        from els_server.domain.quest_flow import handle
        event=Event(0x202,performers=(0,),kind=0xfd,payload=struct.pack('>i',10045))
        before=self.snapshot()
        # Real current Myu route rejects a guildless character, then delegates
        # to its original non-member NPC handler instead of raising a Python error.
        answer=self.loop.run_until_complete(self.app.call(handle,self.s,event,400))
        self.assertIsNotNone(answer)
        self.assertTrue(any(e.kind==0xfe for e in answer))
        for e in answer:encode_event(e)
        self.assertEqual(self.snapshot(),before)
        with patch('els_server.domain.guild_quest_flow.dialogue',side_effect=sqlite3.OperationalError('controlled DB refusal')):
            answer=self.loop.run_until_complete(self.app.call(handle,self.s,event,401))
        self.assertTrue(any(e.kind==0xfe for e in answer))
        self.assertEqual(self.snapshot(),before)

    def test_apple_atomic_failure_lock_and_actor_ownership(self):
        import els_server.storage.potion_choice_box as target
        item=self.seed(716611,1)
        from els_server.domain.retained_native_consumables import _ExistingNativeConsumable
        self.assertIs(type(item),_ExistingNativeConsumable)
        self.preview(item)
        with patch.object(target,'encode_event',side_effect=ValueError('controlled apple late encoding failure')):
            self.rejected(item,choices=(710313,),sequence=500)
        from els_server.storage.bag_capacity import allowances
        with closing(sqlite3.connect(self.path))as db:limits=allowances(db,self.uid)
        limits[6]=max((i['slot']+1 for i in self.items()if i['group']==6),default=0)
        with patch('els_server.storage.bag_capacity.allowances',return_value=limits):
            self.rejected(item,choices=(710313,),sequence=501)
        from els_server.storage.item_locks import assign
        import time
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');assign(db,self.uid,item['uid'],int(time.time())+300)
        self.rejected(item,choices=(710313,),sequence=502)
        # The same box UID cannot be charged from another character or lease.
        account=self.s.account
        self.s.account=self.root.for_character(self.other)
        try:
            self.dispatch(Event(0x202,performers=(0,),kind=0x640),499)
            self.rejected(item,choices=(710313,),sequence=503)
        finally:self.s.account=account
        from els_server.domain.acquisition_policy import can_acquire
        self.assertFalse(can_acquire(716611))
        with closing(sqlite3.connect(self.path))as db:
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

names=[x for x in sys.argv[1:]if x!='--baseline'and not x.startswith('--report=')]or []
suite=unittest.defaultTestLoader.loadTestsFromNames(names,Repairs)
result=unittest.TextTestRunner(verbosity=2).run(suite)
report=dict(ok=result.wasSuccessful(),baseline=BASELINE,tests=result.testsRun,names=names,errors=[s for _,s in result.errors],failures=[s for _,s in result.failures],natural_GUI=False,installed=False,temporary_databases_cleaned=not any(TEMP.iterdir()))
report_name=next((x.split('=',1)[1]for x in sys.argv[1:]if x.startswith('--report=')),'tests-before.json'if BASELINE else'tests-after.json')
assert Path(report_name).name==report_name and report_name.endswith('.json')
(HOME/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in report.items()if k not in('errors','failures')}))
sys.exit(not result.wasSuccessful())
