"""Real private Application/TLS ERP requests, existing owned activation and state."""
import source
from source import HERE,BASE
import asyncio,contextlib,hashlib,importlib.util,json,sqlite3,struct
from unittest.mock import patch
def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
fixture=load('erp_tls_support',HERE/'tls_support.py');t=fixture.t
from els_server.protocol.protocol_codec import Event
from els_server.domain import resonance_allocation_flow as flow
from els_server.domain.resonance_2026_allocations import ResonanceAllocations
from els_server.storage.inventory_state import grant_items,load_items
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.storage.seal_quests import QuestState
from els_server.result_messages import result_messages

async def main():
 case=t.FriendsTests();await case.asyncSetUp();root=case.root.resolve();out=dict(passed=False,actual_Application_TLS=True,online_actions=0,natural_GUI=False);rows=[]
 try:
  peer=await case.peer(case.alice);await peer.roster();account=case.alice['id'];uid=case.app.accounts[account].uid
  QuestState(case.config.state_file,uid,account_id=account).snapshot()
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:db.execute('UPDATE characters SET level=99,revision=revision+1 WHERE uid=?',(uid,))
  await peer.enter_town(uid);session=case.app.playing[account]
  curve,definition=flow.definitions();rules=ResonanceAllocations.from_original(definition);stat=rules.stats[0];other=next(s for s in rules.stats if s.tab==stat.tab and s.stat_id!=stat.stat_id)
  def allocation(delta=1,page=1,more=()):
   values=((stat.stat_id,delta),*more)
   return struct.pack('>IBI',1,stat.tab,len(values))+b''.join(struct.pack('>ii',*v)for v in values)+bytes((page,))
  def snapshot():
   # Includes full ERP schemas/receipts, inventory and balances. Lazy tables
   # created during a rejected transaction must also roll back.
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db:
    names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND(name LIKE '%resonance%' OR name IN('inventory_items','inventory_action_receipts','reward_balances')) ORDER BY name")]
    return {n:db.execute('SELECT * FROM "'+n+'" ORDER BY rowid').fetchall()for n in names}
  def grant(template,quantity=1):
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
    return grant_items(db,[dict(template=template,metadata=VERIFIED_TEMPLATES[template],group=TEMPLATE_BAG_GROUPS[template],quantity=quantity)],uid)[0]
  async def send(label,kind,payload,expected,*,unchanged=True):
   before=snapshot();await peer.send(kind,payload);reply=await peer.until({0x611:0x612,0x613:0x614,0x79e:0x79f,0x718:0x719,0x219:0x21a}[kind]);actual=struct.unpack_from('>i',reply.payload)[0]
   assert actual==expected,(label,actual,expected)
   if unchanged:assert snapshot()==before,label+' mutated ERP/inventory/economic state'
   row=dict(label=label,kind=hex(kind),reply=hex(reply.kind),result=actual,native_text=result_messages().text(actual),state_unchanged=unchanged,payload=reply.payload.hex());rows.append(row)
   return reply
  await send('未开放共鸣不能切页',0x79e,struct.pack('>i',1),1788)
  await send('未开放共鸣不能加点',0x611,allocation(),1788)
  await send('无效加点报文仍静默',0x611,b'\0',256)
  await send('无效洗点报文仍静默',0x613,b'\x07\x01',256)
  await send('无效期限道具报文仍静默',0x718,b'',256)
  book=grant(163561)
  await send('已有共鸣书正常开启',0x219,struct.pack('>QQiiIB',book['uid'],0,0,0,0,0),0,unchanged=False)
  await send('可用点数不足',0x611,allocation(2),3046)
  await send('加点页与当前页不同',0x611,allocation(1,2),2051)
  await send('未扩张的页不可切换',0x79e,struct.pack('>i',2),2056)
  await send('当前页正常选择',0x79e,struct.pack('>i',1),0,unchanged=False)
  await send('空分类不能洗点',0x613,bytes((stat.tab,1)),1789)
  await send('正常加点',0x611,allocation(),0,unchanged=False)
  await send('混合退点加点预算不足',0x611,allocation(-1,more=((other.stat_id,3),)),3046)
  await send('洗点硬币不足',0x611,allocation(-1),1791)
  await send('分类洗点卷轴不足',0x613,bytes((stat.tab,1)),1787)
  await send('洗点硬币请求页过期',0x611,allocation(-1,2),2051)
  await send('分类卷轴请求页过期',0x613,bytes((stat.tab,2)),2051)
  await send('期限道具不存在',0x718,struct.pack('>QiB',2**60,stat.stat_id,1),459)
  blessing=grant(712417,2)
  await send('期限道具请求页过期',0x718,struct.pack('>QiB',blessing['uid'],stat.stat_id,2),2051)
  coin=grant(710106)
  await send('持有硬币正常退点',0x611,allocation(-1),0,unchanged=False)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:assert not any(i['uid']==coin['uid']for i in load_items(db,uid))
  await send('退点后正常加回',0x611,allocation(),0,unchanged=False)
  scroll=grant(163564)
  await send('分类卷轴正常退点',0x613,bytes((stat.tab,1)),0,unchanged=False)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:assert not any(i['uid']==scroll['uid']for i in load_items(db,uid))
  await send('期限共鸣祝福正常使用',0x718,struct.pack('>QiB',blessing['uid'],stat.stat_id,1),0,unchanged=False)
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db:blessing=next(i for i in load_items(db,uid)if i['template']==712417)
  await send('已有祝福不能重复扣道具',0x718,struct.pack('>QiB',blessing['uid'],stat.stat_id,1),1971)
  # Only this owned fixture's account XP is prepared at a real curve threshold.
  # The existing synchronization grants the corresponding authoritative budget.
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
   db.execute('UPDATE account_resonance SET experience=?,revision=revision+1 WHERE account_id=?',(curve.threshold(min(999,stat.maximum+1)),account))
   flow.prepare(db,session)
  await send('期限加点不得超过原生上限',0x611,allocation(stat.maximum-4),1973)
  # A recognized stale actor remains an acknowledged silent refusal.
  with patch('els_server.domain.equipment_chip_flow.current_lease',return_value=False):
   await send('失效角色租约仍静默',0x611,allocation(),256)
  assert not[e for e in case.events if e['event']in('worker_error','protocol_error','connection_task_error')]
  before=snapshot();await peer.close();c=await case.peer(case.alice);await c.roster();await c.enter_town(uid);assert snapshot()==before,'cold login mutated committed ERP state'
  out.update(passed=True,cold_read_preserved=True,rows=rows)
 finally:
  await case.asyncTearDown();out['rows']=rows;out['cleanup']=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections));(HERE/'business-tests.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(dict(passed=out['passed'],cases=len(rows),cleanup=out['cleanup']),ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
