"""Actual private dungeon entry, shortcut use, death confirmation and paid revival."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,tempfile,time,traceback,uuid
sys.path.insert(0,str(F.parent/'guild-post-v1'))
from achievement_qa_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.quick_slots import save_request,encode,empty
from els_server.storage.known_resurrection import _set as set_stones
from els_server.storage import achievements as state,achievement_history as history
from els_server.domain.town_travel import catalog as towns
from els_server.domain.quick_bindings import item_binding
from els_server.domain.consumables import catalog as consumables
from els_server.game_data import client_data


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures='Level99, owned MP potion, one known resurrection stone and retained999uses/99paid-revivals',natural_acquisition=False)
    app=server=None;peers=[];errors=[]
    with tempfile.TemporaryDirectory(prefix='owned-consumption-history-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=6,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start()
            account=app.registry.create('ownedconsumptionhist');foreign=app.registry.create('ownedconsumeforeign')
            uid=Characters(cfg.state_file,account['id']).create('ConsumeHist',1,'owned-consume-character')['uid']
            alt=Characters(cfg.state_file,account['id']).create('ConsumeAlt',2,'owned-consume-alt')['uid']
            other=Characters(cfg.state_file,foreign['id']).create('ConsumeOther',3,'owned-consume-other')['uid']
            for owner in(uid,alt,other):LocalState(cfg.state_file,owner).save(20001,0,0,towns()['towns']['20001']['xyz'])
            assert consumables()[77010]['cooldown_group']==4 and item_binding(77010)!=4
            enum=client_data().resource('Enum.lua')['COOLTIME_ITEM_GROUP']
            assert {enum[k]for k in('CIG_MP_POTION','CIG_FULL_RECOVER_ITEM','CIG_DRINK','CIG_THROW_ITEM','CIG_FOOD','CIG_GUILD_POTION')}=={2,4,5,6,15,40}
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET experience=?',(client_data().thresholds[98],))
                potion=grant_items(db,[dict(template=77010,metadata=2,group=6,quantity=1)],uid)[0]
                set_stones(db,uid,1)
                db.execute('CREATE TABLE consumable_uses(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,item_uid INTEGER NOT NULL,template INTEGER NOT NULL,used_at REAL NOT NULL)')
                db.executemany('INSERT INTO consumable_uses VALUES(?,?,?,?,?,?)',
                    [('owned-retained-potion:'+str(n),'owned-fixture',uid,potion['uid'],77010,1000+n)for n in range(999)])
                # A different legitimate group must remain separate from MP.
                db.execute('INSERT INTO consumable_uses VALUES(?,?,?,?,?,?)',('owned-retained-food','owned-fixture',uid,potion['uid'],72000,1000))
                db.execute('CREATE TABLE known_resurrection_spends(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,owner INTEGER NOT NULL,run TEXT NOT NULL,life INTEGER NOT NULL,UNIQUE(owner,run,life))')
                epoch=str(uuid.uuid4())
                db.executemany('INSERT INTO known_resurrection_spends VALUES(?,?,?,?,?)',
                    [('owned-retained-revival:'+str(n),'owned-fixture',uid,epoch,n+1)for n in range(99)])
            save_request(cfg.state_file,struct.pack('>i',1)+encode({**empty(),5:item_binding(77010)}),uid)
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(owner,name):return dict(uid=owner,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            p=await connect(identity(uid,'ConsumeHist'),peers)
            await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert state.snapshot(db,account['id'],uid)['completed']==[]
                assert history.counts(db,account['id'],{35})[(35,4)]==999
            async def success(kind,body=b'',reply=None):
                answer=await p.query(kind,body,reply)
                assert answer.payload[:4]==bytes(4),(hex(kind),answer.payload[:20].hex())
                return answer
            # Town admission still rejects ordinary potion use and revival.
            answer=await p.query(0x113,struct.pack('>HBBB',5,0,0,0));assert answer.payload[:4]!=bytes(4)
            await success(0x7d4,struct.pack('>ii',1,30000))
            create_request=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')
            await success(0x382,create_request)
            await success(0x91,struct.pack('>ii',100,0))
            await success(0xb3,bytes(9))
            await success(0x113,struct.pack('>HBBB',5,0,0,0))
            answer=await p.query(0x113,struct.pack('>HBBB',5,0,0,0));assert answer.payload[:4]!=bytes(4)
            use=struct.pack('>?QQ?',False,0,uid,False)
            answer=await p.query(0x160,use);assert answer.payload[:4]!=bytes(4),'Alive character must not spend a stone'
            death=struct.pack('>iQQBffi?',-1,uid,uid,0,0,0,-1,False)
            answer=await p.query(0xa7,death);assert answer.payload[4:8]==bytes(4),answer.payload.hex()
            await p.query(0xaa,reply=0xac)
            await success(0x160,use)
            answer=await p.query(0x160,use);assert answer.payload[:4]!=bytes(4)
            with closing(sqlite3.connect(cfg.state_file))as db:
                got=history.counts(db,account['id'],{35,36})
                assert got[(35,4)]==1000 and got[(36,0)]==100,got
                assert db.execute('SELECT count FROM known_resurrection_stones WHERE owner=?',(uid,)).fetchone()==(0,)
                assert not any(i['uid']==potion['uid']for i in load_items(db,uid))
                done={r['id']for r in state.snapshot(db,account['id'],uid)['completed']};assert done=={210,235},done
                assert history.counts(db,foreign['id'],{35,36})=={(36,0):0}
                before=[r for r in db.iterdump()if 'native_achievement_'in r]
            await p.query(0x6be);await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert before==[r for r in db.iterdump()if 'native_achievement_'in r]
            await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while account['id']in app.playing:await asyncio.sleep(.05)
            p=await connect(identity(alt,'ConsumeAlt'),peers);await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert {r['id']for r in state.snapshot(db,account['id'],alt)['completed']}==done
            assert not errors,errors
            report.update(ok=True,completed=sorted(done),counts={str(k):v for k,v in got.items()},checks=[
                'Ordinary town request rejects potion use; native7D4/382/91/B3 enters actual isolated dungeon',
                'One actual113use consumes owned MP potion and completes210; no-material failure adds no use',
                'Alive160rejected; actualA7/AAdeath followed by160spends one known stone and completes235',
                'Second160cannot spend again; separate cooldown group and other account remain isolated',
                'Repeated6BEis stable and alternative-character cold login restores both shared completions'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-consumption-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
