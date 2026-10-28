"""Delivery-state controls; original packet/native gameplay proofs are separate."""
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from els_server.protocol.protocol_codec import Event

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'references/native-server-attributes-20261027-v1/els_server/domain/native_attribute_delivery.py'
spec=importlib.util.spec_from_file_location('candidate_attribute_delivery',PATH)
DELIVERY=importlib.util.module_from_spec(spec);sys.modules[spec.name]=DELIVERY;spec.loader.exec_module(DELIVERY)


def skills(uid=1001, marker=b'current-skill-control'):
    return Event(0x201,kind=0x55b,payload=struct.pack('>Q',uid)+marker)


def attributes(uid=1001):
    # Only the delivery-state UID boundary is exercised here; this is not
    # passed to the native106 codec or described as an accepted full packet.
    return Event(0x201,kind=0x106,payload=b'\0'+struct.pack('>Q',uid)+b'attribute-state-control')


def copied(uid=1001):
    # Current prefix: result4 + Unit's9 bytes preceding its UID.
    return Event(0x201,kind=0x2a,payload=bytes(13)+struct.pack('>Q',uid))


class DeliveryTests(unittest.TestCase):
    def prepare(self,cursor,epoch,*,at=10,end=20,active=None,style=None,skill=None,attribute=None):
        return cursor.prepare(epoch,skills=skill or skills(),attribute=attribute or attributes(),
            active=active,style=style,valid_before=end,at=at)

    def test_waits_for_written_Unit_and_actual_actor_readiness(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(skills(),copied()),actor_ready=False)
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(skills(),),actor_ready=True)
        plan=self.prepare(cursor,epoch)
        self.assertEqual([e.kind for e in plan.events],[0x106])
        self.assertTrue(cursor.current(plan,at=10))
        self.assertTrue(cursor.sent(plan))
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch).events],[0x106])
        self.assertFalse(cursor.sent(plan))

    def test_LuCiel_all_preferences_restore_before_106_and_then_deduplicate(self):
        for active in(0,1):
            for style in(0,1,2):
                cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,10)
                cursor.observe_sent(epoch,(copied(),skills()),actor_ready=True)
                plan=self.prepare(cursor,epoch,active=active,style=style)
                self.assertEqual([e.kind for e in plan.events],[0x4e3,0x70b,0x106])
                self.assertEqual(plan.events[0].payload,struct.pack('>QB',1001,active))
                self.assertEqual(plan.events[1].payload,struct.pack('>QB',1001,style))
                self.assertTrue(cursor.sent(plan))
                self.assertEqual([e.kind for e in self.prepare(cursor,epoch,active=active,style=style).events],[0x106])
                changed=self.prepare(cursor,epoch,active=1-active,style=style)
                self.assertEqual([e.kind for e in changed.events],[0x4e3,0x106])

    def test_preparation_and_failed_transport_do_not_advance_cursor(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,10)
        cursor.observe_sent(epoch,(copied(),),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch,active=1,style=2))
        cursor.observe_sent(epoch,(skills(),),actor_ready=True)
        first=self.prepare(cursor,epoch,active=1,style=2)
        repeated=self.prepare(cursor,epoch,active=1,style=2)
        self.assertEqual(first.events,repeated.events)
        self.assertEqual([e.kind for e in first.events],[0x4e3,0x70b,0x106])
        cursor.discard()  # Failed/partial socket write must close its connection.
        self.assertFalse(cursor.sent(first))
        self.assertFalse(cursor.current(repeated,at=10))

    def test_foreign_owner_and_forged_equal_epoch_do_not_publish(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        cursor.observe_sent(epoch,(copied(1002),skills(1002)),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(copied(),skills()),actor_ready=True)
        forged=DELIVERY.ActorEpoch(epoch.owner_uid,epoch.account_id,epoch.unit_type,epoch.serial)
        self.assertIsNone(self.prepare(cursor,forged))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,skill=skills(1002))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,attribute=attributes(1002))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,active=0,style=0)

    def test_scene_selection_and_intervening_delivery_invalidate_old_plan(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        cursor.observe_sent(epoch,(copied(),skills()),actor_ready=True)
        plan=self.prepare(cursor,epoch)
        cursor.observe_sent(epoch,(Event(0x201,kind=0x228,payload=bytes(4)),),actor_ready=True)
        self.assertFalse(cursor.current(plan,at=10))
        self.assertFalse(cursor.sent(plan))
        moved=cursor.relocate(epoch)
        self.assertIsNone(self.prepare(cursor,moved))
        cursor.observe_sent(moved,(),actor_ready=True)
        self.assertEqual([e.kind for e in self.prepare(cursor,moved).events],[0x106])
        self.assertIsNone(self.prepare(cursor,moved,skill=skills(marker=b'changed-source')))
        next_epoch=cursor.begin(1001,2,5)
        self.assertIsNone(self.prepare(cursor,next_epoch))
        self.assertFalse(cursor.observe_sent(moved,(copied(),skills()),actor_ready=True))

    def test_deadline_and_malformed_restore_are_atomic(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,10)
        cursor.observe_sent(epoch,(copied(),skills()),actor_ready=True)
        plan=self.prepare(cursor,epoch,active=0,style=0)
        self.assertFalse(cursor.current(plan,at=20))
        self.assertIsNone(self.prepare(cursor,epoch,active=0,style=0,at=20))
        revision=cursor.revision
        malformed=Event(0x201,kind=0x70b,payload=struct.pack('>QB',1001,3))
        with self.assertRaises(ValueError):
            cursor.observe_sent(epoch,(skills(marker=b'new'),malformed),actor_ready=True)
        self.assertEqual(cursor.revision,revision)
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch,active=0,style=0).events],[0x4e3,0x70b,0x106])
        for clock in(True,float('inf'),float('nan')):
            with self.assertRaises(ValueError):self.prepare(cursor,epoch,active=0,style=0,at=clock)


if __name__=='__main__':unittest.main()
