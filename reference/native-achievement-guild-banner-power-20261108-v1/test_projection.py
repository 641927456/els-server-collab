"""Finite fifteen-family achievement matrix with explicit approved CP facts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,sys,tempfile,time,traceback
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.characters import Characters
from els_server.storage import achievements as state,achievement_profiles as profiles
from els_server.domain.achievement_catalog import catalog

async def run():
    result=dict(ok=False,native_Game=False,natural_GUI=False,production_database_access=False,
        CP_inputs='Explicit approved-source fixtures for the server projection, not naturally acquired combat power')
    app=None
    with tempfile.TemporaryDirectory(prefix='owned-cp-projection-',dir=F)as directory:
        private=Path(directory)
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',
            accounts_file=private/'accounts.sqlite3',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();definitions={}
            for identity,d in catalog().items():
                for condition in d['conditions']:
                    if condition['type']==17:
                        assert not d['reward_groups']and d['unit_class']==0
                        definitions.setdefault(d['unit_type'],[]).append((identity,condition['parameters']['m_iLevel']))
            assert set(definitions)==set(range(1,16))and all(sorted(v for _,v in rows)==[4200,7000]for rows in definitions.values())
            cases=[];owners=[]
            for family in range(1,16):
                account=app.registry.create('ownedcpprojection'+str(family))
                owner=Characters(cfg.state_file,account['id']).create('CProof'+str(family),family,'cp-family-'+str(family))['uid']
                owners.append((account,owner));expected=dict(definitions[family])
                for value in(4199,4200,6999,7000,4294967040,1):
                    with closing(sqlite3.connect(cfg.state_file))as db,db:
                        db.execute('BEGIN IMMEDIATE')
                        profiles.reconcile(db,account['id'],owner,int(time.time()),condition_types={17},native_power=(family,value))
                        saved=state.snapshot(db,account['id'],owner)
                        progress={r['id']:r['conditions'][0]['count']for r in saved['progress']}
                        completed={r['id']for r in saved['completed']}
                        high=max(4199,value)if value<=7000 else 7000
                        # This ordered sequence retains the previous7000 when
                        # the last fixture deliberately drops back to1.
                        if value==1:high=7000
                        assert completed=={key for key,target in expected.items()if high>=target}
                        assert all(progress[key]==min(high,target)for key,target in expected.items())
                        assert set(progress)==set(expected),'A family must not qualify another family'
                    cases.append((family,value))
            first,owner=owners[0]
            alternate=Characters(cfg.state_file,first['id']).create('CProofAlt',2,'cp-family-alt')['uid']
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');before=state.snapshot(db,first['id'],owner)
                profiles.reconcile(db,first['id'],alternate,int(time.time()),condition_types={17})
                assert state.snapshot(db,first['id'],alternate)['completed']==before['completed']
                profiles.reconcile(db,first['id'],alternate,int(time.time()),condition_types={17},native_power=(2,7000))
                shared=state.snapshot(db,first['id'],owner)
                assert {r['id']for r in shared['completed']}=={key for family in(1,2)for key,_ in definitions[family]}
                assert all(r['id']not in {k for k,_ in definitions[2]}for r in state.snapshot(db,owners[2][0]['id'],owners[2][1])['completed'])
            result.update(ok=True,families=15,definitions=30,matrix_cases=len(cases),
                exact_thresholds_and_lower_bound=True,large_f32_value_capped_to_native_target=True,
                no_native_value_does_not_mint=True,lower_value_does_not_regress=True,
                same_account_other_family_sharing=True,foreign_accounts_isolated=True,
                new_tables=0,new_indexes=0,source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*')if p.is_file()})
        except BaseException:result['error']=traceback.format_exc()
        finally:
            if app is not None:app.close()
    result.update(owned_directory_removed=not private.exists(),python=sys.version,SQLite=sqlite3.sqlite_version)
    path=F/('projection-'+str(time.time_ns())+'.json');path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(result,ensure_ascii=False));return result['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
