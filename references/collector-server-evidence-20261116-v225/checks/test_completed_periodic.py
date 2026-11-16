"""Original route and HP guards, in memory only; no account/server/client."""
import importlib.util
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
import argparse
options = argparse.ArgumentParser(add_help=False)
options.add_argument('--runtime', type=Path, required=True)
arguments, remaining = options.parse_known_args()
sys.argv[1:] = remaining
RUNTIME = arguments.runtime.resolve(strict=True)
sys.path[:0]=[str(RUNTIME),str(RUNTIME/'vendor')]
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_hp_c1 import _Context
from els_server.domain.local_session import SessionOrderError

def load(folder):
    spec=importlib.util.spec_from_file_location('periodic_'+folder,(RUNTIME if folder == 'base' else ROOT/'source')/'els_server/periodic_work.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.next_poll_deadline

old=load('base');fixed=load('candidate')
class Session(SimpleNamespace):__hash__=object.__hash__

class CompletedPeriodicTests(unittest.TestCase):
    def setUp(self):
        run=DungeonRun(34320,'00000000-0000-0000-0000-000000000001');run._load_stage(3)
        account=SimpleNamespace(uid=1,account_id=7,store=object())
        self.app=SimpleNamespace(world=SimpleNamespace(party_of={},pvp=SimpleNamespace(room=lambda s:None),
            racing=SimpleNamespace(room=lambda s:None),field_bosses=SimpleNamespace(room=lambda s:None)))
        self.now=time.monotonic()
        self.session=Session(account=account,application=self.app,_periodic_idle=lambda:True,role='game',phase='dungeon_active',released=False,
            next_periodic=self.now+1,dungeon_run=run,dungeon_substage_synced=True,part_end_notified=True,clear_notified=False,dungeon_failed=False,
            dungeon_id=34320,dungeon_participants=frozenset((1,)),reward_test=True,reward_run_id=run.run_id)
        hp=_Context(self.session,34320,run.run_id,0);hp.run=run;hp.preparing=False;self.session._c1_hp_context=hp;run.hp_context=hp
        # No synthetic Application/authentication environment. Only the owner
        # lookup is substituted; the real lifecycle/HP predicates still run.
        self.lease=patch.object(_Context,'_valid_lease',return_value=True);self.lease.start();self.addCleanup(self.lease.stop)

    def test_original_completed_state_fails_fixed_state_retains_upkeep(self):
        self.session.clear_notified=True
        with self.assertRaisesRegex(SessionOrderError,'C1 HP instance lease/phase changed'):
            old(self.app,self.session,self.now)
        self.assertEqual(fixed(self.app,self.session,self.now),self.now+1)

    def test_failed_dungeon_also_has_closed_hp_lease(self):
        self.session.dungeon_failed=True
        with self.assertRaises(SessionOrderError):old(self.app,self.session,self.now)
        self.assertEqual(fixed(self.app,self.session,self.now),self.now+1)

    def test_active_native_gate_keeps_original_schedule(self):
        self.assertEqual(fixed(self.app,self.session,self.now),old(self.app,self.session,self.now))

    def test_active_invalid_hp_context_still_refused(self):
        self.session.reward_run_id='different-run'
        with self.assertRaises(SessionOrderError):fixed(self.app,self.session,self.now)

    def test_pending_notifications_still_run_immediately(self):
        self.session.clear_notified=True;self.session._periodic_pending=True
        self.assertEqual(fixed(self.app,self.session,self.now),self.now)

if __name__=='__main__':unittest.main(verbosity=2)
