"""Authenticated native requests: unrestricted admission and atomic settlement."""
from tls_helpers import *
from els_server.storage.item_seals import assign
from els_server.storage.equipment_attributes import replace_attributes
from els_server.storage.equipment_enhancement import replace as enhancement
from els_server.storage.npc_trade import balances
import time

async def main():
    report=dict(ok=False,steps=[],natural_GUI=False,production_database_access=False,
        admission='User-approved: no minimum level, no waiting period or level-reached timestamp',
        fixture='Own new characters levels1/1/99, ED5000, ordinary materials and sealed gear; real elapsed invitation timeout')
    peers=[];app=server=None;stage='start'
    with tempfile.TemporaryDirectory(prefix='owned-trade-tls-',dir=OUT)as temporary:
        private=Path(temporary);cert=create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',
            accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',
            tls_key=private/'server-key.pem',log_dir=private/'logs')
        logs=[]
        try:
            app=Application(cfg);await app.start()
            server=GameServer(cfg,app,lambda event,**kw:logs.append(dict(event=event,**kw)))
            _,port=await server.start()
            identities=[app.registry.create('ownedtradetls'+str(i))for i in range(3)];uids=[]
            from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
            for index,a in enumerate(identities):
                uid=Characters(cfg.state_file,a['id']).create('TradeWire'+str(index),1,'owned-trade-'+str(index))['uid'];uids.append(uid)
                local=__import__('els_server.domain.local_session',fromlist=['LocalAccount']).LocalAccount(LocalState(cfg.state_file,uid),account_id=a['id'])
                local.enable_characters(characters=Characters(cfg.state_file,a['id']));local.get_inventory_snapshot()
                with closing(sqlite3.connect(cfg.state_file))as db,db:
                    db.execute('UPDATE characters SET level=? WHERE uid=?',(99 if index==2 else 1,uid))
                    db.execute('UPDATE reward_balances SET ed=5000 WHERE uid=?',(uid,))
                    grants=[(500040,10 if index==0 else 3)]if index<2 else[]
                    if index==0:grants.append((30154,1))
                    if grants:grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=n)for t,n in grants],uid)
                    if index==0:
                        gear=next(i for i in load_items(db,uid)if i['template']==30154)
                        assign(db,uid,gear['uid'],True,2);replace_attributes(db,uid,gear['uid'],[0]*4,[1,0,0,0]);enhancement(db,uid,gear['uid'],0,8)
                LocalState(cfg.state_file,uid).save(20000,0,0,(1.,2.,3.))
            async def connect(index):
                a=identities[index];p=Peer()
                p.bridge=Bridge(BridgeConfig('127.0.0.1',port,a['name'],a['token'],cert))
                p.reader,p.writer=await p.bridge.remote();p.keys=BOOTSTRAP_KEYS;p.incoming=1;p.received=[]
                welcome=await p.until(0x1);p.spi,p.keys=read_welcome(welcome);p.outgoing=1;peers.append(p)
                for kind,reply in((0x1a,0x1b),(0x1e,0x19c),(0x35,0x36),(0x1ef,0x1f0),(0x39,0x3a),(0x485,0x488)):
                    await p.send(kind);await p.until(reply)
                for kind,reply,body in((0x490,0x491,b''),(0x28,0x29,struct.pack('>Q',uids[index])),
                        (0x6e9,0x6ea,b''),(0x5bf,0x5c0,bytes(8)),(0x32,0x33,b''),
                        (0x225,0x226,struct.pack('>iB',20000,0)),(0x227,0x228,struct.pack('>fffBH',1.,2.,3.,0,0))):
                    await p.send(kind,body);ack=await p.until(reply)
                    if kind in(0x225,0x227):assert ack.payload[:4]==bytes(4),(kind,ack.payload.hex())
                await p.query(0x48d,b'',0x48f);return p
            def assets():
                with closing(sqlite3.connect(cfg.state_file))as db:
                    return{uid:dict(items=load_items(db,uid),money=balances(db,uid))for uid in uids}
            async def action(p,kind,body=b'',ok=True):
                ack=await p.query(kind,body,kind+1)
                assert(ack.payload[:4]==bytes(4))is ok,(hex(kind),ack.payload.hex())
                return ack
            async def open_trade(first,second,first_index,second_index):
                await action(first,0x174,struct.pack('>Q',uids[second_index]));await second.until(0x176)
                ack=await second.query(0x177,struct.pack('>QBi',uids[first_index],1,0),0x179)
                assert len(ack.payload)>0
                await first.query(0x48d,b'',0x48f)
            stage='authenticated-town-login'
            a,b,c=[await connect(i)for i in range(3)]
            assert all(app.playing[row['id']].phase=='town_ready'for row in identities)
            stage='new-level-one-admission'
            await open_trade(a,b,0,1)
            report['steps'].append('New level1/level1 accounts enter trade through174/176/177/179 without level timestamps or waiting')
            before=assets();gear=next(i for i in before[uids[0]]['items']if i['template']==30154)
            material=[next(i for i in before[uids[j]]['items']if i['template']==500040)for j in(0,1)]
            stage='offers-registration-and-approval'
            for item,n in((gear,1),(material[0],4)):await action(a,0x17f,struct.pack('>QiB',item['uid'],n,0))
            await action(b,0x17f,struct.pack('>QiB',material[1]['uid'],1,0))
            await action(a,0x182,struct.pack('>Q',101));await action(b,0x182,struct.pack('>Q',20))
            await action(a,0x185)
            await action(b,0x182,struct.pack('>Q',20))
            room=app.world.player_trades.by_session[app.playing[identities[0]['id']]]
            assert room['registered']==set()
            await action(a,0x185);await action(b,0x185)
            await action(a,0x188);assert assets()==before
            await action(b,0x188);await a.query(0x48d,b'',0x48f)
            after=assets();assert[after[u]['money']['ed']for u in uids]==[4918,5076,5000]
            assert[sum(i['count']for i in after[u]['items']if i['template']==500040)for u in uids[:2]]==[7,6]
            moved=next(i for i in after[uids[1]]['items']if i['uid']==gear['uid'])
            assert moved['enhancement']==8 and moved['sealed']is False and moved['seal_used']==2
            assert not app.world.player_trades.by_session
            assert all(any(e.kind==0x18b for e in p.received)for p in(a,b))
            report['steps'].append('17F/182 offers; peer edit resets registration; both185/188 required; sealed enhanced UID retained, partial quantities transferred, receiver fees total6 ED')
            stage='replayed-final-and-forged-consent'
            await action(b,0x188,ok=False);assert assets()==after
            await action(a,0x174,struct.pack('>Q',uids[1]));await b.until(0x176)
            await action(c,0x174,struct.pack('>Q',uids[1]),ok=False)
            denied=await a.query(0x177,struct.pack('>QBi',uids[0],1,0),0x178);assert denied.payload
            await action(a,0x17a,struct.pack('>i',0x72));await b.query(0x48d,b'',0x48f)
            assert not app.world.player_trades.by_session and assets()==after
            report['steps'].append('Replayed final approval, busy third party and inviter-forged consent cannot settle; native17A cancels both reservations without economic mutation')
            stage='actual-elapsed-invitation-timeout'
            began=time.monotonic();await action(a,0x174,struct.pack('>Q',uids[1]));await b.until(0x176)
            async with asyncio.timeout(14):
                while app.world.player_trades.by_session:await asyncio.sleep(.1)
            elapsed=time.monotonic()-began;assert elapsed>=10
            await a.query(0x48d,b'',0x48f);await b.query(0x48d,b'',0x48f)
            assert assets()==after
            report['invitation_timeout_seconds']=elapsed
            report['steps'].append('Actual ten-second pending invitation timeout releases both actors and delivers denial')
            stage='disconnect-cancel'
            await open_trade(a,b,0,1);await b.close();peers.remove(b)
            async with asyncio.timeout(5):
                while identities[1]['id']in app.playing:await asyncio.sleep(.01)
            assert not app.world.player_trades.by_session
            await a.query(0x48d,b'',0x48f);assert any(e.kind==0x17c for e in a.received)
            assert assets()==after
            report['steps'].append('Real socket close cancels active trade and notifies surviving current actor')
            stage='normal-level99-level1-trade'
            await open_trade(c,a,2,0);await action(c,0x182,struct.pack('>Q',11))
            for p in(c,a):await action(p,0x185)
            for p in(c,a):await action(p,0x188)
            final=assets();assert[final[u]['money']['ed']for u in uids]==[4928,5076,4989]
            report['steps'].append('Normal level99 and new level1 also complete native bilateral ED trade with shared fee/wallet limits')
            stage='cold-reconnect'
            for p in(a,c):await p.close();peers.remove(p)
            async with asyncio.timeout(5):
                while app.playing:await asyncio.sleep(.01)
            cold=[await connect(i)for i in range(3)];assert assets()==final
            assert all(app.playing[x['id']].account.get_inventory_snapshot()['items']==final[uid]['items']for x,uid in zip(identities,uids))
            with closing(sqlite3.connect(cfg.state_file))as db:assert db.execute('SELECT count(*) FROM native_player_trades').fetchone()[0]==2
            report['steps'].append('Three authenticated cold reconnects retain exact committed items and balances; exactly two settlement receipts')
            report['ok']=True
        except BaseException:
            report['failure_stage']=stage;report['failure']=traceback.format_exc()
        finally:
            for p in reversed(peers):
                try:await p.close()
                except Exception:pass
            if server is not None:await server.close()
            if app is not None:app.close()
            report['connections_closed']=server is None or not server.connections
            report['server_errors']=[row for row in logs if row['event']in('connection_error','disconnect_error','periodic_error','state_error')]
            report['ok']=report['ok']and not report['server_errors']
            report['loaded_sources']={n:dict(path=str(m.__file__),sha256=hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest())
                for n,m in list(sys.modules.items())if n.startswith('els_server.')and getattr(m,'__file__',None)}
    target=OUT/('trade-tls-'+str(time.time_ns())+'.json');target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items()if k!='loaded_sources'},ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(0 if asyncio.run(main())else 1)
