"""Executable shared-entry properties; native ABI proof is recorded separately."""
from pathlib import Path
from types import ModuleType
from unittest.mock import patch
import hashlib,importlib.util,itertools,math,struct,sys,unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'references/registered-ground-items-20261101-v1/source/server/online/els_server/domain'

class RegisteredGroundTests(unittest.TestCase):
    def setUp(self):
        self.modules={};self.refuse=False
        def module(name,**values):
            result=ModuleType(name);result.__dict__.update(values);self.modules[name]=result;return result
        def descriptor(t):
            if self.refuse:raise ValueError('source evidence rejected')
        module('els_server.domain.hunter_chest_rules',ground_templates=lambda:frozenset())
        module('els_server.domain.fishing_bait_loot',TEMPLATES=frozenset())
        self.registered={77000:2,77010:2,77180:2,250003246:0,118177:0}
        module('els_server.domain.inventory_items',VERIFIED_TEMPLATES=self.registered)
        for name in('dungeon_equipment_loot_rules','dungeon_loot_catalog','dungeon_material_loot_catalog','dungeon_source_loot','native_script_loot'):
            module('els_server.domain.'+name,TEMPLATES=frozenset((118177,))if name=='dungeon_source_loot'else frozenset(),descriptor=descriptor)
        self.patch=patch.dict(sys.modules,self.modules);self.patch.start();self.addCleanup(self.patch.stop)
        self.pickup=self.load('drop_pickup');self.drop=self.load('dungeon_drops')
        # Synthetic fixed body isolates parser properties from the native ABI.
        # Actual320-byte native constructors and2240 writers are qualified offline.
        self.body=struct.pack('>I',77000)+bytes(316)
        self.pickup.BODY_SHA=hashlib.sha256(self.body).hexdigest()

    def load(self,name):
        full='els_server.domain.'+name;spec=importlib.util.spec_from_file_location(full,SOURCE/(name+'.py'))
        value=importlib.util.module_from_spec(spec);self.modules[full]=value;sys.modules[full]=value;spec.loader.exec_module(value);return value

    def packet(self,t,order):
        values={'item':struct.pack('>I',t)+self.body[4:],'drop_id':struct.pack('>I',12345),
            'flag':bytes(1),'player_xyz':struct.pack('>3f',10.,20.,30.),'drop_xyz':struct.pack('>3f',11.,21.,31.),'opaque':struct.pack('>I',4)+b'test'}
        return b''.join(values[k]for k in order)

    def test_registered_templates_preserve_CF_and_D2_identity(self):
        for t in self.registered:
            with self.subTest(template=t):
                self.assertEqual(struct.unpack_from('>i',self.drop.ground_drop_notice(12345,(0,0,0),template=t).payload,4)[0],t)
                self.assertEqual(struct.unpack_from('>i',self.drop.ground_pickup_notice(12345,template=t).payload,8)[0],t)

    def test_every_field_order_preserves_server_identity_and_fixed_quantity(self):
        fields=('item','drop_id','flag','player_xyz','drop_xyz','opaque')
        for order in itertools.permutations(fields):
            mode=dict(mode=4,fields=[dict(field=k)for k in order])
            for t in self.registered:
                value=self.pickup.decode_mode(self.packet(t,order),mode)
                self.assertEqual((value['template'],value['drop_id'],value['quantity']),(t,12345,1))
                self.assertEqual(value['drop_xyz'],(11.,21.,31.))

    def test_unknown_and_non_integer_templates_are_rejected(self):
        for t in(True,False,0,-1,2**31,None,1.0,'77010',999999):
            with self.subTest(template=t),self.assertRaises(ValueError):self.pickup.require_ground_template(t)

    def test_registered_source_still_requires_its_existing_descriptor(self):
        self.refuse=True
        for fn in(lambda:self.pickup.require_ground_template(118177),lambda:self.drop.ground_drop_notice(12345,(0,0,0),template=118177),lambda:self.drop.ground_pickup_notice(12345,template=118177)):
            with self.assertRaises(ValueError):fn()

    def test_client_cannot_mutate_native_body_or_currency_amount(self):
        order=('item','drop_id','flag','player_xyz','drop_xyz','opaque');mode=dict(mode=4,fields=[dict(field=k)for k in order])
        raw=bytearray(self.packet(77010,order));raw[5]=2
        with self.assertRaises(ValueError):self.pickup.decode_mode(bytes(raw),mode)
        with self.assertRaises(ValueError):self.drop.ground_pickup_notice(12345,template=77010,ed=1)

if __name__=='__main__':unittest.main()
