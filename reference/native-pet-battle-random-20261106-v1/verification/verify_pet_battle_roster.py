"""Exercise the real shared storage readers over an isolated SQLite fixture."""
from pathlib import Path
from dataclasses import FrozenInstanceError
import hashlib,importlib.util,json,sqlite3,sys,time,traceback

K=Path(__file__).resolve().parent
S=K.parent/'wedding-v1/period-wire-v4/test-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(S),'G:/els/tools/pylibs','G:/els/tools','G:/els']
for name,rel in [('els_server.domain.pet_battle','domain/pet_battle.py'),
                 ('els_server.storage.pet_battle_roster','storage/pet_battle_roster.py')]:
    spec=importlib.util.spec_from_file_location(name,K/'candidate/els_server'/rel)
    module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
from els_server.storage.pet_battle_roster import roster
from els_server.storage.pet_progression import ensure as progression
from els_server.domain.pet_progression import catalog
from els_server.storage.boosting_2026_limited_pet import ensure as limited, TABLE
from els_server.domain.boosting_2026_limited_pet import UNIT,DAYS
from els_server.storage.character_lifecycle import initialize as lifecycle

report=dict(ok=False,actual_TLS=False,native_Game=False,production_database_access=False,
    isolated_sqlite_fixture=True,cases=[],source_pins={})
try:
    definitions=catalog()['templates']
    unit=next(int(k)for k,d in definitions.items()if d['EVOLUTION_ALL_STEP']==3 and not 20000<=int(k)<=25000)
    db=sqlite3.connect(':memory:')
    db.execute('CREATE TABLE characters(uid INTEGER PRIMARY KEY,level INTEGER)')
    db.execute('CREATE TABLE character_owners(uid INTEGER PRIMARY KEY,account_id INTEGER)')
    db.execute('INSERT INTO characters VALUES(1001,99)')
    db.execute('INSERT INTO character_owners VALUES(1001,7)')
    db.execute('CREATE TABLE companions(uid INTEGER PRIMARY KEY,owner INTEGER,kind TEXT,unit INTEGER,name TEXT,source_item INTEGER)')
    progression(db)
    for i in range(3):
        uid=9001+i
        db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',(uid,1001,'pet',unit,'Own'+str(i),100+i))
        state=dict(step=3,satiety=3840,growth=0,personality={'0':100,'1':200,'2':0,'3':1000},nutrition=0,hunger_remainder=0,digest_until=0)
        db.execute('INSERT INTO pet_progression VALUES(?,?,?)',(uid,1001,json.dumps(state)))
    selection=((9001,0),(9002,1),(9003,-1))
    before='\n'.join(db.iterdump());frozen=roster(db,1001,7,selection)
    assert before=='\n'.join(db.iterdump())
    assert tuple(e.fact.uid for e in frozen)==(9001,9002,9003)
    assert tuple(e.fact.ability for e in frozen)==(0,1,-1)
    assert all(e.fact.attribute==definitions[str(unit)]['ATTRIBUTE']for e in frozen)
    assert all(e.fact.growth==(100,200,0,1000) and isinstance(e.record,bytes)for e in frozen)
    assert roster(db,1001,7,selection)==frozen
    report['cases'].append('current owned full-grown roster; exact immutable facts/DTOs; repeated read and no writes')
    try:frozen[0].fact.uid=12
    except FrozenInstanceError:pass
    else:raise AssertionError('Combat input was mutable')
    db.execute('SAVEPOINT changed')
    changed=dict(state,personality={'0':1000})
    db.execute('UPDATE pet_progression SET state=? WHERE pet=9001',(json.dumps(changed),))
    assert roster(db,1001,7,selection)[0].fact.growth==(1000,0,0,0)
    assert frozen[0].fact.growth==(100,200,0,1000)
    db.execute('ROLLBACK TO changed');db.execute('RELEASE changed')
    report['cases'].append('frozen registration independent from later saved point changes')
    def denied(name,setup=lambda:None,*,account=7,chosen=selection):
        db.execute('SAVEPOINT denied');setup();snapshot='\n'.join(db.iterdump())
        try:roster(db,1001,account,chosen)
        except ValueError:pass
        else:raise AssertionError(name+' was admitted')
        assert snapshot=='\n'.join(db.iterdump()),name+' changed storage'
        db.execute('ROLLBACK TO denied');db.execute('RELEASE denied')
        report['cases'].append(name)
    denied('wrong account',account=8)
    denied('level98',lambda:db.execute('UPDATE characters SET level=98'))
    denied('foreign pet',lambda:db.execute('UPDATE companions SET owner=1002 WHERE uid=9001'))
    denied('duplicate pet',chosen=((9001,0),(9001,1),(9003,-1)))
    denied('only two pets',chosen=selection[:2])
    denied('not fully grown',lambda:db.execute('UPDATE pet_progression SET state=? WHERE pet=9001',(json.dumps(dict(state,step=2)),)))
    denied('unallocated selected effect',chosen=((9001,2),(9002,1),(9003,-1)))
    denied('growth choice outside original enum',chosen=((9001,4),(9002,1),(9003,-1)))
    def expedition():
        db.execute('CREATE TABLE pet_expedition_runs(owner INTEGER,pets TEXT)')
        db.execute('INSERT INTO pet_expedition_runs VALUES(1001,?)',(json.dumps([9001]),))
    denied('currently exploring',expedition)
    def housing():
        db.execute('CREATE TABLE character_housing_pets_v1(owner INTEGER,pet INTEGER)')
        db.execute('INSERT INTO character_housing_pets_v1 VALUES(1001,9001)')
    denied('currently placed in housing',housing)
    denied('native VIP unit range',lambda:db.execute('UPDATE companions SET unit=20000 WHERE uid=9001'))
    def period():
        limited(db)
        db.execute('UPDATE companions SET unit=? WHERE uid=9001',(UNIT,))
        db.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,?,?,?,?,?,?)',(9001,1001,100,4,0,'owned-period',100,100+DAYS*86400,0))
    denied('period pet even if not expired',period)
    def deleting():
        lifecycle(db)
        db.execute('INSERT INTO character_lifecycle(uid,account_id,created_at,requested_at)VALUES(1001,7,1,2)')
    denied('pending deleted actor',deleting)
    report['source_pins']={str(p.relative_to(K/'candidate')):hashlib.sha256(p.read_bytes()).hexdigest()for p in (K/'candidate/els_server/storage/pet_battle_roster.py',K/'candidate/els_server/domain/pet_battle.py')}
    report.update(ok=True,cases_passed=len(report['cases']),scope='Storage eligibility and immutable read facts only; queue binding, Native room/turn delivery and settlement are not implemented by this helper.')
except BaseException:
    report['error']=traceback.format_exc()
finally:
    if 'db'in globals():db.close()
    target=K/('roster-check-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,indent=2)+'\n','utf8')
    print(json.dumps(dict(ok=report['ok'],cases_passed=report.get('cases_passed'),report=str(target),error=report.get('error'))))
if not report['ok']:raise SystemExit(1)
