"""Portable regression contracts; actual App/SQL evidence is separately frozen."""
from pathlib import Path
import ast,importlib.util,math,struct,sys,unittest
from tools.check_trade_board_sources import ARCHIVE,verify

def module(name,relative):
    spec=importlib.util.spec_from_file_location(name,ARCHIVE/'shared'/relative)
    result=importlib.util.module_from_spec(spec);sys.modules[name]=result
    spec.loader.exec_module(result)
    return result

class TradeBoardReferenceTests(unittest.TestCase):
    def test_frozen_dual_manifest_and_exact_hook_scope(self):
        self.assertTrue(verify()['ok'])

    def test_native_saved_search_signed_key_and_complete_body(self):
        wire=module('tradeboard_favorite_reference','els_server/protocol/tradeboard_favorite_messages.py')
        record={name:'角色收藏'if name=='text_09'else '魔法'if kind=='text'else True if kind=='bool'else (17,29)if kind=='vector'else 0 for name,kind in wire.LAYOUT}
        record['key_00']=-7
        payload=wire.request_body(wire.Request(2,record))
        self.assertEqual(wire.request(payload),wire.Request(2,record))
        for cut in range(len(payload)):
            with self.assertRaises(ValueError):wire.request(payload[:cut])
        with self.assertRaises(ValueError):wire.request(payload+b'\0')
        reader=wire.Reader(wire.reply([record,dict(record,key_00=4)]).payload)
        self.assertEqual((reader.number('i'),reader.number('B'),reader.number('I')),(0,0,2))
        self.assertEqual([reader.cc()['key_00']for _ in range(2)],[-7,4])
        self.assertEqual(reader.pos,len(reader.payload))
        with self.assertRaises(ValueError):wire.reply([dict(record,key_00=4),record])

    def test_wallet_batches_keep_whole_units_and_telescoping_fee(self):
        # Extract the unchanged pure functions, without importing live database
        # dependencies. This checks the archived source, not a copied algorithm.
        tree=ast.parse((ARCHIVE/'shared/els_server/storage/trade_board_state.py').read_bytes())
        selected=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in ('commission','settlement_batch')]
        self.assertEqual(len(selected),2)
        scope={'math':math};exec(compile(ast.Module(body=selected,type_ignores=[]),'archived settlement functions','exec'),scope)
        fee,batch=scope['commission'],scope['settlement_batch']
        self.assertEqual(batch(8,10_000_000_000,70_000_000_000),(7,70_000_000_000,3_500_000_000,66_500_000_000))
        self.assertEqual(batch(1,10_000_000_000,3_500_000_000),(0,0,0,0))
        self.assertEqual(batch(10,1,0),(1,1,1,0))
        for pending in (1,2,9,10,11,19,20,21,67):
            for price in (1,2,9,97,101):
                for room in (0,1,8,20,92,100):
                    units,gross,charged,net=batch(pending,price,room)
                    self.assertLessEqual(net,room)
                    self.assertEqual((gross,net),(units*price,gross-charged))
                    self.assertEqual(charged+fee((pending-units)*price),fee(pending*price))
                    possible=[u for u in range(pending+1)if u*price-(fee(pending*price)-fee((pending-u)*price))<=room]
                    self.assertEqual(units,max(possible))
        for bad in ((True,1,0),(1,10_000_000_001,0),(1,1,70_000_000_001)):
            with self.assertRaises(ValueError):batch(*bad)

if __name__=='__main__':unittest.main()
