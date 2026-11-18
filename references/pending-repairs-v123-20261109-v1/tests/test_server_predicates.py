"""Execute real source predicates with inert, explicitly synthetic collaborators.

Imports are fixture modules, not the game catalog or a running application.
No socket, database, game, native code or global repository source is loaded.
"""
import ast
from contextlib import contextmanager
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest

AREA = Path(__file__).resolve().parents[1]


def production_function(variant, filename, name, class_name=None):
    path = AREA / variant / 'els_server/domain' / filename
    tree = ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
    nodes = tree.body if class_name is None else next(
        n.body for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    function = next(n for n in nodes if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), path.name, 'exec'), namespace)
    return namespace[name]


class Application:
    pass


class FriendsSession:
    pass


class DungeonClock:
    started = 1.0


class DungeonRun:
    pass


@contextmanager
def admission_fixture(encounter):
    catalog = NS(_data={'routes': {'35080': {}}}, graph=lambda _: {'source_sha256': 'fixture'})
    modules = {
        'els_server.application': dict(Application=Application, FriendsSession=FriendsSession),
        'els_server.domain.equipment_chip_flow': dict(current_lease=lambda s: s.lease_valid),
        'els_server.domain.dungeon_clock': dict(DungeonClock=DungeonClock),
        'els_server.domain.dungeon_routes': dict(DungeonRun=DungeonRun, route_catalog=lambda: catalog),
        'els_server.domain.event_dungeons': dict(is_reviewed=lambda _: False),
        'els_server.domain.raid_party': dict(raid_definition=lambda _: None),
        'els_server.domain.daily_ticket_rules': dict(giant_definitions=lambda: {}),
        'els_server.game_data': dict(client_data=lambda: NS(dungeon=lambda _: {'m_eDungeonType': 1})),
    }
    saved = {name: sys.modules.get(name) for name in modules}
    for name, values in modules.items():
        module = ModuleType(name)
        module.__dict__.update(values)
        sys.modules[name] = module
    application, session, run = Application(), FriendsSession(), DungeonRun()
    # A relative sentinel path is compared, never opened or created.
    application.config = NS(mode='friends', state_file='unused-fixture.sqlite3')
    application.world = NS(party_of={}, members=set(), dungeons=NS(transport_room=lambda _: None))
    application.registry = NS(enabled=lambda _: True)
    run.__dict__.update(identity=35080, stage=0, catalog=catalog, encounter=encounter,
        graph={'source_sha256': 'fixture'}, part=0, parts={0: {}}, started_at=1.0,
        run_id='00000000-0000-4000-8000-000000000001')
    session.__dict__.update(account=NS(account_id=1, uid=2, store=NS(path='unused-fixture.sqlite3')),
        role='game', client_build='dx11_260923', item_test=True, lease_valid=True,
        social_overflow=False, coop_error=False, enter_dungeon=True, population_test=True,
        phase='dungeon_active', dungeon_substage_synced=True, gate_stage_loading=False,
        dungeon_return_pending=False, clear_notified=False, dungeon_failed=False,
        reward_receipt=None, dungeon_end_payload=None, dungeon_requested=False,
        requested_dungeon_id=None, requested_dungeon_mode=None,
        dungeon_participants=frozenset((2,)), dungeon_clock=DungeonClock(),
        part_end_notified=False, dungeon_id=35080, dungeon_run=run, gate_stage=0,
        reward_test=True, reward_run_id=run.run_id)
    try:
        yield session, application
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class ServerPredicates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admission = {v: production_function(v, 'apple_consumables.py', '_normal_solo_stage_ready')
                         for v in ('baseline', 'source')}
        cls.condition = {v: production_function(v, 'dungeon_routes.py', 'condition_ready', 'DungeonRun')
                         for v in ('baseline', 'source')}

    def test_gold_castle_admission_catches_baseline_defect(self):
        with admission_fixture({'kind': 'gold_castle'}) as (session, app):
            self.assertFalse(self.admission['baseline'](session, app))
            self.assertTrue(self.admission['source'](session, app))

    def test_ordinary_and_other_encounter_boundaries(self):
        for encounter, expected in ((None, True), ({'kind': 'henir_local_rotation'}, False)):
            with self.subTest(encounter=encounter), admission_fixture(encounter) as (session, app):
                for function in self.admission.values():
                    self.assertEqual(function(session, app), expected)

    def test_session_guards_remain_required(self):
        for field, value in (('lease_valid', False), ('gate_stage_loading', True),
                             ('clear_notified', True), ('reward_receipt', object()),
                             ('dungeon_participants', frozenset((2, 3))),
                             ('reward_run_id', '00000000-0000-4000-8000-000000000002')):
            with self.subTest(field=field), admission_fixture({'kind': 'gold_castle'}) as (session, app):
                self.assertTrue(self.admission['source'](session, app))
                setattr(session, field, value)
                self.assertFalse(self.admission['source'](session, app))

    def test_run_identity_and_clock_guards(self):
        for field, value in (('identity', 30000), ('stage', 1), ('started_at', float('nan')),
                             ('run_id', 'not-a-uuid'), ('catalog', object())):
            with self.subTest(field=field), admission_fixture({'kind': 'gold_castle'}) as (session, app):
                setattr(session.dungeon_run, field, value)
                self.assertFalse(self.admission['source'](session, app))
        with admission_fixture({'kind': 'gold_castle'}) as (session, app):
            session.dungeon_clock.started = None
            self.assertFalse(self.admission['source'](session, app))
            session.part_end_notified = True
            self.assertTrue(self.admission['source'](session, app))

    def make_gate(self, completed=(), retired=True, destination=4):
        run = NS(encounter={'kind': 'gold_castle', 'hub': 0, 'boss': 4, 'wings': [1, 2, 3]},
            stage=0, part=0, identity=35080, completed_stages=set(completed),
            current={'npcs': [{'key': 10, 'template': 8832}]}, defeated={10: 1} if retired else {})
        condition = {'kind': 3, 'required': [8832], 'next': [{'stage': destination}]}
        return run, condition

    def test_each_single_wing_unlocks_boss_and_baseline_fails(self):
        for wing in (1, 2, 3):
            with self.subTest(wing=wing):
                run, condition = self.make_gate((wing,))
                self.assertFalse(self.condition['baseline'](run, condition))
                self.assertTrue(self.condition['source'](run, condition))

    def test_gate_still_requires_wing_and_original_retirement(self):
        for completed, retired in (((), True), ((1,), False), ((2,), False), ((3,), False)):
            with self.subTest(completed=completed, retired=retired):
                run, condition = self.make_gate(completed, retired)
                self.assertFalse(self.condition['source'](run, condition))

    def test_completed_destination_remains_refused(self):
        for destination in (1, 2, 3, 4):
            with self.subTest(destination=destination):
                run, condition = self.make_gate((1, 2, 3, 4), destination=destination)
                self.assertFalse(self.condition['source'](run, condition))

    def test_missing_actor_does_not_count_as_retired(self):
        run, condition = self.make_gate((1,))
        run.current['npcs'] = []
        self.assertFalse(self.condition['source'](run, condition))


if __name__ == '__main__':
    unittest.main(verbosity=2)
