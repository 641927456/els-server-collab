"""Actual41400 four-room clear; unmodified server monotonic clock."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievement_history as history,achievements as state
from els_server.domain.town_travel import catalog
from els_server.protocol import achievement_messages as achievement
from els_server.domain.achievement_catalog import points
from els_server.game_data import client_data


def death(npc,owner):
    return (struct.pack('>iBQQ6fBf',npc['key'],0,owner,owner,0.,0.,0.,0.,0.,0.,0,npc['hp'])
        +bytes(8)+struct.pack('>Q',0)+bytes(4)+struct.pack('>Q',owner))


async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        natural_combat=False,clock_patched=False,fixtures='Owned level99 actors and explicit reports for actual admitted NPCs',checks=[])
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-timed-history-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start();auth=app.registry.create('ownedtimedhistory');foreign=app.registry.create('ownedtimedother')
            account=auth['id'];uid=Characters(cfg.state_file,account).create('TimeHist',1,'owned-time-character')['uid']
            alt=Characters(cfg.state_file,account).create('TimeHistAlt',2,'owned-time-alt')['uid']
            other=Characters(cfg.state_file,foreign['id']).create('TimeOther',3,'owned-time-other')['uid']
            for owner in(uid,alt,other):LocalState(cfg.state_file,owner).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET experience=?',(client_data().thresholds[98],))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name):return dict(uid=owner,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin))
            p=await connect(identity(uid,'TimeHist'),peers)
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def snap(aid=account,owner=uid):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,aid,owner)
            async def success(kind,body=b'',reply=None):
                answer=await p.query(kind,body,reply)
                assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
                return answer
            assert not snap()['completed']
            await success(0x7d4,struct.pack('>ii',2,41400))
            opaque=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
            await success(0x37f,opaque)
            await success(0x91,struct.pack('>ii',100,0));await success(0xb3,bytes(9))
            s=app.playing[account];run=s.dungeon_run
            assert run.identity==41400 and s.dungeon_substage_synced
            assert not snap()['completed']and read('SELECT * FROM dungeon_records')==[]
            await asyncio.sleep(1.1)
            stages=[];last=None;clear_start=None
            for step in range(4):
                assert s.dungeon_substage_synced and not s.clear_notified
                stages.append(run.stage)
                for npc in tuple(run.current['npcs']):
                    if not npc['active']:continue
                    last=death(npc,uid);await success(0xad,last)
                assert s.part_end_notified and run.poll_ready(),(run.stage,s.part_end_notified,run.next)
                if step<3:assert read('SELECT * FROM dungeon_records')==[]and not snap()['completed']
                clear_start=len(p.received)
                await success(0xbb,struct.pack('>b',run.part))
                if step<3:await success(0xb3,bytes(9))
            assert set(stages)=={0,1,2,3}and len(stages)==4 and s.clear_notified
            records=read('SELECT uid,map_id,seconds FROM dungeon_records');assert len(records)==1
            assert records[0][:2]==(uid,41400)and 1<=records[0][2]<=60,records
            saved=snap();completed={r['id']for r in saved['completed']}
            assert {2,3,4,5,6}<=completed and not snap(foreign['id'],other)['completed']
            fresh=[r for r in saved['completed']if r['id']in{2,3,4,5,6}]
            assert len(fresh)==5
            expected=achievement.completion(fresh,points(saved['completed']),[],False).payload
            assert any(e.kind==0xc1 for e in p.received[clear_start:])
            assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[clear_start:])
            report['checks'].append('Actual7D4(mode2)/37F/91/B3 enters41400; original roster deaths andBB/B3 traverse four unique source rooms; only final committedC1 creates positive server-measured record and immediately completes2..6')
            before=snap();await success(0xad,last);await success(0xbb,struct.pack('>b',run.part))
            await p.query(0x6be);await p.query(0x6be)
            assert snap()==before and records==read('SELECT uid,map_id,seconds FROM dungeon_records')
            old=s;await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(account)is old:await asyncio.sleep(.02)
            p=await connect(identity(alt,'TimeHistAlt'),peers);await p.query(0x6be)
            assert snap(account,alt)['completed']==before['completed']and snap(account,alt)['watched']==[]
            assert not errors,errors
            report['checks'].append('Repeated terminalAD/BB and6BE retain one record/completion; alternative-character cold login shares completion; foreign account stays uncredited')
            report.update(ok=True,stages=stages,record=list(records[0]),completed=sorted(completed),immediate_notification=True)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not root.exists(),
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('live-timed-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
