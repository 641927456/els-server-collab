"""Owned App/TLS official match; explicit preexisting profiles and HP reports."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback,uuid
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from fixture_helpers import balanced_profiles,register_fixture,registration
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievement_history as history,achievements as state
from els_server.domain.town_travel import catalog
from els_server.domain.pvp_support import SOURCE_SHA
from els_server.protocol import achievement_messages as achievement
from els_server.domain.achievement_catalog import points
from els_server.game_data import client_data
from els_server.friends_relay import read_packet


def hp(value):
    raw=bytearray(182);struct.pack_into('>f',raw,0,value)
    return bytes(raw)+b'PVP1'+struct.pack('>f',1000.)


async def relay_fixture(peer):
    """Authenticated controlled readiness; no native probe/Game is claimed."""
    reader,writer=await peer.bridge.remote(role='relay')
    def send(body):writer.write(struct.pack('>I',len(body))+body)
    send(b'\7'+json.dumps(dict(version=1,ready=True,epoch=str(uuid.uuid4()),source_sha256=SOURCE_SHA)).encode())
    send(b'\3'+struct.pack('>Q',1));await writer.drain()
    async def heartbeat():
        counter=1
        while True:
            await asyncio.sleep(5);counter+=1
            send(b'\3'+struct.pack('>Q',counter));await writer.drain()
    async def drain():
        while True:await read_packet(reader)
    tasks=[asyncio.create_task(heartbeat()),asyncio.create_task(drain())]
    return writer,tasks


async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        natural_combat=False,clock_patched=False,fixtures='Owned level75 actors; approved-policy calculated99win/99loss retained profiles; authenticated readiness and native HP reports',checks=[])
    app=server=None;peers=[];relays=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-combat-history-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=10,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for index,letter in enumerate('ABC'):
                auth=app.registry.create('ownedcombathistory'+letter.lower());name='CombatHist'+letter
                uid=Characters(cfg.state_file,auth['id']).create(name,index+1,'owned-combat-'+letter)['uid']
                LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
                values.append(dict(uid=uid,account_id=auth['id'],character_name=name,auth=auth))
            ids=[v['uid']for v in values];accounts=[v['account_id']for v in values]
            alt=Characters(cfg.state_file,accounts[0]).create('CombatAlt',4,'owned-combat-alt')['uid']
            LocalState(cfg.state_file,alt).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=75')
                db.execute('UPDATE reward_balances SET experience=?',(client_data().thresholds[74],))
            for actor,profile in zip(values,balanced_profiles()):register_fixture(cfg.state_file,actor,profile)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for v in values:
                auth=v.pop('auth');v['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
                await connect(v,peers)
            a,b,observer=peers
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def snap(index):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,accounts[index],ids[index])
            def counts(index):
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,accounts[index],{4,5})
            async def success(p,kind,body=b'',reply=None):
                answer=await p.query(kind,body,reply)
                assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
                return answer
            async def seen(p,kind,start=0):
                old=next((e for e in p.received[start:]if e.kind==kind),None)
                return old if old is not None else await p.until(kind)
            assert all(not snap(i)['completed']for i in range(3))
            for p in(a,b):relays.append(await relay_fixture(p))
            async with asyncio.timeout(10):
                while not all(app.world.pvp.support_ready(app.playing[account])for account in accounts[:2]):await asyncio.sleep(.02)
            for p in(a,b):await success(p,0x7d4,struct.pack('>ii',5,30000));await success(p,0x342,registration())
            for p in(a,b):await seen(p,0x349)
            assert counts(0)==counts(1)=={(4,12):99,(5,12):99}
            for p in(a,b):await p.send(0x34a,b'\1\1\0'+bytes(4)+b'\0')
            for p in(a,b):await p.until(0x34b)
            for p in(a,b):await success(p,0x91,struct.pack('>ii',100,0))
            for p in(a,b):await seen(p,0x96)
            room=app.world.pvp.room(app.playing[accounts[0]])
            assert room.phase=='active'and all(not snap(i)['completed']for i in range(3))
            death=struct.pack('>iQQBffi?',-1,ids[0],ids[0],0,0.,0.,-1,False)
            ack=await b.query(0xa7,death);assert ack.payload[4:8]==bytes(4),ack.payload.hex()
            await b.send(0xaa)
            for p in(a,b):await p.until(0x9d)
            assert counts(0)==counts(1)=={(4,12):99,(5,12):99}
            starts=[len(p.received)for p in(a,b)]
            await success(a,0x9e,hp(1000.));await success(b,0x9e,hp(0.))
            for index,p in enumerate((a,b)):await seen(p,0xc2,starts[index]);await p.query(0x48d,reply=0x48f)
            assert room.phase=='result'
            assert counts(0)=={(4,12):100,(5,12):99}and counts(1)=={(4,12):99,(5,12):100}
            assert counts(2)=={(4,12):0,(5,12):0}
            for index,identity in((0,13),(1,16)):
                saved=snap(index);fresh=[r for r in saved['completed']if r['id']==identity]
                assert len(fresh)==1 and not fresh[0]['received']
                expected=achievement.completion(fresh,points(saved['completed']),[],False).payload
                assert any(e.kind==0x6c0 and e.payload==expected for e in peers[index].received[starts[index]:])
            assert not any(e.kind==0x6c0 for e in observer.received)
            report['checks'].append('Actual7D4/342/349/both34A/34B/both91/96 then victimA7/AA and both9E seals one current-policy official match; registration/loading/death alone add no count; winner13 and loser16 are immediately notified separately')
            original=[snap(i)for i in range(3)];records=read('SELECT * FROM official_pvp_results')
            for p,value in((a,1000.),(b,0.)):await success(p,0x9e,hp(value))
            assert original==[snap(i)for i in range(3)]and records==read('SELECT * FROM official_pvp_results')and len(records)==1
            for p,identity,value in((a,13,1000.),(b,16,0.)):
                for _ in range(2):
                    denied=await p.query(0x6c9,struct.pack('>i',identity));assert denied.payload[:4]==struct.pack('>i',2005)
                await success(p,0x67,struct.pack('>i',0)+hp(value)+bytes(4))
                await success(p,0x225,struct.pack('>iB',20001,0))
                await success(p,0x227,struct.pack('>fffBH',*catalog()['towns']['20001']['xyz'],0,0))
                await p.query(0x6be);await p.query(0x6be)
            assert original==[snap(i)for i in range(3)]
            report['checks'].append('Repeated9E and6BE are stable; missing original reward3000010 stays2005/unreceived for both13/16; actual67/68/D9 and225/227 return to town')
            old=app.playing[accounts[0]];await a.close();peers.remove(a)
            async with asyncio.timeout(10):
                while app.playing.get(accounts[0])is old:await asyncio.sleep(.02)
            p=await connect(dict(values[0],uid=alt,character_name='CombatAlt'),peers);await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:alternative=state.snapshot(db,accounts[0],alt)
            assert alternative['completed']==original[0]['completed']and alternative['watched']==[]
            assert not errors,errors
            report['checks'].append('Alternative-character cold login retains account victory13, no unrelated defeat16; observer stays uncredited')
            report.update(ok=True,completed=[[r['id']for r in snap(i)['completed']]for i in range(3)],
                one_real_settlement=True,both_accounts_immediately_notified=True)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            for writer,tasks in relays:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                writer.close()
                try:await writer.wait_closed()
                except (ConnectionError,ssl.SSLError):pass
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not root.exists(),
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('live-pvp-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
