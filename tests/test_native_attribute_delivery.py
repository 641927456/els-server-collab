"""Delivery-state controls; original packet/native gameplay proofs are separate."""
import importlib.util
import json
from pathlib import Path
import struct
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from els_server.protocol.protocol_codec import Event
from tests.test_native_skill_delivery_sources import initial,copy_event,records,identifiers,preset

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'references/native-server-attributes-20261027-v1/els_server/domain/native_attribute_delivery.py'
SOURCE_PATH=PATH.with_name('native_skill_delivery_sources.py')
source_spec=importlib.util.spec_from_file_location('candidate_delivery_skill_sources',SOURCE_PATH)
SOURCES=importlib.util.module_from_spec(source_spec);sys.modules[source_spec.name]=SOURCES;source_spec.loader.exec_module(SOURCES)
producer_spec=importlib.util.spec_from_file_location('candidate_delivery_skill_production',SOURCE_PATH.with_name('native_skill_production.py'))
PRODUCER=importlib.util.module_from_spec(producer_spec);sys.modules[producer_spec.name]=PRODUCER
with patch.dict(sys.modules,{'els_server.domain.native_skill_delivery_sources':SOURCES}):producer_spec.loader.exec_module(PRODUCER)
ready_spec=importlib.util.spec_from_file_location('candidate_delivery_readiness',SOURCE_PATH.with_name('native_attribute_readiness.py'))
READINESS=importlib.util.module_from_spec(ready_spec);sys.modules[ready_spec.name]=READINESS
with patch.dict(sys.modules,{'els_server.domain.native_skill_production':PRODUCER}):ready_spec.loader.exec_module(READINESS)
spec=importlib.util.spec_from_file_location('candidate_attribute_delivery',PATH)
DELIVERY=importlib.util.module_from_spec(spec);sys.modules[spec.name]=DELIVERY
with patch.dict(sys.modules,{'els_server.domain.native_skill_delivery_sources':SOURCES,
                           'els_server.domain.native_attribute_readiness':READINESS}):spec.loader.exec_module(DELIVERY)
COPIES={}


def skills(uid=1001, marker=b'current-skill-control'):
    return initial(uid=uid,learned=((25410,4 if marker==b'current-skill-control'else 5),(25030,1)),forces=SOURCES.ZERO_FORCE)


def attributes(uid=1001):
    # Only the delivery-state UID boundary is exercised here; this is not
    # passed to the native106 codec or described as an accepted full packet.
    return Event(0x201,kind=0x106,payload=b'\0'+struct.pack('>Q',uid)+b'attribute-state-control')


def copied(uid=1001):
    event,fields=copy_event(uid=uid,kind=0x2a,forces=SOURCES.ZERO_FORCE)
    COPIES[id(event)]=SOURCES.bind_copy(event,fields)
    return event


def observe(cursor,epoch,events,**kwargs):
    # Existing delivery-state controls explicitly assume a qualified skill UI.
    # Separate tests below withhold/stale its real receipt and test rejection.
    if kwargs.get('actor_ready') and 'ui_receipts'not in kwargs:
        reply,proof=ui_receipt(epoch)
        events=events+(reply,);kwargs['ui_receipts']=(proof,)
    if 'skill_updates'in kwargs:
        kwargs['skill_updates']=tuple(SOURCES.UpdateReceipt(epoch,e,epoch.owner_uid)
            for e in kwargs['skill_updates'])
    proofs=tuple(COPIES[id(event)]for event in events if id(event)in COPIES
                 and COPIES[id(event)].owner==epoch.owner_uid)
    return cursor.observe_sent(epoch,events,copies=proofs,**kwargs)


def ui_receipt(epoch):
    store=SimpleNamespace(uid=epoch.owner_uid)
    account=SimpleNamespace(uid=epoch.owner_uid,account_id=epoch.account_id,store=store)
    session=SimpleNamespace(account=account,shop_session_id='explicit-unit-control',role='game',phase='town_ready',released=False)
    request=Event(0x202,kind=0x6e9,payload=b'')
    reply=Event(0x201,kind=0x6ea,payload=b'explicit-unit-layout-control')
    return reply,READINESS.SkillUIReceipt(epoch,request,7,reply,epoch.owner_uid,session,account,store,session.shop_session_id)


