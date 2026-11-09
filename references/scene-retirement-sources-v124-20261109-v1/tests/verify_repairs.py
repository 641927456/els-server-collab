"""Actual current dispatcher/resources with an owned ephemeral FriendsSession."""
from pathlib import Path
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
import copy
import json
import sqlite3
import struct
import sys
import tempfile
import uuid

from runtime_support import ROOT, server_root, added_rules
HERE = Path(__file__).resolve().parent
PARENT = server_root()
BASELINE = '--baseline' in sys.argv
NEGATIVES_ONLY = '--negative-only' in sys.argv
sys.path.insert(0, str(PARENT))
import els_server.domain
if not BASELINE:
    els_server.domain.__path__.insert(0, str(ROOT/'source/els_server/domain'))
from els_server.application import Application, FriendsSession
from els_server.config import ServerConfig
from els_server.domain.local_session import LocalAccount
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.dungeon_clock import DungeonClock
from els_server.domain import dungeon_flow as flow, dungeon_hp_c1 as c1, scene_actor_retirements as retirement
from els_server.domain.dungeon_lifecycle import death_report
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.storage.accounts import Accounts
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState, ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables
from els_server.storage.inventory_state import ensure_inventory

MAX = 2**64-1
rules = added_rules()
results = []

def event(npc, owner, *, flag=255):
    source = MAX if flag == 255 else owner
    payload = struct.pack('>iBQQ6fBf', npc['key'], flag, source, source, 0,0,0,0,0,0,1,npc['hp'])
    payload += struct.pack('>IIQBQIQ', 0,1,owner,0,0,0,0 if flag == 255 else owner)
    result = Event(0x202, performers=(0,), kind=0xad, payload=payload)
    death_report(payload)
    return result

def kinds(events):
    return [e.kind for e in events or ()]

def state(s):
    r=s.dungeon_run
    return copy.deepcopy((r.defeated,r.next,r.ready_at,r.current['npcs'],s.part_end_notified,
                          s.dungeon_clock.total,s.dungeon_clock.started))

