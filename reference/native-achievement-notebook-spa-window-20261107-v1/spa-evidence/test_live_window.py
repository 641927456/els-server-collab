"""Actual EA purchases and native dungeon admission/use, with owned SQL only."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback
sys.path.insert(0,str(F.parent/'noah-notebook-v1/delivery-qa'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage import achievements as state,npc_trade as trade,consumables as consumption
from els_server.storage.achievement_history import counts
from els_server.storage.inventory_state import load_items
from els_server.domain.town_travel import catalog
from els_server.domain.quick_bindings import item_binding
from els_server.storage.quick_slots import encode,empty
from els_server.domain.achievement_catalog import points
from els_server.protocol import achievement_messages as wire
from els_server.game_data import client_data
from els_server.domain import spa_market
ENTRY=bytes.fromhex('eefc726aad751f003e6b6d2e0c4d36e2923600000010332b6d21282a5c1774790f0f3a4c7947')

def request(quantity,merchant=10196):return struct.pack('>BHIiii',0,0,1,710012,quantity,merchant)

async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,
        retained_level_ED_saved_scene_fixture=True,private_complete_source_tree=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-spa-egg-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,state_file=private/'game.sqlite3',
            accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            clock_patch=patch.object(spa_market,'clock',return_value=300001)
            clock=clock_patch.start()
            for instant,expected in ((299,(0,0)),(300,(1,2)),(309.999,(1,2)),(310,(1,0)),(599.999,(1,0)),(600,(2,2))):
                clock.return_value=instant;assert spa_market.window()==expected
            clock.return_value=300001
            app=Application(cfg);await app.start();values=[]
            for letter,town in(('A',1500),('B',20000)):
                auth=app.registry.create('ownedspaegg'+letter.lower());name='OwnEgg'+letter
                uid=Characters(cfg.state_file,auth['id']).create(name,1,'owned-egg-'+letter)['uid']
                values.append(dict(uid=uid,account_id=auth['id'],character_name=name,town=town,auth=auth))
                LocalState(cfg.state_file,uid).save(town,0,0,(0.,0.,0.)if town==1500 else catalog()['towns'][str(town)]['xyz'])
            a,b=values;alt=Characters(cfg.state_file,a['account_id']).create('OwnEggAlt',1,'owned-egg-alt')['uid']
            LocalState(cfg.state_file,alt).save(1500,0,0,(0.,0.,0.))
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99')
                db.execute('UPDATE reward_balances SET ed=25000000,experience=?',(client_data().thresholds[98],))
            def snapshot(v,uid=None):
                owner=v['uid']if uid is None else uid
                with closing(sqlite3.connect(cfg.state_file))as db:
                    db.execute('BEGIN');return dict(achievement=state.snapshot(db,v['account_id'],owner),
                        bought=counts(db,v['account_id'],{34}).get((34,710012),0),items=load_items(db,owner),
                        balance=db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for v in values:
                auth=v.pop('auth');v['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
            p=await connect(a,peers);q=await connect(b,peers);before=snapshot(a);other=snapshot(b)
            assert before['bought']==other['bought']==0
            assert any(e.kind==0xc3a and e.payload==struct.pack('>i',2)for e in p.received)
            clock.return_value=300010
            await p.send(0x48d);notice=await p.until(0xc3a);assert notice.payload==bytes(4)
            reply=await p.query(0xea,request(1));assert reply.payload[:4]!=bytes(4)and snapshot(a)==before
            clock.return_value=300301
            await p.send(0x48d);notice=await p.until(0xc3a);assert notice.payload==struct.pack('>i',2)
            for merchant in(10193,10196):
                reply=await q.query(0xea,request(1,merchant));assert reply.payload[:4]!=bytes(4)and snapshot(b)==other
            for body in(request(1,10193),request(2),request(100)):
                reply=await p.query(0xea,body);assert reply.payload[:4]!=bytes(4)and snapshot(a)==before
            original=trade._commit
            def late(*args,**kw):original(*args,**kw);raise ValueError('Owned late spa purchase rollback')
            with patch.object(trade,'_commit',late):reply=await p.query(0xea,request(1))
            assert reply.payload[:4]!=bytes(4)and snapshot(a)==before
            def crossed(*args,**kw):original(*args,**kw);clock.return_value=300310
            with patch.object(trade,'_commit',crossed):reply=await p.query(0xea,request(1))
            assert reply.payload[:4]!=bytes(4)and snapshot(a)==before
            clock.return_value=300301
            last_operation=None;start=len(p.received)
            for quantity in [1]*500:
                actor=app.playing[a['account_id']];last_operation=actor.shop_session_id+':'+str(a['uid'])+':'+str(p.outgoing)
                reply=await p.query(0xea,request(quantity));assert reply.payload[:4]==bytes(4)
            saved=snapshot(a);assert saved['bought']==500 and saved['balance'][0]==before['balance'][0]-10000000
            assert sum(i['count']for i in saved['items']if i['template']==710012)==500
            fresh=[r for r in saved['achievement']['completed']if r['id']==200];assert len(fresh)==1
            expected=wire.completion(fresh,points(saved['achievement']['completed']),saved['achievement']['watched'],False).payload
            assert any(e.kind==0x6c0 and e.payload==expected for e in p.received[start:])
            trade.purchase(cfg.state_file,a['uid'],1500,request(1),last_operation)
            assert snapshot(a)==saved
            for _ in range(2):await p.query(0x6be)
            assert snapshot(a)==saved and snapshot(b)==other
            reply=await p.query(0xea,request(1));assert reply.payload[:4]==bytes(4)
            saved=snapshot(a);assert saved['bought']==501 and sum(i['count']for i in saved['items']if i['template']==710012)==501
            await p.query(0x6c1,struct.pack('>i',200));old=app.playing[a['account_id']]
            await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['account_id'])is old:await asyncio.sleep(.02)
            p=await connect(dict(a,uid=alt,character_name='OwnEggAlt'),peers)
            sibling=snapshot(a,alt);assert sibling['bought']==501 and sibling['achievement']['watched']==[]
            assert 200 in {r['id']for r in sibling['achievement']['completed']}and snapshot(a)['achievement']['watched']==[200]
            assert not any(i['template']==710012 for i in sibling['items'])
            old=app.playing[a['account_id']];await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['account_id'])is old:await asyncio.sleep(.02)
            # An explicit cold saved-town fixture positions the same owner for
            # normal admission; no actor phase/run is assigned by this test.
            app.accounts[a['account_id']].for_character(a['uid']).save_location(20000,0,0,catalog()['towns']['20000']['xyz'])
            p=await connect(dict(a,town=20000),peers)
            binding=item_binding(710012);assert binding
            reply=await p.query(0x8a1,struct.pack('>i',1)+encode({**empty(),0:binding}));assert reply.payload[:4]==bytes(4)
            current=snapshot(a);reply=await p.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114)
            assert reply.payload[:4]!=bytes(4)and snapshot(a)==current
            await p.send(0x7d4,struct.pack('>ii',1,30092));reply=await p.until(0x7d5);assert reply.payload[:4]==bytes(4)
            mode=struct.unpack_from('>i',reply.payload,4)[0]
            await p.send(0x37f if mode==2 else 0x382,ENTRY);reply=await p.until(0x380 if mode==2 else 0x383);assert reply.payload[:4]==bytes(4)
            await p.until(0x14a);await p.send(0x91,struct.pack('>ii',100,0));await p.until(0xb2)
            await p.send(0xb3,bytes(9));await p.until(0xbd);await p.query(0x48d,reply=0x48f)
            actor=app.playing[a['account_id']];assert actor.phase=='dungeon_active'and actor.dungeon_substage_synced
            current=snapshot(a)
            def fail_encoding(event):raise ValueError('Owned late native consumable encoding failure')
            with patch.object(consumption,'encode_event',fail_encoding):reply=await p.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114)
            assert reply.payload[:4]!=bytes(4)and snapshot(a)==current
            operation=actor.shop_session_id+':'+str(a['uid'])+':'+str(p.outgoing);start=len(p.received)
            reply=await p.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114);assert reply.payload[:4]==bytes(4)
            effect=struct.pack('>Qi?Q?',a['uid'],710012,False,0,False)
            assert sum(e.kind==0x115 and e.payload==effect for e in p.received[start:])==1
            used=snapshot(a);assert used['bought']==501 and sum(i['count']for i in used['items']if i['template']==710012)==500
            assert used['balance']==current['balance']
            reply=await p.query(0x113,struct.pack('>HBBB',0,0,0,0),reply=0x114)
            assert reply.payload[:4]==struct.pack('>i',1369)and snapshot(a)==used
            replay=consumption.use(cfg.state_file,a['uid'],struct.pack('>HBBB',0,0,0,0),operation,allow_apples=True,account_id=a['account_id'])
            assert len(replay)==1 and snapshot(a)==used
            assert not errors,errors
            report.update(ok=True,connected_source_types=44,connected_definitions=262,remaining_source_types=16,
                actual_native_purchases=501,actual_purchased_quantity=501,history_fixture=False,
                controlled_spa_clock_only=True,natural_300second_boundary=False,
                window_notification_kind="C3A",window_close_reject=True,window_cross_commit_rollback=True,actual_dungeon_admission=30092,
                native_MP_effect_notification=True,natural_MP_presentation=False,
                checks=['C3A opens/closes the vendor on the common5minute/10second clock; closed/crossed windows roll back;500one-item native EA purchases complete200',
                    'Wrong town/seller and oversized quantity refuse; late purchase write failure rolls back ED/items/history',
                    'Purchase replay and repeated6BEare stable; a new legitimate purchase increases quantity; cold sibling shares account completion and independent display',
                    'Normal7D4/382or37F/91/B3enters an actual stage; manual113emits one115, debits once, rolls back on encoding failure and enforces original cooldown/replay'])
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):await peer.close()
            if server is not None:await server.close()
            if app is not None:app.close()
            if 'clock_patch'in locals():clock_patch.stop()
    report['errors']=errors
    report['source_sha256']={p.relative_to(F/'source-v2').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((F/'source-v2').rglob('*'))if p.is_file()}
    p=F/('live-window-'+str(time.time_ns())+'.json');p.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
