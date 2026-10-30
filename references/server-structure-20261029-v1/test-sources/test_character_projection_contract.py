"""Compare frozen formal producers with candidate producers on owned SQLite.

Both readers use the same unchanged native codecs and static catalog inputs.
The baseline source copies retain their exact formal SHA; no historical test is
rewritten. SQL traces include original ordering and same-writer reads.
"""
from contextlib import closing, contextmanager, ExitStack
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

TASK = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['ELS_RUNTIME_ROOT']).resolve()
if RUNTIME not in ((TASK/'runtimes/online').resolve(), (TASK/'runtimes/local').resolve()):
    raise RuntimeError('Use this task owned runtime')
sys.path.insert(0, str(RUNTIME))
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage import characters, seal_quests, career_shop, character_projection
from els_server.protocol.protocol_codec import encode_event
from els_server.domain.character_rules import CLASSES, default_slots
from els_server.protocol.local_messages import player_initialization
from els_server.protocol.quest_messages import reward_ack
from els_server.protocol.career_messages import career_notice
from els_server.protocol.dungeon_messages import member, return_user_sync

BASE_SHA = {'characters.py': '54cb4afdccc26303c62487d26218688dd204b35e654b3fdbf705f50175d86c32',
            'seal_quests.py': 'ab14d3f23104c7272e232d3459b05410e862b17fb973d02ab211b87e20daf2d2',
            'career_shop.py': '337fa5e7a28faf58f60ee7fef2292c0784821e41c572a290ae22d25f392b3613'}
SOURCE_SHA = {}
for module in (characters, seal_quests, career_shop, character_projection):
    rel = Path('els_server/storage') / Path(module.__file__).name
    actual = RUNTIME / rel
    if Path(module.__file__).resolve() != actual:
        raise RuntimeError('Unexpected runtime import')
    if module is career_shop:
        if sha256(actual.read_bytes()).hexdigest() != BASE_SHA['career_shop.py']:
            raise RuntimeError('Unchanged career consumer differs from formal source')
    elif actual.read_bytes() != (TASK/'candidate'/RUNTIME.name/rel).read_bytes():
        raise RuntimeError('Candidate/runtime mismatch')
    SOURCE_SHA[str(rel)] = sha256(actual.read_bytes()).hexdigest()

