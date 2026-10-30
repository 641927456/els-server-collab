"""Pinned pre-refactor consumers versus explicit candidate source, owned SQL only."""
import ast
import copy
import hashlib
import importlib
import importlib.util
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from contextlib import closing, ExitStack
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
CHANNEL=RUNTIME.name
PIN=ROOT/'pinned-inputs/dispatch-baseline'/CHANNEL
from els_server.domain import local_session as session_module
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.storage.local_state import LocalState
from els_server.domain.dungeon_clock import DungeonClock
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain import session_dispatch as dispatch
from els_server.domain import dungeon_settlement_commands as commands
from els_server.domain import pve_economy_flow as pve
from els_server.storage import group_settlement as group
from els_server.protocol.protocol_codec import Event,encode_event

LEAVES=('domain/local_session.py','domain/session_dispatch.py',
        'domain/dungeon_settlement_commands.py','domain/pve_economy_flow.py',
        'storage/group_settlement.py')
BASE_SHA={'online':'51872cbbdc44fba3425417be63f4efa615dc7e95b7a3fff9fdeb808d118a88f3',
          'local':'266565e4331cb503a42e8422d7053a00c6f3a91bf288f9c6aca7cc01168c06d8'}
old_tree=ast.parse((PIN/'domain/local_session.py').read_text(encoding='utf8'))
old_class=next(n for n in old_tree.body if isinstance(n,ast.ClassDef) and n.name=='LocalSession')
old_function=next(n for n in old_class.body if isinstance(n,ast.FunctionDef) and n.name=='_handle')
code=compile(ast.fix_missing_locations(ast.Module(body=[copy.deepcopy(old_function)],type_ignores=[])),str(PIN/'domain/local_session.py'),'exec')
namespace=dict(session_module.__dict__)
exec(code,namespace)
OLD_HANDLE=namespace['_handle']

def old_module(relative):
    spec=importlib.util.spec_from_file_location('pinned_'+relative.replace('/','_').replace('.','_'),PIN/relative)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
OLD_PVE=old_module('domain/pve_economy_flow.py')
OLD_GROUP=old_module('storage/group_settlement.py')
# Preserve current private capability identity while executing the pinned old
# function: its AD branch originally imported the current dungeon consumer too.
for name in ('death','clear'):
    tree=ast.parse((PIN/'domain/pve_economy_flow.py').read_text(encoding='utf8'))
    function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    scope=dict(pve.__dict__)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function],type_ignores=[])),str(PIN/'domain/pve_economy_flow.py'),'exec'),scope)
    setattr(OLD_PVE,name,scope[name])

def wires(events):return [encode_event(e) for e in events]

def death(npc,uid=1001):
    # Native AD schema with an owned actor and exact resource-derived float HP.
    payload=struct.pack('>iBQQ6fBf',npc['key'],0,uid,uid,0.,0.,0.,1.,2.,3.,0,npc['hp'])
    payload+=struct.pack('>IQf',1,uid,1.)+struct.pack('>IQB',1,uid,1)+bytes(12)+struct.pack('>Q',uid)
    return Event(0x202,performers=(0,),kind=0xad,payload=payload)

BB=Event(0x202,performers=(0,),kind=0xbb,payload=b'\0')

