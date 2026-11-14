"""Real owned expired rows, the original deadline boundary and SQL rollback."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,tempfile,time,traceback
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.storage.characters import Characters
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.bag_capacity import allowances
from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
from els_server.storage import achievements as state
from els_server.storage.achievement_collections import counts
from els_server.storage.achievement_profiles import reconcile
from els_server.domain.equipment_requirements import inspect_requirements
from create_friends_certificate import create

async def main():
    report=dict(ok=False,production_database_access=False,production_clock_patch=False,retained_expired_worn_fixture=True,checks=[])
    with tempfile.TemporaryDirectory(prefix='owned-worn-source-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1');cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        app=Application(cfg)
        try:
            await app.start();auth=app.registry.create('ownedwornsource');uid=Characters(cfg.state_file,auth['id']).create('WornSource',1,'owned-worn-source')['uid'];deadline=int(time.time())-1
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');state.ensure(db)
                original=load_items(db,uid);limits=allowances(db,uid);occupied={group:{i['slot']for i in original if i['group']==group}for group in limits}
                for item in original:
                    if item['group']!=9:continue
                    group=TEMPLATE_BAG_GROUPS[item['template']];slot=next(n for n in range(limits[group])if n not in occupied[group]);occupied[group].add(slot)
                    db.execute('UPDATE inventory_items SET bag_group=?,slot=? WHERE uid=?',(group,slot,item['uid']))
                items=grant_items(db,[dict(template=t,metadata=1,group=1,quantity=1,expires_at=deadline)for t in range(118153,118157)],uid)
                for item in items:db.execute('UPDATE inventory_items SET bag_group=9,slot=? WHERE uid=?',(inspect_requirements(item['template'],1)['equipment_slot'],item['uid']))
            def snapshot():
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,auth['id'],uid)
            before=snapshot()
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert counts(db,auth['id'],uid,deadline+1,{50})[(50,372)]==0
                assert counts(db,auth['id'],uid,deadline,{50})[(50,372)]==4
            try:
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('BEGIN IMMEDIATE');result=reconcile(db,auth['id'],uid,deadline,condition_types={50});assert set(result['completed'])=={371,372}
                    raise ValueError('Owned late response preparation failure')
            except ValueError as error:assert str(error)=='Owned late response preparation failure'
            assert snapshot()==before
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');assert set(reconcile(db,auth['id'],uid,deadline,condition_types={50})['completed'])=={371,372}
            completed=snapshot()
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');assert not reconcile(db,auth['id'],uid,deadline,condition_types={50})['completed'];assert not reconcile(db,auth['id'],uid,deadline+1,condition_types={50})['completed']
            assert snapshot()==completed
            report.update(ok=True,checks=['Expired retained worn rows do not count; the original exact deadline remains valid','Late caller failure rolls back progress and completions; normal retry completes both armor definitions once','Repeat and later expiry do not duplicate or retract attained account achievements'])
        except BaseException:report['error']=traceback.format_exc()
        finally:app.close()
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((F/'source-v1').rglob('*.py'))}
    p=F/('source-transactions-'+str(time.time_ns())+'.json');p.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
