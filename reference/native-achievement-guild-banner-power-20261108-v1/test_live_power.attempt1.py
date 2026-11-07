"""Owned App/TLS CP source: input binding, rollback and account persistence."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback
from unittest.mock import patch
sys.path.insert(0,str(F.parent/'notebook-spa-clear-closure-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items
from els_server.storage import achievements as state
from els_server.domain import achievement_flow as flow,raid_native_power as native
from els_server.domain.achievement_catalog import catalog,progress_projection
from els_server.domain.town_travel import catalog as towns
from els_server.protocol import achievement_messages as wire

async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        native_CP_values='Explicit native-source payload fixtures; no natural gear acquisition or native arithmetic claimed')
    app=server=None;peers=[];errors=[]
    CP={identity for identity,d in catalog().items()if any(c['type']==17 for c in d['conditions'])}
    with tempfile.TemporaryDirectory(prefix='owned-achievement-cp-live-',dir=F)as directory:
        private=Path(directory);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            a=app.registry.create('ownedlivecpa');b=app.registry.create('ownedlivecpb')
            uid=Characters(cfg.state_file,a['id']).create('LiveCPA',1,'live-cp-a')['uid']
            other=Characters(cfg.state_file,b['id']).create('LiveCPB',2,'live-cp-b')['uid']
            alt=Characters(cfg.state_file,a['id']).create('LiveCPAlt',2,'live-cp-alt')['uid']
            for owner in(uid,other,alt):LocalState(cfg.state_file,owner).save(20001,0,0,towns()['towns']['20001']['xyz'])
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name,account):return dict(uid=owner,character_name=name,town=20001,
                bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            def snapshot(account=a['id'],owner=uid):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,account,owner)
            def cp(account=a['id'],owner=uid):
                value=snapshot(account,owner)
                return dict(completed=[r for r in value['completed']if r['id']in CP],
                    progress=[r for r in value['progress']if r['id']in CP])
            def body(owner,value):return struct.pack('>IQf',native.MAGIC,owner,value)
            async def check(peer,payload,account=a['id'],owner=uid):
                answer=await peer.query(0x6be,payload);current=snapshot(account,owner)
                assert answer.payload==wire.initialization([],progress_projection(current),current['completed'],current['watched']).payload
                return cp(account,owner)
            async def rejected(peer,payload):
                try:
                    async with asyncio.timeout(5):await peer.query(0x6be,payload)
                except(asyncio.IncompleteReadError,ConnectionResetError,BrokenPipeError):return
                raise AssertionError('Invalid source unexpectedly got an achievement snapshot')
            async def close(peer,account):
                old=app.playing.get(account['id']);await peer.close();peers.remove(peer)
                async with asyncio.timeout(10):
                    while app.playing.get(account['id'])is old and old is not None:await asyncio.sleep(.02)
            p=await connect(identity(uid,'LiveCPA',a),peers)
            foreign=await connect(identity(other,'LiveCPB',b),peers)
            assert await check(p,b'')==dict(completed=[],progress=[])
            value=await check(p,body(uid,4199));assert value['completed']==[]
            assert {r['id']:r['conditions'][0]['count']for r in value['progress']}=={85:4199,86:4199}
            value=await check(p,body(uid,4200));assert {r['id']for r in value['completed']}=={85}
            assert await check(p,b'')==value
            assert await check(p,body(uid,4199))==value
            original=flow.encode_event
            def fail_encoding(event):
                if event.kind==0x6bf:raise ValueError('Owned CP final encoding failure')
                return original(event)
            with patch.object(flow,'encode_event',fail_encoding):await rejected(p,body(uid,7000))
            assert cp()==value;await close(p,a)
            p=await connect(identity(uid,'LiveCPA',a),peers)
            assert await check(p,b'')==value
            basis=native.basis;calls=[]
            def change_inputs(session):
                captured=basis(session);calls.append(captured)
                if len(calls)==1:
                    with closing(sqlite3.connect(cfg.state_file))as db,db:
                        grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],uid)
                return captured
            with patch.object(native,'basis',change_inputs):await rejected(p,body(uid,7000))
            assert len(calls)==2 and calls[0]!=calls[1],'Writer-time basis must observe the changed authoritative inventory'
            assert cp()==value;await close(p,a)
            before_foreign=cp(b['id'],other)
            await rejected(foreign,body(uid,7000));assert cp(b['id'],other)==before_foreign
            await close(foreign,b)
            p=await connect(identity(uid,'LiveCPA',a),peers)
            value=await check(p,body(uid,7000));assert {r['id']for r in value['completed']}=={85,86}
            assert await check(p,body(uid,4294967040))==value
            assert await check(p,body(uid,7000))==value
            await close(p,a)
            p=await connect(identity(alt,'LiveCPAlt',a),peers)
            assert await check(p,b'',a['id'],alt)==value
            value=await check(p,body(alt,7000),a['id'],alt)
            assert {r['id']for r in value['completed']}=={85,86,87,88}
            await close(p,a)
            p=await connect(identity(uid,'LiveCPA',a),peers)
            assert await check(p,b'')==value
            foreign=await connect(identity(other,'LiveCPB',b),peers)
            assert await check(foreign,b'',b['id'],other)==before_foreign
            # The three deliberate refusal/failure cases must be the only
            # protocol errors; worker/notification/task errors stay forbidden.
            expected=('Owned CP final encoding failure','Achievement native power inputs changed','Raid native CP source/number')
            assert len(errors)==3 and all(row['event']=='protocol_error'for row in errors),errors
            assert all(any(text in json.dumps(row,ensure_ascii=False)for row in errors)for text in expected),errors
            report.update(ok=True,full_native_snapshot_matches=True,threshold4199_4200_7000=True,
                no_payload_no_new_CP=True,lower_CP_does_not_regress=True,late_encoding_rollback=True,
                actual_inventory_input_change_rejected=True,foreign_UID_rejected=True,
                repeated_and_large_CP_no_extra_award=True,cold_same_account_two_family_sharing=True,
                foreign_account_isolated=True,completed_CP_ids=[r['id']for r in value['completed']],
                expected_protocol_errors=3,new_tables=0,new_indexes=0)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(owned_directory_removed=not private.exists(),observed_error_events=errors,
        python=sys.version,SQLite=sqlite3.sqlite_version,
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*')if p.is_file()})
    path=F/('live-power-'+str(time.time_ns())+'.json');path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
