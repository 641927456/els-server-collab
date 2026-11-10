"""Actual guild commands distinguish voluntary departure, expulsion and retry."""
from pathlib import Path
from contextlib import closing
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
F=Path(__file__).resolve().parent;R=Path('G:/els');B=R/'releases/online/native-achievement-foundation-20261107-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(F),str(B),str(B/'vendor'),str(B/'tools'),str(R/'tools/pylibs'),str(F.parent/'release-integration-v1/delivery')]
ctypes.WinDLL(str(B/'python/sqlite3.dll'))
import els_server.domain,els_server.storage
els_server.domain.__path__.insert(0,str(F/'source-v1/els_server/domain'))
els_server.storage.__path__.insert(0,str(F/'source-v1/els_server/storage'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import achievements as state,achievement_history as history
from els_server.domain.town_travel import catalog
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.game_data import client_data
from els_server.protocol.local_messages import wstring
from create_friends_certificate import create
from achievement_qa_client import connect


def notice_ids(payload):
    count=struct.unpack_from('>I',payload)[0];offset=4;result=[]
    for _ in range(count):
        identity,length=struct.unpack_from('>iI',payload,offset);offset+=8+length+1;result.append(identity)
    return result


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        license_level_and_ED_fixture=True,natural_acquisition=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-live-guild-exit-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            owners=[app.registry.create('ownedexithist'+v)for v in('a','b','c')]
            names=['ExitHist'+v for v in('A','B','C')]
            uids=[Characters(cfg.state_file,owner['id']).create(name,index+1,'owned-exit-'+str(index))['uid']for index,(owner,name)in enumerate(zip(owners,names))]
            alt_uid=Characters(cfg.state_file,owners[1]['id']).create('ExitHistAlt',4,'owned-exit-alt')['uid']
            for uid in[*uids,alt_uid]:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE')
                db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                license=grant_items(db,[dict(template=110845,metadata=VERIFIED_TEMPLATES[110845],group=TEMPLATE_BAG_GROUPS[110845],quantity=1)],uids[0])[0]
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            identities=[]
            for owner,uid,name in zip(owners,uids,names):
                identity=dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin))
                identities.append(identity);await connect(identity,peers)
            master,member,victim=peers
            async def request(p,kind,body,success=True):
                answer=await p.query(kind,body)
                assert(answer.payload[:4]==bytes(4))==success,(hex(kind),answer.payload.hex())
                return answer
            def completed(index,uid=None):
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return state.snapshot(db,owners[index]['id'],uids[index]if uid is None else uid)
            await request(master,0x276,struct.pack('>Q',license['uid'])+wstring('ExitProof')+wstring('Owned fixture'))
            with closing(sqlite3.connect(cfg.state_file))as db:
                guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uids[0],)).fetchone()[0]
            async def join(p,index):
                await request(master,0x285,wstring(names[index])+struct.pack('>Q',uids[index]))
                await p.query(0x48d,reply=0x48f)
                await request(p,0x288,struct.pack('>i',guild)+wstring(names[0])+struct.pack('>i',0))
            await join(member,1);await join(victim,2)
            with closing(sqlite3.connect(cfg.state_file))as db:
                before_money=db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[1],)).fetchone()
            await request(member,0x290,struct.pack('>QB',uids[1],0))
            current=completed(1)
            assert {row['id']for row in current['completed']}=={130}
            assert not current['completed'][0]['received']
            notices=[notice_ids(e.payload)for e in member.received if e.kind==0x6c0]
            assert notices==[[130]],notices
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert history.counts(db,owners[1]['id'],{23})[(23,0)]==1
                assert db.execute('SELECT ed,experience FROM reward_balances WHERE uid=?',(uids[1],)).fetchone()==before_money
                before=[row for row in db.iterdump()if 'native_achievement_'in row]
            await request(member,0x290,struct.pack('>QB',uids[1],0),False)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert before==[row for row in db.iterdump()if 'native_achievement_'in row]
            await request(master,0x290,struct.pack('>QB',uids[2],1))
            for p in(master,victim):await p.query(0x48d,reply=0x48f)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert history.counts(db,owners[0]['id'],{23})[(23,0)]==0
                assert history.counts(db,owners[2]['id'],{23})[(23,0)]==0
            assert completed(0)['completed']==completed(2)['completed']==[]
            await request(member,0x6c1,struct.pack('>i',130))
            await member.close();peers.remove(member)
            async with asyncio.timeout(10):
                while owners[1]['id']in app.playing:await asyncio.sleep(.05)
            alternate=dict(identities[1],uid=alt_uid,character_name='ExitHistAlt')
            alt=await connect(alternate,peers);await alt.query(0x6be)
            shared=completed(1,alt_uid)
            assert {row['id']for row in shared['completed']}=={130}and shared['watched']==[]
            assert completed(1)['watched']==[130]
            assert not errors,errors
            report.update(ok=True,checks=[
                'Ordinary276creation,285invitation and288acceptance establish the actual guild members',
                'Ordinary voluntary290departure commits one source receipt and one130completion notice; no ED or XP is awarded',
                'A failed repeat without membership adds no achievement progress or operation',
                'Master expulsion does not count as either the master or victim voluntarily leaving',
                'Alternative character cold-loads the shared130completion and keeps a separate display list'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-guild-exit-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
