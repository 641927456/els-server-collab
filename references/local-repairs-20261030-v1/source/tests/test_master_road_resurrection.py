"""Master Road deaths must reach the qualified solo resurrection lane."""
import struct
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'els_server/data'
MASTER_ROAD = (34370, 34380, 34390, 34400, 34410, 34420, 34430, 34440,
               34450, 34460, 34470, 34480, 34490, 34500, 34690, 34700)


def _session(dungeon, run):
    uid = 2
    return SimpleNamespace(
        role='game', client_build='dx11_260923', item_test=True, application=None,
        account=SimpleNamespace(uid=uid, store=SimpleNamespace(uid=uid), account_id=1, characters=None),
        identity=None, shop_session_id='master-road-resurrection',
        phase='dungeon_active', dungeon_id=dungeon, gate_stage=0, dungeon_run=run,
        reward_run_id=run.run_id if run is not None else str(uuid.uuid4()),
        dungeon_participants=frozenset((uid,)),
        enter_dungeon=True, reward_test=True, population_test=True,
        dungeon_substage_synced=True, gate_stage_loading=False, dungeon_return_pending=False,
        clear_notified=False, dungeon_failed=False, part_end_notified=False,
        reward_receipt=None, dungeon_end_payload=None, coop_error=None)


def _death(uid):
    from els_server.protocol.protocol_codec import Event
    return Event(0x202, kind=0xa7, payload=struct.pack('>iQQBffi?', -1, uid, uid, 0, 0.0, 0.0, -1, False))


@unittest.skipUnless((DATA / 'client/catalog.sqlite3').is_file(), 'version-locked runtime catalog required')
class MasterRoadResurrection(unittest.TestCase):
    def test_catalog_qualifies_every_master_road_dungeon_as_solo(self):
        from els_server.domain import known_resurrection_maps
        catalog = known_resurrection_maps.catalog()
        for dungeon in MASTER_ROAD:
            with self.subTest(dungeon=dungeon):
                row = catalog[str(dungeon)]
                self.assertNotIn('encounter', row)
                stage = row['stages']['0']
                self.assertEqual(stage['parts'], [0])
                self.assertEqual(stage['keys'], [])
                self.assertIs(stage['native_solo_selector'], True)

    def test_every_master_road_death_is_accepted(self):
        from els_server.domain.dungeon_routes import DungeonRun
        from els_server.domain.known_resurrection_flow import handle
        for dungeon in MASTER_ROAD:
            with self.subTest(dungeon=dungeon):
                run = DungeonRun(dungeon, uuid.uuid4().hex)
                run.loaded()
                s = _session(dungeon, run)
                replies = handle(s, _death(s.account.uid), 3)
                self.assertEqual([event.kind for event in replies], [0xa8])
                self.assertEqual(struct.unpack('>fihh', replies[0].payload), (0.0, 0, 0, 0))
                self.assertIsNone(s.resurrection_rejection)
                self.assertEqual(s.known_resurrection_life['phase'], 'dying')

    def test_unlisted_dungeon_is_still_rejected_and_reasons_survive(self):
        from els_server.domain.known_resurrection_flow import handle
        s = _session(34000, None)
        replies = handle(s, _death(s.account.uid), 3)
        self.assertEqual([event.kind for event in replies], [0xa8])
        self.assertEqual(struct.unpack('>fihh', replies[0].payload)[1], -1)
        self.assertEqual(s.resurrection_rejection, 'Resurrection scene source not qualified')


if __name__ == '__main__':
    unittest.main()
