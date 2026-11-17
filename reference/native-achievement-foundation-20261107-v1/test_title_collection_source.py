"""Account title ownership drives region collection through the existing C23 flow."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,records,state,flow
from els_server.storage import titles,game_mail
from els_server.storage.achievement_collections import counts
from els_server.protocol import title_messages


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        title_ownership_fixture_only=True,natural_title_acquisition=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-title-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();ident=app.registry.create('ownedachtitle');foreign=app.registry.create('ownedachtforeign')
            a=Characters(cfg.state_file,ident['id']).create('AchTitleA',1,'own-title-A')['uid']
            b=Characters(cfg.state_file,ident['id']).create('AchTitleB',2,'own-title-B')['uid']
            c=Characters(cfg.state_file,foreign['id']).create('AchTitleC',3,'own-title-C')['uid']
            for uid in(a,b,c):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            now=int(time.time())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');titles.schema(db)
                for title in(10,20,30):db.execute('INSERT INTO title_ownership VALUES(?,?,?,?,?,0)',('account',ident['id'],title,'owned-fixture',now))
                db.execute('INSERT INTO title_ownership VALUES(?,?,?,?,?,?)',('account',ident['id'],40,'owned-expired-fixture',now-100,now-1))
                db.execute('INSERT INTO title_ownership VALUES(?,?,?,?,?,0)',('account',foreign['id'],50002,'owned-foreign-fixture',now))
                db.execute('INSERT INTO title_ownership VALUES(?,?,?,?,?,0)',('character',b,10,'old-wrong-scope-fixture',now))
                before=list(db.iterdump());value=counts(db,ident['id'],a,now,{42})
                assert value=={(42,1):3}and before==list(db.iterdump())
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            identity=dict(uid=a,character_name='AchTitleA',bridge=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=pin))
            p=await connect(identity,peers);await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert 270 not in {r['id']for r in state.snapshot(db,ident['id'],a)['completed']}
            live=app.playing[ident['id']]
            with app.world_lock:
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute("UPDATE title_ownership SET expires_at=0 WHERE scope='account'AND subject=?AND title=40",(ident['id'],))
                with closing(sqlite3.connect(cfg.state_file))as db:
                    before=[r for r in db.iterdump()if 'native_achievement_'in r];snapshot=titles.snapshot(db,a,int(time.time()))
                with patch.object(flow,'encode_event',side_effect=RuntimeError('owned title projection failure')):
                    try:flow.synchronize(live,None,[title_messages.initialization(snapshot)])
                    except RuntimeError as error:assert str(error)=='owned title projection failure'
                    else:raise AssertionError('Late title projection failure was swallowed')
                with closing(sqlite3.connect(cfg.state_file))as db:assert [r for r in db.iterdump()if 'native_achievement_'in r]==before
            for _ in range(2):
                answer=await p.query(0xc22,struct.pack('>i',0),0xc23);assert answer.payload[:4]==bytes(4)
            notices=[records(e.payload)for e in p.received if e.kind==0x6c0]
            assert len(notices)==1 and [r['id']for r in notices[0][0]]==[270]and notices[0][1]==[10,0,0,0]
            for _ in range(2):
                ack=await p.query(0x6c9,struct.pack('>i',270),0x6ca)
                assert ack.payload[:4]==bytes(4)and ack.payload[-1:]==b'\1'
            assert game_mail.inbox(cfg.state_file,ident['id'],a)==(0,[])
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert {r['id']for r in state.snapshot(db,ident['id'],b)['completed']}=={270}
                assert state.snapshot(db,foreign['id'],c)['completed']==[]
            assert not errors,errors
            report.update(ok=True,completed=[270],category_scores=[10,0,0,0],
                checks=['Existing account title scope, native title region, unique title identities and expiry; no schema changes during read',
                'Three valid region1titles stay incomplete; expired fourth, wrong character scope and foreign account title do not inflate count',
                'Late encoding failure rolls back achievement derivation',
                'Ordinary authenticated C22/C23 refresh observes the fourth owned title and emits one original6C0, including on repeated read',
                'Account alt shares completion; repeated no-reward6C9creates no mail'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in peers:
                try:await peer.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
    (W/('title-collection-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
