"""Circuit mode16 requires the selected actor's current authenticated lease."""
import struct,sys,unittest
from types import SimpleNamespace as NS
from unittest.mock import patch
from els_server.domain.equipment_circuit_flow import handle
from els_server.protocol.protocol_codec import Event

def actor():
    account=NS(uid=1001,account_id=8,store=NS(uid=1001,path='unused'),characters=[1001])
    root=NS(character_accounts={1001:account});account.root=root
    s=NS(role='game',phase='town_ready',account=account,identity={'id':8},released=False,client_build='dx11_260923',item_test=True,shop_session_id='test')
    s.application=NS(accounts={8:root},playing={8:s});return s

class CircuitAdmission(unittest.TestCase):
    def event(self):return Event(0x202,kind=0x6e7,payload=struct.pack('>QIiIiQBiB',3001,1,28,1,1,3002,0,16,0))
    def reject(self,s):
        def forbidden():raise AssertionError('Stale actor read balances')
        s.account.get_reward_balances=forbidden
        # Admission unit only; full native encoding is qualified in artifact TLS.
        with patch('els_server.domain.equipment_circuit_flow.acknowledgement',
                   side_effect=lambda uid,ed,result:Event(0x201,kind=0x6e8,payload=struct.pack('>i',result))):
            answer=handle(s,self.event(),1)
        self.assertEqual(answer[0].kind,0x6e8)
        self.assertEqual(struct.unpack_from('>i',answer[0].payload)[0],2005)
    def test_replaced_playing_lease(self):
        s=actor();s.application.playing[8]=object();self.reject(s)
    def test_selected_store_mismatch(self):
        s=actor();s.account.store.uid=1002;self.reject(s)
    def test_replaced_account_root(self):
        s=actor();s.application.accounts[8]=object();self.reject(s)
    def test_authenticated_identity_is_forwarded(self):
        s=actor();s.account.get_reward_balances=lambda:{'ed':77};calls=[]
        core=NS(perform=lambda *args,**kwargs:calls.append((args,kwargs))or[])
        with patch.dict(sys.modules,{'els_server.storage.equipment_circuits':core}):
            self.assertEqual(handle(s,self.event(),9),[])
        self.assertEqual(calls[0][1],{'account_id':8})
        self.assertEqual(calls[0][0][1],1001)

if __name__=='__main__':unittest.main()
