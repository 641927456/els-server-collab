"""Owned fixture: authenticated104 first wear, pending storage, rollback and expiry."""
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import asyncio,ctypes,hashlib,json,sqlite3,ssl,struct,sys,tempfile,time,traceback,uuid
R=Path('G:/els');G=Path(__file__).resolve().parent;W=G.parents[1];B=G/'test-source-v1'
sys.dont_write_bytecode=True
sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R),str(W/'delivery-duel-v1')]
ctypes.WinDLL(str(W/'duel-wire-v2/full-source/python/sqlite3.dll'))
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.transport import GameServer
from els_server.storage.characters import Characters
from els_server.storage.local_state import LocalState
from els_server.storage.inventory_state import load_items
from els_server.storage.item_instances import insert,next_uid
from els_server.storage import item_expiration,wear_moves,bank_state
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,FASHION_EQUIP_SLOTS,item_body
from els_server.domain.town_travel import catalog
from els_server.game_data import client_data
from create_friends_certificate import create
from native_peer import connect

from els_server.domain import wedding_gifts as gifts
from els_server.storage import fixed_cubes
from els_server.storage.inventory_state import grant_items
from els_server.storage.item_instances import remove
from els_server.domain.ordinary_accessories import definitions as accessory_definitions

async def main():
 report=dict(ok=False,actual_authenticated_TLS=True,native_Game=False,natural_GUI=False,production_database_access=False,checks=[],opened=[])
 app=server=None;peers=[];errors=[];stage='setup'
 with tempfile.TemporaryDirectory(prefix='owned-wedding-gifts-',dir=G)as name:
  private=Path(name).resolve();create(private,'127.0.0.1')
  cfg=ServerConfig(mode='friends',host='127.0.0.1',port=0,state_file=private/'game.sqlite3',accounts_file=private/'accounts.sqlite3',tls_cert=private/'server-cert.pem',tls_key=private/'server-key.pem',log_dir=private/'logs')
  try:
   app=Application(cfg);await app.start();identity=app.registry.create('ownedweddinggifts')
   roster=Characters(cfg.state_file,identity['id']);male=roster.create('GiftMale',1,'owned-gift-male')['uid'];female=roster.create('GiftLithia',15,'owned-gift-lithia')['uid']
   for uid in(male,female):LocalState(cfg.state_file,uid).save(20001,0,0,catalog()['towns']['20001']['xyz'])
   def items(uid):
    with closing(sqlite3.connect(cfg.state_file))as db:return load_items(db,uid)
   def facts():
    with closing(sqlite3.connect(cfg.state_file))as db:
     return {t:db.execute('SELECT *FROM '+t+' ORDER BY 1').fetchall()for t, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
   def seed(uid,t,group=None,slot=None):
    with closing(sqlite3.connect(cfg.state_file))as db,db:
     db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE');group=TEMPLATE_BAG_GROUPS[t]if group is None else group;occupied={i['slot']for i in load_items(db,uid)if i['group']==group}
     if slot is None:slot=next(s for s in range(24)if s not in occupied)
     item=dict(uid=next_uid(db),template=t,metadata=VERIFIED_TEMPLATES[t],count=1,group=group,slot=slot);insert(db,uid,item);return item
   def clear(uid,ids):
    with closing(sqlite3.connect(cfg.state_file))as db,db:
     db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
     for item in load_items(db,uid):
      if item['uid']in ids:remove(db,uid,item)
   def use(item,choices=(),minor=0):return struct.pack('>QBBBI',item['uid'],0,minor,0,len(choices))+b''.join(struct.pack('>i',t)for t in choices)+struct.pack('>i',1)
   server=GameServer(cfg,app,lambda event,**kw:errors.append(dict(event=event,**kw))if event in('protocol_error','worker_error','notification_error','connection_task_error')else None)
   _,port=await server.start();bridge=dict(host='127.0.0.1',port=port,name=identity['name'],token=identity['token'],certificate_sha256=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cfg.tls_cert.read_text('ascii'))).hexdigest())
   peer=await connect(dict(uid=male,bridge=bridge),peers)
   async def open_one(uid,item,choices=()):
    before=items(uid);ids={i['uid']for i in before};char=roster.get(uid);char['active_unit']=0
    expected=gifts.selected_outputs(item['template'],char,choices)
    preview=await peer.query(0x559,struct.pack('>iIBB',item['template'],0,0,0));assert preview.payload[:4]==bytes(4),(item['template'],'preview',preview.payload.hex())
    raw=use(item,choices);answer=await peer.query(0x196,raw);assert answer.payload[:4]==bytes(4),(item['template'],'open',answer.payload.hex())
    after=items(uid);new=[i for i in after if i['uid']not in ids];actual={}
    for i in new:actual[i['template']]=actual.get(i['template'],0)+i['count']
    assert actual=={r['template']:r['quantity']for r in expected},(item['template'],actual,expected)
    assert not any(i['uid']==item['uid']for i in after)
    duration=30*86400 if item['template']in(277143,277145)else 86400 if item['template']in(277184,277185,277186,277187)else None
    if duration:assert all(i.get('activation_seconds')==duration and'expires_at'not in i for i in new)
    else:assert all('expires_at'not in i and'activation_seconds'not in i for i in new)
    # The real connection operation is read from its committed receipt, never guessed.
    with closing(sqlite3.connect(cfg.state_file))as db:
     receipts=db.execute('SELECT operation_id,before_json FROM inventory_action_receipts WHERE owner=?AND kind=406 ORDER BY rowid DESC',(uid,)).fetchall()
    operation=next(op for op,b in receipts if any(i.get('uid')==item['uid']for i in json.loads(b)))
    stable=facts();replayed=fixed_cubes.open_cube(cfg.state_file,uid,item['template'],raw,operation,account_id=identity['id'],prepare=lambda db:None)
    assert replayed and facts()==stable
    report['opened'].append(dict(box=item['template'],outputs=actual,pending_seconds=duration))
    return new
   stage='male robe boxes'
   for box in(()if '--resume' in sys.argv else(277143,277144)):
    new=await open_one(male,seed(male,box))
    if box==277143:
     robe=new[0];slot=FASHION_EQUIP_SLOTS[robe['template']];begin=int(time.time())
     answer=await peer.query(0x104,struct.pack('>BiBiB',robe['group'],robe['slot'],9,slot,0));assert answer.payload[-4:]==bytes(4)
     current=next(i for i in items(male)if i['uid']==robe['uid']);assert current['expires_at']>=begin+30*86400 and'activation_seconds'not in current
    clear(male,{i['uid']for i in new})
   stage='all four selectable1day packages'
   for box in(277184,277185,277186,277187):
    selected=([seed(male,box)]if '--resume' in sys.argv and box==277184 else await open_one(male,seed(male,277147),(box,)));assert len(selected)==1
    new=await open_one(male,selected[0]);assert len(new)=={277184:7,277185:9,277186:10,277187:6}[box]
    if box==277186:
     accessory=next(i for i in new if i['template']==289160);slot=FASHION_EQUIP_SLOTS[accessory['template']];begin=int(time.time())
     answer=await peer.query(0x104,struct.pack('>BiBiB',accessory['group'],accessory['slot'],9,slot,0));assert answer.payload[-4:]==bytes(4)
     current=next(i for i in items(male)if i['uid']==accessory['uid']);assert current['expires_at']>=begin+86400 and'activation_seconds'not in current
    clear(male,{i['uid']for i in new})
   report['checks'].append('Actual559/55A previews and196/197 opens all four choices; packages grant exactly7/9/10/6 pieces, including alternate hair and accessories, pending1day each')
   stage='failed result rollback and full fashion bag'
   source=seed(male,277143);before=facts()
   with patch.object(fixed_cubes,'result',side_effect=ValueError('owned deliberate cube result failure')):
    try:fixed_cubes.open_cube(cfg.state_file,male,277143,use(source),'owned-failed-gift-result',account_id=identity['id'],prepare=lambda db:None)
    except ValueError as e:assert str(e)=='owned deliberate cube result failure'
    else:raise AssertionError('Failed gift result committed')
   assert facts()==before
   from els_server.storage.bag_capacity import allowances
   with closing(sqlite3.connect(cfg.state_file))as db:limit=allowances(db,male)[7]
   occupied={i['slot']for i in items(male)if i['group']==7};fill=[seed(male,277170,slot=s)for s in range(limit)if s not in occupied]
   before=facts();await peer.query(0x559,struct.pack('>iIBB',277143,0,0,0));answer=await peer.query(0x196,use(source));assert answer.payload[:4]!=bytes(4)and facts()==before
   clear(male,{i['uid']for i in fill});new=await open_one(male,source);clear(male,{i['uid']for i in new})
   report['checks'].append('Late result failure and a genuinely full fashion bag roll back debit, UID sequence, pending periods, source ledger and receipts; the preserved box works after space is freed')
   stage='congratulation box'
   new=await open_one(male,seed(male,277153));assert{r['template']:r['count']for r in new}=={277156:1,277155:200};clear(male,{i['uid']for i in new})
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   peer=await connect(dict(uid=female,bridge=bridge),peers)
   stage='current female robe and Lithia reward'
   for box in(277145,277146):
    new=await open_one(female,seed(female,box));assert new[0]['template']==277255;clear(female,{i['uid']for i in new})
   new=await open_one(female,seed(female,277153));assert{r['template']:r['count']for r in new}=={277256:1,277155:200}
   source=seed(female,277187);before=facts();preview=await peer.query(0x559,struct.pack('>iIBB',277187,0,0,0));assert preview.payload[:4]!=bytes(4)and facts()==before
   answer=await peer.query(0x196,use(source));assert answer.payload[:4]!=bytes(4)and facts()==before
   wrong=seed(female,277143);before=facts();answer=await peer.query(0x559,struct.pack('>iIBB',277143,0,0,0));assert answer.payload[:4]!=bytes(4)and facts()==before
   report['checks'].append('Female temporary/permanent robes use current Lithia277255; congratulations grants277256 plus200 cakes; unsupported May/Lithia and wrong-gender robe preserve the box and inventory')
   await peer.close();peers.remove(peer)
   async with asyncio.timeout(8):
    while identity['id']in app.playing:await asyncio.sleep(.01)
   peer=await connect(dict(uid=female,bridge=bridge),peers);assert any(i['template']==277256 for i in items(female))and any(i['template']==277155 and i['count']==200 for i in items(female))
   stage='generic acquisition and arbitrary timer refusal'
   with closing(sqlite3.connect(cfg.state_file))as db,db:
    db.execute('BEGIN IMMEDIATE')
    for plan in([dict(template=277170,metadata=0,group=7,quantity=1)],[dict(template=306699,metadata=VERIFIED_TEMPLATES[306699],group=TEMPLATE_BAG_GROUPS[306699],quantity=1,activation_seconds=86400)]):
     db.execute('SAVEPOINT reject');stable=tuple(db.iterdump())
     try:grant_items(db,plan,male)
     except ValueError:pass
     else:raise AssertionError('Generic wedding/timer source admitted')
     assert tuple(db.iterdump())==stable;db.execute('ROLLBACK TO reject');db.execute('RELEASE reject')
   assert not errors
   report['checks'].append('Every exact open receipt replays without new awards; cold login retains outputs; generic new wedding grants and arbitrary first-use timer plans remain closed')
   report.update(ok=True,source_pins={p.relative_to(G/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()for p in(G/'candidate').rglob('*')if p.is_file()})
  except BaseException:report.update(stage=stage,error=traceback.format_exc())
  finally:
   for peer in reversed(peers):await peer.close()
   if server is not None:await server.close()
   if app is not None:app.close()
 report.update(owned_private_directory_removed=not private.exists(),owned_listeners_closed=True)
 if '--resume'in sys.argv:report['reused_successes']=dict(evidence='wedding-gifts-TLS-1793957143585924700.json',cases=[277143,277144,'277147-choice277184'],scope='Only failed fashion-weapon admission and remaining cases rerun; earlier successful robe/choice cases retained')
 out=G/('wedding-gifts-TLS-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False));return report['ok']
raise SystemExit(not asyncio.run(main()))
