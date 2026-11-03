"""Native-sender requests through the actual Application/session dispatcher."""
import bootstrap,asyncio,importlib.util,json,sqlite3,struct,tempfile
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
from native_request import NativeWithdrawal
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.protocol.protocol_codec import Event
from els_server.storage import modern_ice
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.bag_capacity import allowances
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS

async def main():
 native=NativeWithdrawal();checks=[]
 with tempfile.TemporaryDirectory(prefix='owned-withdraw-',dir=bootstrap.HERE)as folder:
  path=Path(folder)/'own.sqlite3';app=Application(ServerConfig(state_file=path,log_dir=Path(folder)/'logs'));sessions=[]
  try:
   await app.start()
   def seed():
    root=app.account;a=root.characters.create('WithdrawA',2,'a')['uid'];b=root.characters.create('WithdrawB',1,'b')['uid']
    with closing(sqlite3.connect(path))as db,db:
     for t,n in((293028,5),(130467,20),(800006,1)):modern_ice.add(db,1,t,n)
    return a,b
   a,b=await app.call(seed)
   async def town(uid):
    s=await app.session();sessions.append(s)
    def select():s.role='game';s.phase='characters_ready'
    await app.call(select)
    await app.call(s.handle,Event(0x202,kind=0x28,payload=struct.pack('>Q',uid),performers=(0,)),90+len(sessions))
    def enter():s.account=app.account.for_character(uid);s.role='game';s.phase='town_ready';s.active_map=20000;s.completed.update((0x28,0x225,0x227))
    await app.call(enter);return s
   s=await town(a)
   def snapshot():
    with closing(sqlite3.connect(path))as db:return dict(bag=modern_ice.bag_items(db,1),items=load_items(db,a),points=modern_ice.point_balance(db,1),receipts=db.execute('SELECT count(*) FROM modern_ice_receipts').fetchone()[0]if modern_ice.exists(db,'modern_ice_receipts')else 0)
   async def current():return await app.call(snapshot)
   initial=await current();bag={i['template']:i for i in initial['bag']}
   request=native.event(((bag[293028]['uid'],2),(bag[130467]['uid'],20)))
   spec=importlib.util.spec_from_file_location('old_withdraw_flow',bootstrap.BASE/'els_server/domain/modern_ice_flow.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
   assert await app.call(old.handle,s,request,1)is None
   checks.append('Old online entry ignores the original BD3 request; regression reproduced before dispatch fix')
   def assert_reply(messages):
    ack=next(e for e in messages if e.kind==0xbd4);assert ack.payload[:4]==bytes(4)
    assert any(e.kind==0x105 for e in messages)
    r=native.r;buf=r.buffer(ack.payload);dto=r.alloc(28);r.call(0xc4f050,buf,dto)
    assert int.from_bytes(r.read(buf+32,4),'little')==len(ack.payload)
   answer=await app.call(s.handle,request,1);assert_reply(answer);after=await current()
   counts={t:sum(i['count']for i in after['items']if i['template']==t)-sum(i['count']for i in initial['items']if i['template']==t)for t in(293028,130467)}
   assert counts=={293028:2,130467:20}
   assert {i['template']:i['count']for i in after['bag']}=={293028:3,800006:1} and after['points']==initial['points']
   assert_reply(await app.call(s.handle,request,1));assert await current()==after
   checks.append('Native multi-selection crosses two normal bag groups; partial stack, full stack, BD4/native parser and replay pass')
   bad=native.event(((bag[293028]['uid'],4),(bag[800006]['uid'],1)))
   reply=await app.call(s.handle,bad,2);ack=next(e for e in reply if e.kind==0xbd4);assert ack.payload[:4]!=bytes(4)and await current()==after
   checks.append('Excess quantity rejects the entire batch without spending or granting')
   box=native.event(((bag[800006]['uid'],1),))
   with patch('els_server.storage.modern_ice.encode_event',side_effect=ValueError('owned framing fault')):
    reply=await app.call(s.handle,box,3)
   assert next(e for e in reply if e.kind==0xbd4).payload[:4]!=bytes(4)and await current()==after
   checks.append('Response serialization failure rolls back bag and inventory in the same transaction')
   assert_reply(await app.call(s.handle,box,4));taken=await current()
   cube=next(i for i in taken['items']if i['template']==800006)
   await app.call(s.handle,Event(0x202,kind=0x196,payload=struct.pack('>QBBBIi',cube['uid'],0,0,0,0,0)),5)
   opened=await current();assert any(i['template']==800030 for i in opened['items'])
   assert_reply(await app.call(s.handle,box,4));assert await current()==opened
   checks.append('Character withdraws part cube and opens its own role item; old withdrawal replay does not recreate it')
   # One inventory category full, no existing stack of this remaining reward.
   def fill():
    with closing(sqlite3.connect(path))as db,db:
     db.execute('DELETE FROM inventory_items WHERE owner=? AND template=293028',(a,))
     limit=allowances(db,a)[4];used=db.execute('SELECT count(*) FROM inventory_items WHERE owner=? AND bag_group=4',(a,)).fetchone()[0]
     for _ in range(limit-used):grant_items(db,[dict(template=800000,metadata=VERIFIED_TEMPLATES[800000],group=4,quantity=TEMPLATE_MAX_STACKS[800000])],a)
   await app.call(fill);full=await current();request=native.event(((bag[293028]['uid'],1),))
   reply=await app.call(s.handle,request,6);assert next(e for e in reply if e.kind==0xbd4).payload[:4]!=bytes(4)and await current()==full
   checks.append('Full destination bag rejects withdrawal and preserves the shared bag')
   out=dict(passed=True,checks=checks,real_Application_session=True,native_sender=True,natural_GUI=False,source_files=1,old_receipt_family_preserved=True)
   (bootstrap.HERE/'withdraw-proof.json').write_text(json.dumps(out,indent=2)+'\n','utf8');print(json.dumps(out))
  finally:
   for s in sessions:await app.release(s)
   app.close()
asyncio.run(main())
