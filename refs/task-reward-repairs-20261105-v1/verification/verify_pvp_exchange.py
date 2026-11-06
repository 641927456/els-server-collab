"""Task32010 coins through original selected exchange and unchanged shared ledger."""
import json,struct,unittest
from types import SimpleNamespace
from unittest.mock import patch
import verify_furniture as harness
from verify_furniture import Consumers,encode,checks,PRIVATE,OUT,temp
from els_server.domain.pvp_material_exchange_flow import handle
from els_server.protocol.protocol_codec import Event
from els_server.domain.pvp_material_exchange import catalog

class Coins(Consumers):
    def test_source_coin_exchange(self):
        self.ready(32010);source=self.claim(32010)
        self.assertEqual({i['template']:i['count']for i in source['updates']if i['template']in(72920,72980)},{72920:6,72980:10})
        town=int(next(iter(catalog()['towns'])))
        self.account.save_location(town,0,0,(0.,0.,0.))
        s=SimpleNamespace(account=self.account,active_map=town,shop_session_id='owned-pvp-exchange')
        def event(t,count=1):
            payload=struct.pack('>iQiiiiiBi',40016,0,72920,1,t,3,count,1,0)
            return Event(0x202,kind=0x223,payload=payload,performers=(0,))
        with patch('els_server.domain.housing_access_flow.capture',return_value=(lambda:True,self.guard)):
            for sequence,t in enumerate((72930,72940,72950),1):
                before=self.dump()
                with patch('els_server.storage.material_exchange.encode_event',side_effect=ValueError('owned late exchange fault')):
                    encode(handle(s,event(t,2),sequence))
                self.assertEqual(before,self.dump())
                encode(handle(s,event(t,2),sequence))
                self.assertEqual(next(i for i in self.items()if i['template']==t)['count'],2)
                before=self.dump();encode(handle(s,event(t,2),sequence));self.assertEqual(before,self.dump())
            self.assertFalse(any(i['template']==72920 for i in self.items()))
            before=self.dump();encode(handle(s,event(72930),99));self.assertEqual(before,self.dump())
        self.assertEqual(next(i for i in self.items()if i['template']==72980)['count'],10)
        checks.append(dict(case='task32010_coin_exchange',source_coins=6,source_fragments=10,selected_stones_each=2,ratio='1:1',rollback=True,replay=True,insufficient_no_debit=True,
                           original223_dispatch=True,current_actor_capture_reused=True,actor_capture_mocked_for_owned_test=True))

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(['Coins.test_source_coin_exchange'],module=__import__(__name__)));temp.cleanup()
    report=dict(ok=result.wasSuccessful(),checks=checks,failures=[dict(test=str(t),trace=e)for t,e in result.failures+result.errors],private_SQL_removed=not PRIVATE.exists(),formal_SQL=False,natural_GUI=False,network=False)
    (OUT/'pvp-exchange-validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(dict(ok=report['ok'],private_SQL_removed=report['private_SQL_removed'])))
    raise SystemExit(0 if report['ok']else 1)