class DispatchSettlement(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='dispatch-',dir=ROOT/'test-tmp')
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'owned.sqlite3'
        self.now=[0.]

    def session(self,uid=1001,*,application=False,items=False):
        if uid!=1001:
            from els_server.storage.characters import Characters
            Characters(self.path)
            with closing(sqlite3.connect(self.path)) as db,db:
                db.execute('INSERT OR IGNORE INTO characters VALUES (?,?,?,?,?,1,0,0,0)',(uid,'Owned'+str(uid),'owned'+str(uid),1,1))
                db.execute('INSERT OR IGNORE INTO character_owners VALUES (?,?)',(uid,1))
        a=LocalAccount(LocalState(self.path,uid));a.enable_characters()
        s=LocalSession(a,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
            npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
            reward_test=True,item_test=items,drop_probe=items)
        s.role='game';s.phase='dungeon_active';s.dungeon_substage_synced=True;s.dungeon_failed=False
        s.reward_run_id='f757515a-0905-5f3b-9295-'+str(uid).zfill(12)
        s.dungeon_clock=DungeonClock(lambda:self.now[0]);s.dungeon_clock.resume()
        s.dungeon_participants=frozenset((uid,))
        if application:
            from els_server.application import Application
            from els_server.config import ServerConfig
            app=Application(ServerConfig(state_file=self.path));app.account=a
            self.addCleanup(app.executor.shutdown,wait=True)
            s._c1_local_application=app;s._c1_local_live=True
            pve.bind_story(s)
        return s

    def legacy_final(self,**kw):
        s=self.session(**kw);s.gate_stage=2
        from els_server.domain.dungeon_population import population
        n=population(2)['npcs'][0]
        s.defeated_npcs={n['key']:death(n,s.account.uid).payload}
        s.part_end_notified=True;s.dungeon_clock.pause()
        return s

    def static_final(self,uid=1001,identity=30092,*,challenge=False):
        s=self.session(uid)
        if challenge:
            from els_server.storage.challenge_state import ChallengeState
            ledger=ChallengeState(self.path,uid);state=ledger.begin(4,1,account_id=1)
            s.active_challenge=ledger.admit(identity);self.assertIsNotNone(s.active_challenge)
            s.challenge_deadline=state['deadline'];s.challenge_clear_effect=None
        s.dungeon_run=DungeonRun(identity,s.reward_run_id,clock=lambda:self.now[0],internal=challenge)
        r=s.dungeon_run
        # Select the real resource final stage and satisfy its own NPC condition.
        finals=[(int(k),int(p)) for k,v in r.graph['stages'].items() for p,z in v['parts'].items()
                if any(t['kind']==4 for c in z['conditions'] for t in c['next'])]
        stage,part=finals[-1];r._load_stage(stage);r.part=part;r.loaded()
        r.defeated={n['key']:death(n,uid).payload for n in r.current['npcs'] if n.get('team',1)!=0}
        s.defeated_npcs=r.defeated;s.gate_stage=stage
        r.poll_ready();self.now[0]+=86401
        self.assertTrue(r.poll_ready());self.assertEqual(r.next['kind'],4)
        s.part_end_notified=True;s.dungeon_clock.pause()
        return s

    def snapshot(self,s):
        return dict(balances=s.account.get_reward_balances(),receipt=copy.deepcopy(s.reward_receipt),
                    flags=(s.clear_notified,s.clear_items_synced,s.part_end_notified,s.gate_stage),
                    defeated=copy.deepcopy(s.defeated_npcs))

    def test_source_and_ast_contract(self):
        self.assertEqual(hashlib.sha256((PIN/'domain/local_session.py').read_bytes()).hexdigest(),BASE_SHA[CHANNEL])
        for leaf in LEAVES:
            self.assertEqual((RUNTIME/'els_server'/leaf).read_bytes(),(ROOT/'candidate'/CHANNEL/'els_server'/leaf).read_bytes())
        self.assertEqual(Path(session_module.__file__).resolve(),RUNTIME/'els_server/domain/local_session.py')
        new_tree=ast.parse((RUNTIME/'els_server/domain/local_session.py').read_text(encoding='utf8'))
        new_class=next(n for n in new_tree.body if isinstance(n,ast.ClassDef) and n.name=='LocalSession')
        new_function=next(n for n in new_class.body if isinstance(n,ast.FunctionDef) and n.name=='_handle')
        d=ast.parse((RUNTIME/'els_server/domain/session_dispatch.py').read_text(encoding='utf8'))
        functions={n.name:n for n in d.body if isinstance(n,ast.FunctionDef)}
        first=next(i for i,n in enumerate(old_function.body) if isinstance(n,ast.Assign) and ast.unparse(n)=='kind = event.kind')
        last=next(i for i,n in enumerate(old_function.body) if isinstance(n,ast.If) and ast.unparse(n.test).startswith('self.dungeon_run is not None'))
        dump=lambda ns:ast.dump(ast.Module(body=ns,type_ignores=[]),include_attributes=False)
        self.assertEqual(dump(functions['priority_handlers'].body[:-1]),dump(old_function.body[:first]))
        self.assertEqual(dump(functions['feature_handlers'].body[:-1]),dump(old_function.body[first+1:last]))
        legacy=next(n for n in old_function.body if isinstance(n,ast.If) and ast.unparse(n.test).startswith('self.npc_slot_test and'))
        c=ast.parse((RUNTIME/'els_server/domain/dungeon_settlement_commands.py').read_text(encoding='utf8'))
        extracted=next(n for n in c.body if isinstance(n,ast.FunctionDef) and n.name=='legacy_dungeon_event')
        self.assertEqual(ast.dump(legacy),ast.dump(extracted.body[2]))
        a=copy.deepcopy(old_tree);b=copy.deepcopy(new_tree)
        for t in (a,b):
            cls=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='LocalSession')
            next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='_handle').body=[]
            # Independently coordinated lifecycle work: only the two terms
            # accessors bridge the account cache's process-local bool holder.
            account=next(n for n in t.body if isinstance(n,ast.ClassDef) and n.name=='LocalAccount')
            for fn in account.body:
                if isinstance(fn,ast.FunctionDef) and fn.name in ('accept_terms','has_terms'):fn.body=[]
        self.assertEqual(ast.dump(a),ast.dump(b))

    def test_order_empty_list_consumes_and_none_declines(self):
        s=self.session();event=Event(0x202,kind=0x559,payload=b'')
        seen=[]
        with patch('els_server.domain.black_market_flow.handle',side_effect=lambda *a:seen.append('first')), \
             patch('els_server.domain.black_market_box_flow.handle',side_effect=lambda *a:seen.append('second') or []), \
             patch('els_server.domain.pve_economy_flow.solo',side_effect=AssertionError('must stop')):
            self.assertEqual(s._handle(event,17),[])
        self.assertEqual(seen,['first','second'])
        # These share an item-use opcode; preserving their relative priority matters.
        seen=[]
        with patch('els_server.domain.potion_choice_box.handle',side_effect=lambda *a:seen.append('choice') or []), \
             patch('els_server.domain.teacher_elixir_boxes.handle',side_effect=AssertionError('must stop')):
            self.assertEqual(dispatch.priority_handlers(s,event,23),[])
        self.assertEqual(seen,['choice'])

    def test_real_ad_bb_prechain_declines_without_state_or_sql_effects(self):
        s=self.session(application=True,items=True);s._pve_internal=True
        # Current published factory, including its original enabled/availability reads.
        from els_server.domain.selected_2026_pair_runtime import from_pack
        manager=from_pack(self.path,RUNTIME/'els_server/data/selected2026/local-pair.json');manager.install()
        s.activity2026_awards=manager(s.account)
        from els_server.domain.dungeon_population import population
        callbacks={}
        tree=ast.parse((RUNTIME/'els_server/domain/session_dispatch.py').read_text(encoding='utf8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom):
                module=importlib.import_module(node.module)
                for name in node.names:
                    fn=getattr(module,name.name)
                    if callable(fn) and hasattr(fn,'__code__'):callbacks[fn.__code__]=node.module+'.'+name.name
        callbacks[type(s.activity2026_awards).handle.__code__]='activity2026_awards.handle'
        begin=next(i for i,n in enumerate(old_function.body) if isinstance(n,ast.If) and ast.unparse(n.test).startswith('self.dungeon_run is not None'))
        end=next(i for i,n in enumerate(old_function.body) if isinstance(n,ast.If) and ast.unparse(n.test).startswith('self.npc_slot_test and'))
        intervening=[n for n in old_function.body[begin:end] if isinstance(n,ast.If)]
        traces=[]
        for event in (death(population(0)['npcs'][0]),BB):
            before=self.snapshot(s)
            with closing(sqlite3.connect(self.path)) as db:sql_before=list(db.iterdump())
            calls=[]
            def trace(frame,action,value):
                if action=='return' and frame.f_code in callbacks:
                    calls.append((callbacks[frame.f_code],value))
            sys.setprofile(trace)
            try:
                self.assertIsNone(dispatch.priority_handlers(s,event))
                self.assertIsNone(dispatch.feature_handlers(s,event))
            finally:sys.setprofile(None)
            self.assertGreater(len(calls),65)
            self.assertTrue(all(value is None for name,value in calls),calls)
            gates=[]
            for node in intervening:
                condition=compile(ast.Expression(body=copy.deepcopy(node.test)),'<pinned intermediate gate>','eval')
                matched=eval(condition,dict(session_module.__dict__),dict(self=s,event=event,kind=event.kind,request_sequence=None))
                self.assertFalse(matched,ast.unparse(node.test))
                gates.append(dict(condition=ast.unparse(node.test),matched=False,line=node.lineno))
            self.assertEqual(self.snapshot(s),before)
            with closing(sqlite3.connect(self.path)) as db:self.assertEqual(list(db.iterdump()),sql_before)
            traces.append(dict(kind=hex(event.kind),calls=[name for name,value in calls],intermediate_gates=gates))
        (ROOT/f'dispatch-prechain-{CHANNEL}.json').write_text(__import__('json').dumps(traces,indent=2),encoding='utf8')

    def test_legacy_clear_and_replay_byte_equivalence(self):
        old=self.legacy_final();before=self.snapshot(old)
        expected=wires(OLD_HANDLE(old,BB));expected_state=self.snapshot(old)
        old.clear_notified=False;old.reward_receipt=None;old.clear_items_synced=False
        replay=wires(commands.settle_clear(old,BB))
        self.assertEqual(replay,expected)
        state=self.snapshot(old);state['receipt']['replayed']=expected_state['receipt']['replayed']
        self.assertEqual(state,expected_state)
        self.assertGreater(state['balances']['ed'],before['balances']['ed'])
        balances=old.account.get_reward_balances()
        self.assertEqual([e.kind for e in commands.settle_clear(old,BB)],[0xbc])
        self.assertEqual(old.account.get_reward_balances(),balances)

    def test_static_final_gate_and_clear_byte_equivalence(self):
        s=self.static_final();r=s.dungeon_run
        s.part_end_notified=False
        self.assertEqual(wires(OLD_HANDLE(s,BB)),wires(commands.settle_clear(s,BB)))
        self.assertFalse(s.clear_notified)
        s.part_end_notified=True;ready=r.ready_at;r.ready_at=self.now[0]+10
        self.assertEqual(OLD_HANDLE(s,BB),[]);self.assertEqual(commands.settle_clear(s,BB),[])
        self.assertFalse(s.clear_notified);r.ready_at=ready
        with patch('els_server.domain.story_controller_retirements.gate_predecessor_blocked',return_value=True):
            self.assertEqual(OLD_HANDLE(s,BB),[]);self.assertEqual(commands.settle_clear(s,BB),[])
        self.assertFalse(s.clear_notified)
        s.part_end_notified=True;expected=wires(OLD_HANDLE(s,BB));balances=s.account.get_reward_balances()
        s.clear_notified=False;s.reward_receipt=None;s.clear_items_synced=False
        self.assertEqual(wires(commands.settle_clear(s,BB)),expected)
        self.assertEqual(s.account.get_reward_balances(),balances)
        self.assertEqual(r.next['kind'],4)

    def test_legacy_ad_current_consumer_and_duplicate_equivalence(self):
        from els_server.domain.dungeon_population import population
        s=self.session();event=death(population(0)['npcs'][0])
        other=copy.copy(s);other.defeated_npcs={};other.dungeon_clock=copy.copy(s.dungeon_clock)
        self.assertEqual(wires(OLD_HANDLE(s,event)),wires(commands.settle_death(other,event)))
        self.assertEqual(self.snapshot(s),self.snapshot(other))
        self.assertEqual(wires(OLD_HANDLE(s,event)),wires(commands.settle_death(other,event)))
        wrong=Event(0x202,kind=0xbb,payload=b'bad')
        self.assertEqual(OLD_HANDLE(s,wrong),commands.settle_clear(other,wrong))

    def test_group_second_member_failure_rolls_back_then_commit_observers(self):
        members=[self.static_final(1001,34850,challenge=True),self.static_final(1002,34850,challenge=True)]
        from els_server.storage.challenge_state import ChallengeState
        before=[self.snapshot(s) for s in members]
        from els_server.domain import dungeon_clear
        original=dungeon_clear.reward_clear_notice
        count=[0]
        def fail_second(*args,**kwargs):
            count[0]+=1
            if count[0]==2:raise ValueError('owned second-member encode failure')
            return original(*args,**kwargs)
        with patch.object(dungeon_clear,'reward_clear_notice',side_effect=fail_second),patch('els_server.domain.challenge_flow.notification',side_effect=AssertionError('precommit notification')):
            with self.assertRaisesRegex(ValueError,'second-member'):group.settle(members,BB)
        self.assertEqual([self.snapshot(s) for s in members],before)
        self.assertEqual([ChallengeState(self.path,s.account.uid).current()['progress'] for s in members],[0,0])
        self.assertTrue(all(not hasattr(s,'reward_transaction') for s in members))
        seen=[]
        from els_server.domain import challenge_flow,quest_flow,pet_progression_flow,artifact_flow
        def observer(name,fn):
            def check(s,*args):
                self.assertTrue(all(not hasattr(m,'reward_transaction') for m in members))
                self.assertTrue(all(m.account.get_reward_balances()['ed']>before[i]['balances']['ed'] for i,m in enumerate(members)))
                seen.append((s.account.uid,name));return fn(s,*args)
            return check
        with ExitStack() as stack:
            for module,name,label in ((challenge_flow,'notification','phase'),(quest_flow,'observe','quest'),(pet_progression_flow,'observe','pet'),(artifact_flow,'observe','artifact')):
                stack.enter_context(patch.object(module,name,side_effect=observer(label,getattr(module,name))))
            result=group.settle(members,BB)
        self.assertEqual(seen,[(s.account.uid,name) for s in members for name in ('phase','quest','pet','artifact')])
        self.assertEqual(len(result),2)
        for s,events in result:self.assertIn(0xc1,[e.kind for e in events]);wires(events)
        self.assertEqual([ChallengeState(self.path,s.account.uid).current()['progress'] for s in members],[1,1])

    def test_group_old_and_new_receipts_notifications_and_recovery_match(self):
        from els_server.domain import dungeon_flow
        from els_server.storage.challenge_state import ChallengeState
        from els_server.storage.reward_state import RewardConflict
        wall_time=[int(dungeon_flow.time.time())]
        # Only this consumer's wall clock is controlled; global time is untouched.
        clock=patch.object(dungeon_flow,'time',SimpleNamespace(time=lambda:wall_time[0]))
        clock.start();self.addCleanup(clock.stop)
        members=[self.static_final(1001,34850,challenge=True),self.static_final(1002,34850,challenge=True)]
        saved=[dict(m.__dict__) for m in members]
        clone=Path(self.tmp.name)/'group-preimage.sqlite3'
        with closing(sqlite3.connect(self.path)) as source,closing(sqlite3.connect(clone)) as target:source.backup(target)
        with patch.object(LocalSession,'_handle',OLD_HANDLE):expected=OLD_GROUP.settle(members,BB)
        expected_wire=[(m.account.uid,wires(events)) for m,events in expected]
        expected_balances=[m.account.get_reward_balances() for m in members]
        with closing(sqlite3.connect(clone)) as source,closing(sqlite3.connect(self.path)) as target:source.backup(target)
        for m,state in zip(members,saved):m.__dict__.clear();m.__dict__.update(state)
        actual=group.settle(members,BB)
        self.assertEqual([(m.account.uid,wires(events)) for m,events in actual],expected_wire)
        self.assertEqual([m.account.get_reward_balances() for m in members],expected_balances)
        committed_effects=[copy.deepcopy(m.challenge_clear_effect) for m in members]
        committed_progress=[ChallengeState(self.path,m.account.uid).current() for m in members]
        # A response replay keeps the issued operation evidence even after a second boundary.
        for m in members:m.clear_notified=False;m.reward_receipt=None
        wall_time[0]+=2
        replay=group.settle(members,BB)
        self.assertEqual([(m.account.uid,wires(events)) for m,events in replay],expected_wire)
        self.assertEqual([m.account.get_reward_balances() for m in members],expected_balances)
        self.assertEqual([m.challenge_clear_effect for m in members],committed_effects)
        self.assertEqual([ChallengeState(self.path,m.account.uid).current() for m in members],committed_progress)
        # Reconstructing evidence for a committed run must still conflict, without a second award.
        for m in members:m.clear_notified=False;m.reward_receipt=None;m.challenge_clear_effect=None
        with self.assertRaises(RewardConflict):group.settle(members,BB)
        self.assertEqual([m.account.get_reward_balances() for m in members],expected_balances)
        self.assertEqual([ChallengeState(self.path,m.account.uid).current() for m in members],committed_progress)

    def test_prepared_commands_do_not_reenter_full_dispatch(self):
        s=self.legacy_final()
        with patch.object(LocalSession,'_handle',side_effect=AssertionError('full dispatcher reentry')):
            self.assertIn(0xc1,[e.kind for e in commands.settle_clear(s,BB)])
        for relative in ('storage/group_settlement.py','domain/pve_economy_flow.py'):
            tree=ast.parse((RUNTIME/'els_server'/relative).read_text(encoding='utf8'))
            self.assertFalse(any(isinstance(n,ast.Attribute) and n.attr=='_handle' for n in ast.walk(tree)))

    def test_pve_clear_old_new_encoding_failure_and_replay(self):
        s=self.legacy_final(application=True,items=True)
        before=self.snapshot(s);saved=dict(s.__dict__)
        clone=Path(self.tmp.name)/'clear-preimage.sqlite3'
        with closing(sqlite3.connect(self.path)) as source,closing(sqlite3.connect(clone)) as target:source.backup(target)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('owned clear encode failure')):
            with self.assertRaisesRegex(ValueError,'clear encode'):pve.clear((s,),BB,s)
        self.assertEqual(self.snapshot(s),before)
        with patch.object(LocalSession,'_handle',OLD_HANDLE):expected=wires(OLD_PVE.clear((s,),BB,s))
        expected_balances=s.account.get_reward_balances()
        with closing(sqlite3.connect(clone)) as source,closing(sqlite3.connect(self.path)) as target:source.backup(target)
        s.__dict__.clear();s.__dict__.update(saved)
        self.assertEqual(wires(pve.clear((s,),BB,s)),expected)
        self.assertEqual(s.account.get_reward_balances(),expected_balances)
        s.clear_notified=False;s.reward_receipt=None;s.clear_items_synced=False
        self.assertEqual(wires(pve.clear((s,),BB,s)),expected)
        self.assertEqual(s.account.get_reward_balances(),expected_balances)

    def test_pve_writer_rollback_and_cold_recovery(self):
        from els_server.domain.dungeon_population import population
        s=self.session(application=True,items=True);event=death(population(0)['npcs'][0])
        before=self.snapshot(s)
        with patch('els_server.protocol.protocol_codec.encode_event',side_effect=ValueError('owned precommit encode failure')):
            with self.assertRaisesRegex(ValueError,'precommit'):pve.death((s,),event,s)
        self.assertEqual(self.snapshot(s),before)
        events=pve.death((s,),event,s);self.assertIn(0xaf,[e.kind for e in events]);wires(events)
        self.assertIn(0,s.defeated_npcs)
        self.assertGreater(s.account.get_reward_balances()['experience'],before['balances']['experience'])
        self.assertEqual(LocalAccount(LocalState(self.path)).get_reward_balances(),s.account.get_reward_balances())

    def test_pve_original_writer_consumer_replay_equivalence(self):
        from els_server.domain.dungeon_population import population
        s=self.session(application=True,items=True);event=death(population(0)['npcs'][0])
        # Both implementations get an identical private database preimage and same run UUID.
        clone=Path(self.tmp.name)/'preimage.sqlite3'
        with closing(sqlite3.connect(self.path)) as source,closing(sqlite3.connect(clone)) as target:source.backup(target)
        with patch.object(LocalSession,'_handle',OLD_HANDLE):expected=wires(OLD_PVE.death((s,),event,s))
        expected_balances=s.account.get_reward_balances()
        with closing(sqlite3.connect(clone)) as source,closing(sqlite3.connect(self.path)) as target:source.backup(target)
        s.defeated_npcs={};s.part_end_notified=False;s.world_drops={};s.world_drop_sequence=910001;s.world_drop_issued=None
        self.assertEqual(wires(pve.death((s,),event,s)),expected)
        self.assertEqual(s.account.get_reward_balances(),expected_balances)

    def test_pve_static_death_original_capability_and_writer_match(self):
        from els_server.domain.legacy_pve_exp import eligible
        s=self.session(application=True,items=True)
        s.dungeon_run=DungeonRun(30092,s.reward_run_id,clock=lambda:self.now[0]);s.dungeon_run.loaded()
        s.defeated_npcs=s.dungeon_run.defeated
        npc=next(n for n in s.dungeon_run.current['npcs'] if eligible(n));event=death(npc)
        saved=pve._shadow(s);clone=Path(self.tmp.name)/'static-death-preimage.sqlite3'
        with closing(sqlite3.connect(self.path)) as source,closing(sqlite3.connect(clone)) as target:source.backup(target)
        expected=wires(OLD_PVE.death((s,),event,s));balances=s.account.get_reward_balances()
        with closing(sqlite3.connect(clone)) as source,closing(sqlite3.connect(self.path)) as target:source.backup(target)
        pve._adopt(s,saved)
        self.assertEqual(wires(pve.death((s,),event,s)),expected)
        self.assertEqual(s.account.get_reward_balances(),balances)
