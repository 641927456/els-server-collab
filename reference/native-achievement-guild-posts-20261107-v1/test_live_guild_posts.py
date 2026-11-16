"""A real board post reaches the retained account achievement threshold."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_guild_exit import F,R,B,Application,ServerConfig,GameServer,Characters,LocalState,grant_items,state,history,catalog,VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,client_data,wstring,create,connect,notice_ids
from els_server.storage import guild_system_state as system
from els_server.protocol import guild_system_messages as wire


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures=dict(level_ED_license=True,retained_posts=99),natural_acquisition=False,checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-live-guild-posts-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedguildpost'+v)for v in('a','b')];names=['PostHistA','PostHistB']
            uids=[Characters(cfg.state_file,o['id']).create(n,i+1,'owned-post-'+str(i))['uid']for i,(o,n)in enumerate(zip(owners,names))]
            alt_uid=Characters(cfg.state_file,owners[0]['id']).create('PostHistAlt',3,'owned-post-alt')['uid']
            for uid in[*uids,alt_uid]:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                license=grant_items(db,[dict(template=110845,metadata=VERIFIED_TEMPLATES[110845],group=TEMPLATE_BAG_GROUPS[110845],quantity=1)],uids[0])[0]
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest();identities=[]
            for owner,uid,name in zip(owners,uids,names):
                identity=dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin))
                identities.append(identity);await connect(identity,peers)
            first,second=peers
            async def request(p,kind,body,success=True):
                answer=await p.query(kind,body)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload.hex())
                return answer
            await request(first,0x276,struct.pack('>Q',license['uid'])+wstring('PostProof')+wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uids[0],)).fetchone()[0]
            await request(first,0x285,wstring(names[1])+struct.pack('>Q',uids[1]));await second.query(0x48d,reply=0x48f)
            await request(second,0x288,struct.pack('>i',guild)+wstring(names[0])+struct.pack('>i',0))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');stamp=int(time.time())
                for i in range(99):
                    key='owned-retained-post-'+str(i);event=wire.reply(0x27e,struct.pack('>iB',0,9))
                    system.record(db,key,key,guild,uids[0],0x27d,dict(events=[(event.kind,event.payload.hex())]),stamp-86400-i)
                balance=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[0],)).fetchone()
            await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert history.counts(db,owners[0]['id'],{26})[(26,0)]==99
                assert state.snapshot(db,owners[0]['id'],uids[0])['completed']==[]
            await request(first,0x27d,bytes((1,))+wstring('First actual post'))
            assert [notice_ids(e.payload)for e in first.received if e.kind==0x6c0]==[[145]]
            await request(first,0x27d,bytes((1,))+wstring(' '),False)
            await request(first,0x28e,wstring('A separate announcement'))
            await request(first,0x6a9,struct.pack('>Q',1))
            await request(second,0x27d,bytes((1,))+wstring('Another account post'))
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert history.counts(db,owners[0]['id'],{26})[(26,0)]==100
                assert history.counts(db,owners[1]['id'],{26})[(26,0)]==1
                assert {r['id']for r in state.snapshot(db,owners[0]['id'],uids[0])['completed']}=={145}
                assert state.snapshot(db,owners[1]['id'],uids[1])['completed']==[]
                assert db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[0],)).fetchone()==balance
                before=[r for r in db.iterdump()if 'native_achievement_'in r]
            await first.query(0x6be);await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert before==[r for r in db.iterdump()if 'native_achievement_'in r]
            await first.close();peers.remove(first)
            async with asyncio.timeout(10):
                while owners[0]['id']in app.playing:await asyncio.sleep(.05)
            alt=await connect(dict(identities[0],uid=alt_uid,character_name='PostHistAlt'),peers);await alt.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert {r['id']for r in state.snapshot(db,owners[0]['id'],alt_uid)['completed']}=={145}
            assert not errors,errors
            report.update(ok=True,checks=[
                'Ordinary guild creation and join establish two actual members',
                'Ninety-nine retained-post receipt fixtures plus one ordinary27Dpost complete145once, without ED or XP',
                'Blank-post failure, announcement edit and later deletion add no count and do not erase post history',
                'Another account legitimate post counts only for that account; repeated6BEadds no operation',
                'Alternative-character cold login restores the shared145completion'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-guild-posts-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
