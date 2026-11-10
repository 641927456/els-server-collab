from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import hashlib,json,sqlite3,struct,sys,unittest,uuid
ROOT=Path('G:/els');W=Path(__file__).resolve().parent;B=ROOT/'analysis/pr771-firstbatch-20261103-v1';R=B/'runtime'
sys.path[:0]=[str(R),str(B)]
import test_secondbatch as base
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.reward_rules import item_plan
from els_server.storage.companion_state import handle as activate,snapshot
from els_server.storage import mount_races as races,mount_growth,mount_state
from els_server.domain import mount_racing_plan as plans,mount_racing_rules as rules
from els_server.protocol import mount_racing_messages as wire


class Races(unittest.TestCase):
    def setUp(self):
        base.SecondBatch.setUp(self);self.members=[]
        for i in range(6):
            if i==0:owner,account=self.a.uid,self.a.account_id
            else:
                account=200+i;role=Characters(self.path,account).create('Racer'+str(i),1,'create-racer'+str(i));owner=role['uid']
            with closing(sqlite3.connect(self.path))as db,db:
                db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
                item=grant_items(db,[item_plan(550431,1)],owner)[0]
            activate(self.path,owner,0x432,struct.pack('>Q',item['uid']),'fixture-racer-'+str(i),account_id=account)
            mount=next(p for p in snapshot(self.path,owner)['companions']if p['kind']=='mount')
            self.members.append((owner,account,mount['uid']))
        self.race=str(uuid.uuid4());self.prepared=[]
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE mount_runtime SET accounted_at=1000')

    def prepare(self,db):self.prepared.append(1)
    def encode(self,db,data):return wire.booster_map(data['plans'])
    def begin(self,members=None,**kw):
        return races.begin(self.path,self.race,self.members if members is None else members,prepare=self.prepare,encode=self.encode,now=2000,**kw)
    def state(self):
        with closing(sqlite3.connect(self.path))as db:return {t:db.execute('SELECT * FROM '+t+' ORDER BY 1,2').fetchall()for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name NOT LIKE 'sqlite_%'ORDER BY name")}

    def test_start_once_cold_replay_and_stamina_freeze_until_town(self):
        data,event=self.begin(randbelow=lambda n:0);saved=self.state()
        again,reply=self.begin(randbelow=lambda n:1/0)
        self.assertEqual((data,event),(again,reply));self.assertEqual(self.state(),saved)
        for owner,account,uid in self.members:
            with patch('els_server.storage.mount_state.timestamp',return_value=5000):snap=snapshot(self.path,owner)
            m=next(p for p in snap['companions']if p['uid']==uid)
            self.assertEqual(m['stamina'],races.rules.policy()['race_stamina'])
        owner,account,uid=self.members[0];races.leave(self.path,owner,now=5000)
        with patch('els_server.storage.mount_state.timestamp',return_value=5060):snap=snapshot(self.path,owner)
        m=next(p for p in snap['companions']if p['uid']==uid)
        self.assertGreater(m['stamina'],60)

    def test_no_debit_for_wrong_roster_mount_level_or_encode_failure(self):
        before=self.state()
        for members in(self.members[:2],[self.members[0]]*3,[self.members[0],self.members[1],(*self.members[2][:2],self.members[0][2])]):
            with self.assertRaises(ValueError):self.begin(members)
            self.assertEqual(self.state(),before)
        with patch.object(races.plans,'standings',side_effect=ValueError('plan failure')):
            with self.assertRaisesRegex(ValueError,'plan failure'):self.begin()
        self.assertEqual(self.state(),before)
        def invalid_encode(db,data):raise ValueError('native encoder')
        with self.assertRaisesRegex(ValueError,'native encoder'):races.begin(self.path,self.race,self.members,prepare=self.prepare,encode=invalid_encode,now=2000)
        self.assertEqual(self.state(),before)

    def test_plan_rank_ties_and_client_cannot_set_growth(self):
        data,event=self.begin(randbelow=lambda n:0)
        self.assertEqual([r['uid']for r in data['standings']],[m[0]for m in self.members])
        self.assertEqual([r['rank']for r in data['standings']],list(range(1,7)))
        forged=struct.pack('>I',6)+b''.join(struct.pack('>Qiff',m[0],6-i,50.,3.)for i,m in enumerate(self.members))+struct.pack('>f',50.)
        claimed,duration=wire.finish_request(forged,[m[0]for m in self.members])
        self.assertEqual(claimed[0][1],6);self.assertEqual(data['standings'][0]['rank'],1)
        self.assertNotEqual(claimed[0][1],data['standings'][0]['rank'])

    def test_settle_once_actual_growth_cold_read_bonus_and_rollback(self):
        data,event=self.begin(randbelow=lambda n:0);owner,account,uid=self.members[0]
        def encode(db,data,rows):return {uid:wire.result(data,**r)for uid,r in rows.items()}
        members=[m[:2]for m in self.members]
        before=self.state()
        def failed(*args):raise ValueError('encode failed')
        with self.assertRaisesRegex(ValueError,'encode failed'):races.settle(self.path,self.race,members,prepare=self.prepare,encode=failed,now=2200)
        self.assertEqual(self.state(),before)
        races.leave(self.path,self.members[1][0],now=2050)
        answer=races.settle(self.path,self.race,members,prepare=self.prepare,encode=encode,now=2200);saved=self.state()
        self.assertEqual(races.settle(self.path,self.race,members,prepare=self.prepare,encode=encode,now=2200),answer)
        self.assertEqual(self.state(),saved)
        with closing(sqlite3.connect(self.path))as db:
            value=mount_growth.read(db,owner,uid)
            self.assertEqual(value['experience'],132)
            self.assertEqual(db.execute('SELECT COUNT(*)FROM mount_race_results WHERE settled=1').fetchone()[0],6)
        with closing(sqlite3.connect(self.path))as db:self.assertEqual(mount_growth.read(db,self.members[1][0],self.members[1][2])['experience'],0)

    def test_crystal_bonus_current_inventory_retry_and_late_guard_rollback(self):
        data,event=self.begin(randbelow=lambda n:n-1);owner,account,uid=self.members[0]
        members=[m[:2]for m in self.members]
        before=self.state();calls=[]
        def changed(db):
            calls.append(1)
            if len(calls)==2:raise ValueError('selected actor changed')
        def encode(db,data,rows):return rows
        with self.assertRaisesRegex(ValueError,'selected actor changed'):
            races.settle(self.path,self.race,members,prepare=changed,encode=encode,now=2200)
        self.assertEqual(self.state(),before)
        result=races.settle(self.path,self.race,members,prepare=self.prepare,encode=encode,now=2200)
        item=result[owner]['receipt']['items'][0];self.assertEqual((item['template'],item['count']),(714108,1))
        with closing(sqlite3.connect(self.path))as db,db:
            occupied={i['slot']for i in load_items(db,owner)if i['group']==item['group']}
            moved=next(i for i in range(30)if i not in occupied)
            db.execute('UPDATE inventory_items SET slot=? WHERE owner=? AND uid=?',(moved,owner,item['uid']))
        before=self.state();retry=races.settle(self.path,self.race,members,prepare=self.prepare,encode=encode,now=2200)
        self.assertEqual(self.state(),before)
        self.assertIn(((item['group'],item['slot']),None),retry[owner]['changes'])
        self.assertTrue(any(pos==(item['group'],moved)and value['uid']==item['uid']for pos,value in retry[owner]['changes']))

    def test_qualification_duplicate_start_and_crash_login_release(self):
        owner,account,uid=self.members[0]
        def refuse(change,pattern):
            with closing(sqlite3.connect(self.path))as db,db:change(db)
            before=self.state()
            with self.assertRaisesRegex(ValueError,pattern):self.begin()
            self.assertEqual(self.state(),before)
        refuse(lambda db:db.execute('UPDATE characters SET level=98 WHERE uid=?',(owner,)),'level99')
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE characters SET level=99 WHERE uid=?',(owner,))
        refuse(lambda db:db.execute('UPDATE companions SET unit=10005 WHERE uid=?',(uid,)),'permanent')
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE companions SET unit=105 WHERE uid=?',(uid,))
        refuse(lambda db:db.execute('UPDATE mount_runtime SET stamina=0,accounted_at=2000 WHERE uid=?',(uid,)),'60 stamina')
        with closing(sqlite3.connect(self.path))as db,db:db.execute('UPDATE mount_runtime SET stamina=120 WHERE uid=?',(uid,))
        self.begin(randbelow=lambda n:0);before=self.state()
        with self.assertRaisesRegex(ValueError,'already racing'):
            races.begin(self.path,str(uuid.uuid4()),self.members,prepare=self.prepare,encode=self.encode,now=2000)
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            mount_state.login(db,owner,now=5000)
        with closing(sqlite3.connect(self.path))as db:
            self.assertIsNone(db.execute('SELECT 1 FROM mount_race_busy WHERE owner=?',(owner,)).fetchone())
            self.assertEqual(db.execute('SELECT disconnected,settled FROM mount_race_results WHERE owner=?',(owner,)).fetchone(),(1,0))
            self.assertEqual(db.execute('SELECT stamina FROM mount_runtime WHERE uid=?',(uid,)).fetchone()[0],60)

    def test_temporary_mount_admission_and_in_race_reset_reject_without_debit(self):
        owner,account,uid=self.members[0]
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');mount_state.assign_lifetime(db,owner,mount_state.owned(db,owner,uid),dict(group=4,slot=0,template=550431),1,1000)
        before=self.state()
        with self.assertRaisesRegex(ValueError,'permanent'):self.begin()
        self.assertEqual(self.state(),before)
        with closing(sqlite3.connect(self.path))as db,db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM mount_lifetimes')
            mount_growth.save(db,owner,uid,rules.grow(0,{},200,lambda n:0))
            grant_items(db,[item_plan(714108,1)],owner)
        self.begin(randbelow=lambda n:0);before=self.state()
        from els_server.storage.mount_reset import perform
        with self.assertRaisesRegex(ValueError,'during a race'):
            perform(self.path,owner,account,struct.pack('>Q',uid),'racing-reset',prepare=self.prepare)
        self.assertEqual(self.state(),before)


if __name__=='__main__':unittest.main(verbosity=2)
