import json,math,struct,unittest
from pathlib import Path
from unittest.mock import patch
from els_server.domain.equipment_repair import template_quote,normal_quote
from els_server.domain.normal_equipment import definitions
from els_server.game_data import client_data
from els_server.protocol.repair_messages import request,acknowledgement


class RepairQuoteTests(unittest.TestCase):
    def test_native_float_order_and_missing_durability(self):
        # Float32 multiplication rounds 81999.998... to 82000 before truncation.
        self.assertEqual(template_quote(60100,0)['subtotal_ed'],82000)
        self.assertEqual(template_quote(60100,9999)['subtotal_ed'],8)
        self.assertEqual(template_quote(30224,1999)['subtotal_ed'],9601)
        self.assertEqual(template_quote(100,10000)['subtotal_ed'],0)
        self.assertEqual(template_quote(3000,0)['subtotal_ed'],0)
        item=dict(uid=1,template=100,metadata=1,count=1,group=1,slot=0)
        q=normal_quote([item]);self.assertEqual(q['baseline_total_ed'],2000)
        self.assertFalse(q['transaction_authorized']);self.assertEqual(q['items'][0]['current'],0)
        with self.assertRaises(ValueError):normal_quote([item,item])
        for durability in (-1,10001,True,1.5):
            with self.assertRaises(ValueError):template_quote(100,durability)

    def test_full_admitted_catalog_rates_and_overflow_rejection(self):
        data=client_data();repairable=0
        for template in definitions():
            d=data.item(template)
            if d['flags4']&0xf000000!=0x1000000:continue
            repairable+=1;rate=struct.unpack_from('<f',d['record'],20)[0]
            self.assertTrue(math.isfinite(rate) and rate>=0)
            self.assertEqual(template_quote(template,10000)['subtotal_ed'],0)
        self.assertGreater(repairable,40000)
        d=dict(data.item(100));raw=bytearray(d['record']);struct.pack_into('<f',raw,20,1e9);d['record']=bytes(raw)
        # Keep the verified maximum intact; synthetic corrupt rate is rejected.
        with patch.object(data,'item',return_value=d):
            with self.assertRaises(ValueError):template_quote(100,0)

    def test_request_context_and_ack_preserve_inventory_fields(self):
        wire=struct.pack('>IQQBBi',2,123,124,0,0,0)
        self.assertEqual(request(wire),dict(uids=(123,124),flag_a=0,flag_b=0,form=0))
        for bad in (wire[:-1],wire+b'\0',struct.pack('>IQQBBi',2,123,123,0,0,0),struct.pack('>IQBBi',1,123,2,0,0),struct.pack('>IQBBi',1,123,0,0,2),bytes(10)):
            with self.assertRaises(ValueError):request(bad)
        i=dict(uid=123,template=100,metadata=1,count=1,group=9,slot=9,durability=10000,attributes=[1,0,0,0])
        result=acknowledgement(98400,[i]);self.assertEqual(struct.unpack_from('>iQiiI',result),(0,98400,0,0,1))
        self.assertEqual(struct.unpack_from('>h',result,24+20),(10000,))
        with self.assertRaises(ValueError):acknowledgement(98400,[i,i])

if __name__=='__main__':unittest.main()
