"""Reproduce late-peer and recreated-actor banner loss in owned App/TLS."""
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
from pathlib import Path

fixed='--fixed'in sys.argv
if fixed:
    import els_server.domain,els_server.storage
    els_server.domain.__path__.insert(0,str(F/'source-v2/els_server/domain'))
    els_server.storage.__path__.insert(0,str(F/'source-v2/els_server/storage'))
sys.path.insert(0,str(F.parent/'notebook-spa-clear-closure-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import achievement_history as history
from els_server.domain.town_travel import catalog as towns
from els_server.protocol.social_messages import wstring
from els_server.game_data import client_data

async def run():
    report=dict(ok=False,expected_fixed=fixed,production_database_access=False,
        native_Game=False,natural_GUI=False,explicit_protocol_requests=True)
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-banner-peer-sync-',dir=F)as directory:
        private=Path(directory);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start()
            a=app.registry.create('ownedbannersynca');b=app.registry.create('ownedbannersyncb')
            uid=Characters(cfg.state_file,a['id']).create('BannerSyncA',1,'banner-sync-a')['uid']
            other=Characters(cfg.state_file,b['id']).create('BannerSyncB',2,'banner-sync-b')['uid']
            for owner in(uid,other):LocalState(cfg.state_file,owner).save(20001,0,0,towns()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                grant_items(db,[dict(template=110845,metadata=0,group=4,quantity=1)],uid)
                license=next(r['uid']for r in load_items(db,uid)if r['template']==110845)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name,account):return dict(uid=owner,character_name=name,town=20001,
                bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            def count():
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,a['id'],{59}).get((59,0),0)
            def notices(peer,start=0):return [e for e in peer.received[start:]if e.kind==0x7e2 and e.payload[:9]==struct.pack('>Q?',uid,True)]
            p=await connect(identity(uid,'BannerSyncA',a),peers)
            response=await p.query(0x276,struct.pack('>Q',license)+wstring('BS'+str(uid))+wstring('Owned peer sync fixture'))
            assert response.payload[:4]==bytes(4)
            for n in range(10):
                if n:assert(await p.query(0x7e0,b'\0')).payload==bytes(4)
                assert(await p.query(0x7e0,b'\1')).payload==bytes(4)
            assert count()==10
            foreign=await connect(identity(other,'BannerSyncB',b),peers)
            late=notices(foreign);report['late_peer_active_notices']=len(late)
            assert bool(late)is fixed
            marker=len(foreign.received)
            response=await p.query(0x6c1,struct.pack('>I',350))
            assert response.payload[:4]==bytes(4),response.payload.hex()
            await foreign.query(0x48d,reply=0x48f)
            changed=[e for e in foreign.received[marker:]if e.kind==0x22a]
            assert changed,'Actual public achievement display must recreate the peer actor'
            replay=notices(foreign,marker);report['appearance_rebuild_active_notices']=len(replay)
            assert bool(replay)is fixed
            assert count()==10,'State replay must never mint an achievement source'
            # Normal master invitation/acceptance; both clients then use the
            # original territory entry, rather than an administrative join.
            response=await p.query(0x285,wstring('BannerSyncB')+struct.pack('>Q',other))
            assert response.payload[:4]==bytes(4),response.payload.hex()
            with closing(sqlite3.connect(cfg.state_file))as db:
                guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uid,)).fetchone()[0]
            response=await foreign.query(0x288,struct.pack('>i',guild)+wstring('BannerSyncA')+bytes(4))
            assert response.payload[:4]==bytes(4),response.payload.hex()
            async def enter(peer):
                for kind,body,answer in((0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc),
                    (0x225,struct.pack('>iB',25000,0),0x226),
                    (0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505)):
                    response=await peer.query(kind,body,answer)
                    assert response.payload[:4]==bytes(4),(hex(kind),response.payload.hex())
            await enter(p)
            assert(await p.query(0x7e0,b'\1')).payload==bytes(4)
            assert count()==11
            marker=len(foreign.received);await enter(foreign)
            hall=notices(foreign,marker);report['guild_agit_late_peer_active_notices']=len(hall)
            assert bool(hall)is fixed
            marker=len(foreign.received)
            response=await p.query(0x6c1,struct.pack('>I',350))
            assert response.payload[:4]==bytes(4)
            await foreign.query(0x48d,reply=0x48f)
            assert any(e.kind==0x4fd for e in foreign.received[marker:]),'GuildAgit actor rebuild missing'
            hall_replay=notices(foreign,marker);report['guild_agit_rebuild_active_notices']=len(hall_replay)
            assert bool(hall_replay)is fixed
            assert(await p.query(0x7e0,b'\0')).payload==bytes(4)
            marker=len(foreign.received)
            assert(await p.query(0x6c1,struct.pack('>I',350))).payload[:4]==bytes(4)
            await foreign.query(0x48d,reply=0x48f)
            assert not notices(foreign,marker),'Withdrawn banners must not be restored'
            assert count()==11
            report.update(ok=True,actual_display_350_toggle=True,public_actor_rebuilt=True,
                replay_does_not_increment_count=True,late_peer_bug_reproduced=not fixed,
                appearance_rebuild_bug_reproduced=not fixed,guild_agit_variants_reproduced=not fixed,
                native_invitation_and_acceptance=True,withdrawn_banner_not_restored=True,
                owned_level_ED_license_fixtures=True)
            assert not errors,errors
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):
                try:await peer.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not private.exists())
    (F/('peer-sync-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
