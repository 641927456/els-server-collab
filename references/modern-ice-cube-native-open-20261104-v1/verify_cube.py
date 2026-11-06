"""Native single-open messages through real isolated Application sessions."""
import bootstrap,asyncio,json,sqlite3,tempfile
from pathlib import Path
from contextlib import closing
from native_requests import NativeRequests
from els_server.application import Application
from els_server.config import ServerConfig
from els_server.protocol.protocol_codec import Event
from els_server.protocol.ice_messages import use_request,preview_request
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES
from els_server.domain.modern_ice import output_for

async def main():
 native=NativeRequests();candidate='--candidate'in __import__('sys').argv;checks=[]
 with tempfile.TemporaryDirectory(prefix='owned-native-cube-',dir=bootstrap.HERE)as folder:
  path=Path(folder)/'own.sqlite3';app=Application(ServerConfig(state_file=path,log_dir=Path(folder)/'logs'));sessions=[]
  try:
   await app.start()
   def seed():
    uid=app.account.characters.create('OwnCubeEve',5,'eve')['uid'];lu=app.account.characters.create('OwnCubeCiel',10,'ciel')['uid']
    with closing(sqlite3.connect(path))as db,db:
     def grant(owner,t,n):return grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=4,quantity=n)],owner)[0]
     eve_item=grant(uid,800007,2);ciel_item=grant(lu,800006,1)
     from els_server.storage.luciel_state import ensure_active
     ensure_active(db);db.execute('INSERT INTO luciel_active_states VALUES(?,?,?)',(lu,1,1))
    return uid,lu,eve_item,ciel_item
   uid,lu,item,ciel=await app.call(seed)
   async def town(owner):
    s=await app.session();sessions.append(s)
    def select():s.role='game';s.phase='characters_ready'
    await app.call(select)
    import struct
    await app.call(s.handle,Event(0x202,kind=0x28,payload=struct.pack('>Q',owner),performers=(0,)),90+len(sessions))
    def enter():s.account=app.account.for_character(owner);s.role='game';s.phase='town_ready';s.active_map=20000;s.completed.update((0x28,0x225,0x227))
    await app.call(enter);return s
   def inventory(owner):
    with closing(sqlite3.connect(path))as db:return load_items(db,owner)
   s=await town(uid);before=await app.call(inventory,uid)
   preview=await app.call(s.handle,native.preview(800007),1);ack=next(e for e in preview if e.kind==0x55a)
   assert int.from_bytes(ack.payload[:4],'big',signed=True)==0
   event=native.use(item['uid']);request=use_request(event.payload)
   assert(event.kind,request.option,request.choices)==(0x196,1,())
   result=await app.call(s.handle,event,2);ack=next(e for e in result if e.kind==0x197);code=int.from_bytes(ack.payload[:4],'big',signed=True)
   if not candidate:
    assert code==-1 and await app.call(inventory,uid)==before
    checks.append('Original native option1 reproduces rejection without spending')
   else:
    assert code==0
    decoded=native.r.result(ack.payload);assert decoded['rewards']==[(output_for(800007,5,0)['template'],1)]
    after=await app.call(inventory,uid);assert next(i for i in after if i['uid']==item['uid'])['count']==1
    assert sum(i['count']for i in after if i['template']==output_for(800007,5,0)['template'])==1
    await app.call(s.handle,event,2);assert await app.call(inventory,uid)==after
    checks.append('Native option1 spends exactly one and grants Eve top; original native reader and replay pass')
    for option in(-1,2):
     rejected=await app.call(s.handle,native.use(item['uid'],option),3+option+1)
     assert int.from_bytes(next(e for e in rejected if e.kind==0x197).payload[:4],'big',signed=True)!=0
     assert await app.call(inventory,uid)==after
    legacy=await app.call(s.handle,native.use(item['uid'],0),8)
    assert int.from_bytes(next(e for e in legacy if e.kind==0x197).payload[:4],'big',signed=True)==0
    checks.append('Legacy option0 remains one use; negative and multi-use options reject atomically')
   s=await town(lu);event=native.preview(800006,1);assert (preview_request(event.payload).flag1,preview_request(event.payload).flag2)==(1,0)
   result=await app.call(s.handle,event,10);ack=next(e for e in result if e.kind==0x55a);code=int.from_bytes(ack.payload[:4],'big',signed=True)
   if candidate:
    assert code==0
    parsed=native.r.preview(ack.payload);assert parsed['entries']==[(output_for(800006,10,1)['template'],0,1)]
    result=await app.call(s.handle,native.use(ciel['uid'],1,1),11)
    assert int.from_bytes(next(e for e in result if e.kind==0x197).payload[:4],'big',signed=True)==0
    checks.append('Ciel preview uses first preview byte; single open grants current Ciel weapon')
   else:
    assert code==-1;checks.append('Old preview incorrectly reads second byte and rejects active Ciel')
   out=dict(passed=True,candidate=candidate,checks=checks,original_preview_sender='2353800',original_use_sender='2353C10',callbacks_simulated=['session sequence getter'],natural_GUI=False)
   (bootstrap.HERE/('candidate-proof.json'if candidate else'baseline-proof.json')).write_text(json.dumps(out,indent=2),'utf8');print(json.dumps(out))
  finally:
   for s in sessions:await app.release(s)
   app.close()
asyncio.run(main())
