"""Normal private quest claims and all15 native role mappings through shared boxes."""
import json,sqlite3,struct,unittest
import uuid
from contextlib import closing
from unittest.mock import patch
import verify_furniture as harness
from verify_furniture import Consumers,encode,box,checks,PRIVATE,OUT,temp
from els_server.domain.owned_reward_boxes import outputs_for,plan_for
from els_server.domain.character_rules import CLASSES
from els_server.domain.equipment_requirements import catalog as requirements
from els_server.game_data import client_data
from els_server.storage.fixed_cubes import open_cube
from els_server.storage.equipment_moves import move_equipment
from els_server.storage.item_instances import remove
from els_server.protocol.protocol_codec import Event

class Boxes(Consumers):
    def test_pvp_accessories(self):
        from els_server.domain.ordinary_accessories import definitions
        from els_server.storage.identification_ui import perform as identify
        from els_server.domain.identification_ui import initial_pending
        from els_server.storage.wear_moves import move
        session=str(uuid.uuid4());sequence=0;count=0;items_used=0
        for base in sorted({r['base_class']for r in CLASSES.values()}):
            unit=client_data().unit(base)['unitType']
            self.sql('UPDATE characters SET unit_type=?,unit_class=?WHERE uid=?',(unit,base,self.uid))
            character=dict(unit_type=unit,unit_class=base,level=99,transcendence=False,master=False)
            for qid,t in((32020,701049),(32040,701050)):
                if base==1:
                    self.ready(qid);claim=self.claim(qid);item=next(i for i in claim['updates']if i['template']==t)
                else:item=self.grant(t)[0]
                before_ids={i['uid']for i in self.items()};payload=box(item['uid']);operation=f'box-{t}-{base}'
                if base==1:
                    before=self.dump()
                    with patch('els_server.storage.fixed_cubes.result',side_effect=ValueError('owned accessory encoding fault')):
                        with self.assertRaises(ValueError):open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard)
                    self.assertEqual(before,self.dump())
                encode(open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard))
                awarded=[i for i in self.items()if i['uid']not in before_ids]
                self.assertEqual({i['template']for i in awarded},{i['template']for i in outputs_for(t,character)})
                self.assertEqual(len(awarded),8 if t==701050 and unit==10 else 4)
                self.assertTrue(all(i['count']==1 and i['group']==2 and 'expires_at'not in i for i in awarded))
                before=self.dump();encode(open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard));self.assertEqual(before,self.dump())
                for i in awarded:
                    if i.get('identified')is False or initial_pending(i):
                        encode(identify(self.path,self.uid,0x438,struct.pack('>QB Ii',i['uid'],0,0,0),f'identify-{i["uid"]}',randbelow=lambda n:0,account_id=1))
                    slot=definitions()[i['template']]['slots'][0]
                    sequence+=1;response=move(self.path,struct.pack('>BiBiB',2,i['slot'],9,slot,0),self.uid,account_id=1,session_id=session,sequence=sequence)
                    encode(Event(0x201,kind=0x105,payload=response))
                    self.assertEqual(next(r for r in self.items()if r['uid']==i['uid'])['group'],9)
                    sequence+=1;response=move(self.path,struct.pack('>BiBiB',9,slot,2,i['slot'],0),self.uid,account_id=1,session_id=session,sequence=sequence)
                    encode(Event(0x201,kind=0x105,payload=response));items_used+=1
                with closing(sqlite3.connect(self.path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    for i in self.items():
                        if i['uid']not in before_ids:remove(db,self.uid,i)
                count+=1
        self.assertEqual(count,30);self.assertEqual(items_used,124)
        checks.append(dict(case='pvp_accessory_boxes',role_groups=count,templates=[701049,701050],source_claims=True,permanent_fixed_sets=True,
                           luciel_both_sets=True,items_identified_equipped_and_removed=items_used,rollback=True,replay=True))
    def test_pvp_gear(self):
        # Each simulated role must have its own empty equipment slots. Keep
        # the original Elsword starter gear out of other roles' fixture swaps.
        initial=[i for i in self.items()if i['group']==9]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            for i in initial:remove(db,self.uid,i)
        bases=sorted({r['base_class']for r in CLASSES.values()});count=0
        for base in bases:
            unit=client_data().unit(base)['unitType']
            self.sql('UPDATE characters SET unit_type=?,unit_class=?WHERE uid=?',(unit,base,self.uid))
            character=dict(unit_type=unit,unit_class=base,level=99,transcendence=False,master=False)
            for qid,t in((32000,72970),(32090,79076)):
                if base==1:
                    self.ready(qid);claim=self.claim(qid);item=next(i for i in claim['updates']if i['template']==t)
                else:item=self.grant(t)[0]
                before_ids={i['uid']for i in self.items()};payload=box(item['uid']);operation=f'box-{t}-{base}'
                if base==1:
                    before=self.dump()
                    with patch('els_server.storage.fixed_cubes.result',side_effect=ValueError('owned late cube encoding fault')):
                        with self.assertRaises(ValueError):open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard)
                    self.assertEqual(before,self.dump())
                encode(open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard))
                awarded=[i for i in self.items()if i['uid']not in before_ids]
                self.assertEqual({i['template']for i in awarded},{i['template']for i in outputs_for(t,character)})
                self.assertEqual(len(awarded),4 if t==72970 else 1)
                self.assertTrue(all(i['enhancement']==9 and i['count']==1 and i['group']==1 for i in awarded))
                before=self.dump();encode(open_cube(self.path,self.uid,t,payload,operation,account_id=1,prepare=self.guard));self.assertEqual(before,self.dump())
                for i in awarded:
                    slot=requirements()[1][client_data().item(i['template'])['equip_position']]
                    response=move_equipment(self.path,struct.pack('>BiBiB',1,i['slot'],9,slot,0),self.uid)
                    encode(Event(0x201,kind=0x105,payload=response))
                    worn=next(r for r in self.items()if r['uid']==i['uid'])
                    self.assertEqual((worn['group'],worn['slot'],worn['enhancement']),(9,slot,9))
                    response=move_equipment(self.path,struct.pack('>BiBiB',9,slot,1,i['slot'],0),self.uid)
                    encode(Event(0x201,kind=0x105,payload=response))
                with closing(sqlite3.connect(self.path))as db,db:
                    db.execute('BEGIN IMMEDIATE')
                    for i in self.items():
                        if i['uid']not in before_ids:remove(db,self.uid,i)
                count+=1
        self.assertEqual(count,30)
        checks.append(dict(case='pvp_gear_boxes',role_groups=30,templates=[72970,79076],source_claims=True,plus9_exact=True,all75_equipped_and_removed=True,rollback=True,replay=True))

if __name__=='__main__':
    import sys
    names=['Boxes.'+name for name in sys.argv[1:]]if len(sys.argv)>1 else['Boxes.test_pvp_gear','Boxes.test_pvp_accessories']
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromNames(names,module=__import__(__name__)));temp.cleanup()
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,checks=checks,failures=[dict(test=str(t),trace=e)for t,e in result.failures+result.errors],private_SQL_removed=not PRIVATE.exists(),formal_SQL=False,network=False,natural_battle=False,natural_GUI=False)
    (OUT/('pvp-accessory-validation.json'if len(sys.argv)>1 else'pvp-box-validation.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(ok=report['ok'],private_SQL_removed=report['private_SQL_removed'])))
    raise SystemExit(0 if report['ok']else 1)
