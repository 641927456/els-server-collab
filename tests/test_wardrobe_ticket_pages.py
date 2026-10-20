"""Portable static-page checks using private synthetic definition rows only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing,contextmanager
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.protocol import wardrobe_messages as wire


class SyntheticClient:
    def __init__(self,path,roles,identity='pack-a'):
        self.path=path
        self.manifest=dict(client_sha256='synthetic-client',catalog_sha256=identity)
        self.connections=0;self.queries=[]
        with closing(sqlite3.connect(path)) as db,db:
            db.execute('CREATE TABLE items(id INTEGER PRIMARY KEY,record BLOB)')
            db.executemany('INSERT INTO items VALUES (?,?)',((key,bytes(210)+bytes([role])) for key,role in roles.items()))

    @contextmanager
    def connect(self):
        self.connections+=1
        owner=self
        class Connection(sqlite3.Connection):
            def execute(self,sql,parameters=()):
                owner.queries.append((sql,len(parameters)))
                return super().execute(sql,parameters)
        db=sqlite3.connect(self.path.as_uri()+'?mode=ro&immutable=1',uri=True,factory=Connection)
        try:yield db
        finally:db.close()


class TicketPageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.client=SyntheticClient(self.root/'one.sqlite3',{101:2,102:1,103:2})
        self.data=dict(client_sha256='synthetic-client',tickets={'10':dict(group_id=7,part=8)},ticket_allowed={'10':[101,102,101,103]})
        modules={'els_server.game_data':SimpleNamespace(client_data=lambda:self.client),
                 'els_server.domain.wardrobe_extensions':SimpleNamespace(catalog=lambda:self.data)}
        self.modules=patch.dict(sys.modules,modules);self.modules.start();self.addCleanup(self.modules.stop)
        wire._ticket_page_parts.cache_clear();self.addCleanup(wire._ticket_page_parts.cache_clear)

    def page(self,page=0,force=0):return wire.ticket_information(struct.pack('>iB',page,force))

    def test_preserves_role_order_duplicates_and_request_force(self):
        ints=lambda values:struct.pack('>I',len(values))+b''.join(struct.pack('>i',n)for n in values)
        expected=bytes(4)+struct.pack('>Iii',1,10,7)+ints([8])+ints([])
        expected+=struct.pack('>Iii',1,7,2)+struct.pack('>i',1)+ints([102])+struct.pack('>i',2)+ints([101,101,103])
        for force in (0,1):
            event=self.page(force=force)
            self.assertEqual((event.event_id,event.kind),(0x201,0x564))
            self.assertEqual(event.payload,expected+struct.pack('>iBB',0,1,force))
        self.assertEqual(self.client.connections,1)

    def test_batches_a_large_page_in_one_connection(self):
        self.client=SyntheticClient(self.root/'many.sqlite3',{n:n%16 for n in range(1,1008)},'pack-many')
        self.data['ticket_allowed']['10']=list(range(1,1008))
        self.page();self.page()
        self.assertEqual(self.client.connections,1)
        self.assertEqual([n for _,n in self.client.queries],[900,107])
        self.assertTrue(all(sql.startswith('SELECT ') for sql,_ in self.client.queries))

    def test_invalid_input_and_source_changes(self):
        for payload,message in ((b'','Ticket info size'),(bytearray(5),'Ticket info size'),
                                (struct.pack('>iB',-1,0),'Ticket info page'),
                                (struct.pack('>iB',1,0),'Ticket info page'),
                                (struct.pack('>iB',0,2),'Ticket info page')):
            with self.subTest(payload=payload),self.assertRaisesRegex(ValueError,message):wire.ticket_information(payload)
        initial=self.page().payload
        self.data['ticket_allowed']['10'].reverse()
        reordered=self.page().payload
        self.assertNotEqual(initial,reordered);self.assertEqual(self.client.connections,2)
        self.client=SyntheticClient(self.root/'two.sqlite3',{101:3,102:1,103:2},'pack-b')
        self.assertNotEqual(reordered,self.page().payload);self.assertEqual(self.client.connections,1)
        self.data['client_sha256']='different-client'
        with self.assertRaisesRegex(ValueError,'Wardrobe extension version'):self.page()

    def test_concurrent_calls_compile_once_and_failures_are_not_cached(self):
        with ThreadPoolExecutor(max_workers=8)as pool:
            answers=list(pool.map(lambda _:self.page(force=1),range(32)))
        self.assertTrue(all(answer==answers[0]for answer in answers));self.assertEqual(self.client.connections,1)
        self.data['ticket_allowed']['10']=[999]
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'Unknown client item: 999'):self.page()
        self.assertEqual(self.client.connections,3)
        self.assertEqual(wire._ticket_page_parts.cache_info().currsize,1)

    def test_cache_remains_bounded_when_page_inputs_change(self):
        for group in range(70):
            self.data['tickets']['10']['group_id']=group
            self.page()
        info=wire._ticket_page_parts.cache_info()
        self.assertEqual((info.maxsize,info.currsize),(64,64))
        self.data['tickets']['10']['group_id']=0
        self.page()
        self.assertEqual(self.client.connections,71)


if __name__=='__main__':unittest.main()