def baseline(name):
    path = TASK/'pinned-inputs/projection-baseline'/RUNTIME.name/(name+'.py')
    if sha256(path.read_bytes()).hexdigest() != BASE_SHA[path.name]:
        raise RuntimeError('Frozen producer source changed')
    spec = importlib.util.spec_from_file_location('projection_baseline_'+name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


OLD_CHARACTERS = baseline('characters')
OLD_QUESTS = baseline('seal_quests')
OLD_CAREER = baseline('career_shop')
OBSERVATIONS = {}


class ProjectionContractTests(unittest.TestCase):
    def setUp(self):
        scratch = TASK/'scratch/character-projection'
        scratch.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix=RUNTIME.name+'-', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name)/'owned.sqlite'
        self.account = LocalAccount(LocalState(self.path))
        self.account.enable_characters()
        self.account.enable_inventory()
        self.old_roster = OLD_CHARACTERS.Characters(self.path)
        self.location = self.account.get_location()
        self.economy = self.account.get_reward_balances()

    def dump(self):
        with closing(sqlite3.connect(self.path)) as db:
            return tuple(db.iterdump())

    def pair(self, module, actor, db):
        queries = []
        db.set_trace_callback(queries.append)
        @contextmanager
        def same_connection(path):
            self.assertEqual(Path(path).resolve(), self.path.resolve())
            yield db
        with patch.object(module, 'snapshot_connection', same_connection):
            result = actor.get(1001)
        db.set_trace_callback(None)
        return result, queries

    def compare_roster(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('BEGIN')
            old, old_sql = self.pair(OLD_CHARACTERS, self.old_roster, db)
            new, new_sql = self.pair(characters, self.account.characters, db)
        self.assertEqual(new, old)
        self.assertEqual(new_sql, old_sql)
        return old, new

    def compare_quest(self, db, account_id=1):
        queries = []
        db.set_trace_callback(queries.append)
        old = OLD_QUESTS.load_character(db, 1001, account_id)
        old_sql = list(queries)
        queries.clear()
        new = seal_quests.load_character(db, 1001, account_id)
        db.set_trace_callback(None)
        self.assertEqual(new, old)
        self.assertEqual(queries, old_sql)
        return old, new

    def wires(self, c):
        slots = default_slots(c)
        events = {
            '2A': player_initialization(self.location, True, self.economy, [], c),
            'F5': reward_ack(1, c, self.location, slots, self.economy, [], completed_at=123),
            '29F': career_notice(c, self.location, slots, self.economy, []),
            'D9': return_user_sync(self.location, slots, self.economy, [], c),
        }
        return {**{name: encode_event(event) for name, event in events.items()},
                'FullUser': member(slots, c, [], account_id=c['account_id'])}

    def compare_wires(self, label, old, new):
        expected, actual = self.wires(old), self.wires(new)
        self.assertEqual(actual, expected)
        OBSERVATIONS[label] = {key: {'length': len(value), 'sha256': sha256(value).hexdigest()}
                               for key, value in actual.items()}

    def set_career(self, db, stage, *, unit_type=1, master=False, transcendence=None):
        base = characters.BASE_CLASSES[unit_type]
        target = next(k for k,v in CLASSES.items() if v['base_class']==base and v['stage']==stage)
        trans = stage==3 if transcendence is None else transcendence
        db.execute('UPDATE characters SET unit_type=?,unit_class=?,level=99,transcendence=?,master=?,revision=revision+1 WHERE uid=1001',
                   (unit_type, target, int(trans), int(master)))
        if master:
            from els_server.game_data import client_data
            level = client_data().artifact_curve(4)[0]['ARTIFACT_LEVEL']
            db.execute('INSERT OR REPLACE INTO character_artifacts VALUES (1001,?,4,?,0,?)', (unit_type,level,json.dumps([0]*4)))
        return target

    def rich_fields(self, db):
        self.set_career(db, 3, master=True)
        from els_server.domain.skill_traits import bases, catalog
        row = characters.Characters._row(db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=1001').fetchone())
        artifact = db.execute('SELECT template,evolution,level,experience,potentials FROM character_artifacts WHERE uid=1001').fetchone()
        row['artifact'] = dict(zip(('template','evolution','level','experience','potentials'),artifact))
        row['artifact']['potentials'] = json.loads(row['artifact']['potentials'])
        allowed = bases(row)
        skill, notes = next((s, ns) for (cls,s), ns in catalog().items() if cls==row['unit_class'] and s in allowed)
        note = next(iter(notes))
        db.execute('CREATE TABLE character_skill_traits(owner INTEGER,skill INTEGER,note INTEGER,revision INTEGER)')
        db.execute('INSERT INTO character_skill_traits VALUES(1001,?,?,1)', (skill,note))
        from els_server.storage.ordinary_skill_pages import ensure, _save_snapshot
        ensure(db)
        db.execute('INSERT INTO ordinary_skill_page_states VALUES(1001,2,1,3)')
        _save_snapshot(db, 1001, 2, [0]*22, {}, [[0,0]]*11)
        from els_server.storage.boosting_2026_force_inventory import initialize
        initialize(db)
        db.execute('INSERT INTO selected_2026_force_inventory VALUES(1001,900401,3,295707,0)')
        db.execute('CREATE TABLE selected_2026_force_slots(owner INTEGER,slot INTEGER,skill INTEGER,rank INTEGER)')
        db.execute('INSERT INTO selected_2026_force_slots VALUES(1001,0,900401,3)')
        db.execute('INSERT INTO dungeon_records VALUES(1001,30000,45)')
        from els_server.storage.profession_state import replace
        from els_server.protocol.profession_messages import ProfessionState
        replace(db, 1001, 1, 0, ProfessionState(2,7,123,{4:8},9,20))

    def test_default_profiles_full_dict_sql_order_and_native_bytes(self):
        before = self.dump()
        old, new = self.compare_roster()
        self.assertNotIn('skill_traits', new)
        self.assertNotIn('ordinary_skill_pages', new)
        self.assertIn('character_custom', new)
        self.compare_wires('default-roster', old, new)
        with closing(sqlite3.connect(self.path)) as db:
            old, new = self.compare_quest(db)
        self.assertEqual(new['skill_traits'], {})
        self.assertEqual(new['ordinary_skill_pages']['count'], 1)
        self.assertIn('guild_membership', new)
        self.assertNotIn('character_custom', new)
        self.compare_wires('default-quest', old, new)
        self.assertEqual(self.dump(), before)

    def test_saved_traits_pages_force_profession_artifact_and_cold_read(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            self.rich_fields(db)
        old, new = self.compare_roster()
        self.assertTrue(new['skill_traits'])
        self.assertEqual(new['ordinary_skill_pages']['count'], 2)
        self.assertEqual(new['force_slots'][0], (900401,3))
        self.assertEqual(new['cleared_dungeons'], (30000,))
        self.assertEqual(new['profession']['experience'], 123)
        self.compare_wires('saved-roster', old, new)
        with closing(sqlite3.connect(self.path)) as db:
            old, new = self.compare_quest(db)
        self.compare_wires('saved-quest', old, new)
        self.assertEqual(characters.Characters(self.path).get(1001), self.account.characters.get(1001))

    def test_luciel_roster_fields_remain_distinct_from_quest(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            self.set_career(db, 3, unit_type=10)
            db.execute('CREATE TABLE luciel_style_states(uid INTEGER PRIMARY KEY,style INTEGER,revision INTEGER)')
            db.execute('INSERT INTO luciel_style_states VALUES(1001,2,1)')
        old, new = self.compare_roster()
        self.assertEqual(new['luciel_style'], 2)
        self.assertIn('luciel_active_unit', new)
        self.compare_wires('luciel-roster', old, new)
        with closing(sqlite3.connect(self.path)) as db:
            old, new = self.compare_quest(db)
        self.assertNotIn('luciel_style', new)
        self.assertNotIn('luciel_active_unit', new)
        self.compare_wires('luciel-quest', old, new)

    def test_writer_projection_sees_uncommitted_fields_and_rolls_back(self):
        before = self.dump()
        committed = self.account.characters.get(1001)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            self.rich_fields(db)
            old, new = self.compare_quest(db)
            self.assertTrue(db.in_transaction)
            self.assertEqual(new['profession']['experience'], 123)
            self.assertEqual(self.account.characters.get(1001), committed)
            self.compare_wires('uncommitted-quest', old, new)
            db.rollback()
        self.assertEqual(self.dump(), before)
        self.assertEqual(self.account.characters.get(1001), committed)

    def compare_notifications(self, db, c, before, after, replayed):
        with patch.object(seal_quests, 'load_character', OLD_QUESTS.load_character):
            old = OLD_CAREER.notifications(db,1001,deepcopy(c),self.location,before,after,replayed)
        new = career_shop.notifications(db,1001,deepcopy(c),self.location,before,after,replayed)
        self.assertEqual([(e.kind,encode_event(e)) for e in new], [(e.kind,encode_event(e)) for e in old])
        return new

    def test_career_class_stage_and_replay_preserve_current_event_contract(self):
        for route in ('class', 'stage'):
            with self.subTest(route=route), closing(sqlite3.connect(self.path)) as db:
                db.execute('BEGIN IMMEDIATE')
                if route=='stage':
                    self.set_career(db,2,transcendence=False)
                before = seal_quests.load_character(db,1001,1)
                if route=='class':
                    self.set_career(db,1)
                else:
                    db.execute('UPDATE characters SET transcendence=1,revision=revision+1 WHERE uid=1001')
                after = seal_quests.load_character(db,1001,1)
                result = self.compare_notifications(db,before,before,after,False)
                self.assertEqual(result[0].kind, 0x29f if route=='class' else 0xd9)
                replay = self.compare_notifications(db,after,before,after,True)
                self.assertFalse({0x29f,0xd9}&{e.kind for e in replay})
                db.rollback()

    def test_owner_rejections_and_career_validation_are_preserved(self):
        with closing(sqlite3.connect(self.path)) as db:
            for load in (OLD_QUESTS.load_character, seal_quests.load_character):
                with self.assertRaisesRegex(ValueError,'Quest character owner mismatch'):
                    load(db,1001,2)
            current = seal_quests.load_character(db,1001,1)
            for load in (OLD_CAREER.notifications, career_shop.notifications):
                with self.assertRaisesRegex(ValueError,'Career caller account identity'):
                    load(db,1001,dict(current,account_id=2),self.location,current,current,True)
                with self.assertRaisesRegex(ValueError,'Career refresh account identity'):
                    load(db,1001,current,self.location,current,dict(current,account_id=2),False)
                with self.assertRaisesRegex(ValueError,'Career refresh projection mismatch'):
                    load(db,1001,dict(current,level=current['level']+1),self.location,current,current,True)
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE character_owners SET account_id=2 WHERE uid=1001')
            for load in (OLD_QUESTS.load_character, seal_quests.load_character):
                with self.assertRaisesRegex(ValueError,'Quest character owner mismatch'):
                    load(db,1001,1)
            db.commit()
        for roster in (self.old_roster,self.account.characters):
            with self.assertRaisesRegex(ValueError,'Unknown character'):
                roster.get(1001)

    def test_native_encoding_failure_does_not_commit_caller_writer(self):
        before = self.dump()
        with self.assertRaisesRegex(ValueError,'injected codec failure'):
            with closing(sqlite3.connect(self.path)) as db, db:
                db.execute('BEGIN IMMEDIATE')
                self.set_career(db,1)
                value = seal_quests.load_character(db,1001,1)
                with patch('els_server.protocol.local_messages.character_unit',side_effect=ValueError('injected codec failure')):
                    reward_ack(1,value,self.location,default_slots(value),self.economy,[])
        self.assertEqual(self.dump(), before)

    def test_identity_does_not_depend_on_extended_field_groups(self):
        expected = self.account.characters.identity(1001)
        with patch.object(character_projection,'profession_fields',side_effect=AssertionError('extended read')):
            self.assertEqual(self.account.characters.identity(1001), expected)
            with self.assertRaisesRegex(AssertionError,'extended read'):
                self.account.characters.get(1001)

    def quest_route(self, route, *, old):
        from els_server.domain.local_session import LocalSession
        from els_server.storage.seal_quests import QuestState
        from els_server.domain.seal_quests import quest_catalog, sequence
        from els_server.protocol.protocol_codec import Event
        with tempfile.TemporaryDirectory(prefix='flow-',dir=TASK/'scratch/character-projection') as temporary, ExitStack() as stack:
            if old:
                stack.enter_context(patch.object(characters.Characters,'_project',OLD_CHARACTERS.Characters._project))
                stack.enter_context(patch.object(seal_quests,'load_character',OLD_QUESTS.load_character))
            stack.enter_context(patch('time.time',return_value=1800000000.))
            path=Path(temporary)/'flow.sqlite'
            account=LocalAccount(LocalState(path));account.enable_characters()
            quest=QuestState(path,account_id=1);quest.snapshot()
            session=LocalSession(account,enter_town=True,client_build='dx11_260923')
            session.item_test=True;session.role='game';session.phase='town_ready'
            seq=0;replies=[]
            def record(events):
                replies.append([(e.kind,encode_event(e)) for e in events])
                return events
            def action(kind,qid,*,retry=False):
                nonlocal seq
                if not retry:seq+=1
                definition=quest_catalog().quest(qid)
                payload=struct.pack('>ii',qid,10025) if kind==0xee else struct.pack('>iiI5B',qid,definition['m_eEndNPCID'],0,0,0,1,1,0)
                return record(session.handle(Event(0x202,performers=(0,),kind=kind,payload=payload),seq))
            with closing(sqlite3.connect(path)) as db,db:
                if route=='book':
                    db.execute('UPDATE characters SET unit_class=100,level=30 WHERE uid=1001')
                elif route=='elsword':
                    db.execute('UPDATE characters SET unit_class=1,level=15 WHERE uid=1001')
                    db.execute("INSERT INTO completed_quests VALUES(1001,103020,1,'{}')")
                else:
                    db.execute('UPDATE characters SET unit_type=15,unit_class=205,level=20 WHERE uid=1001')
                    db.executemany("INSERT INTO completed_quests VALUES(1001,?,1,'{}')",[(53670,),(53671,)])
            if route=='book':
                action(0xee,6980)
                record(quest.record('clear-proof',dict(kind='clear',dungeon=30252,level=30,rank=None),b'clear'))
                action(0xf4,6980);action(0xee,6990)
                condition=quest_catalog().objectives(6990)[0]['m_ClearCondition']
                record(quest.record('kill-proof',dict(kind='kill',dungeon=sequence(condition['m_eDungeonID'])[0],level=30,npc=sequence(condition['m_eKillNPCID'])[0]),b'kill'))
                action(0xf4,6990)
                book=next(i for i in account.get_inventory_snapshot()['items'] if i['template']==276289)
                seq+=1
                payload=struct.pack('>QQiiIB',book['uid'],0,0,0,0,0)
                record(session.handle(Event(0x202,kind=0x219,payload=payload),seq))
                self.assertEqual(account.character()['skill_seal_groups'],(2,))
            else:
                qid=103030 if route=='elsword' else 53672
                action(0xee,qid)
                if route=='elsword':
                    record(quest.record('job-clear',dict(kind='clear',dungeon=30182,level=15,rank=None),b'job-clear'))
                else:
                    # Same accepted talk objective fixture as the frozen test.
                    with closing(sqlite3.connect(path)) as db,db:
                        db.execute('UPDATE character_quests SET objectives=? WHERE owner=1001 AND quest=53672',(json.dumps({28030:1}),))
                action(0xf4,qid)
                action(0xf4,qid,retry=True)
                self.assertEqual(account.character()['unit_class'],10 if route=='elsword' else 92)
            return replies

    def test_current_quest_flows_preserve_each_native_event_and_replay(self):
        for route in ('book','elsword','lithia'):
            with self.subTest(route=route):
                old=self.quest_route(route,old=True)
                new=self.quest_route(route,old=False)
                self.assertEqual(new,old)
                OBSERVATIONS['flow-'+route]=[
                    [{'kind':hex(kind),'length':len(wire),'sha256':sha256(wire).hexdigest()} for kind,wire in group]
                    for group in new]


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProjectionContractTests))
    report = {'channel':RUNTIME.name,'source_sha256':SOURCE_SHA,'baseline_sha256':BASE_SHA,
              'test_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
              'tests_run':result.testsRun,'success':result.wasSuccessful(),
              'failures':[(str(t),s) for t,s in result.failures],
              'errors':[(str(t),s) for t,s in result.errors], 'native_bytes':OBSERVATIONS,
              'scope':'Owned synthetic SQLite and unchanged static catalogs only; no native process, production, service or deployment test'}
    (TASK/('projection-contract-'+RUNTIME.name+'.json')).write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
