"""Full native Unit equality with saved Artifact and life-equipment slots."""
import asyncio,contextlib,hashlib,json,struct,sys,traceback
import runtime_fixture as h
from profile_current import seed
import sqlite3
from els_server.protocol.protocol_codec import encode_event

async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();result=dict(ok=False,checks={})
 try:
  uid=seed(c)
  from els_server.domain.fishing_equipment import ROWS,definition
  from els_server.domain.artifact_progression import catalog,slots
  from els_server.domain.inventory_items import VERIFIED_TEMPLATES
  added=[]
  def next_uid(db):
   value=db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
   db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1',(value+1,))
   return value
  with contextlib.closing(sqlite3.connect(c.config.state_file))as db,db:
   for group in(22,23):
    template,row=next((t,definition(t))for t in ROWS if definition(t)['equipped']==group)
    item_uid=next_uid(db)
    db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(item_uid,uid,template,row['metadata'],1,group,row['slot']));added.append((group,item_uid))
   template=next(int(t)for t in catalog()['equipment']if slots(int(t)))
   item_uid=next_uid(db)
   db.execute('INSERT INTO inventory_items VALUES(?,?,?,?,?,?,?)',(item_uid,uid,template,VERIFIED_TEMPLATES[template],1,24,slots(template)[0]));added.append((24,item_uid))
  peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid,1010)
  s=c.app.playing[c.alice['id']]
  await peer.send(0xd2c);assert(await peer.until(0xd2d)).payload==bytes(4)
  def check():
   from els_server.storage.resonance_state import state
   from els_server.protocol.dungeon_messages import return_user_sync
   from els_server.domain.assembly_rules import uniform
   from els_server.storage.seal_quests import load_character
   import time
   full=s.account.get_inventory_snapshot();worn=s.account.get_inventory_snapshot(equipped_only=True)
   assert {i['group']for i in worn['items']}=={9,22,23,24}
   assert all(any(i['group']==g and i['uid']==u for i in worn['items'])for g,u in added)
   current=state(c.config.state_file,uid,c.alice['id']);character=dict(s.account.character(),resonance=current)
   def packet(items):return return_user_sync(s.account.get_location(),s.account.get_skills(),full['balances'],items,character,inventory_updates=[])
   expected=packet(full['items']);old=packet([i for i in full['items']if i['group']==9]);actual=s.saved_user_sync(resonance_snapshot=current)
   assert encode_event(old)!=encode_event(expected),'Counterexample did not exercise special native slots'
   assert encode_event(actual)==encode_event(expected),'Special equipped native fields were lost'
   now=int(time.time());assert uniform(full['items'],character,now)==uniform(worn['items'],character,now)
   return dict(groups=[9,22,23,24],special_slots_retained=True,old_nine_only_projection_differs=True,full_native_unit_equal=True,bytes=len(actual.payload),sha256=hashlib.sha256(actual.payload).hexdigest(),camp_uniform_equal=True),dict(synthetic_owned_fixture=True,expected_full_event_hex=encode_event(expected).hex(),candidate_event_hex=encode_event(actual).hex(),rejected_nine_only_event_hex=encode_event(old).hex())
  result['checks'],result['golden_vectors']=await c.app.call(check)
  result['ok']=True
 except BaseException:
  result['error']=traceback.format_exc();raise
 finally:
  await c.asyncTearDown();result.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections),candidate_bindings=h.bootstrap.SOURCE_BINDINGS)
  (h.H/'verification-special-slots.json').write_text(json.dumps(result,indent=2)+'\n','utf8')
 print(json.dumps({k:v for k,v in result.items()if k!='golden_vectors'}))

if __name__=='__main__':asyncio.run(main())