class DeliveryTests(unittest.TestCase):
    def prepare(self,cursor,epoch,*,at=10,end=20,active=None,style=None,skill=None,attribute=None):
        return cursor.prepare(epoch,skills=skill or skills(),extra_skills=((25410,4),),attribute=attribute or attributes(),
            active=active,style=style,valid_before=end,at=at)

    def test_waits_for_actual_written_UI_reply_of_this_selection(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True,ui_receipts=())
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(),actor_ready=True,ordinary_page_ready=True)
        self.assertFalse(cursor._ui_ready)
        reply,proof=ui_receipt(epoch)
        cursor.observe_sent(epoch,(reply,),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch))
        clone=Event(reply.event_id,kind=reply.kind,payload=reply.payload)
        revision=cursor.revision
        with self.assertRaises(ValueError):
            cursor.observe_sent(epoch,(clone,),actor_ready=True,ui_receipts=(proof,))
        self.assertEqual(cursor.revision,revision);self.assertFalse(cursor._ui_ready)
        cursor.observe_sent(epoch,(reply,),actor_ready=True,ui_receipts=(proof,))
        self.assertIsNotNone(self.prepare(cursor,epoch))

    def test_new_copy_resets_UI_but_same_Unit_scene_move_preserves_it(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        self.assertIsNotNone(self.prepare(cursor,epoch))
        old_reply,old_proof=ui_receipt(epoch)
        moved=cursor.relocate(epoch)
        self.assertTrue(cursor._ui_ready);self.assertFalse(cursor._actor_ready)
        cursor.observe_sent(moved,(),actor_ready=True)
        self.assertIsNotNone(self.prepare(cursor,moved))
        with self.assertRaises(ValueError):
            cursor.observe_sent(moved,(old_reply,),actor_ready=True,ui_receipts=(old_proof,))
        observe(cursor,moved,(copied(),skills()),actor_ready=True,ui_receipts=())
        self.assertFalse(cursor._ui_ready);self.assertIsNone(self.prepare(cursor,moved))
        reply,proof=ui_receipt(moved)
        cursor.observe_sent(moved,(reply,),actor_ready=True,ui_receipts=(proof,))
        self.assertIsNotNone(self.prepare(cursor,moved))

    def test_stale_UI_source_graph_loses_evidence_without_rewriting_reply(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True,ui_receipts=())
        reply,proof=ui_receipt(epoch);payload=reply.payload
        proof.session.account.store=SimpleNamespace(uid=1001)
        self.assertFalse(proof.current())
        self.assertTrue(cursor.observe_sent(epoch,(reply,),actor_ready=True,ui_receipts=(proof,)))
        self.assertEqual(reply.payload,payload);self.assertFalse(cursor._ui_ready)
        self.assertIsNone(self.prepare(cursor,epoch))

    def test_484_boolean_cannot_replace_native_UI_receipt(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True,ui_receipts=())
        selected=((900405,6),)+((0,0),)*10
        force=Event(0x201,kind=0x6d1,payload=bytes(4)+preset(forces=selected))
        cursor.observe_sent(epoch,(force,),actor_ready=True,
            skill_updates=(SOURCES.UpdateReceipt(epoch,force,1001),))
        self.assertEqual(cursor._skills.forces,selected)
        raw=json.loads((SOURCE_PATH.parents[2]/'native-original484-readiness-goldens-v2.json').read_bytes())['payload_hex']
        page=Event(0x201,kind=0x484,payload=bytes.fromhex(raw))
        update=SOURCES.UpdateReceipt(epoch,page,1001)
        cursor.observe_sent(epoch,(page,),actor_ready=True,skill_updates=(update,),ordinary_page_ready=True)
        self.assertIsNone(cursor._skills.forces);self.assertIsNone(self.prepare(cursor,epoch))
        reply,proof=ui_receipt(epoch)
        cursor.observe_sent(epoch,(reply,),actor_ready=True,ui_receipts=(proof,))
        cursor.observe_sent(epoch,(page,),actor_ready=True,skill_updates=(update,))
        self.assertEqual(cursor._skills.forces,SOURCES.ZERO_FORCE)
        self.assertIsNotNone(self.prepare(cursor,epoch))

    def test_waits_for_written_Unit_and_actual_actor_readiness(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        self.assertIsNone(self.prepare(cursor,epoch))
        observe(cursor,epoch,(skills(),copied()),actor_ready=False)
        self.assertIsNone(self.prepare(cursor,epoch))
        observe(cursor,epoch,(),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch))
        observe(cursor,epoch,(skills(),),actor_ready=True)
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
                observe(cursor,epoch,(copied(),skills()),actor_ready=True)
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
        observe(cursor,epoch,(copied(),),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch,active=1,style=2))
        observe(cursor,epoch,(skills(),),actor_ready=True)
        first=self.prepare(cursor,epoch,active=1,style=2)
        repeated=self.prepare(cursor,epoch,active=1,style=2)
        self.assertEqual(first.events,repeated.events)
        self.assertEqual([e.kind for e in first.events],[0x4e3,0x70b,0x106])
        cursor.discard()  # Failed/partial socket write must close its connection.
        self.assertFalse(cursor.sent(first))
        self.assertFalse(cursor.current(repeated,at=10))

    def test_foreign_owner_and_forged_equal_epoch_do_not_publish(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(1002),skills(1002)),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch))
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        forged=DELIVERY.ActorEpoch(epoch.owner_uid,epoch.account_id,epoch.unit_type,epoch.serial)
        self.assertIsNone(self.prepare(cursor,forged))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,skill=skills(1002))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,attribute=attributes(1002))
        with self.assertRaises(ValueError):self.prepare(cursor,epoch,active=0,style=0)

    def test_scene_selection_and_intervening_delivery_invalidate_old_plan(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        plan=self.prepare(cursor,epoch)
        observe(cursor,epoch,(Event(0x201,kind=0x228,payload=bytes(4)),),actor_ready=True)
        self.assertFalse(cursor.current(plan,at=10))
        self.assertFalse(cursor.sent(plan))
        moved=cursor.relocate(epoch)
        self.assertIsNone(self.prepare(cursor,moved))
        observe(cursor,moved,(),actor_ready=True)
        self.assertEqual([e.kind for e in self.prepare(cursor,moved).events],[0x106])
        self.assertIsNone(self.prepare(cursor,moved,skill=skills(marker=b'changed-source')))
        next_epoch=cursor.begin(1001,2,5)
        self.assertIsNone(self.prepare(cursor,next_epoch))
        self.assertFalse(observe(cursor,moved,(copied(),skills()),actor_ready=True))

    def test_deadline_and_malformed_restore_are_atomic(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,10)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        plan=self.prepare(cursor,epoch,active=0,style=0)
        self.assertFalse(cursor.current(plan,at=20))
        self.assertIsNone(self.prepare(cursor,epoch,active=0,style=0,at=20))
        revision=cursor.revision
        malformed=Event(0x201,kind=0x70b,payload=struct.pack('>QB',1001,3))
        with self.assertRaises(ValueError):
            observe(cursor,epoch,(skills(marker=b'new'),malformed),actor_ready=True)
        self.assertEqual(cursor.revision,revision)
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch,active=0,style=0).events],[0x4e3,0x70b,0x106])
        for clock in(True,float('inf'),float('nan')):
            with self.assertRaises(ValueError):self.prepare(cursor,epoch,active=0,style=0,at=clock)

    def test_normal_incremental_rank_update_and_slot_move_need_no_extra_55B(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        update=Event(0x201,kind=0x131,payload=bytes(4)+records(((25410,5),))+identifiers(()))
        old=self.prepare(cursor,epoch)
        observe(cursor,epoch,(update,),actor_ready=True,skill_updates=(update,))
        self.assertFalse(cursor.current(old,at=10))
        self.assertIsNone(self.prepare(cursor,epoch))
        current=skills(marker=b'changed-source')
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch,skill=current).events],[0x106])
        moved=initial(learned=((25410,5),(25030,1)),forces=SOURCES.ZERO_FORCE,
            pages=(preset(forces=SOURCES.ZERO_FORCE,slots=((25030,1),)+((0,0),)*21),))
        update=Event(0x201,kind=0x123,payload=struct.pack('>5i',0,0,25030,-1,0))
        observe(cursor,epoch,(update,),actor_ready=True,skill_updates=(update,))
        self.assertNotEqual(current.payload,moved.payload)
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch,skill=moved).events],[0x106])

    def test_55B_does_not_attest_changed_Force_but_normal_6D1_does(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        forces=((100100,5),)+((0,0),)*10;canonical=initial(forces=forces)
        observe(cursor,epoch,(canonical,),actor_ready=True)
        self.assertIsNone(self.prepare(cursor,epoch,skill=canonical))
        update=Event(0x201,kind=0x6d1,payload=bytes(4)+preset(forces=forces))
        observe(cursor,epoch,(update,),actor_ready=True,skill_updates=(update,))
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch,skill=canonical).events],[0x106])
        self.assertIsNone(self.prepare(cursor,epoch))
        event,fields=copy_event(forces=SOURCES.ZERO_FORCE)
        proof=SOURCES.bind_copy(event,fields)
        cursor.observe_sent(epoch,(event,),actor_ready=True,copies=(proof,))
        self.assertEqual([e.kind for e in self.prepare(cursor,epoch).events],[0x106])

    def test_unbound_copy_or_UIDless_reply_invalidates_uncertain_sources(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        update=Event(0x201,kind=0x131,payload=bytes(4)+records(((25410,5),))+identifiers(()))
        observe(cursor,epoch,(update,),actor_ready=True)  # No producer epoch proof.
        self.assertIsNone(self.prepare(cursor,epoch))
        observe(cursor,epoch,(skills(),),actor_ready=True)
        self.assertIsNotNone(self.prepare(cursor,epoch))
        event,fields=copy_event(forces=SOURCES.ZERO_FORCE)
        cursor.observe_sent(epoch,(event,),actor_ready=True)  # No shared-writer proof.
        self.assertIsNone(self.prepare(cursor,epoch))
        cursor.observe_sent(epoch,(event,),actor_ready=True,copies=(SOURCES.bind_copy(event,fields),))
        self.assertIsNotNone(self.prepare(cursor,epoch))
        foreign_batch=Event(0x201,kind=0x6d1,payload=bytes(4)+preset(forces=SOURCES.ZERO_FORCE))
        with self.assertRaises(ValueError):
            cursor.observe_sent(epoch,(),actor_ready=True,skill_updates=(foreign_batch,))
        self.assertIsNotNone(self.prepare(cursor,epoch))

    def test_written_copy_proof_cannot_be_reused_for_an_equal_Event(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        event,fields=copy_event(kind=0x2a,forces=SOURCES.ZERO_FORCE)
        proof=SOURCES.bind_copy(event,fields);same_bytes=Event(0x201,kind=0x2a,payload=event.payload)
        revision=cursor.revision
        with self.assertRaises(ValueError):
            cursor.observe_sent(epoch,(same_bytes,),actor_ready=True,copies=(proof,))
        self.assertEqual(cursor.revision,revision)
        self.assertIsNone(self.prepare(cursor,epoch))

    def test_UIDless_update_requires_same_producer_epoch_and_exact_Event(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        update=Event(0x201,kind=0x131,payload=bytes(4)+records(((25410,5),))+identifiers(()))
        moved=cursor.relocate(epoch)
        revision=cursor.revision
        equal=Event(0x201,kind=update.kind,payload=update.payload)
        old=SOURCES.UpdateReceipt(epoch,update,1001)
        for proof in(update,old,SOURCES.UpdateReceipt(moved,equal,1001),
                     SOURCES.UpdateReceipt(moved,update,1002)):
            with self.assertRaises(ValueError):
                cursor.observe_sent(moved,(update,),actor_ready=True,skill_updates=(proof,))
            self.assertEqual(cursor.revision,revision)
        proof=SOURCES.UpdateReceipt(moved,update,1001)
        self.assertTrue(cursor.observe_sent(moved,(update,),actor_ready=True,skill_updates=(proof,)))
        self.assertIsNotNone(self.prepare(cursor,moved,skill=skills(marker=b'changed-source')))

    def test_extra_stat_source_must_match_even_when_ordinary_and_Force_match(self):
        cursor=DELIVERY.DeliveryCursor();epoch=cursor.begin(1001,2,5)
        observe(cursor,epoch,(copied(),skills()),actor_ready=True)
        args=dict(skills=skills(),attribute=attributes(),active=None,style=None,valid_before=20,at=10)
        self.assertIsNone(cursor.prepare(epoch,extra_skills=(),**args))
        self.assertIsNotNone(cursor.prepare(epoch,extra_skills=((25410,4),),**args))
        observe(cursor,epoch,(skills(),),actor_ready=True)
        self.assertIsNone(cursor.prepare(epoch,extra_skills=(),**args))
        unbound,_=copy_event()
        cursor.observe_sent(epoch,(unbound,),actor_ready=True)
        self.assertIsNone(cursor.prepare(epoch,extra_skills=((25410,4),),**args))


if __name__=='__main__':unittest.main()
