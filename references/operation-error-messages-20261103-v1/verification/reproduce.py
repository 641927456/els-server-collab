"""Existing production handlers over private Application/TLS; no online writes."""
import source
from source import HERE,BASE
import asyncio,contextlib,functools,hashlib,importlib.util,json,os,sqlite3,struct
from unittest.mock import patch

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
t=load('prompt_tls_fixture',HERE/'friends_fixture.py')
from els_server.protocol.protocol_codec import Event,encode_event,encode_frame
from els_server.storage.seal_quests import QuestState
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.result_messages import result_messages
async def send(self,kind,payload=b'',event_id=0x202):
 if kind==0x5bf and not payload:payload=bytes(8)
 self.writer.write(encode_frame(encode_event(Event(event_id,kind=kind,payload=payload,performers=(0,))),self.keys,spi=self.spi,sequence=self.outgoing));self.outgoing+=1;await self.writer.drain()
t.Peer.send=send;load('prompt_tls_reader',HERE/'native_fixture_reader.py').install(t)

async def main():
 case=t.FriendsTests();await case.asyncSetUp();root=case.root.resolve();rows=[];out=dict(ok=False,actual_Application_TLS=True,online_actions=0,natural_GUI=False)
 try:
  peer=await case.peer(case.alice);await peer.roster();uid=case.app.accounts[case.alice['id']].uid
  QuestState(case.config.state_file,uid,account_id=case.alice['id']).snapshot()
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
   db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
   owned=grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)for template,quantity in((60100,1),(163135,1),(135184,1))],uid)
   db.execute('UPDATE reward_balances SET ed=0 WHERE uid=?',(uid,))
  await peer.enter_town(uid);session=case.app.playing[case.alice['id']]
  items={i['template']:i for i in owned};gear=items[60100];stone=items[135184]
  def snapshot():
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db:
    receipts=db.execute('SELECT * FROM inventory_action_receipts WHERE owner=? ORDER BY operation_id',(uid,)).fetchall() if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone() else []
    return(db.execute('SELECT * FROM reward_balances WHERE uid=?',(uid,)).fetchall(),db.execute('SELECT * FROM inventory_items WHERE owner=? ORDER BY uid',(uid,)).fetchall(),receipts)
  async def check(label,kind,payload,ack,expected,module=None,function=None):
   if any(r['label']==label for r in rows):return
   errors=[];before=snapshot()
   def capture(original):
    @functools.wraps(original)
    def observed(*args,**kwargs):
     try:return original(*args,**kwargs)
     except ValueError as error:errors.append(str(error));raise
    return observed
   manager=patch.object(module,function,capture(getattr(module,function)))if module else contextlib.nullcontext()
   with manager:
    await peer.send(kind,payload);reply=await peer.until(ack)
   code=struct.unpack_from('>i',reply.payload)[0];assert code==expected,(label,code,expected,reply.payload.hex())
   assert snapshot()==before,label+' changed inventory/ED/receipt'
   rows.append(dict(label=label,request=hex(kind),reply=hex(ack),code=code,catalog_text=result_messages().text(code),underlying_errors=errors,economic_unchanged=True))
  from els_server.storage import sage_sockets,paid_enhancement,manufacture,equipment_restoration
  from els_server.domain import equipment_ui_flow
  socket=struct.pack('>QIiQBBI',gear['uid'],1,0,stone['uid'],0,0,6)+bytes(24)
  await check('镶嵌ED不足',0x1c4,socket,0x1c5,1355,sage_sockets,'socket')
  enhance=struct.pack('>QiiBBBBiB',gear['uid'],0,0,0,0,1,0,0,0)
  await check('强化ED不足',0x5ff,enhance,0x600,373,equipment_ui_flow,'enhance')
  await check('制作拒绝原因丢失',0x198,struct.pack('>iiqI',30445,1,-1,0),0x199,303,manufacture,'execute')
  from els_server.storage.equipment_enhancement import replace
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:db.execute('BEGIN IMMEDIATE');replace(db,uid,gear['uid'],0,-8)
  from els_server.domain.owned_scroll_families import catalog
  scroll=next(iter(catalog()['restoration']))
  await check('复原缺少卷轴',0x21f,struct.pack('>QiB',gear['uid'],scroll,0),0x220,380,equipment_restoration,'restore')
  await check('共鸣未开放时切页',0x79e,struct.pack('>i',1),0x79f,256)
  await check('共鸣期限道具不存在',0x718,struct.pack('>QiB',2**60,0,1),0x719,256)
  # Recognized unknown old preview is not an owned generation; no new roll is requested.
  from els_server.storage import sage_sockets as sockets
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:db.execute('BEGIN IMMEDIATE');replace(db,uid,gear['uid'],-8,0)
  await check('镶嵌应用缺少当前预览',0x8b1,struct.pack('>QI',gear['uid'],0),0x8b2,1,sockets,'apply')
  if True:
   await peer.send(0x225,struct.pack('>iB',1012,0));await peer.until(0x226)
   await peer.send(0x227,struct.pack('>fffBH',1.,2.,3.,0,0));await peer.until(0x228)
   from els_server.storage import trade_board_state
   await check('交易上架拒绝提示',0xa04,struct.pack('>QiiQQ',items[163135]['uid'],163135,1,100,0),0xa05,1,trade_board_state,'perform_sale')
  from els_server.domain.manufacture_requirements import requirements
  materials=requirements(30445,1)['materials']
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
   grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q)for t,q in materials.items()],uid)
  await check('制作材料齐全但ED不足',0x198,struct.pack('>iiqI',30445,1,-1,0),0x199,302,manufacture,'execute')
  assert not[e for e in case.events if e['event']in('worker_error','protocol_error','connection_task_error')]
  out.update(ok=True,rows=rows)
 finally:
  await case.asyncTearDown();out['rows']=rows;out['cleanup']=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections))
  (HERE/'reproduction.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
