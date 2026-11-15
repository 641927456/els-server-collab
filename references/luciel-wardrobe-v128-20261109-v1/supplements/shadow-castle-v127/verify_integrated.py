"""Controlled 17-5 route regression against an integrated runtime.

No native combat, player databases, network listener or runtime modifications.
Usage: python -B verify_integrated.py --runtime <runtime> --output <result.json>
"""
import argparse
import asyncio
import hashlib
import json
import sqlite3
import struct
import sys
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
runtime = args.runtime.resolve()
output = args.output.resolve()
assert output.parent.is_dir()
sys.dont_write_bytecode = True
sys.path[:0] = [str(runtime), str(runtime/'tools/pylibs')]

from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.accounts import Accounts
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState, ensure_local_tables
from els_server.storage.reward_state import ensure_reward_tables
from els_server.storage.inventory_state import ensure_inventory
from els_server.storage.seal_quests import QuestState
from els_server.domain.local_session import LocalAccount
from els_server.domain.dungeon_routes import DungeonRun
from els_server.domain.region_quests import region_catalog
from els_server.domain.dungeon_result_rules import admission_power
from els_server.domain import dungeon_flow as flow
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event, encode_event


class Owned:
    def __init__(self):
        self.temp = tempfile.TemporaryDirectory(prefix='owned-castle-', dir=output.parent)
        self.path = Path(self.temp.name)/'game.sqlite3'
        registry = Accounts(Path(self.temp.name)/'accounts.sqlite3')
        identity = registry.create('castleqa')
        with closing(sqlite3.connect(self.path)) as db, db:
            ensure_local_tables(db)
            ensure_reward_tables(db)
            ensure_inventory(db)
        uid = Characters(self.path, identity['id']).create(
            'CastleOnlyQA', 1, 'castle-route-fixture', quick_start=True)['uid']
        self.root = LocalAccount(LocalState(self.path, uid), identity['id'], identity['name'])
        self.root.enable_characters()
        self.account = self.root.for_character(uid)
        self.account.get_inventory_snapshot()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('UPDATE characters SET unit_class=150,level=99,transcendence=1 WHERE uid=?', (uid,))
            required = {region_catalog().data['regions'][str(r)]['requirement'].get('RequireQuestID')
                for r in region_catalog().data['dungeons']['34800']
                if str(r) in region_catalog().data['regions']} - {None, 0}
            db.executemany('INSERT OR IGNORE INTO completed_quests VALUES (?,?,?,?)',
                [(uid, quest, 1, '{}') for quest in required])
        QuestState(self.path, uid, account_id=identity['id']).snapshot()
        self.app = Application(ServerConfig(state_file=self.path, accounts_file=registry.path))
        self.app.registry = registry
        self.app.accounts[identity['id']] = self.root
        self.loop = asyncio.new_event_loop()
        self.loop.run_until_complete(self.app.call(self.app.checkpoints.prepare))
        self.s = self.loop.run_until_complete(self.app.session(
            identity={key:identity[key] for key in ('id', 'name')}))
        self.s.account = self.account
        self.app.playing[identity['id']] = self.s
        s = self.s
        s.role = 'game'
        s.phase = 'dungeon_active'
        s.active_map = 20000
        s.completed.update((0x28, 0x225, 0x227))
        s.reward_test = s.item_test = s.drop_probe = s.drop_test = s.population_test = True
        s.dungeon_return_pending = False
        self.clock = [0.]
        self.sequence = 100
        s.reward_run_id = str(uuid.uuid4())
        s.dungeon_run = DungeonRun(34800, s.reward_run_id, clock=lambda:self.clock[0])
        s.dungeon_id = 34800
        s.gate_stage = 0
        s.dungeon_substage_synced = True
        s.gate_stage_loading = False
        s.dungeon_failed = False
        s.dungeon_participants = frozenset((uid,))
        s.defeated_npcs = s.dungeon_run.defeated
        s.dungeon_run.loaded()
        s.dungeon_clock.resume()
        s.dungeon_result_power = admission_power(s)

    def dispatch(self, event):
        self.sequence += 1
        return self.loop.run_until_complete(self.app.call(self.s.handle, event, self.sequence))

    def sql_hash(self):
        with closing(sqlite3.connect(self.path)) as db:
            return hashlib.sha256('\n'.join(db.iterdump()).encode('utf8')).hexdigest()

    def close(self):
        self.app.close()
        self.loop.close()
        self.temp.cleanup()


