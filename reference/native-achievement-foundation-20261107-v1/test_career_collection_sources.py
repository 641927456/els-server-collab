"""Two attained characters, ordinary advancement items and no class-change recount."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,records,state
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.achievement_collections import counts
from els_server.storage.achievement_profiles import reconcile


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        first_character_career_and_item_acquisition_fixtures=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-career-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();ident=app.registry.create('ownedachcareer');foreign=app.registry.create('ownedachcareerforeign')
            a=Characters(cfg.state_file,ident['id']).create('AchCareerA',1,'owned-career-A')['uid']
            b=Characters(cfg.state_file,ident['id']).create('AchCareerB',1,'owned-career-B')['uid']
            c=Characters(cfg.state_file,foreign['id']).create('AchCareerC',1,'owned-career-C')['uid']
            for uid in(a,b,c):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE characters SET unit_class=100,transcendence=1 WHERE uid IN(?,?)',(a,c))
                sources=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)
                    for t in(214410,216420,288319)],b)
                before=list(db.iterdump());initial=counts(db,ident['id'],b,int(time.time()),{67,68})
                assert initial=={(67,1):1,(67,2):1,(67,3):0,(68,0):1},initial
                assert before==list(db.iterdump())
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            p=await connect(dict(uid=b,character_name='AchCareerB',bridge=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=pin)),peers)
            await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert state.snapshot(db,ident['id'],b)['completed']==[]
            for template,expected in((214410,60),(216420,65),(288319,70)):
                item=next(i for i in sources if i['template']==template)
                answer=await p.query(0x219,struct.pack('>QQiiIB',item['uid'],0,0,0,0,0),0x21a)
                assert answer.payload[:4]==bytes(4),(template,answer.payload.hex())
                notices=[records(e.payload)[0]for e in p.received if e.kind==0x6c0]
                assert notices[-1][0]['id']==expected and len(notices[-1])==1
            await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');before=list(db.iterdump())
                assert counts(db,ident['id'],b,int(time.time()),{67,68})=={(67,1):2,(67,2):2,(67,3):0,(68,0):2}
                assert reconcile(db,ident['id'],a,int(time.time()))==dict(completed=[],replayed=False)
                assert before==list(db.iterdump())
                assert {r['id']for r in state.snapshot(db,ident['id'],a)['completed']}=={60,65,70}
                assert state.snapshot(db,foreign['id'],c)['completed']==[]
            assert [[r['id']for r in records(e.payload)[0]]for e in p.received if e.kind==0x6c0]==[[60],[65],[70]]
            assert not errors,errors
            report.update(ok=True,completed=[60,65,70],checks=[
                'One own stage2/transcendent character backfills one first/second/transcendent count; foreign identical character is excluded',
                'Ordinary219uses real owned214410first advancement,216420second advancement and288319transcendence book; second same-unit character reaches each threshold and sends one6C0',
                'Higher stage still counts first and second attainment; account sibling reads completion; unchanged reconciliation writes nothing and repeated6BEdoes not recount'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    (W/('career-collection-sources-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
