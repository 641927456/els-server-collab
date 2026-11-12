"""Authoritative profile recovery, account separation and real reward mail."""
from pathlib import Path
from contextlib import closing
import hashlib,json,sqlite3,sys,tempfile,time,unittest
W=Path(__file__).resolve().parent;R=Path('G:/els');BASE=R/'releases/online/native-feature-closures-20261107-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(R/'tools/pylibs'),str(R/'tools'),str(R)]
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(W/'source-v1/els_server/domain'))
els_server.storage.__path__.insert(0,str(W/'source-v1/els_server/storage'))
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import achievements as state,profession_state,resonance_state,game_mail
from els_server.storage.achievement_profiles import reconcile
from els_server.protocol.profession_messages import ProfessionState
from els_server.domain.profession_growth import advance_blacksmith,BLACKSMITH_STEPS
from els_server.domain.resonance import curve,level
from els_server.domain.achievement_catalog import points,progress_projection
from els_server.protocol.mail_attachment_messages import claim_ack


class ProfileSources(unittest.TestCase):
    def test_real_profile_authorities_backfill_once_rollback_share_and_claim(self):
        with tempfile.TemporaryDirectory(prefix='owned-achievement-profile-',dir=W)as folder:
            path=Path(folder)/'own.sqlite3';prepare(path)
            a=Characters(path,1).create('AchProfA',1,'profile-A')['uid']
            b=Characters(path,1).create('AchProfB',2,'profile-B')['uid']
            foreign=Characters(path,2).create('AchProfC',3,'profile-C')['uid']
            initial=ProfessionState(2,1,0,{},0,BLACKSMITH_STEPS[1])
            attained,granted,changed=advance_blacksmith(initial,sum(BLACKSMITH_STEPS[n]for n in range(1,7)))
            self.assertEqual(attained.level,7);self.assertTrue(changed)
            lesser,_,_=advance_blacksmith(initial,BLACKSMITH_STEPS[1])
            self.assertEqual(lesser.level,2)
            xp=curve()[149]['TOTAL_ER_EXP'];self.assertEqual(level(xp),150)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                profession_state.replace(db,a,1,0,attained)
                profession_state.replace(db,b,1,0,lesser)
                resonance_state.ensure(db);db.execute('INSERT INTO account_resonance VALUES(1,1,?,1)',(xp,))
            def dump():
                with closing(sqlite3.connect(path))as db:return list(db.iterdump())
            def recover(account,owner):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');return reconcile(db,account,owner,1794000000)
            before=dump()
            with self.assertRaisesRegex(RuntimeError,'late response failure'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');reconcile(db,1,a,1794000000)
                    raise RuntimeError('late response failure')
            self.assertEqual(dump(),before)
            self.assertEqual(set(recover(1,b)['completed']),{19,20,21,73,74,75})
            before=dump();self.assertEqual(recover(1,a),dict(completed=[],replayed=False));self.assertEqual(dump(),before)
            with closing(sqlite3.connect(path))as db:
                current=state.snapshot(db,1,a);self.assertEqual(current,state.snapshot(db,1,b))
                self.assertEqual(points(current['completed']),[60,60,0,0])
                self.assertEqual(len(progress_projection(current)),371)
                counts={row['id']:row['conditions'][0]['count']for row in current['progress']}
                self.assertEqual(counts[22],7)  # Two characters' levels7+2 are not level9.
                self.assertEqual(state.snapshot(db,2,foreign),dict(progress=[],completed=[],watched=[]))
            before=dump();self.assertEqual(recover(2,foreign),dict(completed=[],replayed=False));self.assertEqual(dump(),before)
            with self.assertRaises(ValueError):recover(2,a)
            self.assertEqual(dump(),before)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE');mids=state.claim(db,1,b,21,1794000100)
            self.assertEqual(len(mids),1)
            total,letters=game_mail.inbox(path,1,b,now=1794000200)
            self.assertEqual(total,1);self.assertEqual(letters[0]['item']['template'],118204)
            self.assertEqual(letters[0]['item']['count'],20)
            self.assertEqual(game_mail.inbox(path,1,a,now=1794000200),(0,[]))
            game_mail.claim(path,1,b,mids,lambda ids,ed,changes:claim_ack(ids,ed,changes),now=1794000200,include_items=True)
            before=dump();recover(1,b);self.assertEqual(dump(),before)
            with closing(sqlite3.connect(path))as db:
                self.assertEqual(db.execute('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=118204',(b,)).fetchone()[0],20)


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,production_database_access=False,
        profile_fixture_only=True,natural_profession_or_ERP_growth=False,
        verified='existing blacksmith growth function and canonical ERP curve, transactional cache backfill, rollback, account/character mail ownership and actual escrow-to-inventory claim',
        source_sha256={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts},
        errors=[detail[-2400:]for _,detail in result.errors],failures=[detail[-2400:]for _,detail in result.failures])
    (W/('profile-sources-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    raise SystemExit(not report['ok'])
