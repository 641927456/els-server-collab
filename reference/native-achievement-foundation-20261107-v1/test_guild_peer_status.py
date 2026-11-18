"""Ordinary guild creation/join/entry and peer achievement display replacement."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,state,records
from test_full_unit_projection import UnitReplay,stream,status
from els_server.domain.achievement_catalog import achievement
from els_server.storage.inventory_state import grant_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.protocol.local_messages import wstring


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        owned_license_and_completion_fixtures=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-guild-peer-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();owners=[app.registry.create('ownedachguild'+v)for v in('a','b')]
            uids=[Characters(cfg.state_file,owner['id']).create('AchGuild'+v,unit,'owned-ach-guild-'+v)['uid']for owner,v,unit in zip(owners,('A','B'),(11,1))]
            for uid in uids:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=6000000')
                license=grant_items(db,[dict(template=110845,metadata=VERIFIED_TEMPLATES[110845],group=TEMPLATE_BAG_GROUPS[110845],quantity=1)],uids[0])[0]
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for owner,uid,v in zip(owners,uids,('A','B')):
                await connect(dict(uid=uid,character_name='AchGuild'+v,bridge=dict(host='127.0.0.1',port=port,name=owner['name'],token=owner['token'],certificate_sha256=pin)),peers)
            first,peer=peers
            answer=await first.query(0x276,struct.pack('>Q',license['uid'])+wstring('AchGuildTest')+wstring('Owned QA'),0x277)
            assert answer.payload[:4]==bytes(4)
            answer=await first.query(0x285,wstring('AchGuildB')+struct.pack('>Q',uids[1]),0x286);assert answer.payload[:4]==bytes(4)
            await peer.query(0x48d,reply=0x48f)
            for n in range(5):
                await peer.send(0x6c8);await peer.query(0x48d,reply=0x48f)
                with closing(sqlite3.connect(cfg.state_file))as db:
                    assert db.execute('SELECT COUNT(*)FROM native_guild_actions WHERE owner=?AND kind=?',(uids[1],0x6c8)).fetchone()==(n+1,)
                assert [[r['id']for r in records(e.payload)[0]]for e in peer.received if e.kind==0x6c0]==[[135+i]for i in range(n+1)]
                # An empty replay has no current invitation to consume.
                await peer.send(0x6c8);await peer.query(0x48d,reply=0x48f)
                answer=await first.query(0x285,wstring('AchGuildB')+struct.pack('>Q',uids[1]),0x286);assert answer.payload[:4]==bytes(4)
                await peer.query(0x48d,reply=0x48f)
            with closing(sqlite3.connect(cfg.state_file))as db:guild=db.execute('SELECT guild_id FROM native_guild_members WHERE owner=?',(uids[0],)).fetchone()[0]
            answer=await peer.query(0x288,struct.pack('>i',guild)+wstring('AchGuildA')+struct.pack('>i',0),0x289);assert answer.payload[:4]==bytes(4)
            for p in peers:
                answer=await p.query(0x4fb,struct.pack('>IfffI',0,0.,0.,0.,25000),0x4fc);assert answer.payload[:4]==bytes(4)
                answer=await p.query(0x504,struct.pack('>fffBH',0.,0.,0.,0,0),0x505);assert answer.payload[:4]==bytes(4)
            assert all(app.playing[v['id']].phase=='guild_agit_ready'for v in owners)
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');state.record(db,owners[0]['id'],uids[0],
                    [dict(achievement=19,condition=c['id'],value=1,complete=True)for c in achievement(19)['conditions']],
                    'owned-guild-peer-completion',int(time.time()))
            replay=UnitReplay()
            for watched in([19],[]):
                start=len(peer.received)
                answer=await first.query(0x6c1,struct.pack('>i',19),0x6c2);assert answer.payload[:4]==bytes(4)
                await peer.query(0x48d,reply=0x48f)
                notices=[e for e in peer.received[start:]if e.kind in(0x500,0x4fd)]
                assert [e.kind for e in notices]==[0x500,0x4fd]
                assert notices[0].payload==struct.pack('>Qi',uids[0],0)
                reader,buffer=stream(replay,notices[1].payload);dto=replay.alloc(0x22f);replay.call(0x2c44bc0,dto)
                assert replay.call(0xda42b0,reader,dto)&255==1
                assert int.from_bytes(replay.read(buffer+32,4),'little')==len(notices[1].payload)
                assert status(replay,dto+0x154)==dict(points=[10,0,0,0],watched=watched,state_flag=False)
            assert not errors,errors
            report.update(ok=True,checks=[
                'Ordinary276guild creation consumes owned license;285invitation/288acceptance joins exact online peer;4FB/504enter the real same-guild room',
                'Five real285invitations followed by original empty6C8refusals complete135..139once each; repeated refusal without an invitation does not count;6C8is not intercepted by achievements',
                'Ordinary6C1 display enable and disable each publish500removal then4FDcurrent actor only to the ready peer',
                'Original DA42B0 reads exact member payload, ten account points and current per-character display list; no self6C7is sent to foreign actor'])
        except BaseException:
            report['error']=traceback.format_exc()
            if 'replay'in locals():report['native_fault']=getattr(replay,'last_fault',None)
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    (W/('guild-peer-status-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
