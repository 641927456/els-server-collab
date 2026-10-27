"""An auxiliary Boss draw must never tear down an accepted death.

Regression for the 纳斯德生产基地 (30282) disconnect: the bait draw snapshots
``s.identity`` to detect a changed session lease, but solo local play runs a
plain ``LocalSession`` which never sets that attribute (only the application
session in ``els_server/application.py`` does). The AttributeError escaped from
``dungeon_equipment_loot_flow.accepted_death`` - it is raised while building
the bait source, before the ``storage.LootActorRejected`` guard - so the worker
dropped the connection right after the client's 0xAD Boss death report.
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from els_server.domain import dungeon_equipment_loot_flow, fishing_bait_loot


def local_session():
    """A plain local session: no ``identity``, i.e. the production solo shape."""
    account = NS(uid=1004, account_id=7, get_location=lambda: {'map': 30282})
    return NS(account=account, active_map=30282, application=None,
              dungeon_run=NS(identity=30282), pending_map=None,
              map_synchronizing=None, role='game', phase='dungeon_active')


def boss():
    return dict(key=3, template=1234, source_index=0, active=True, boss=True,
                no_drop=False, ally=False, team=1)


class BaitFactsWithoutIdentity(unittest.TestCase):
    def test_snapshot_reads_an_identity_less_session(self):
        session = local_session()
        self.assertFalse(hasattr(session, 'identity'))
        facts = fishing_bait_loot._facts(session)
        self.assertEqual(len(facts), 8)
        self.assertEqual(facts[3], repr(None))
        self.assertEqual(facts[4], 30282)

    def test_snapshot_is_stable_between_calls(self):
        session = local_session()
        self.assertEqual(fishing_bait_loot._facts(session),
                         fishing_bait_loot._facts(session))

    def test_identity_still_participates_when_present(self):
        session = local_session()
        session.identity = {'id': 7}
        self.assertEqual(fishing_bait_loot._facts(session)[3],
                         repr({'id': 7}))


class AuxiliarySourceNeverRaises(unittest.TestCase):
    def test_refusal_degrades_to_no_bait(self):
        session = local_session()
        for error in (AttributeError("'LocalSession' object has no attribute 'identity'"),
                      ValueError('Hunter finite ordinary route'),
                      KeyError('npcs'), TypeError('bad source'),
                      StopIteration()):
            with patch.object(fishing_bait_loot, 'source', side_effect=error):
                self.assertIsNone(dungeon_equipment_loot_flow._bait(session, boss()))

    def test_accepted_source_passes_through(self):
        session = local_session()
        sentinel = object()
        with patch.object(fishing_bait_loot, 'source', return_value=sentinel):
            self.assertIs(dungeon_equipment_loot_flow._bait(session, boss()), sentinel)


if __name__ == '__main__':
    unittest.main(verbosity=2)
