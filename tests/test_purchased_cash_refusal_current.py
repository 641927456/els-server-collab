"""Portable original D7D refusal contract and its exact bounded route."""
import ast,struct,unittest
from pathlib import Path
from types import SimpleNamespace
from els_server.domain import local_session
from els_server.protocol.protocol_codec import Event
from els_server.protocol.shop_messages import purchased_cash_unavailable_ack

class PurchasedCashRefusal(unittest.TestCase):
    def test_original_failure_shape_and_no_account_access(self):
        expected=struct.pack('>iiIIi',-1,0,0,0,0)
        result=purchased_cash_unavailable_ack()
        self.assertEqual((result.event_id,result.kind,result.payload),(0x201,0xd7d,expected))
        # Execute only the actual frozen D7C branch, without fabricating the
        # rest of a live session. Original authenticated TLS evidence is separate.
        tree=ast.parse(Path(local_session.__file__).read_bytes())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef)and n.name=='LocalSession')
        fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef)and n.name=='_handle')
        branches=[n for n in fn.body if isinstance(n,ast.If)and any(isinstance(x,ast.Constant)and x.value==0xd7c for x in ast.walk(n.test))]
        self.assertEqual(len(branches),1)
        probe=ast.parse('def invoke(self,event,kind):\n    pass\n');probe.body[0].body=[branches[0],ast.Return(value=ast.Constant(None))]
        ast.fix_missing_locations(probe);namespace={};exec(compile(probe,'<actual-D7C-branch>','exec'),namespace)
        class NoAccount:
            shop_test=True
            def __getattr__(self,name):raise AssertionError('Refusal may not inspect account/player state: '+name)
        for payload in(b'',bytes(3),struct.pack('>iiIIB',1,77000,0,0,0)):
            event=Event(0x202,kind=0xd7c,payload=payload)
            replies=namespace['invoke'](NoAccount(),event,event.kind)
            self.assertEqual([(e.kind,e.payload)for e in replies],[(0xd7d,expected)])
        self.assertIsNone(namespace['invoke'](SimpleNamespace(shop_test=False),Event(0x202,kind=0xd7c,payload=b''),0xd7c))

if __name__=='__main__':unittest.main()
