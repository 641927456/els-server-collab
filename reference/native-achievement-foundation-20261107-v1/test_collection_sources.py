"""Real App registrations/bank transfer finish three derived collection conditions."""
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_live_profiles import W,Application,ServerConfig,GameServer,Characters,LocalState,create,catalog,connect,records,state
from els_server.domain.companions import catalog as companion_catalog
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,validate_item
from els_server.storage import companion_state,bank_state,mount_state,game_mail
from els_server.storage.item_instances import next_uid
from els_server.storage.inventory_state import grant_items
from els_server.storage.achievement_collections import counts
from els_server.storage.achievement_profiles import reconcile
from els_server.protocol.local_messages import wstring


async def run():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        initial_collection_and_capacity_fixtures=True,natural_registration_item_acquisition=False,checks=[])
    errors=[];peers=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-achievement-collections-',dir=W)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,
            state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',
            tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();ident=app.registry.create('ownedachcollect');foreign=app.registry.create('ownedachforeign')
            a=Characters(cfg.state_file,ident['id']).create('AchCollectA',1,'own-collection-A')['uid']
            b=Characters(cfg.state_file,ident['id']).create('AchCollectB',1,'own-collection-B')['uid']
            c=Characters(cfg.state_file,foreign['id']).create('AchCollectC',1,'own-collection-C')['uid']
            for uid in(a,b,c):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            definitions=companion_catalog()
            pet_source,pet_rule=next((t,v)for t,v in sorted(definitions['pet'].items())if t in VERIFIED_TEMPLATES and v['duration']==-1 and len(v['outcomes'])==1)
            mount_source,mount_rule=next((t,v)for t,v in sorted(definitions['mount'].items())if t in VERIFIED_TEMPLATES and v['duration']==-1 and len(v['outcomes'])==1)
            rental_source,rental_rule=next((t,v)for t,v in sorted(definitions['mount'].items())if 713152<=t<=713161 and v['duration']==14 and len(v['outcomes'])==1)
            now=int(time.time())
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');companion_state.ensure(db)
                def owned(owner,kind,unit,n):
                    values=[]
                    for _ in range(n):
                        identity=next_uid(db);source=next_uid(db)
                        row=dict(uid=identity,owner=owner,kind=kind,unit=unit,name='Owned'+str(identity),source_item=source)
                        db.execute('INSERT INTO companions VALUES(?,?,?,?,?,?)',tuple(row.values()));values.append(row)
                    return values
                owned(a,'pet',pet_rule['outcomes'][0][0],9);owned(b,'pet',pet_rule['outcomes'][0][0],1)
                owned(c,'pet',pet_rule['outcomes'][0][0],20)
                owned(a,'mount',mount_rule['outcomes'][0][0],4);owned(b,'mount',mount_rule['outcomes'][0][0],2)
                owned(c,'mount',mount_rule['outcomes'][0][0],10)
                expired=owned(a,'mount',rental_rule['outcomes'][0][0],1)[0]
                mount_state.assign_lifetime(db,a,expired,dict(group=4,slot=0,template=rental_source),14,now-15*86400)
                bank_state.set_capacity(db,a,16,48)
                for slot in range(47):
                    item=validate_item(dict(uid=next_uid(db),template=77000,metadata=VERIFIED_TEMPLATES[77000],group=TEMPLATE_BAG_GROUPS[77000],slot=0,count=1))
                    bank_state.put(db,a,(16,slot),item)
                sources=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)for t in(pet_source,mount_source,77000)],a)
                available={item['template']:item for item in sources}
                before=list(db.iterdump());initial=counts(db,ident['id'],a,now,{37,38,39});assert before==list(db.iterdump())
                assert initial[(37,1)]==9 and initial[(38,1)]==4 and initial[(39,0)]==47
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            def identity(uid,name):return dict(uid=uid,character_name=name,bridge=dict(host='127.0.0.1',port=port,name=ident['name'],token=ident['token'],certificate_sha256=pin))
            p=await connect(identity(a,'AchCollectA'),peers);await p.query(0x6be)
            with closing(sqlite3.connect(cfg.state_file))as db:assert state.snapshot(db,ident['id'],a)['completed']==[]
            pet=available[pet_source];ack=await p.query(0x2e8,struct.pack('>Q',pet['uid'])+wstring('AchPetTen'),0x2e9)
            assert ack.payload[:4]==bytes(4)
            mount=available[mount_source];ack=await p.query(0x432,struct.pack('>Q',mount['uid']),0x433)
            assert ack.payload[:4]==bytes(4)
            item=available[77000]
            transfer=struct.pack('>BiBiiQi',item['group'],item['slot'],16,47,1,0,77000)
            ack=await p.query(0x551,transfer,0x552);assert ack.payload[-4:]==bytes(4)
            notices=[records(e.payload)[0]for e in p.received if e.kind==0x6c0]
            assert [[r['id']for r in rows]for rows in notices]==[[240],[252],[264]],notices
            for identity_value in(240,252,264):
                for _ in range(2):
                    ack=await p.query(0x6c9,struct.pack('>i',identity_value),0x6ca)
                    assert ack.payload[:4]==bytes(4)and ack.payload[-1:]==b'\1'
            total,letters=game_mail.inbox(cfg.state_file,ident['id'],a)
            assert total==2 and sorted((r['item']['template'],r['item']['count'])for r in letters)==[(185080,10),(710118,20)]
            assert game_mail.inbox(cfg.state_file,ident['id'],b)==(0,[])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');before=list(db.iterdump())
                assert reconcile(db,ident['id'],b,int(time.time()))==dict(completed=[],replayed=False)
                assert before==list(db.iterdump())
                current=state.snapshot(db,ident['id'],b)
                assert {r['id']for r in current['completed']}=={240,252,264}
                assert state.snapshot(db,foreign['id'],c)['completed']==[]
                assert db.execute('SELECT COUNT(*)FROM shared_bank_items WHERE account_id=?',(ident['id'],)).fetchone()[0]==48
            assert not errors,errors
            report.update(ok=True,real_registrations=[pet_source,mount_source],completed=[240,252,264],
                checks=['Read-only collection snapshot:9+1sibling pets remain9;4+2sibling mounts remain4;expired rental excluded;foreign20pets/10mounts excluded;47shared slots incomplete',
                'Ordinary authenticated2E8/2E9 permanent pet registration and432/433 mount registration consume their real owned items and each emit one6C0',
                'Ordinary551/552 moves the48thslot into the shared bank and emits264completion',
                'Repeated ordinary6C9 gives one20fruit mail and one10fuel mail; no-reward264gives no mail',
                'Alt character sees account completion, no duplicate progress writes and no access to recipient mail'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in peers:
                try:await peer.close()
                except Exception:report.setdefault('close_errors',[]).append(traceback.format_exc())
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors
    report['source_sha256']={str(p.relative_to(W/'source-v1')):hashlib.sha256(p.read_bytes()).hexdigest()for p in(W/'source-v1').rglob('*')if p.is_file()and '__pycache__'not in p.parts}
    (W/('collection-sources-'+str(time.time_ns())+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(run()))
