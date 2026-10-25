"""9450 keeps source/lease authentication and exact original quest admissions."""
import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from els_server.domain import story_controller_retirements as target
from els_server.domain import dungeon_flow
from els_server.domain.dungeon_lifecycle import death_report
from els_server.domain.seal_quests import quest_catalog
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.seal_quests import QuestState
from test_tunnel_native_retirements import WitnessStore
from test_lithia_memory8_offfield_expiry import OWNER,run_stage,session,event_for

def identity(row):return (row['dungeon'],row['stage'],row['part'],row['template'],row['source']['source_index'])

def fixture(rule,quest=0):
    run=run_stage(rule['stage'],rule['part'],rule['dungeon'])
    s=session(run)
    npc=next(n for n in run.current['npcs'] if n['template']==rule['template'] and n['source_index']==rule['source']['source_index'])
    e=event_for(run,npc['key']);r=death_report(e.payload)
    return s,e,r,WitnessStore(quest)

def call(s,e,r,state):
    with patch('els_server.domain.quest_flow.store',return_value=state):return target.handle(s,e,r)

class Memory8Retirements(unittest.TestCase):
    @property
    def rules(self):return [r for r in target.RULES if r['template']==9450 and r['dungeon'] in (35320,35321)]

    def test_only_two_original_source_gates_change(self):
        self.assertEqual([identity(r) for r in target.RULES if r.get('retirement_admission_quests')],[(35320,1,0,9450,10),(35321,0,0,9450,10)])
        self.assertFalse(any(r.get('retire_without_quest') for r in target.RULES))
        for rule in self.rules:self.assertEqual(rule['retirement_admission_quests'],rule['map_quests'])

    def test_original_map_quest_state_or_objective_accepts_and_replays(self):
        for rule in self.rules:
            for quest in rule['map_quests']:
                with self.subTest(source=identity(rule),quest=quest):
                    s,e,r,state=fixture(rule,quest)
                    try:
                        self.assertEqual([x.kind for x in call(s,e,r,state)],[0xae,0xaf])
                        self.assertEqual([x.kind for x in call(s,e,r,state)],[0xae])
                        self.assertEqual(state.calls,1);self.assertEqual(s.dungeon_run.defeated,{r['index']:e.payload})
                    finally:state.db.close()

    def test_no_quest_or_other_map_quest_does_not_admit(self):
        for rule in self.rules:
            for quest in (0,99999)+((28540,) if rule['dungeon']==35321 else ()):
                s,e,r,state=fixture(rule,quest)
                try:
                    self.assertEqual(call(s,e,r,state),[]);self.assertFalse(s.dungeon_run.defeated)
                finally:state.db.close()

    def test_source_owner_graph_hp_unit_and_lease_reject(self):
        for change in ('source','owner','graph','hp','unit','lease'):
            s,e,r,state=fixture(self.rules[0],28540)
            if change=='source':s.dungeon_run.current['npcs'][r['index']]['points']=[999999]
            if change=='owner':r['readiness']={OWNER+1:0}
            if change=='graph':s.dungeon_run.graph['source_sha256']='0'*64
            if change=='hp':r['hp_bits']=0
            if change=='unit':s.account.character=lambda:{'unit_type':16,'level':70}
            if change=='lease':s.application.playing[71]=object()
            try:
                self.assertEqual(call(s,e,r,state),[]);self.assertFalse(s.dungeon_run.defeated);self.assertEqual(state.calls,0)
            finally:state.db.close()

    def test_prepare_failure_keeps_controller_and_gate_pending(self):
        s,e,r,state=fixture(self.rules[0],28540);state.fail_prepare=True
        try:
            with self.assertRaises(RuntimeError):call(s,e,r,state)
            self.assertFalse(s.dungeon_run.defeated);self.assertIsNone(s.dungeon_run.next)
        finally:state.db.close()

    def test_controller_cannot_fall_through_to_generic_expiry_or_player_kill(self):
        s,e,r,state=fixture(self.rules[0],28540)
        try:
            with patch('els_server.domain.story_controller_retirements.handle',return_value=None):
                self.assertEqual(dungeon_flow.handle(s,e),[])
            r['flag']=1
            self.assertEqual(call(s,e,r,state),[])
            self.assertFalse(s.dungeon_run.defeated);self.assertEqual(state.calls,0)
        finally:state.db.close()

    def test_real_sqlite_visit_does_not_grant_objective_and_active_objective_progresses_once(self):
        for quest,expected in ((28540,0),(28550,1)):
            with self.subTest(quest=quest),tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'private-retirement.db'
                a=LocalAccount(LocalState(path));a.enable_characters()
                state=QuestState(path,account_id=1);state.snapshot()
                with closing(sqlite3.connect(path)) as db,db:
                    db.execute('UPDATE characters SET unit_type=15,level=70 WHERE uid=?',(OWNER,))
                    db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(OWNER,quest,1,1,json.dumps({quest:0})))
                s,e,r,unused=fixture(self.rules[0]);unused.db.close()
                # Use the same real owner/account pair in lease and SQL checks.
                s.account.account_id=1;s.identity={'id':1};s.application.playing={1:s};s.application.accounts={1:s.account.root}
                reply=call(s,e,r,state)
                self.assertEqual([x.kind for x in reply],[0xae,0xaf]+([0xf3] if expected else []))
                self.assertEqual([x.kind for x in call(s,e,r,state)],[0xae])
                with closing(sqlite3.connect(path)) as db,db:
                    counts=json.loads(db.execute('SELECT objectives FROM character_quests WHERE owner=? AND quest=?',(OWNER,quest)).fetchone()[0])
                    self.assertEqual(counts[str(quest)],expected)
                    self.assertEqual(db.execute('SELECT count(*) FROM quest_progress_events WHERE owner=?',(OWNER,)).fetchone()[0],1)
                    self.assertEqual(db.execute('SELECT count(*) FROM completed_quests WHERE owner=?',(OWNER,)).fetchone()[0],0)

if __name__=='__main__':unittest.main()
