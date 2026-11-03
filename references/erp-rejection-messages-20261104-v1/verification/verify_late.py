"""Corrected remaining-stack fixture; reuse 23 unaffected successful cases."""
import verify as v
from verify import HERE,asyncio,contextlib,sqlite3,struct,json,patch
from els_server.storage.resonance_state import ensure
from els_server.storage.inventory_state import grant_items,load_items

async def main():
 case=v.t.FriendsTests();await case.asyncSetUp();root=case.root.resolve();rows=[];out=dict(passed=False,actual_Application_TLS=True,natural_GUI=False)
 try:
  peer=await case.peer(case.alice);await peer.roster();account=case.alice['id'];uid=case.app.accounts[account].uid
  v.QuestState(case.config.state_file,uid,account_id=account).snapshot();curve,definition=v.flow.definitions();rules=v.ResonanceAllocations.from_original(definition);stat=next(s for s in rules.stats if s.maximum<999)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
   db.execute('BEGIN IMMEDIATE');db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,));ensure(db);db.execute('INSERT INTO account_resonance VALUES(?,1,?,1)',(account,curve.threshold(stat.maximum+1)))
   grant_items(db,[dict(template=712417,metadata=v.VERIFIED_TEMPLATES[712417],group=v.TEMPLATE_BAG_GROUPS[712417],quantity=2)],uid)
  await peer.enter_town(uid);session=case.app.playing[account]
  def snapshot():
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db:
    names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND(name LIKE '%resonance%' OR name IN('inventory_items','inventory_action_receipts','reward_balances')) ORDER BY name")]
    return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()for n in names}
  async def send(label,kind,payload,ack,code,unchanged=True):
   before=snapshot();await peer.send(kind,payload);reply=await peer.until(ack);actual=struct.unpack_from('>i',reply.payload)[0];assert actual==code,(label,actual,code)
   if unchanged:assert snapshot()==before
   rows.append(dict(label=label,kind=hex(kind),reply=hex(ack),result=actual,native_text=v.result_messages().text(actual),state_unchanged=unchanged,payload=reply.payload.hex()))
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:item=next(i for i in load_items(db,uid)if i['template']==712417)
  await send('期限祝福后续场景准备',0x718,struct.pack('>QiB',item['uid'],stat.stat_id,1),0x719,0,False)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:item=next(i for i in load_items(db,uid)if i['template']==712417)
  await send('已有祝福不能重复扣道具',0x718,struct.pack('>QiB',item['uid'],stat.stat_id,1),0x719,1971)
  payload=struct.pack('>IBIiiB',1,stat.tab,1,stat.stat_id,stat.maximum-4,1)
  await send('期限加点不得超过原生上限',0x611,payload,0x612,1973)
  with patch('els_server.domain.equipment_chip_flow.current_lease',return_value=False):
   await send('失效角色租约仍静默',0x611,payload,0x612,256)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:
   pages=v.flow.profiles(db).pages.read(account,uid);assert pages.selected_page==1 and pages.selected().available_points==stat.maximum+1 and not any(p for s,p in pages.selected().points)
  before=snapshot();await peer.close();cold=await case.peer(case.alice);await cold.roster();await cold.enter_town(uid);assert snapshot()==before
  assert not[e for e in case.events if e['event']in('worker_error','protocol_error','connection_task_error')]
  out.update(passed=True,cold_read_preserved=True)
 finally:
  await case.asyncTearDown();out.update(rows=rows,cleanup=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections)));(HERE/'late-cases.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(passed=out['passed'],cases=len(rows),cleanup=out['cleanup'])))
if __name__=='__main__':asyncio.run(main())
