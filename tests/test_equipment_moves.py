import sqlite3,struct,tempfile,unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from els_server.domain.local_session import LocalAccount
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from tests.historical_inventory import seed_existing_items as grant_items
from els_server.storage.equipment_attributes import replace_attributes
from els_server.storage.equipment_durability import replace_durability
from els_server.storage.equipment_moves import move_equipment
from els_server.domain.fashion_state import equipment_map
from els_server.domain.equipment_instance import restricted_templates


class EquipmentMoveTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)/'state.sqlite3';self.account=LocalAccount(LocalState(self.path));self.account.enable_characters()
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=2 WHERE uid=1001')
            self.gear=[grant_items(db,[dict(template=t,metadata=1,quantity=1,group=1)])[0] for t in (100,105,1000,28000,28005)]

    def snapshot(self):return self.account.get_inventory_snapshot()
    def move(self,a,b,owner=1001):return move_equipment(self.path,struct.pack('>BiBiB',*a,*b,0),owner)

    def test_wear_swap_unwear_preserves_uid_attributes_durability_and_relogin(self):
        first=self.gear[0]
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace_durability(db,1001,first['uid'],10000,1999)
            replace_attributes(db,1001,first['uid'],[0]*4,[1,0,0,0])
        initial=self.snapshot()
        for source,dest in [((1,0),(9,9)),((1,1),(9,9)),((9,9),(1,1)),((1,2),(9,1)),((9,1),(1,2))]:
            wire=self.move(source,dest);self.assertEqual(struct.unpack_from('>I',wire)[0],2);self.assertEqual(wire[-4:],bytes(4))
            state=self.snapshot();other=LocalAccount(LocalState(self.path));other.enable_characters();self.assertEqual(other.get_inventory_snapshot(),state)
            self.assertEqual({i['uid'] for i in state['items']},{i['uid'] for i in initial['items']})
            item=next(i for i in state['items'] if i['uid']==first['uid']);self.assertEqual(item['durability'],1999);self.assertEqual(item['attributes'],[1,0,0,0])
            equipment_map(state['items'])
        self.move((9,9),(1,0));self.assertEqual(self.snapshot(),initial)
        self.move((1,1),(1,0));self.move((1,1),(1,0));self.assertEqual(self.snapshot(),initial)
        with closing(sqlite3.connect(self.path)) as db,db:self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])

    def test_rejections_and_encoder_failure_are_atomic(self):
        before=self.snapshot()
        for source,dest,owner in [((1,0),(9,1),1001),((1,3),(9,9),1001),((1,4),(9,9),1001),((1,35),(9,9),1001),((1,0),(1,36),1001),((1,0),(9,9),1002)]:
            with self.assertRaises(ValueError):self.move(source,dest,owner)
            self.assertEqual(self.snapshot(),before)
        with patch('els_server.storage.equipment_moves.move_ack',side_effect=ValueError('encoding failure')):
            with self.assertRaises(ValueError):self.move((1,0),(9,9))
        self.assertEqual(self.snapshot(),before)
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('UPDATE characters SET level=1 WHERE uid=1001')
        with self.assertRaises(ValueError):self.move((1,1),(9,9))
        self.assertEqual(self.snapshot(),before)

    def test_zero_durability_blocks_wear_but_never_blocks_unwear(self):
        self.move((1,0),(9,9))
        with closing(sqlite3.connect(self.path)) as db,db:
            db.execute('BEGIN IMMEDIATE');replace_durability(db,1001,self.gear[0]['uid'],10000,0)
        self.move((9,9),(1,0))
        before=self.snapshot()
        with self.assertRaises(ValueError):self.move((1,0),(9,9))
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(restricted_templates(),{28005,28006,8200077,8200078,8200079,8200080,8200081})

    def test_dispatch_flag_phase_and_owned_character(self):
        from els_server.config import ServerConfig
        from els_server.domain.local_session import LocalSession
        from els_server.protocol.protocol_codec import Event
        self.assertFalse(ServerConfig().normal_equipment_moves_enabled)
        for kwargs in ({'normal_equipment_moves_enabled':1},{'normal_equipment_moves_enabled':True,'profile':'bootstrap'}):
            with self.assertRaises(ValueError):ServerConfig(**kwargs)
        request=Event(0x202,kind=0x104,payload=struct.pack('>BiBiB',1,0,9,9,0));before=self.snapshot()
        disabled=LocalSession(self.account,**ServerConfig().session_options());disabled.role='game';disabled.phase='town_ready'
        self.assertNotEqual(disabled.handle(request,1)[0].payload[-4:],bytes(4));self.assertEqual(self.snapshot(),before)
        session=LocalSession(self.account,**ServerConfig(normal_equipment_moves_enabled=True).session_options());session.role='game'
        for phase in ('characters_ready','dungeon_active'):
            session.phase=phase;self.assertNotEqual(session.handle(request,1)[0].payload[-4:],bytes(4));self.assertEqual(self.snapshot(),before)
        session.phase='town_ready';reply=session.handle(request,1)[0]
        self.assertEqual(reply.kind,0x105);self.assertEqual(reply.payload[-4:],bytes(4))
        self.assertEqual(next(i for i in self.snapshot()['items'] if i['uid']==self.gear[0]['uid'])['group'],9)

if __name__=='__main__':unittest.main()
