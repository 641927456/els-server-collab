"""Private App/TLS: original requests, live profile notices and shared preview rows."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,os,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=Path('G:/els')
runtime=Path(os.environ.get('ELS_ACHIEVEMENT_RUNTIME','G:/els/analysis/feature-closure-20261105-v1/release-integration-v3/full-source'))
sys.dont_write_bytecode=True
sys.path[:0]=[str(runtime),str(runtime/'vendor'),str(runtime/'tools'),str(R/'tools/pylibs'),str(R/'tools'),str(R),str(Path(os.environ.get('ELS_ACHIEVEMENT_QA_TOOLS','G:/els/analysis/feature-closure-20261105-v1/release-integration-v3/delivery-v87')))]
ctypes.WinDLL(str(runtime/'python/sqlite3.dll'))
import els_server,els_server.domain,els_server.storage,els_server.protocol
for package,relative in((els_server,''),(els_server.domain,'domain'),(els_server.storage,'storage'),(els_server.protocol,'protocol')):
    package.__path__.insert(0,str(W/'source-v1/els_server'/relative))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state,profession_state,resonance_state,game_mail
from els_server.protocol.profession_messages import ProfessionState
from els_server.protocol.protocol_codec import Event
from els_server.domain import achievement_flow as flow
from els_server.domain.profession_growth import advance_blacksmith,BLACKSMITH_STEPS
from els_server.domain.resonance import curve
from els_server.domain.achievement_catalog import rewards
from els_server.domain.ariel_attendance_preview import project
from els_server.domain.growth_attendance_2026_campaign import reward_rows
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from create_friends_certificate import create
from combined_qa_client import connect


def records(payload):
    n,=struct.unpack_from('>I',payload);offset=4;out=[]
    for _ in range(n):
        identity,length=struct.unpack_from('>iI',payload,offset);offset+=8
        date=payload[offset:offset+length].decode('utf-16le');offset+=length
        received=bool(payload[offset]);offset+=1
        out.append(dict(id=identity,completed_at=date,received=received))
    count,=struct.unpack_from('>I',payload,offset);offset+=4
    scores=list(struct.unpack_from('>'+str(count)+'i',payload,offset));offset+=count*4
    count,=struct.unpack_from('>I',payload,offset);offset+=4+count*4
    assert payload[offset:]==b'\0'
    return out,scores


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        profile_fixture_only=True,natural_profession_or_ERP_growth=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-app-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();ident=app.registry.create('ownedachlive');other=app.registry.create('ownedachother')
            a=Characters(cfg.state_file,ident['id']).create('AchLiveA',1,'owned-ach-live-A')['uid']
            b=Characters(cfg.state_file,ident['id']).create('AchLiveB',2,'owned-ach-live-B')['uid']
            c=Characters(cfg.state_file,other['id']).create('AchLiveC',3,'owned-ach-live-C')['uid']
            for uid in(a,b,c):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            initial=ProfessionState(2,1,0,{},0,BLACKSMITH_STEPS[1])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET experience=?',(client_data().thresholds[-1],))
                profession_state.replace(db,a,ident['id'],0,initial)
                resonance_state.ensure(db);db.execute('INSERT INTO account_resonance VALUES(?,1,?,1)',(ident['id'],curve()[148]['TOTAL_ER_EXP']))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,uid,name):return dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin))
            p=await connect(identity(ident,a,'AchLiveA'),peers);foreign=await connect(identity(other,c,'AchLiveC'),peers)
            await p.query(0x6be);await foreign.query(0x6be)
            expected={rid:tuple((i['template'],i['count'],0)for i in items)for rid,items in rewards().items()}
            initial_rows=reward_rows(next(e.payload for e in reversed(p.received)if e.kind==0x4b6))
            assert len(expected)==50 and all(initial_rows[k]==v for k,v in expected.items())
            assert 3000010 not in initial_rows
            live=app.playing[ident['id']]
            repeated=project(live,[Event(0x201,kind=0x4b6,payload=next(e.payload for e in reversed(p.received)if e.kind==0x4b6))])
            assert reward_rows(repeated[0].payload)==initial_rows
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert {r['id']for r in state.snapshot(db,ident['id'],a)['completed']}=={73,74}
                before=[r for r in db.iterdump()if 'native_achievement_'in r]
            attained,_,_=advance_blacksmith(initial,sum(BLACKSMITH_STEPS[n]for n in range(1,7)))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');profession_state.replace(db,a,ident['id'],1,attained)
                result=resonance_state.award(db,a,'owned-live-erp-transition',b'private profile transition fixture','kill',curve()[149]['TOTAL_ER_EXP']-curve()[148]['TOTAL_ER_EXP'],ident['id'])
                assert not result['replayed']
            with patch.object(flow,'encode_event',side_effect=RuntimeError('owned late encoding failure')):
                try:flow.synchronize(live,None,[live.saved_user_sync()])
                except RuntimeError as error:assert str(error)=='owned late encoding failure'
                else:raise AssertionError('Late projection failure did not propagate')
            with closing(sqlite3.connect(cfg.state_file))as db:assert [r for r in db.iterdump()if 'native_achievement_'in r]==before
            notice=await p.until(0x6c0);completed,scores=records(notice.payload)
            assert {r['id']for r in completed}=={19,20,21,75}and scores==[60,60,0,0]
            count=sum(e.kind==0x6c0 for e in p.received)
            await asyncio.sleep(1.2);await p.query(0x48d,reply=0x48f);await foreign.query(0x48d,reply=0x48f)
            assert sum(e.kind==0x6c0 for e in p.received)==count
            assert not any(e.kind==0x6c0 for e in foreign.received)
            assert (await p.query(0x6c3,struct.pack('>ii',13,10000),0x6c4)).payload==struct.pack('>i',1367)
            assert (await p.query(0x6c5,struct.pack('>i',13),0x6c6)).payload==struct.pack('>i',1367)
            await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while ident['id']in app.playing:await asyncio.sleep(.05)
            alt=await connect(identity(ident,b,'AchLiveB'),peers);await alt.query(0x6be)
            for _ in range(2):
                ack=await alt.query(0x6c9,struct.pack('>i',21),0x6ca)
                assert ack.payload[:4]==bytes(4)and ack.payload[-1:]==b'\1'
            total,mail=game_mail.inbox(cfg.state_file,ident['id'],b)
            assert total==1 and mail[0]['item']['template']==118204 and mail[0]['item']['count']==20
            assert game_mail.inbox(cfg.state_file,ident['id'],a)==(0,[])
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert {r['id']for r in state.snapshot(db,ident['id'],b)['completed']}=={19,20,21,73,74,75}
                assert state.snapshot(db,other['id'],c)['completed']==[]
                assert 13 not in {r['id']for r in state.snapshot(db,ident['id'],b)['completed']}
            assert not errors,errors
            report.update(ok=True,qualified_preview_groups=len(expected),preserved_other_preview_groups=len(initial_rows)-len(expected),
                live_completions=sorted(r['id']for r in completed),category_scores=scores,
                checks=['Pinned TLS and ordinary character entry','Full4B6 preserves existing providers and all50qualified achievement rows on cold load and repeat',
                'Late response encoding rolls back derived progress','Existing profession/ERP authorities trigger original6C0 through actual App periodic delivery exactly once',
                'Foreign account gets no completion; debug requests rejected','Alt character cold-loads account completion; repeated ordinary6C9 creates one character-owned20mithril mail'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in peers:
                try:await peer.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
    (W/('live-profiles-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
