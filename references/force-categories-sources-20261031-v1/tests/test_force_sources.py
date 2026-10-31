"""Owned temporary SQLite: real Force consumers and acquisition transactions."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import json,sqlite3,struct,sys,unittest,uuid
import test_force_categories as base
from els_server.domain.native_force_catalog import catalog,exclusion_group
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import next_uid,insert
from els_server.storage.native_force_exchange import exchange
NOW=1793420000
PACKETS=[]

class Sources(unittest.TestCase):
    setUp=base.ForceCategories.setUp
    dump=base.ForceCategories.dump

    def seed(self,t,n=1):
        # Explicit owned fixture state; production grants use their source writer.
        with closing(sqlite3.connect(self.path))as db,db:
            rows=load_items(db,1001);group=TEMPLATE_BAG_GROUPS[t];used={i['slot']for i in rows if i['group']==group};out=[]
            while n:
                slot=next(s for s in range(36)if s not in used);used.add(slot);take=min(n,TEMPLATE_MAX_STACKS[t]);n-=take
                out.append(insert(db,1001,dict(uid=next_uid(db),template=t,metadata=VERIFIED_TEMPLATES[t],group=group,slot=slot,count=take)))
        return out[0]

    def town(self,t):
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE location SET town=? WHERE uid=1001',(t,))

    def payload(self,r):return struct.pack('>iQiiiiiBi',r['house'],0,r['source'],r['source_quantity'],r['destination']if r['type']==3 else 0,r['type'],1,1,0)

    def test_all_common_books_learn_cold_and_extract(self):
        from els_server.storage.boosting_2026_force_inventory import use_book
        from els_server.domain.local_session import LocalAccount
        from els_server.storage.local_state import LocalState
        for row in catalog()['books']:
            with self.subTest(template=row['item']):
                item=self.seed(row['item']);payload=struct.pack('>QQiiIB',item['uid'],0,0,0,0,0)
                result=use_book(self.path,1001,1,payload,'all-book-'+str(row['item']),now=NOW)
                cold=LocalAccount(LocalState(self.path));cold.enable_characters();cold.enable_inventory();c=cold.character();self.assertIn(dict(skill=row['skill'],rank=row['native_rank'],template=row['item']),[{k:r[k]for k in('skill','rank','template')}for r in c['force_inventory']])
                PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in result['events']if e.kind==0x6cb)
                from els_server.storage.boosting_2026_force_extraction import action
                self.seed(135866)
                answer=action(self.path,1001,1,struct.pack('>iB',row['skill'],row['native_rank']),'extract-'+str(row['item']),now=NOW)
                PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in answer['events'])
                with closing(sqlite3.connect(self.path))as db,db:
                    self.assertTrue(any(i['template']==row['item']for i in load_items(db,1001)))
                    db.execute('DELETE FROM inventory_items WHERE owner=1001')

    def test_native_exchange_all_rows_and_exact_replay(self):
        for i,r in enumerate(catalog()['exchanges']):
            with self.subTest(index=i,template=r['destination']):
                town=catalog()['npc_towns'][str(r['house'])][0];self.town(town);self.seed(r['source'],r['source_quantity']);payload=self.payload(r)
                events=exchange(self.path,1001,town,payload,'exchange-'+str(i),account_id=1,authorize=lambda:True,now=NOW)
                PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in events)
                before=self.dump();exchange(self.path,1001,town,payload,'exchange-'+str(i),account_id=1,authorize=lambda:True,now=NOW);self.assertEqual(self.dump(),before)
                with closing(sqlite3.connect(self.path))as db,db:
                    self.assertTrue(any(i['template']==r['destination']for i in load_items(db,1001)))
                    db.execute('DELETE FROM inventory_items WHERE owner=1001')

    def test_exchange_failure_quota_reset_and_rollback(self):
        r=next(r for r in catalog()['exchanges']if r['destination']==43958);self.town(20010);self.seed(r['source'],960);payload=self.payload(r);before=self.dump()
        with patch('els_server.storage.native_force_exchange._commit',side_effect=ValueError('injected')):
            with self.assertRaisesRegex(ValueError,'injected'):exchange(self.path,1001,20010,payload,'failed',account_id=1,authorize=lambda:True,now=NOW)
        self.assertEqual(self.dump(),before)
        with self.assertRaises(ValueError):exchange(self.path,1001,20010,payload,'owner',account_id=2,authorize=lambda:True,now=NOW)
        self.assertEqual(self.dump(),before)
        exchange(self.path,1001,20010,payload,'quota1',account_id=1,authorize=lambda:True,now=NOW);before=self.dump()
        with self.assertRaisesRegex(ValueError,'weekly'):exchange(self.path,1001,20010,payload,'quota2',account_id=1,authorize=lambda:True,now=NOW)
        self.assertEqual(self.dump(),before)
        exchange(self.path,1001,20010,payload,'quota3',account_id=1,authorize=lambda:True,now=NOW+7*86400)

    def test_shop_craft_and_challenge_selection(self):
        from els_server.storage.npc_trade import purchase
        from els_server.storage.fixed_cubes import open_cube
        self.town(20010)
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE reward_balances SET ed=20000000 WHERE uid=1001')
        purchase(self.path,1001,20010,struct.pack('>BHIiiiiii',0,0,3,295707,1,295722,1,295732,1)+struct.pack('>i',10017),'camilla')
        from els_server.storage.manufacture import execute
        self.seed(190812)
        receipt=execute(self.path,1001,1,struct.pack('>iiqI',295708,1,-1,0),'upgrade',now=NOW)
        self.assertEqual(receipt['audit']['rewards'],{295708:1})
        PACKETS.append(dict(kind=0x199,payload=receipt['response'].hex()))
        cube=self.seed(62263);payload=struct.pack('>QBBBIii',cube['uid'],0,0,0,1,43678,0)
        events=open_cube(self.path,1001,62263,payload,'challenge-cube');PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in events)
        before=self.dump();open_cube(self.path,1001,62263,payload,'challenge-cube');self.assertEqual(self.dump(),before)

    def test_exclusion_groups(self):
        from els_server.domain.boosting_2026_force_equipment import changed
        from els_server.domain.skill_state import validate_slots
        from els_server.domain.skill_rules import equippable_skills
        c=base.role();c['force_inventory']=[dict(skill=r['skill'],rank=r['native_rank'],template=r['item'])for r in catalog()['books']if r['native_rank']in(5,6)]
        for a,b in((900401,900412),(900402,900413),(900406,900414)):
            c['force_slots']=((a,5),)+((0,0),)*10
            slots=changed(c,struct.pack('>iiiB',1,1,b,5));self.assertEqual(slots[0],(0,0));self.assertEqual(slots[1],(b,5))
        slots=(900202,900204)+(0,)*20
        with self.assertRaises(ValueError):validate_slots(slots,equippable_skills(c),c)

    def test_henir_stage_mail_claim_weekly_and_source_guard(self):
        from els_server.domain.dungeon_routes import DungeonRun
        from els_server.storage.henir_force_rewards import issue
        from els_server.storage.game_mail import claim
        for mid,total in((38100,77),(35880,40)):
            run=DungeonRun(mid,str(uuid.uuid4()),clock=lambda:1000)
            for stage in range(len(run.rotation)):
                run.loaded();run.defeated={n['key']:{}for n in run.current['npcs']};run.portal_requested=True
                run.poll_ready();run.ready_at=0;self.assertTrue(run.poll_ready())
                events=issue(self.path,1001,1,run,authorize=lambda:True,now=NOW);PACKETS.extend(dict(kind=e.kind,payload=e.payload.hex())for e in events)
                before=self.dump();self.assertEqual(issue(self.path,1001,1,run,authorize=lambda:True,now=NOW),[]);self.assertEqual(self.dump(),before)
                if run.next['kind']!=4:run.advance()
            with closing(sqlite3.connect(self.path))as db:
                rows=db.execute('SELECT h.mail_id,p.item_json FROM henir_force_rewards h JOIN player_mail_items p ON p.mail_id=h.mail_id WHERE h.dungeon=?',(mid,)).fetchall()
                self.assertEqual(sum(json.loads(r[1])['count']for r in rows),total)
            for mail,_ in rows:
                claim(self.path,1,1001,[mail],lambda *args:[],now=NOW,include_items=True)
            before=self.dump();claim(self.path,1,1001,[rows[0][0]],lambda *args:[],now=NOW,include_items=True);self.assertEqual(self.dump(),before)
        run=DungeonRun(35880,str(uuid.uuid4()));before=self.dump()
        with self.assertRaises(ValueError):issue(self.path,1001,1,run,authorize=lambda:True,now=NOW)
        self.assertEqual(self.dump(),before)

if __name__=='__main__':
    result=unittest.main(argv=[sys.argv[0],*base.remaining],verbosity=2,exit=False)
    if result.result.wasSuccessful():(base.HOME/'source-test-packets.json').write_text(json.dumps(PACKETS),encoding='utf8')
    raise SystemExit(not result.result.wasSuccessful())