with tempfile.TemporaryDirectory(prefix='owned-repair-', dir=HERE) as temp:
    directory=Path(temp)
    config=ServerConfig(mode='friends',state_file=directory/'game.sqlite3',accounts_file=directory/'accounts.sqlite3',
                        log_dir=directory/'logs',tls_cert=directory/'unused.pem',tls_key=directory/'unused-key.pem')
    app=Application(config)
    try:
        app.registry=Accounts(config.accounts_file)
        identity=app.registry.create('owned_repair')
        with closing(sqlite3.connect(config.state_file)) as db,db:
            ensure_local_tables(db);ensure_reward_tables(db);ensure_inventory(db)
        uid=Characters(config.state_file,identity['id']).create('RepairQA',1,'owned-repair')['uid']
        account=LocalAccount(LocalState(config.state_file,uid),identity['id'],identity['name'])
        account.enable_characters();account.enable_rewards();account.get_inventory_snapshot()
        with closing(sqlite3.connect(config.state_file)) as db,db:
            db.execute('UPDATE characters SET level=99 WHERE uid=?',(uid,))
        app.accounts[identity['id']]=account

        def fixture(rule, *, clear_others=False):
            s=FriendsSession(app,identity,account,**config.session_options())
            app.playing[identity['id']]=s
            s.role='game';s.client_build='dx11_260923';s.phase='town_ready'
            s.item_test=True;s.population_test=True
            s.dungeon_requested=True;s.requested_dungeon_id=rule['dungeon'];s.requested_dungeon_mode=2
            seed=str(uuid.uuid4())
            context=c1.prepare(s,Event(0x202,kind=0x37f),rule['dungeon'],seed,None)
            assert context is not None
            r=DungeonRun(rule['dungeon'],seed,hp_context=context)
            s.dungeon_run=r;s.dungeon_id=rule['dungeon'];s.dungeon_participants=frozenset((uid,))
            s.dungeon_failed=False;s.phase='dungeon_loading';s._c1_hp_context=context;s.reward_run_id=seed
            context.activate(r);r._load_stage(rule['stage']);r.part=rule['part']
            s.phase='dungeon_active';s.dungeon_substage_synced=True;s.part_end_notified=False
            s.gate_stage=rule['stage'];s.gate_stage_loading=False;s.clear_notified=False
            s.dungeon_clock=DungeonClock();s.dungeon_clock.resume();r.loaded()
            npc=next(n for n in r.current['npcs'] if n['template']==rule['source']['template']
                     and n['source_index']==rule['source']['source_index'])
            if clear_others:
                r.defeated={n['key']:b'previously accepted ordinary kill fixture' for n in r.current['npcs']
                            if n['active'] and n is not npc}
            s.defeated_npcs=r.defeated
            return s,npc

        observed=next(r for r in rules if (r['dungeon'],r['stage'],r['part'],r['source']['source_index'])==(34760,0,1,6))
        if not NEGATIVES_ONLY:
            # Reproduce the observed second glass door with its exact source key28.
            observed=next(r for r in rules if (r['dungeon'],r['stage'],r['part'],r['source']['source_index'])==(34760,0,1,6))
            s,npc=fixture(observed,clear_others=True)
            assert npc['key']==28
            request=event(npc,uid)
            before=state(s)
            reply=flow.handle(s,request,2110)
            if BASELINE:
                assert reply==[] and state(s)==before
                assert flow.periodic(s)==[]
                results.append('observed_native255_rejected_and_gate_stays_closed')
            else:
                assert kinds(reply)==[0xae,0xaf,0xb7],kinds(reply)
                assert s.dungeon_run.part==1 and not s.part_end_notified
                assert reply[-1].payload==b'\2'
                assert flow.curtain_token(s) is not None
                assert kinds(flow.handle(s,request,2110))==[0xae]
                assert kinds(flow.handle(s,request,2111))==[0xae]
                arrival=Event(0x202,kind=0xb8,payload=b'\2')
                assert kinds(flow.handle(s,arrival))==[0xb9,0xba]
                assert kinds(flow.handle(s,arrival))==[0xb9]
                assert kinds(flow.handle(s,Event(0x202,kind=0xbb,payload=b'\2')))==[0xbc,0xbd]
                assert s.dungeon_run.part==2 and not s.part_end_notified
                assert kinds(flow.handle(s,request,2110))==[0xae]
                assert kinds(flow.handle(s,Event(0x202,kind=0xbb,payload=b'\2')))==[0xbc]
                results.append('observed_gate_B7_then_arrival_B9_BA_then_BC_BD_and_replays')

                # Every added declaration uses the existing current native HP and
                # retirement receiver. No kill, currency, experience or loot route.
                for rule in rules:
                    s,npc=fixture(rule)
                    assert retirement.source_rule(s.dungeon_run,npc) is not None
                    request=event(npc,uid)
                    with patch('els_server.domain.pve_economy_flow.prepared_death',side_effect=AssertionError('Unexpected economy dispatch')):
                        reply=flow.handle(s,request,3001)
                        assert kinds(reply)==[0xae,0xaf],(rule,kinds(reply))
                        assert kinds(flow.handle(s,request,3001))==[0xae]
                    assert npc['active'] is False and s.dungeon_run.defeated[npc['key']]==request.payload
                    assert not s.world_drops and not s.clear_notified
                results.append('all_27_sources_native255_and_replay_without_economy')

                # Remaining active enemies still prevent opening. Ordinary kills
                # retain the original economic dispatcher; unrelated templates are
                # not admitted by the new declarations.
                s,npc=fixture(observed)
                assert kinds(flow.handle(s,event(npc,uid),4001))==[0xae,0xaf]
                assert flow.periodic(s)==[]
                s,npc=fixture(observed)
                marker=[Event(0x201,kind=0xae,payload=bytes(4))]
                with patch('els_server.domain.pve_economy_flow.prepared_death',return_value=marker) as ordinary:
                    assert flow.handle(s,event(npc,uid,flag=1),4002)==marker
                    ordinary.assert_called_once()
                unrelated=next(n for n in s.dungeon_run.current['npcs'] if n['template']==8287)
                assert flow.handle(s,event(unrelated,uid),4003)==[]
                results.append('remaining_enemy_blocks_ordinary_kill_preserved_unrelated_rejected')

                # An encoding failure cannot retire an actor or partially open a gate.
                s,npc=fixture(observed,clear_others=True);before=state(s)
                def fail_open(e):
                    if e.kind==0xb7: raise RuntimeError('controlled B7 encode failure')
                    return encode_event(e)
                with patch('els_server.protocol.protocol_codec.encode_event',side_effect=fail_open):
                    try:flow.handle(s,event(npc,uid),5001)
                    except RuntimeError as error:assert str(error)=='controlled B7 encode failure'
                    else:raise AssertionError('Expected encoding failure')
                assert state(s)==before
                results.append('encode_failure_preserves_actor_gate_clock')

        if not BASELINE:
            for mutation in ('owner','hp','source','graph','lease','generation','loading','performer'):
                s,npc=fixture(observed);request=event(npc,uid)
                if mutation=='owner':request=event(npc,uid+1)
                if mutation=='hp':request=event(dict(npc,hp=npc['hp']/2),uid)
                if mutation=='source':npc['start_point']=-777
                if mutation=='graph':s.dungeon_run.graph=copy.deepcopy(s.dungeon_run.graph);s.dungeon_run.graph['source_sha256']='0'*64
                if mutation=='lease':app.playing[identity['id']]=object()
                if mutation=='generation':s.reward_run_id='other'
                if mutation=='loading':s.dungeon_substage_synced=False
                if mutation=='performer':request=replace(request,performers=(1,))
                before=state(s)
                try:
                    refused=flow.handle(s,request,6001)
                except __import__('els_server.domain.local_session',fromlist=['SessionOrderError']).SessionOrderError:
                    assert mutation in ('lease','generation','loading'),mutation
                else:
                    assert refused==[],mutation
                assert state(s)==before,mutation
            results.append('eight_invalid_contexts_preserve_state')
    finally:
        if app.registry is not None:app.registry.close();app.registry=None
        app.close()
assert not directory.exists()
result=dict(ok=True,baseline=BASELINE,cases=results,temporary_store_removed=True,production_database_access=False,
            natural_GUI=False,native_client_executed=False)
print(json.dumps(result))
