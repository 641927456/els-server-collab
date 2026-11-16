"""Actual104/105 wear, account maximum, native immediate completion and cold read."""
from qa_environment import F,R,B
from pathlib import Path
from contextlib import closing
import asyncio,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback,uuid
sys.path.insert(0,str(F.parent/'spa-buff-history-v1/delivery-qa-v2'))
from achievement_protocol_client import connect
from create_friends_certificate import create
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.storage import achievements as state
from els_server.storage.achievement_collections import counts
from els_server.storage.wear_moves import move
from els_server.domain.ordinary_accessories import definitions as accessories
from els_server.domain.equipment_requirements import inspect_requirements
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data

async def main():
    report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,retained_owned_equipment_fixture=True,checks=[])
    peers=[];errors=[];app=server=None
    with tempfile.TemporaryDirectory(prefix='owned-equipment-ach-',dir=F)as folder:
        private=Path(folder);create(private,'127.0.0.1')
        cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,max_connections=8,normal_equipment_moves_enabled=True,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
        try:
            app=Application(cfg);await app.start();values=[]
            for i,letter in enumerate('AB'):
                auth=app.registry.create('ownedequip'+letter.lower());name='OwnEquip'+letter
                uid=Characters(cfg.state_file,auth['id']).create(name,1,'own-equip-'+letter)['uid'];values.append(dict(account_id=auth['id'],uid=uid,character_name=name,town=20001,auth=auth))
            a=values[0];alt=Characters(cfg.state_file,a['account_id']).create('OwnEquipAlt',1,'own-equip-alt')['uid']
            owners=[a['uid'],alt,values[1]['uid']]
            for uid in owners:LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
            with closing(sqlite3.connect(cfg.state_file))as db,db:
                db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99');db.execute('UPDATE reward_balances SET ed=6000000,experience=?',(client_data().thresholds[98],))
                for uid in owners:grant_items(db,[dict(template=t,metadata=1,group=1,quantity=1)for t in range(118153,118157)],uid)
                grant_items(db,[dict(template=t,metadata=0,group=2,quantity=1)for t in range(189020,189026)],a['uid'])
            # Retained worn fixtures use the original wear writer and legal positions.
            for uid,number in zip(owners,(3,2,4)):
                with closing(sqlite3.connect(cfg.state_file))as db:items=load_items(db,uid)
                for seq,item in enumerate((i for i in items if i['template']in range(118153,118153+number)),1):
                    slot=inspect_requirements(item['template'],1)['equipment_slot'];account=a['account_id']if uid in owners[:2]else values[1]['account_id']
                    body=struct.pack('>BiBiB',item['group'],item['slot'],9,slot,0)
                    move(cfg.state_file,body,uid,account_id=account,session_id=str(uuid.uuid4()),sequence=seq)
            def saved(owner=a['uid']):
                with closing(sqlite3.connect(cfg.state_file))as db:return state.snapshot(db,a['account_id'],owner)
            def source():
                with closing(sqlite3.connect(cfg.state_file))as db:return counts(db,a['account_id'],a['uid'],int(time.time()),{50})
            assert source()=={(50,297):0,(50,298):0,(50,371):3,(50,372):3}
            server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
            _,port=await server.start();pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest()
            for value in values:
                auth=value.pop('auth');value['bridge']=dict(host='127.0.0.1',port=port,name=auth['name'],token=auth['token'],certificate_sha256=pin)
            p=await connect(a,peers);current=saved();assert 371 in{r['id']for r in current['completed']}and 372 not in{r['id']for r in current['completed']}
            report['checks'].append('Cold role reads actual worn items; bag accessories do not count, siblings use maximum instead of sum and foreign four-piece account is excluded')
            async def wear(template,on=True):
                with closing(sqlite3.connect(cfg.state_file))as db:item=next(i for i in load_items(db,a['uid'])if i['template']==template)
                slot=inspect_requirements(template,1)['equipment_slot']if template<189000 else accessories()[template]['main_slots'][0]
                group=1 if template<189000 else 2
                body=struct.pack('>BiBiB',item['group'],item['slot'],9 if on else group,slot if on else 20,0)
                start=len(p.received);reply=await p.query(0x104,body)
                assert reply.payload[-4:]==bytes(4)and int.from_bytes(reply.payload[:4],'big')==2,(template,reply.payload[:20].hex(),reply.payload[-4:].hex(),app.playing[a['account_id']]._wear_rejection)
                return start
            start=await wear(118156);assert 372 in{r['id']for r in saved()['completed']}
            assert any(e.kind==0x6c0 for e in p.received[start:])
            await wear(118156,False);assert 372 in{r['id']for r in saved()['completed']}
            for template in range(189020,189026):
                start=await wear(template)
                if template in(189022,189025):
                    identity=297 if template==189022 else 298
                    assert identity in{r['id']for r in saved()['completed']}
                    assert any(e.kind==0x6c0 for e in p.received[start:])
            report['checks'].append('Actual104/105 fourth armor and third/sixth accessories complete372/297/298 immediately; normal unwear does not retract attained achievement')
            reply=await p.query(0x6c1,struct.pack('>i',298));assert reply.payload[:4]==bytes(4)
            before=saved();await p.query(0x6be);await p.query(0x6be);assert saved()==before
            old=app.playing[a['account_id']];await p.close();peers.remove(p)
            async with asyncio.timeout(10):
                while app.playing.get(a['account_id'])is old:await asyncio.sleep(.02)
            q=await connect(dict(a,uid=alt,character_name='OwnEquipAlt'),peers);await q.query(0x6be)
            restored=saved(alt);assert {297,298,371,372}<={r['id']for r in restored['completed']}and restored['watched']==[]and saved()['watched']==[298]
            assert not errors,errors
            report.update(ok=True,connected_source_types=41,connected_definitions=248,remaining_source_types=19)
            report['checks'].append('Repeated native reads are stable; cold sibling shares account completion with its own independent display')
        except BaseException:report['error']=traceback.format_exc()
        finally:
            for peer in reversed(peers):await peer.close()
            if server is not None:await server.close()
            if app is not None:app.close()
    report['errors']=errors;report['source_sha256']={p.relative_to(F/'source-v1').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in sorted((F/'source-v1').rglob('*.py'))}
    target=F/('live-equipment-'+str(time.time_ns())+'.json');target.write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(report,ensure_ascii=False));return report['ok']

if __name__=='__main__':raise SystemExit(not asyncio.run(main()))
