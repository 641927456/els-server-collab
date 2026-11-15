"""Real private App/TLS requests cross six retained-history thresholds."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from qa_environment import F,R,B
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
from unittest.mock import patch
sys.path.insert(0,str(F.parent/'guild-post-v1'))
from achievement_qa_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage.inventory_actions import _commit
from els_server.storage import achievements as state,achievement_history as history,profession_state,anvil
from els_server.storage.equipment_enhancement import replace as enhancement
from els_server.storage.enhancement_progress import replace as enhancement_progress
from els_server.protocol.profession_messages import ProfessionState
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.town_travel import catalog as towns
from els_server.domain.equipment_spell_rules import catalog as spells
from els_server.domain.acquisition_policy import can_acquire
from els_server.game_data import client_data
from els_server.storage.hunter_sphere import convert


TYPES={32,45,51,52,53,60}


def completions(peer):
    identities=[]
    for event in peer.received:
        if event.kind!=0x6c0:continue
        count=struct.unpack_from('>I',event.payload)[0];offset=4
        for _ in range(count):
            identity,length=struct.unpack_from('>iI',event.payload,offset)
            offset+=8+length+1;identities.append(identity)
    return identities


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        fixtures='Level99/ED, admitted profession snapshots, owned materials, full enhancement gauge and retained prior receipts',
        natural_acquisition=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-equipment-tools-',dir=F)as folder:
        root=Path(folder);create(root,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=root/'game.sqlite3',accounts_file=root/'accounts.sqlite3',
            tls_cert=root/'server-cert.pem',tls_key=root/'server-key.pem',log_dir=root/'logs')
        try:
            app=Application(cfg);await app.start()
            owner=app.registry.create('ownedequipmenttools');other=app.registry.create('ownedforeigntools')
            names=('HistHunter','HistSmith','HistAlchemy','HistAlt')
            uids=[Characters(cfg.state_file,owner['id']).create(name,i+1,'owned-tool-'+str(i))['uid']for i,name in enumerate(names)]
            foreign=Characters(cfg.state_file,other['id']).create('HistForeign',5,'owned-tool-foreign')['uid']
            for uid in[*uids,foreign]:LocalState(cfg.state_file,uid).save(20001,0,0,towns()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=100000000,experience=?',(client_data().thresholds[98],))
                for uid,profession in zip(uids,(1,2,3,0)):
                    if profession:profession_state.replace(db,uid,owner['id'],0,ProfessionState(profession,1,0,{},0,400))
                def grant(uid,t,n=1):
                    return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)],uid)[0]
                gear=grant(uids[0],60100);socket_target=grant(uids[0],11006011)
                stone=grant(uids[0],135184,2);coin=grant(uids[0],117527)
                weapon_template=next(int(t)for t,row in spells()['targets'].items()if row['tag64']and int(t)in VERIFIED_TEMPLATES and can_acquire(int(t)))
                weapon=grant(uids[0],weapon_template);mystic=grant(uids[0],136109)
                ingredients=[grant(uids[2],60100)for _ in range(5)]
                enhancement(db,uids[0],gear['uid'],0,9)
                enhancement_progress(db,uids[0],dict(gear,enhancement=9),180,0)
                _commit(db,'owned-tool-fixture-schema','fixture',uids[0],0x555,[],[],[])
                def retained(key,uid,kind,before,after):
                    db.execute('INSERT INTO inventory_action_receipts VALUES(?,?,?,?,?,?,?)',
                        (key,'owned-retained-fixture',uid,kind,'[]',json.dumps(before),json.dumps(after)))
                for n in range(4):retained('owned-enhance-'+str(n),uids[0],0x5ff,[dict(gear,enhancement=9)],[dict(gear,enhancement=10)])
                retained('owned-sockets',uids[0],0x1c4,[dict(stone,count=998)],[])
                retained('owned-mystics',uids[0],0x6e7,[dict(mystic,count=99)],[])
                for n in range(99):
                    retained('owned-sphere-'+str(n),uids[0],0x705,[coin],[])
                    retained('owned-flask-'+str(n),uids[2],0x707,ingredients,[])
                anvil.create_schema(db)
                db.executemany('INSERT INTO profession_anvil_receipts VALUES(?,?,?,?,?,?,?,?,?)',
                    [('owned-anvil-'+str(n),'owned-retained-fixture',uids[1],owner['id'],100000,1,100,n+1,n+1)for n in range(9)])
                initial=history.counts(db,owner['id'],TYPES)
                assert initial=={(32,10):4,(45,0):998,(51,0):99,(52,0):99,(53,0):9,(60,0):99},initial
            with closing(sqlite3.connect(cfg.state_file))as db:unchanged=list(db.iterdump())
            with patch('els_server.storage.hunter_sphere.acknowledgement',side_effect=ValueError('Owned encoder rollback probe')):
                try:convert(cfg.state_file,uids[0],owner['id'],struct.pack('>i',117527),'owned-rollback-probe',authorize=lambda:True)
                except ValueError as error:assert 'Owned encoder rollback probe'in str(error)
                else:raise AssertionError('Injected encoder failure was swallowed')
            with closing(sqlite3.connect(cfg.state_file))as db:assert unchanged==list(db.iterdump())
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(uid,name,account=owner):
                return dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=account['name'],token=account['token'],certificate_sha256=pin))
            async def successful(peer,kind,body=b''):
                reply=await peer.query(kind,body)
                assert reply.payload[:4]==bytes(4),(hex(kind),reply.payload[:20].hex())
                return reply
            async def logout(peer,account=owner):
                await peer.close();peers.remove(peer)
                async with asyncio.timeout(10):
                    while account['id']in app.playing:await asyncio.sleep(.05)
            first=await connect(identity(uids[0],names[0]),peers)
            await first.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert state.snapshot(db,owner['id'],uids[0])['completed']==[]
            # A real full-gauge enhancement succeeds without altering any RNG policy.
            await successful(first,0x5ff,struct.pack('>QiiBBBBiB',gear['uid'],4,0,0,0,1,0,0,0))
            batch=struct.pack('>QI',socket_target['uid'],2)+b''.join(struct.pack('>iQ',slot,stone['uid'])for slot in(0,1))+struct.pack('>BBI6i',0,0,6,*([0]*6))
            await successful(first,0x1c4,batch)
            preview=struct.pack('>QIiIiQBiB',weapon['uid'],1,10,1,0,mystic['uid'],0,2,0)
            await successful(first,0x6e7,preview)
            await successful(first,0x6e7,struct.pack('>QIBiB',weapon['uid'],0,0,4,0))
            await successful(first,0x705,struct.pack('>i',117527))
            assert completions(first)==[185,205,355,304],completions(first)
            with closing(sqlite3.connect(cfg.state_file))as db:
                operation=db.execute('SELECT operation_id FROM inventory_action_receipts WHERE owner=?AND kind=?AND request_hash<>?ORDER BY rowid DESC LIMIT 1',
                    (uids[0],0x705,'owned-retained-fixture')).fetchone()[0]
                unchanged=list(db.iterdump())
            convert(cfg.state_file,uids[0],owner['id'],struct.pack('>i',117527),operation,authorize=lambda:True)
            with closing(sqlite3.connect(cfg.state_file))as db:assert unchanged==list(db.iterdump()),'Receipt replay mutated economics or source history'
            # All held units were consumed; a further attempt must not count.
            for kind,body in((0x1c4,batch),(0x705,struct.pack('>i',117527))):
                reply=await first.query(kind,body);assert reply.payload[:4]!=bytes(4)
            await logout(first)
            smith=await connect(identity(uids[1],names[1]),peers)
            await successful(smith,0x9b3)
            assert completions(smith)==[309],completions(smith)
            reply=await smith.query(0x9b3);assert reply.payload[:4]!=bytes(4),'Anvil cooldown must remain enforced'
            await logout(smith)
            alchemy=await connect(identity(uids[2],names[2]),peers)
            flask_body=struct.pack('>I5Q',5,*[i['uid']for i in ingredients])
            await successful(alchemy,0x707,flask_body)
            assert completions(alchemy)==[314],completions(alchemy)
            reply=await alchemy.query(0x707,flask_body);assert reply.payload[:4]!=bytes(4)
            await alchemy.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                expected={(32,10):5,(45,0):1000,(51,0):100,(52,0):100,(53,0):10,(60,0):100}
                assert history.counts(db,owner['id'],TYPES)==expected,history.counts(db,owner['id'],TYPES)
                done={r['id']for r in state.snapshot(db,owner['id'],uids[2])['completed']}
                assert done=={185,205,304,309,314,355},done
                assert history.counts(db,other['id'],TYPES)=={(45,0):0,(51,0):0,(52,0):0,(53,0):0,(60,0):0}
                before=[r for r in db.iterdump()if 'native_achievement_'in r]
            await alchemy.query(0x6be);await alchemy.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert before==[r for r in db.iterdump()if 'native_achievement_'in r]
            # The original reward for this completed low tier is still missing.
            with closing(sqlite3.connect(cfg.state_file))as db:unchanged=list(db.iterdump())
            for _ in range(2):
                reply=await alchemy.query(0x6c9,struct.pack('>i',314))
                assert struct.unpack_from('>i',reply.payload)[0]==2005,reply.payload.hex()
            with closing(sqlite3.connect(cfg.state_file))as db:assert unchanged==list(db.iterdump()),'Deferred reward must not pay or mark received'
            await logout(alchemy)
            alt=await connect(identity(uids[3],names[3]),peers);await alt.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:
                assert {r['id']for r in state.snapshot(db,owner['id'],uids[3])['completed']}==done
                assert not any(r['received']for r in state.snapshot(db,owner['id'],uids[3])['completed'])
            assert not errors,errors
            report.update(ok=True,counts={str(k):v for k,v in expected.items()},completed=sorted(done),checks=[
                'Full-gauge ordinary enhancement crosses exact+10 threshold without an amulet',
                'One real two-slot batch consumes two stones and completes205',
                'Paid mystic preview plus apply counts once and completes355',
                'Real sphere, anvil and flask calls complete304/309/314 across three professions',
                'No-material and anvil-cooldown failures add no count; other account remains isolated',
                'Each successful action immediately emits its own6C0completion before a manual query',
                'Encoder failure rolls back the full sphere transaction and replay changes no persisted row',
                'Missing original314reward is refused twice without payment or a received marker',
                'Repeated queries are idempotent and another character cold-restores shared completions'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for p in peers:
                try:await p.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(F/'source-v1').rglob('*.py')}
    (F/('live-equipment-tools-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,indent=2),'utf8')
    print(json.dumps(report));return report['ok']


if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
