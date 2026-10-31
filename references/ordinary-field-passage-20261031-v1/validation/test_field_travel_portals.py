"""Ordinary passage admission; native wire/TLS checks are separate evidence."""
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
import struct
import sys
import unittest
from unittest.mock import Mock,patch

ARCHIVE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
import els_server,els_server.domain,els_server.storage,els_server.protocol
for package in (els_server,els_server.domain,els_server.storage,els_server.protocol):
    for mode in ('common','online'):
        package.__path__.insert(0,str(ARCHIVE/'source'/mode/Path(*package.__name__.split('.'))))
from els_server.domain import field_travel as travel
travel.PROJECT_ROOT=ARCHIVE/'source/common'
from els_server.domain.town_travel import DestinationRequirementError,entry_failure_code
from els_server.protocol.protocol_codec import Event


def join(identity=40001,position=1):
    return Event(0x202,kind=0x374,payload=struct.pack('>iiI',identity,position,0)+bytes(7),performers=(0,))


class OrdinaryPassageTests(unittest.TestCase):
    def setUp(self):
        self.level=14
        self.rooms={}
        self.world=SimpleNamespace(leave=Mock())
        self.manager=SimpleNamespace(rooms=self.rooms,room=lambda s:self.rooms.get(s),world=self.world)
        self.account=SimpleNamespace(characters=object(),uid=1001,get_location=lambda:{'map':20001})
        self.session=Mock()
        self.session.account=self.account
        self.session.role='game';self.session.enter_town=True;self.session.item_test=True
        self.session.client_build='dx11_260923';self.session.dungeon_return_pending=False
        self.session.town_warp_transition=None;self.session.phase='town_ready'
        self.session.active_map=20001;self.session.pending_map=None
        self.session._chip_reset_local_application=None
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.lease=self.stack.enter_context(patch.object(travel,'_ordinary_actor',return_value=True))
        self.stack.enter_context(patch.object(travel,'_character',side_effect=lambda _:dict(unit_type=8,level=self.level)))
        # Isolate admission/state changes from FullUser resource projection.
        self.stack.enter_context(patch.object(travel.wire,'joined',side_effect=lambda *a,**k:Event(
            0x201,kind=0x375,payload=struct.pack('>i',k.get('result',0)))))

    def test_elder_gate_enters_field_and_waits_for_original_ready(self):
        s=self.session
        reply=travel.handle(self.manager,s,join())
        self.assertEqual(reply[0].payload,bytes(4))
        room=self.rooms[s]
        self.assertEqual((room.identity,room.phase,s.active_map),(40001,'loading',40001))
        travel.handle(self.manager,s,Event(0x202,kind=0x91,payload=struct.pack('>ii',100,0)))
        reply=travel.handle(self.manager,s,Event(0x202,kind=0x37a))
        self.assertEqual([(r.kind,len(r.payload))for r in reply],[(0x37b,4),(0x3d6,28)])
        self.assertEqual(room.phase,'active')

    def test_entry_replay_retains_same_room_generation(self):
        first=travel.handle(self.manager,self.session,join());room=self.rooms[self.session]
        again=travel.handle(self.manager,self.session,join())
        self.assertIs(self.rooms[self.session],room)
        self.assertEqual(again,first)

    def test_wrong_native_position_and_nonadjacent_field_do_not_move(self):
        for request in (join(position=2),join(identity=40010)):
            with self.subTest(payload=request.payload):
                reply=travel.handle(self.manager,self.session,request)
                self.assertEqual(reply[0].payload,struct.pack('>i',1359))
                self.assertFalse(self.rooms);self.assertEqual(self.session.active_map,20001)

    def test_field_minimum_level_uses_nonempty_native_failure(self):
        self.level=1
        reply=travel.handle(self.manager,self.session,join())
        self.assertEqual(reply[0].payload,struct.pack('>i',1106))
        self.assertFalse(self.rooms)

    def test_revoked_actor_cannot_allocate_a_room(self):
        self.lease.return_value=False
        reply=travel.handle(self.manager,self.session,join())
        self.assertNotEqual(reply[0].payload,bytes(4));self.assertFalse(self.rooms)

    def test_nonadjacent_town_exit_keeps_the_current_field(self):
        travel.handle(self.manager,self.session,join());room=self.rooms[self.session]
        reply=travel.handle(self.manager,self.session,Event(0x202,kind=0x225,
            payload=struct.pack('>iB',20008,0),performers=(0,)))
        self.assertEqual(reply[0].payload[:4],struct.pack('>i',515))
        self.assertIs(self.rooms[self.session],room)

    def test_village_failure_codes_keep_original_requirement_types(self):
        for error,expected in ((DestinationRequirementError('level',level=15),518),
            (DestinationRequirementError('clear',dungeon=30090),519),
            (DestinationRequirementError('quest',quest=26640),1620),(ValueError('other'),515)):
            with self.subTest(code=expected):self.assertEqual(entry_failure_code(error),expected)


if __name__=='__main__':unittest.main()
