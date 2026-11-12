"""Native catalog map separation, account ownership and the real query plan."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
import ast,asyncio,hashlib,json,sqlite3,tempfile,time,traceback,uuid
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.characters import Characters
from els_server.storage.reward_state import RewardState
from els_server.storage import achievement_history as history,achievement_profiles as profiles,achievements as state
from els_server.domain.achievement_catalog import catalog

async def run():
    report=dict(ok=False,production_database_access=False,historical_receipt_fixtures=True,native_Game=False)
    app=None
    with tempfile.TemporaryDirectory(prefix='owned-clear-count-projection-',dir=F)as directory:
        private=Path(directory);cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            a=app.registry.create('ownedclearprojection');b=app.registry.create('ownedclearforeign')
            uid=Characters(cfg.state_file,a['id']).create('OwnClearA',1,'owned-clear-a')['uid']
            other=Characters(cfg.state_file,b['id']).create('OwnClearB',2,'owned-clear-b')['uid']
            alt=Characters(cfg.state_file,a['id']).create('OwnClearAlt',3,'owned-clear-alt')['uid']
            assert uid==1001 and other!=1001 and alt!=1001
            definitions=[(identity,c)for identity,d in catalog().items()for c in d['conditions']if c['type']==49]
            expected={c['parameters']['m_iDungeonID']:1 for identity,c in definitions}
            expected[34350]=3;expected[34360]=5
            stores={owner:RewardState(cfg.state_file,owner,account_id=a['id']if owner!=other else b['id'])for owner in(uid,other,alt)}
            for mid,count in expected.items():
                for n in range(count):
                    owner=uid if n%2==0 else alt
                    stores[owner].grant(str(uuid.uuid4()),('owned-catalog-clear:'+str(mid)+':'+str(n)).encode(),0,0,lambda balances,best:b'fixture',dungeon_clear=(mid,1))
            stores[other].grant(str(uuid.uuid4()),b'owned-foreign',0,0,lambda balances,best:b'foreign',dungeon_clear=(34350,1))
            stores[uid].grant(str(uuid.uuid4()),b'owned-non-clear',0,0,lambda balances:b'non-clear')
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');state.ensure(db)
                before=db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
                traced=[];db.set_trace_callback(traced.append)
                actual=history.counts(db,a['id'],{49});db.set_trace_callback(None)
                assert actual=={(49,mid):count for mid,count in expected.items()}
                assert history.counts(db,b['id'],{49})=={(49,34350):1}
                assert before==db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
                prefix="SELECT json_extract(a.grant_json,'$.dungeon_clear[0]'),COUNT(*)"
                assert any(prefix in q for q in traced)
                # Trace expansion joins a bound integer with the adjacent
                # AND token. Explain the original prepared SQL and bindings.
                syntax=ast.parse((F/'source-v1/els_server/storage/achievement_history.py').read_bytes())
                queries=[n.value for n in ast.walk(syntax)if isinstance(n,ast.Constant)and isinstance(n.value,str)and n.value.startswith(prefix)]
                assert len(queries)==1
                plan=db.execute('EXPLAIN QUERY PLAN '+queries[0],(a['id'],)).fetchall()
                assert any('SEARCH a USING INDEX native_achievement_clear_owner_dungeon'in r[-1]for r in plan),plan
                profiles.reconcile(db,a['id'],uid,int(time.time()),condition_types={49})
                rows={(ach,condition):value for ach,condition,value in db.execute('SELECT achievement,condition,value FROM native_achievement_progress WHERE account_id=?',(a['id'],))}
                assert all(rows[(identity,c['id'])]==expected[c['parameters']['m_iDungeonID']]for identity,c in definitions)
                legacy=db.execute("SELECT grant_json FROM reward_receipts WHERE json_extract(grant_json,'$.dungeon_clear')IS NOT NULL AND json_extract(grant_json,'$.owner')IS NULL").fetchall()
                explicit=db.execute("SELECT grant_json FROM reward_receipts WHERE json_extract(grant_json,'$.owner')=?",(alt,)).fetchall()
                assert legacy and explicit
            report.update(ok=True,native_definitions_checked=len(definitions),native_dungeon_keys=len(expected),
                different_map_counts_preserved={34350:3,34360:5},default_owner1001_and_explicit_sibling=True,
                foreign_account_excluded=True,nonclear_receipt_excluded=True,source_read_has_no_DDL=True,
                indexed_query_plan=[r[-1]for r in plan],new_index='native_achievement_clear_owner_dungeon')
        except BaseException:report['error']=traceback.format_exc()
        finally:
            if app is not None:app.close()
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    p=F/('projection-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(run()))