def death(npc, owner, retirement=False):
    killer = 2**64-1 if retirement else owner
    raw = struct.pack('>iBQQ6fBf', npc['key'], 255 if retirement else 0,
        killer, killer, 0, 0, 0, 0, 0, 0, 1, npc['hp'])
    raw += struct.pack('>IIQBQIQ', 0, 1, owner, 0, 0, 0, 0 if retirement else owner)
    return Event(0x202, performers=(0,), kind=0xad, payload=raw)


def part_event(kind, part):
    return Event(0x202, performers=(0,), kind=kind, payload=struct.pack('>b', part))


def condition(run):
    flags = bytes([1]*len(run.current['conditions']))
    return Event(0x202, performers=(0,), kind=0x471,
        payload=struct.pack('>iiHI', run.native_stage, run.part, 0, len(flags))+flags+b'\0')


def traverse(shortcut):
    f = Owned()
    try:
        s = f.s
        rooms = []
        notices = []
        rejected = 0
        for _ in range(18):
            run = s.dungeon_run
            cursor = (run.stage, run.part)
            assert cursor not in rooms, cursor
            rooms.append(cursor)
            premature = f.dispatch(condition(run))
            assert [e.kind for e in premature] == [0x472]
            assert struct.unpack_from('>i', premature[0].payload)[0] == 1836
            rejected += 1
            for npc in tuple(run.current['npcs']):
                native = client_data().npc(npc['template'])
                if native['class_id'] == 0 and npc['active'] and run.stage != 2:
                    out = f.dispatch(death(npc, s.account.uid))
                    assert any(e.kind == 0xae for e in out), (cursor, npc['template'])
            for npc in tuple(run.current['npcs']):
                if client_data().npc(npc['template'])['class_id'] != 103:
                    continue
                if run.stage == 2 and npc['template'] != (8397 if shortcut else 8432):
                    continue
                e = death(npc, s.account.uid, retirement=True)
                assert any(r.kind == 0xae for r in f.dispatch(e))
                assert [r.kind for r in f.dispatch(e)] == [0xae]
            flow.periodic(s)
            f.clock[0] += 4
            flow.periodic(s)
            assert run.next is not None and not s.clear_notified
            if run.next.get('curtain_opened'):
                f.dispatch(part_event(0xb8, run.next['part']))
            assert s.part_end_notified
            ending = part_event(0xbb, run.next['part'] if run.next.get('curtain_opened') else run.part)
            events = f.dispatch(ending)
            for e in events:
                encode_event(e)
            if s.clear_notified:
                assert any(e.kind == 0xc1 for e in events)
                assert ((3, 0) not in rooms) == shortcut
                before = f.sql_hash()
                assert not any(e.kind == 0xc1 for e in f.dispatch(ending))
                assert before == f.sql_hash()
                cold = LocalAccount(LocalState(f.path, s.account.uid)).get_inventory_snapshot()
                assert cold == s.account.get_inventory_snapshot()
                return dict(ok=True, shortcut=shortcut, rooms=rooms,
                    premature_condition_rejections=rejected, platform_notifications=notices,
                    C1=True, repeat_BB_no_SQL_delta=True, cold_inventory_equal=True,
                    midboss_body_not_killed=True)
            if not s.dungeon_substage_synced:
                loaded = f.dispatch(Event(0x202, performers=(0,), kind=0xb3, payload=bytes(9)))
                actual = [struct.unpack('>i', e.payload)[0] for e in loaded if e.kind == 0x30c]
                expected = list(range(1, 86 if run.stage == 1 else 56, 2)) if run.stage in (1, 3) else []
                assert actual == expected, (run.stage, actual)
                if actual:
                    notices.append(dict(stage=run.stage, count=len(actual)))
                repeated = f.dispatch(Event(0x202, performers=(0,), kind=0xb3, payload=bytes(9)))
                assert not any(e.kind == 0x30c for e in repeated)
        raise AssertionError('Original room budget exceeded')
    finally:
        f.close()


result = dict(runtime=str(runtime), actual_Application=True, actual_SQL=True,
    original_admission_used=False, controlled_starting_fixture=True,
    actual_network=False, natural_combat=False, natural_AI=False, natural_GUI=False,
    production_data_used=False, production_files_changed=False,
    routes=[traverse(True), traverse(False)], temporary_databases_removed=True)
result['ok'] = all(row['ok'] for row in result['routes'])
result['source_sha256'] = {name:hashlib.sha256((runtime/name).read_bytes()).hexdigest()
    for name in ('els_server/domain/dungeon_flow.py', 'els_server/domain/dungeon_routes.py',
        'els_server/domain/local_session.py', 'els_server/domain/scene_actor_retirements.py',
        'els_server/domain/scene_retirement_sources.py', 'els_server/data/client/dungeon_routes.json')}
output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps(result, ensure_ascii=False))
