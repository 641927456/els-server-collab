"""Actual SQLite mail/inventory boundaries for original and deferred rewards."""
from pathlib import Path
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,sqlite3,sys,tempfile,time,unittest
W=Path(__file__).resolve().parent;R=Path('G:/els');BASE=R/'releases/online/native-feature-closures-20261107-v1'
sys.dont_write_bytecode=True;sys.path[:0]=[str(BASE),str(BASE/'vendor'),str(R/'tools/pylibs'),str(R/'tools'),str(R)]
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(W/'source-v1/els_server/domain'))
els_server.storage.__path__.insert(0,str(W/'source-v1/els_server/storage'))
from els_server.storage.game_schema import prepare
from els_server.storage.characters import Characters
from els_server.storage import achievements as state,game_mail
from els_server.domain.achievement_catalog import catalog
from els_server.protocol.mail_attachment_messages import claim_ack


class RewardMail(unittest.TestCase):
    def test_deferred_atomic_claim_character_scope_race_and_escrow(self):
        with tempfile.TemporaryDirectory(prefix='owned-achievement-mail-',dir=W)as folder:
            path=Path(folder)/'own.sqlite3';prepare(path)
            a=Characters(path,1).create('AchMailA',1,'mail-A')['uid']
            b=Characters(path,1).create('AchMailB',2,'mail-B')['uid']
            c=Characters(path,2).create('AchMailC',3,'mail-C')['uid']
            def dump():
                with closing(sqlite3.connect(path))as db:return list(db.iterdump())
            def complete(identity):
                definition=catalog()[identity]
                updates=[dict(achievement=identity,condition=d['id'],value=d['parameters'].get('m_iCount',1),complete=True)for d in definition['conditions']]
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');state.record(db,1,a,updates,'mail-fixture-'+str(identity),1794000000)
            def claim(owner,identity):
                with closing(sqlite3.connect(path,timeout=15))as db,db:
                    db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
                    return state.claim(db,1,owner,identity,1794000100)
            complete(13);complete(14)
            before=dump()
            with self.assertRaisesRegex(state.AchievementError,'pending verification'):claim(a,13)
            self.assertEqual(dump(),before)
            with self.assertRaises(ValueError):claim(c,14)
            self.assertEqual(dump(),before)
            with self.assertRaisesRegex(RuntimeError,'encoding failed'):
                with closing(sqlite3.connect(path))as db,db:
                    db.execute('BEGIN IMMEDIATE');state.claim(db,1,a,14,1794000100)
                    raise RuntimeError('encoding failed')
            self.assertEqual(dump(),before)
            with ThreadPoolExecutor(2)as executor:
                futures=[executor.submit(claim,owner,14)for owner in(a,b)]
                results=[f.result()for f in futures]
            self.assertEqual(sorted(map(len,results)),[0,1])
            winner=a if results[0]else b;loser=b if winner==a else a;mid=next(v[0]for v in results if v)
            before=dump();self.assertEqual(claim(a,14),[]);self.assertEqual(claim(b,14),[]);self.assertEqual(dump(),before)
            total,letters=game_mail.inbox(path,1,winner,now=1794000200)
            self.assertEqual(total,1);self.assertEqual(letters[0]['item']['template'],98020)
            self.assertEqual(letters[0]['item']['count'],20)
            self.assertEqual(game_mail.inbox(path,1,loser,now=1794000200),(0,[]))
            self.assertEqual(game_mail.inbox(path,2,c,now=1794000200),(0,[]))
            def encode(ids,ed,changes):return claim_ack(ids,ed,changes)
            before=dump()
            with self.assertRaisesRegex(ValueError,'another character'):
                game_mail.claim(path,1,loser,[mid],encode,now=1794000200,include_items=True)
            self.assertEqual(dump(),before)
            game_mail.claim(path,1,winner,[mid],encode,now=1794000200,include_items=True)
            before=dump();game_mail.claim(path,1,winner,[mid],encode,now=1794000300,include_items=True)
            self.assertEqual(dump(),before)
            with closing(sqlite3.connect(path))as db:
                self.assertEqual(db.execute('SELECT SUM(count)FROM inventory_items WHERE owner=?AND template=98020',(winner,)).fetchone()[0],20)
                self.assertEqual(db.execute('SELECT received_at FROM native_achievement_completed WHERE account_id=1 AND achievement=13').fetchone()[0],0)
            wax=next(row['id']for row in catalog().values()if row['reward_groups']==[3000191]);complete(wax)
            mids=claim(a,wax);self.assertEqual(len(mids),11)
            with closing(sqlite3.connect(path))as db:
                counts=[json.loads(raw)['count']for raw, in db.execute('SELECT item_json FROM player_mail_items WHERE mail_id IN('+','.join('?'for _ in mids)+')',mids)]
                self.assertEqual(sum(counts),10000);self.assertLessEqual(max(counts),999)


if __name__=='__main__':
    result=unittest.main(exit=False).result
    report=dict(ok=result.wasSuccessful(),tests=result.testsRun,production_database_access=False,
        scope='server reward fixture, native mail codecs, actual escrow claim and inventory; no actual PvP match qualification',
        source_sha256={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts},
        errors=[detail[-2400:]for _,detail in result.errors],failures=[detail[-2400:]for _,detail in result.failures])
    (W/('reward-mail-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    raise SystemExit(not report['ok'])
