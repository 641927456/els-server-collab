"""A solo profile must answer the native battlefield-join request.

Every captured freeze ended with 0x374 as the last field request: the local
profile has no FieldBosses owner, so nothing replied and the client kept the
join screen with its field tick stopped. The friends world still owns 0x374
whenever an application is present.
"""
import struct,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from els_server.domain.field_boss_entry_flow import handle as entry
from els_server.domain.local_session import LocalAccount,LocalSession
from els_server.protocol.protocol_codec import Event
from els_server.storage.local_state import LocalState

JOIN=struct.pack('>iiIBBHBBB',40046,0,0,0,0,0,0,0,0)


class FieldBossEntryTests(unittest.TestCase):
    def session(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        account=LocalAccount(LocalState(Path(tmp.name)/'field.sqlite3'))
        account.enable_characters();account.get_inventory_snapshot()
        session=LocalSession(account,enter_town=True,enter_dungeon=True,client_build='dx11_260923',
                             npc_slot_test=True,gate_test=True,population_test=True,clear_test=True,
                             reward_test=True,item_test=True)
        session.role='game';session.phase='town_ready'
        return session

    def test_local_join_request_is_refused_instead_of_unanswered(self):
        reply=self.session().handle(Event(0x202,kind=0x374,payload=JOIN),7)
        joined=[e for e in reply if e.event_id==0x201 and e.kind==0x375]
        self.assertEqual(len(joined),1)
        self.assertEqual(struct.unpack_from('>i',joined[0].payload,0)[0],-1)
        self.assertGreater(len(joined[0].payload),4)

    def test_the_friends_world_keeps_owning_the_join(self):
        session=SimpleNamespace(role='game',client_build='dx11_260923',application=object())
        self.assertIsNone(entry(session,Event(0x202,kind=0x374,payload=JOIN),1))

    def test_other_events_pass_through(self):
        local=SimpleNamespace(role='game',client_build='dx11_260923')
        self.assertIsNone(entry(local,Event(0x202,kind=0x375,payload=JOIN),1))
        self.assertIsNone(entry(local,Event(0x201,kind=0x374,payload=JOIN),1))
        self.assertIsNone(entry(SimpleNamespace(role='login',client_build='dx11_260923'),
                                Event(0x202,kind=0x374,payload=JOIN),1))


if __name__=='__main__':unittest.main()
