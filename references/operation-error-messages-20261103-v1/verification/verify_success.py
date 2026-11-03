import source
from source import HERE
import asyncio,contextlib,json,sqlite3,struct
import reproduce as fixture
from els_server.storage.inventory_state import grant_items
from els_server.storage.seal_quests import QuestState
from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
from els_server.domain.sage_sockets import fee

async def main():
 case=fixture.t.FriendsTests();await case.asyncSetUp();root=case.root.resolve();out=dict(passed=False,actual_Application_TLS=True)
 try:
  peer=await case.peer(case.alice);await peer.roster();uid=case.app.accounts[case.alice['id']].uid
  QuestState(case.config.state_file,uid,account_id=case.alice['id']).snapshot()
  with contextlib.closing(sqlite3.connect(case.config.state_file))as db,db:
   owned=grant_items(db,[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)for t in(60100,135184)],uid)
   db.execute('UPDATE reward_balances SET ed=1000000 WHERE uid=?',(uid,))
  await peer.enter_town(uid);items={i['template']:i for i in owned};gear=items[60100];stone=items[135184]
  def state():
   with contextlib.closing(sqlite3.connect(case.config.state_file))as db:
    return dict(ed=db.execute('SELECT ed FROM reward_balances WHERE uid=?',(uid,)).fetchone()[0],stone=db.execute('SELECT count FROM inventory_items WHERE owner=? AND uid=?',(uid,stone['uid'])).fetchone(),receipts=db.execute('SELECT count(*) FROM inventory_action_receipts WHERE owner=?',(uid,)).fetchone()[0])
  payload=struct.pack('>QIiQBBI',gear['uid'],1,0,stone['uid'],0,0,6)+bytes(24)
  await peer.send(0x1c4,payload);reply=await peer.until(0x1c5);assert struct.unpack_from('>i',reply.payload)[0]==0
  before=state();assert before['ed']==1000000-fee(gear,135184) and before['stone']is None and before['receipts']==1
  await peer.send(0x8b1,struct.pack('>QI',gear['uid'],0));reply=await peer.until(0x8b2);assert struct.unpack_from('>i',reply.payload)[0]==0
  after=state();assert after==dict(before,receipts=2)
  out.update(passed=True,checks=['actual_TLS_socket_preview_consumes_one_stone_and_exact_ED_once','actual_TLS_apply_original_selection_completes_without_second_charge'])
 finally:
  await case.asyncTearDown();out['cleanup']=dict(owned_runtime_removed=not root.exists(),active_connections=len(case.server.connections));(HERE/'success-tests.json').write_text(json.dumps(out,indent=2),encoding='utf8')
 print(json.dumps(out))
if __name__=='__main__':asyncio.run(main())
