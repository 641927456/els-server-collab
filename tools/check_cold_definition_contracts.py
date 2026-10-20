"""Portable static-definition contracts; no runtime pack, player DB or game."""
import contextlib
import hashlib
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from els_server.domain import companion_fashion as slots
from els_server.domain import manufacture_rules as craft


class StaticData:
    def __init__(self):
        self.raw=json.dumps({'NOW_EQIP_SLOT_ID':{'NESI_HEAD':0,'NESI_MINORUNIT_HEAD':15}})
        self.manifest={'client_sha256':'synthetic-client'}
        self.connections=0;self.max_parameters=0;self.item_calls=0
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE items(id INTEGER PRIMARY KEY,record BLOB,equip_position INTEGER,stats BLOB,stat_bonus BLOB)')
        for template,minor,role in ((1,False,1),(2,True,10),(3,True,1)):
            record=bytearray(211);record[8]=4 if minor else 0;record[210]=role
            self.db.execute('INSERT INTO items VALUES (?,?,0,?,?)',(template,bytes(record),bytes(28),b''))
    def _resource(self,name):return self.raw
    def item(self,template):
        self.item_calls+=1
        row=self.db.execute('SELECT record,equip_position,stats,stat_bonus FROM items WHERE id=?',(template,)).fetchone()
        if row is None:raise ValueError(f'Unknown client item: {template}')
        struct.unpack('<7f',row[2]);tuple(row[3])
        return dict(record=row[0],equip_position=row[1])
    @contextlib.contextmanager
    def connect(self):
        self.connections+=1
        data=self
        class ReadConnection:
            def execute(self,sql,parameters=()):
                data.max_parameters=max(data.max_parameters,len(parameters))
                if len(parameters)>256:raise AssertionError('Unbounded parameter batch')
                if not sql.startswith('SELECT '):raise AssertionError('Static accessor attempted a write')
                return data.db.execute(sql,parameters)
        yield ReadConnection()
    def proof(self,template=1,group=27):
        record=self.db.execute('SELECT record FROM items WHERE id=?',(template,)).fetchone()[0]
        return dict(template=template,group=group,record_sha256=hashlib.sha256(record).hexdigest())


