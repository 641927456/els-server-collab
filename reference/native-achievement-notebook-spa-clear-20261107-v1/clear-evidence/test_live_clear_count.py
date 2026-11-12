"""Actual34350 four-room clear; unmodified server monotonic clock."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback,uuid
from unittest.mock import patch
sys.path.insert(0,str(F.parent/'relationship-history-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievement_history as history,achievements as state
from els_server.storage.reward_state import RewardState
from els_server.storage.seal_quests import ensure as ensure_quests
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
    with tempfile.TemporaryDirectory(prefix='owned-clear-count-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start();auth=app.registry.create('ownedclearcount');foreign=app.registry.create('ownedclearother')
            account=auth['id'];uid=Characters(cfg.state_file,account).create('TimeHist',1,'owned-time-character')['uid']
            alt=Characters(cfg.state_file,account).create('TimeHistAlt',2,'owned-time-alt')['uid']
            other=Characters(cfg.state_file,foreign['id']).create('TimeOther',3,'owned-time-other')['uid']
            for owner in(uid,alt,other):LocalState(cfg.state_file,owner).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET experience=?',(client_data().thresholds[98],))
                ensure_quests(db)
                # Original region10020 requires completed quest26650. This
                # is an explicit owned historical prerequisite fixture only.
                db.execute('INSERT INTO completed_quests VALUES (?,?,?,?)',(uid,26650,int(time.time()),'[]'))
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))
                if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name):return dict(uid=owner,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin))
            # Explicit owned historical receipts from the original writer,
            # not inferred production history or fabricated client counters.
            first=None
            for index in range(99):
                operation=str(uuid.uuid4());proof=('owned-clear-fixture:'+str(index)).encode()
                value=app.accounts.get(account)
                store=RewardState(cfg.state_file,uid,account_id=account)
                result=store.grant(operation,proof,0,0,lambda balances,best:b'owned-history',dungeon_clear=(34350,1))
                assert not result['replayed']
                if first is None:first=(operation,proof)
            foreign_store=RewardState(cfg.state_file,other,account_id=foreign['id'])
            foreign_store.grant(str(uuid.uuid4()),b'owned-foreign-clear',0,0,lambda balances,best:b'foreign-history',dungeon_clear=(34350,1))
            store.grant(str(uuid.uuid4()),b'owned-nonclear',0,0,lambda balances:b'not-a-clear')
            def recorded():
                with closing(sqlite3.connect(cfg.state_file))as db:return history.counts(db,account,{49})
            assert recorded()=={(49,34350):99}
            original=recorded()
            def bad_encoding(*args):raise ValueError('Owned final clear encode failure')
            try:store.grant(str(uuid.uuid4()),b'owned-failed-clear',0,0,bad_encoding,dungeon_clear=(34350,1))
            except ValueError as error:assert str(error)=='Owned final clear encode failure'
            else:raise AssertionError('Failed clear encoding committed')
            assert recorded()==original
            replay=store.grant(*first,0,0,lambda balances,best:b'unused',dungeon_clear=(34350,1))
            assert replay['replayed']and recorded()==original
            p=await connect(identity(uid,'TimeHist'),peers)
            def read(sql,args=()):
                with closing(sqlite3.connect(cfg.state_file))as db:return db.execute(sql,args).fetchall()
            def snap(aid=account,owner=uid):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,aid,owner)
            async def success(kind,body=b'',reply=None):
                answer=await p.query(kind,body,reply)
                assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
                return answer
            assert 373 not in {r['id']for r in snap()['completed']}
            admitted=await success(0x7d4,struct.pack('>ii',1,34350))
            entry_mode=struct.unpack_from('>i',admitted.payload,4)[0]
            opaque=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
            await success(0x37f if entry_mode==2 else 0x382,opaque)
            await success(0x91,struct.pack('>ii',100,0));await success(0xb3,bytes(9))
            s=app.playing[account];run=s.dungeon_run
            assert run.identity==34350 and s.dungeon_substage_synced
            assert 373 not in {r['id']for r in snap()['completed']}and recorded()=={(49,34350):99}
            await asyncio.sleep(1.1)
            stages=[];last=None;clear_start=None
            for step in range(2):
                assert s.dungeon_substage_synced and not s.clear_notified
                stages.append(run.stage)
                for npc in tuple(run.current['npcs']):
                    if run.poll_ready():break
                    if not npc['active']:continue
                    last=death(npc,uid);await success(0xad,last)
                assert s.part_end_notified and run.poll_ready(),(run.stage,s.part_end_notified,run.next)
                if step<1:assert recorded()=={(49,34350):99}and 373 not in {r['id']for r in snap()['completed']}
                clear_start=len(p.received)
                await success(0xbb,struct.pack('>b',run.part))
                if step<1:await success(0xb3,bytes(9))
            assert set(stages)=={0,1}and len(stages)==2 and s.clear_notified
            records=read('SELECT uid,map_id,seconds FROM dungeon_records WHERE uid=?',(uid,));assert len(records)==1
            assert recorded()=={(49,34350):100}
            assert records[0][:2]==(uid,34350)and 1<=records[0][2]<=60,records
            saved=snap();completed={r['id']for r in saved['completed']}
            assert 373 in completed and 373 not in {r['id']for r in snap(foreign['id'],other)['completed']}
            fresh=[r for r in saved['completed']if r['id']==373]
            assert len(fresh)==1
            expected=achievement.completion(fresh,points(saved['completed']),[],False).payload
            assert any(e.kind==0xc1 for e in p.received[clear_start:])
            assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[clear_start:])
            report['checks'].append('Actual7D4/382or37F/91/B3 enters34350; source-goal deaths andBB/B3 traverse both original rooms; loading and first room keep99fixture receipts; only final committedC1 reaches100and completes373')
            before=snap();await success(0xad,last);await success(0xbb,struct.pack('>b',run.part))
            await p.query(0x6be);await p.query(0x6be)
            assert snap()==before and records==read('SELECT uid,map_id,seconds FROM dungeon_records WHERE uid=?',(uid,))and recorded()=={(49,34350):100}
            old=s;await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(account)is old:await asyncio.sleep(.02)
            p=await connect(identity(alt,'TimeHistAlt'),peers);await p.query(0x6be)
            assert snap(account,alt)['completed']==before['completed']and snap(account,alt)['watched']==[]
            assert not errors,errors
            report['checks'].append('Repeated terminalAD/BB and6BE retain one record/completion; alternative-character cold login shares completion; foreign account stays uncredited')
            report.update(ok=True,stages=stages,record=list(records[0]),completed=sorted(completed),immediate_notification=True,
                historical_clear_fixture_receipts=99,historical_prerequisite_quest_fixture=26650,
                actual_protocol_final_clears=1,source49_count=100,default_owner_contract_uid=uid)
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except BaseException:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report.update(errors=errors,owned_directory_removed=not root.exists(),
        source_sha256={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')})
    (F/('live-clear-count-'+str(time.time_ns())+'.json')).write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode('utf8'))
    print(json.dumps(report,ensure_ascii=False));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
