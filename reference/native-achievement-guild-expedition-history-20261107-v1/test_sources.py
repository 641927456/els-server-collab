"""Read real producer snapshots; participation is independent of later clears."""
from qa_environment import F
from contextlib import closing
import hashlib,json,sqlite3,tempfile,time,unittest
from els_server.storage.characters import Characters
from els_server.storage.game_schema import prepare
from els_server.storage import guild_system_state as system,achievement_history as history
from els_server.storage import achievement_profiles as profiles,achievements as state
from els_server.domain import guild_expedition as expedition
from els_server.domain import guild_rules as rules


def native_signup(actor,stage,stamp,*,prior_same_second=False):
    exp=expedition._new(stamp);exp['stage']=stage
    for number in range(1,stage):
        old=expedition._stage(exp,number,stamp);old.update(hp=0,cleared=stamp-1)
    def participant(when):return dict(uid=actor['uid'],account=actor['account_id'],joined=when,
        until=when+rules.expedition_rules()['LimitExpeditionSec'],combat=1000,class_id=actor['unit_class'],
        name=actor['name'],damage=0,claimed=False,rank=0,rewards={},source='owned-fixture')
    st=expedition._stage(exp,stage,stamp);st['participants'][str(actor['uid'])]=participant(stamp)
    exp['charge_starts'][str(actor['uid'])]=stamp
    if prior_same_second and stage>1:
        old=exp['stages'][str(stage-1)];old['cleared']=stamp
        old['participants'][str(actor['uid'])]=participant(stamp)
    saved=dict(id=77,owner=actor['uid'],system=dict(expedition=exp))
    return expedition.snapshot(saved,stamp,0xabd),saved


class Sources(unittest.TestCase):
    def test_current_participation_thresholds_survive_later_departure(self):
        with tempfile.TemporaryDirectory(prefix='owned-expedition-source-',dir=F)as folder:
            path=F/folder/'game.sqlite3';prepare(path);actors=[]
            for account,name,unit in((1,'ExpSource',1),(1,'ExpAlt',2),(2,'ExpOther',3)):
                actor=Characters(path,account);uid=actor.create(name,unit,'owned-'+name)['uid']
                value=actor.get(uid);self.assertEqual(value['account_id'],account);actors.append(value)
            with closing(sqlite3.connect(path))as db,db:
                db.execute('BEGIN IMMEDIATE')
                expected={4:set(),5:{344,347},49:{344,347},50:{344,345,347,348},
                    99:{344,345,347,348},100:{344,345,346,347,348,349}}
                for turn in range(1,101):
                    stage=12 if turn==100 else 10 if turn>=50 else 8 if turn>=5 else 7
                    actor=actors[(turn-1)%2];stamp=1700000000+turn*86400
                    event,saved=native_signup(actor,stage,stamp,prior_same_second=True)
                    result=dict(events=[(event.kind,event.payload.hex())])
                    system.record(db,'owned-signup:'+str(turn),'owned-fixture',77,actor['uid'],0xabc,result,stamp)
                    if turn not in expected:continue
                    profiles.reconcile(db,1,actors[0]['uid'],stamp,condition_types={57,58})
                    self.assertEqual({r['id']for r in state.snapshot(db,1,actors[0]['uid'])['completed']},expected[turn])
                    self.assertEqual(history.counts(db,1,{57,58}),{(57,0):stage,(58,0):turn})
                event,_=native_signup(actors[2],12,1800000000)
                system.record(db,'owned-foreign','owned-fixture',77,actors[2]['uid'],0xabc,
                    dict(events=[(event.kind,event.payload.hex())]),1800000000)
                self.assertEqual(history.counts(db,2,{57,58}),{(57,0):12,(58,0):1})
                # Clear and claim operations are not new participations.
                system.record(db,'owned-clear','owned-fixture',77,0,0xac1,
                    dict(week=1,stage=12,completed=1800000000,participants={}),1800000000)
                system.record(db,'owned-claim','owned-fixture',77,actors[0]['uid'],0xac0,
                    dict(events=[(0xac1,'00000000')]),1800000000)
                system.record(db,'owned-refusal','owned-fixture',77,actors[0]['uid'],0xabc,
                    dict(events=[(0xabd,'00000001')]),1800000000)
                system.record(db,'owned-leave','owned-fixture',77,actors[0]['uid'],0x290,
                    dict(events=[(0x291,'000000000000000000000003e9')]),1800000000)
                before=list(db.iterdump())
                self.assertEqual(history.counts(db,1,{57,58}),{(57,0):12,(58,0):100})
                self.assertEqual(list(db.iterdump()),before)
                profiles.reconcile(db,1,actors[1]['uid'],1800000001,condition_types={57,58})
                self.assertEqual(len(state.snapshot(db,1,actors[1]['uid'])['completed']),6)
                self.assertEqual(state.snapshot(db,1,actors[1]['uid'])['watched'],[])

    def test_original_prefix_ignores_other_stage_and_member_timestamps(self):
        actor=dict(uid=1001,account_id=9,unit_class=1,name='PrefixSource')
        for stage in range(1,13):
            event,saved=native_signup(actor,stage,1700000000,prior_same_second=True)
            self.assertEqual(history._expedition_join_level(event.payload,9,1001,1700000000),stage)
            with self.assertRaises(ValueError):history._expedition_join_level(event.payload,10,1001,1700000000)
            with self.assertRaises(ValueError):history._expedition_join_level(event.payload,9,1002,1700000000)
            with self.assertRaises(ValueError):history._expedition_join_level(event.payload,9,1001,1700000001)
        # A real guild snapshot can exceed the unrelated chat Reader's4KB
        # bound. Encode actual extra rank members with the same producer.
        st=saved['system']['expedition']['stages']['12'];own=st['participants']['1001']
        for index in range(49):st['participants'][str(2000+index)]=dict(own,uid=2000+index,account=20+index,name='RankMember')
        large=expedition.snapshot(saved,1700000000,0xabd)
        self.assertGreater(len(large.payload),4096)
        self.assertEqual(history._expedition_join_level(large.payload,9,1001,1700000000),12)

    def test_missing_source_is_read_only(self):
        with closing(sqlite3.connect(':memory:'))as db:
            self.assertEqual(history.counts(db,1,{57,58}),{})
            self.assertEqual(list(db.execute('SELECT name FROM sqlite_master')),[])


if __name__=='__main__':
    result=unittest.main(exit=False).result
    proof=dict(ok=result.wasSuccessful(),tests=result.testsRun,errors=[v[-2400:]for _,v in result.errors],
        failures=[v[-2400:]for _,v in result.failures],production_database_access=False,
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('sources-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(proof,indent=2)+'\n').encode())
    print(json.dumps(proof));raise SystemExit(not proof['ok'])