class ColdDefinitionContracts(unittest.TestCase):
    def setUp(self):
        self.data=StaticData();self.addCleanup(self.data.db.close)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'manufacture_inventory.json'
        self.policy={}
        for target in (slots,craft):
            context=patch.object(target,'client_data',lambda:self.data);context.start();self.addCleanup(context.stop)
        for context in (patch.object(craft,'DATA',self.root),patch.object(craft,'policy',lambda:self.policy)):
            context.start();self.addCleanup(context.stop)
        slots._slot_maps.cache_clear();craft.inventory_definitions.cache_clear()
        self.addCleanup(slots._slot_maps.cache_clear);self.addCleanup(craft.inventory_definitions.cache_clear)
    def source_rows(self,rows,client='synthetic-client'):
        raw=json.dumps(dict(client_sha256=client,rows=rows)).encode()
        self.source.write_bytes(raw);self.policy['inventory_sha256']=hashlib.sha256(raw).hexdigest()
        craft.inventory_definitions.cache_clear()
    def test_enum_content_identity_and_no_item_cache(self):
        self.assertEqual(slots.resolve_slots({1:0,2:0}),{1:0,2:15})
        self.assertEqual(slots.resolve_slots({2:0}),{2:15})
        self.assertEqual(slots._slot_maps.cache_info().misses,1)
        self.data.raw=json.dumps({'NOW_EQIP_SLOT_ID':{'NESI_HEAD':0,'NESI_MINORUNIT_HEAD':19}})
        self.assertEqual(slots.resolve_slots({2:0}),{2:19})
        record=bytearray(self.data.item(2)['record']);record[210]=1
        self.data.db.execute('UPDATE items SET record=? WHERE id=2',(bytes(record),))
        with self.assertRaisesRegex(ValueError,'Companion fashion belongs'):slots.resolve_slots({2:0})
    def test_slot_source_and_classification_failures(self):
        with self.assertRaisesRegex(ValueError,'Unknown client item: 999'):slots.resolve_slots({999:0})
        with self.assertRaisesRegex(ValueError,'Unverified companion fashion slot'):slots.resolve_slots({2:99})
        self.data.raw='{}'
        with self.assertRaises(KeyError):slots.resolve_slots({2:0})
    def test_ordered_decoding_and_overflow_fallback(self):
        for field,bad in (('stats',b'bad'),('stat_bonus',None)):
            self.data.db.execute('UPDATE items SET stats=?,stat_bonus=? WHERE id=2',(bytes(28),b''))
            self.data.db.execute('UPDATE items SET '+field+'=? WHERE id=2',(bad,))
            with self.assertRaises((struct.error,TypeError)):slots.resolve_slots({2:0})
            with self.assertRaisesRegex(ValueError,'Companion fashion belongs'):slots.resolve_slots({3:0,2:0})
        with self.assertRaisesRegex(ValueError,'Companion fashion belongs'):slots.resolve_slots({3:0,2**80:0})
        with self.assertRaises(OverflowError):slots.resolve_slots({2**80:0})
    def test_manufacture_batch_order_and_coercion(self):
        first=self.data.proof();second=self.data.proof(2);second['template']='2'
        self.source_rows([first]*600+[second])
        self.assertEqual(craft.inventory_definitions(),{1:first,'2':second})
        self.assertEqual(self.data.connections,1)
        self.assertLessEqual(self.data.max_parameters,256)
    def test_manufacture_identity_and_unknown_failures(self):
        good=self.data.proof();self.source_rows([good],client='changed')
        with self.assertRaisesRegex(ValueError,'Craft client mismatch'):craft.inventory_definitions()
        self.source_rows([good]);self.source.write_bytes(self.source.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'Craft inventory identity'):craft.inventory_definitions()
        self.source_rows([dict(template=999,record_sha256='bad')])
        with self.assertRaisesRegex(ValueError,'Unknown client item: 999'):craft.inventory_definitions()
    def test_manufacture_malformed_error_priority(self):
        self.source_rows([dict(template=1,record_sha256='bad'),dict(template=2**80)])
        with self.assertRaisesRegex(ValueError,'Craft item changed'):craft.inventory_definitions()
        self.source_rows([dict(template=2**80)])
        with self.assertRaises(OverflowError):craft.inventory_definitions()
        self.source_rows([self.data.proof(2)])
        self.data.db.execute('UPDATE items SET stats=? WHERE id=2',(b'bad',))
        with self.assertRaises(struct.error):craft.inventory_definitions()
    def test_transient_fashion_records_are_reproved_and_decode_in_order(self):
        self.source_rows([self.data.proof(1),self.data.proof(2)])
        result=craft.inventory_fashion_records()
        self.assertEqual(craft.inventory_fashion_position(result[2]),0)
        self.assertEqual(slots.resolve_slots_from_records({2:0},{2:result[2][0]}),{2:15})
        self.data.db.execute('UPDATE items SET stats=? WHERE id=2',(b'bad',))
        result=craft.inventory_fashion_records()
        self.assertEqual(craft.inventory_fashion_position(result[1]),0)
        with self.assertRaises(struct.error):craft.inventory_fashion_position(result[2])
        self.data.db.execute('UPDATE items SET record=? WHERE id=2',(bytes(211),))
        with self.assertRaisesRegex(ValueError,'Craft item changed'):craft.inventory_fashion_records()
    def test_companion_batch_uses_one_bounded_connection(self):
        self.data.db.executemany('INSERT INTO items VALUES (?,?,0,?,?)',
            [(t,bytes(211),bytes(28),b'')for t in range(10,610)])
        existing=dict.fromkeys(range(10,610),0)
        self.assertEqual(slots.resolve_slots(existing),existing)
        self.assertEqual(self.data.connections,1)
        self.assertEqual(self.data.item_calls,0)
        self.assertLessEqual(self.data.max_parameters,256)


if __name__=='__main__':unittest.main(verbosity=2)
