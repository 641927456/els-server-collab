"""Resource-free original225 admission block tests, not full session/TLS proof."""
import ast
import copy
from contextlib import closing
import math
import sqlite3
import struct
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import ModuleType,SimpleNamespace as NS
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

def source_gate():
    text=(ROOT/'els_server/domain/local_session.py').read_text(encoding='utf8')
    start=text.index('                native_varnimyr_rest=False')
    end=text.index("\n                warp=getattr(self,'town_warp_transition',None)",start)
    block=textwrap.dedent(text[start:end])
    env={'i32':lambda n:struct.pack('>i',n),'TOWN_SCENES':{1009:851},
         'Event':lambda event_id,**kw:NS(event_id=event_id,**kw)}
    exec(compile('def gate(self,event,request_sequence,requested):\n'+textwrap.indent(block,'    ')+'\n    return native_varnimyr_rest\n','<actual-225-block>','exec'),env)
    return env['gate'],env

class VarnimyrRestEntry(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'model.sqlite3'
        with closing(sqlite3.connect(self.path)) as db,db:
            db.executescript('CREATE TABLE characters(uid,account_id,unit_type,level); CREATE TABLE completed_quests(owner,quest); CREATE TABLE character_quests(owner,quest); CREATE TABLE dungeon_records(uid,map_id); CREATE TABLE location(uid,town);')
            db.execute('INSERT INTO characters VALUES(1,9,1,99)')
            db.execute('INSERT INTO completed_quests VALUES(1,26640)')
            db.execute('INSERT INTO location VALUES(1,20010)')
        self.cached_town=20010
        self.session=NS(client_build='dx11_260923',enter_town=True,role='game',phase='town_ready',
                        account=NS(uid=1,account_id=9,characters=object(),store=NS(path=self.path,uid=1),
                                   get_location=lambda:{'map':self.cached_town}),
                        active_map=20010,dungeon_return_pending=False,actor_current=True)
        self.event=NS(payload=struct.pack('>i',1009)+b'\0',performers=(0,),uid=2**64-1,target_uid=2**64-1,payload_mode=0)
        self.gate,self.env=source_gate()
        # Isolate the admission block from resource-backed full character
        # loading. These stand-ins read real private model SQL, enforce owner,
        # and never manufacture persistent progress or exercise full loading.
        module=ModuleType('els_server.storage.seal_quests')
        def load(db,uid,account_id):
            row=db.execute('SELECT unit_type,level,account_id FROM characters WHERE uid=?',(uid,)).fetchone()
            if row is None or row[2]!=account_id:raise ValueError('Owner mismatch')
            return {'unit_type':row[0],'level':row[1]}
        module.load_character=load
        module.completed_ids=lambda db,uid:{r[0] for r in db.execute('SELECT quest FROM completed_quests WHERE owner=?',(uid,))}
        actor=ModuleType('els_server.domain.town_travel_flow')
        # Only the source block is under test. Real lease/registry behavior is
        # covered by the separately bound originalApplication private proofs.
        actor._ordinary_actor=lambda s:s.actor_current and s.account.store.uid==s.account.uid
        self.patch=patch.dict(sys.modules,{'els_server.storage.seal_quests':module,
                                         'els_server.domain.town_travel_flow':actor})
        self.patch.start();self.addCleanup(self.patch.stop)

    def sql(self,query,*values):
        with closing(sqlite3.connect(self.path)) as db,db:db.execute(query,values)

    def call(self,sequence=1,requested=1009):
        before=self.path.read_bytes();state=copy.copy(vars(self.session))
        result=self.gate(self.session,self.event,sequence,requested)
        self.assertEqual(before,self.path.read_bytes());self.assertEqual(state,vars(self.session))
        return result

    def denied(self,result):
        self.assertIsInstance(result,list);self.assertEqual(len(result),1)
        self.assertEqual(result[0].kind,0x226)
        self.assertEqual(result[0].payload,struct.pack('>iiiii',-1,1009,0,0,0))

    def test_each_current_role_both_native_sources_and_saved_reader(self):
        for unit in range(1,16):
            self.sql('UPDATE characters SET unit_type=?',unit)
            for source in (20010,1010):
                self.sql('UPDATE location SET town=?',source)
                self.cached_town=self.session.active_map=source
                self.assertIs(self.call(),True)
        self.sql('UPDATE location SET town=1009');self.cached_town=1009
        self.session.phase='map_loading';self.session.active_map=None
        # Cold session deliberately has no town_warp_transition attribute.
        self.assertIs(self.call(),True)
        self.session.active_map=1009;self.assertIs(self.call(),True)
        self.session.dungeon_return_pending=True
        self.assertIs(self.call(),True)

    def test_missing_native_qualification_invalid_type_and_source_refused(self):
        cases=[('DELETE FROM completed_quests',()),('UPDATE characters SET level=98',()),
               ('UPDATE characters SET unit_type=?',(0,)),('UPDATE characters SET unit_type=?',(16,)),
               ('UPDATE location SET town=20011',())]
        original=self.path.read_bytes()
        for sql,args in cases:
            self.path.write_bytes(original);self.sql(sql,*args)
            with self.subTest(sql=sql,args=args):self.denied(self.call())
        self.path.write_bytes(original);self.sql('UPDATE characters SET account_id=10')
        with self.assertRaises(ValueError):self.call()

    def test_original_sender_stage_sequence_source_and_pending_warp_guards(self):
        for field,value in [('client_build','legacy'),('enter_town',False),('role','login'),('phase','closing'),('active_map',20011),('dungeon_return_pending',True),('town_warp_transition',{'destination':1009}),('pending_map',1011),('actor_current',False)]:
            had=hasattr(self.session,field);old=getattr(self.session,field,None);setattr(self.session,field,value)
            with self.subTest(field=field):self.denied(self.call())
            if had:setattr(self.session,field,old)
            else:delattr(self.session,field)
        for field,value in [('payload',struct.pack('>i',1009)+b'\1'),('performers',(1,)),('uid',1),('target_uid',1),('payload_mode',1)]:
            old=getattr(self.event,field);setattr(self.event,field,value)
            with self.subTest(field=field):self.denied(self.call())
            setattr(self.event,field,old)
        for sequence in (0,2**32,True,None):self.denied(self.call(sequence))
        self.env['TOWN_SCENES'][1009]=852;self.denied(self.call())

    def test_no_unrelated_clear_or_arrival_task_is_required(self):
        # Native99+26640 works with no traditionalRuben clear and no22375.
        self.assertIs(self.call(),True)
        self.sql('INSERT INTO character_quests VALUES(1,22375)')
        self.assertIs(self.call(),True)
        self.sql('INSERT INTO dungeon_records VALUES(1,30092)')
        self.assertIs(self.call(),True)
        self.cached_town=1010;self.denied(self.call())

    def test_other_destinations_are_not_intercepted(self):
        self.assertIs(self.call(requested=20010),False)

    def test_scene_mapping_reuses_unchanged_location_validation(self):
        tree=ast.parse((ROOT/'els_server/storage/local_state.py').read_text(encoding='utf8'))
        assign=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='TOWN_SCENES' for t in n.targets))
        scenes=ast.literal_eval(assign.value);self.assertEqual(scenes[1009],851)
        node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='validate_location')
        env={'TOWN_SCENES':scenes,'math':math};exec(compile(ast.Module(body=[node],type_ignores=[]),'<existing-validator>','exec'),env)
        env['validate_location'](1009,0,0,(-2475.,1600.,425.))
        for args in ((1009,255,0,(0,0,0)),(1009,0,101,(0,0,0)),(1009,0,0,(float('nan'),0,0)),(99999,0,0,(0,0,0))):
            with self.assertRaises(ValueError):env['validate_location'](*args)

if __name__=='__main__':unittest.main()
