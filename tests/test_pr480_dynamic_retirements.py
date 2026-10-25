"""Exercise actual story-to-generic dispatch for script-created scene actors."""
import unittest
from contextlib import ExitStack
from types import SimpleNamespace as NS
from unittest.mock import patch

from els_server.domain import dungeon_flow, story_controller_retirements as story
from els_server.domain.dungeon_lifecycle import death_report
from els_server.protocol.protocol_codec import Event
from tests.test_scene_actor_native_expiry import fixture, native255, npc


class DynamicRetirementTests(unittest.TestCase):
    def test_dynamic_actor_without_source_index_reaches_generic_expiry(self):
        actor = npc(100, 6510, 500, active=False)
        actor['dynamic'] = True
        actor.pop('source_index')
        session, run = fixture(actor)
        run.identity = 34090
        event = Event(0x202, performers=(0,), kind=0xad, payload=native255(100, 500))
        with ExitStack() as stack:
            stack.enter_context(patch.dict('sys.modules', {
                'els_server.domain.hunter_chest_flow': NS(accepted_death=lambda *a: None),
                'els_server.domain.lithia_memory1_retirements': NS(handle=lambda *a: None),
                'els_server.domain.dungeon_equipment_loot_flow': NS(
                    accepted_death=lambda *a: None, current_lease=lambda *a: True),
                'els_server.domain.legacy_pve_exp': NS(accepted_death=lambda *a: None)}))
            stack.enter_context(patch('els_server.domain.quest_flow.store',
                                      side_effect=AssertionError('expiry cannot grant quest progress')))
            reply = dungeon_flow.handle(session, event)
        self.assertEqual([e.kind for e in reply], [0xae, 0xaf])
        self.assertEqual(set(run.defeated), {100})
        self.assertFalse(story.source_pinned(run, actor))
        self.assertFalse(session.clear_notified)

    def test_static_missing_source_metadata_stays_rejected(self):
        actor = npc(18, 9324, 1000)
        actor.pop('source_index')
        session, run = fixture(actor)
        for flag in (255, 0, 1):
            raw = bytearray(native255(18, 1000))
            raw[4] = flag
            event = Event(0x202, performers=(0,), kind=0xad, payload=bytes(raw))
            with patch('els_server.domain.dungeon_equipment_loot_flow.current_lease', return_value=True):
                self.assertEqual(story.handle(session, event, death_report(event.payload)), [])
        self.assertFalse(story.source_pinned(run, actor))
        self.assertFalse(run.defeated)


if __name__ == '__main__':
    unittest.main()
