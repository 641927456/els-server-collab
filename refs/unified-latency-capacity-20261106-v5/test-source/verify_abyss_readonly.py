"""Independent pinned campaign oracle: quiet views and original recovery SQL."""
import runtime_fixture as h
import asyncio,contextlib,json,sqlite3,time,uuid
from unittest.mock import patch
from profile_town import seed
from els_server.domain import abyss_weapon_campaign as current
from els_server.storage.abyss_weapon_2026 import Campaign,week
from els_server.storage.read_scope import committed_reads
from els_server.protocol.protocol_codec import Event,encode_event
old=h.load('pinned_abyss_readonly',h.BASE/'els_server/domain/abyss_weapon_campaign.py')
NOW=int(time.time())
def dump(path):
 with contextlib.closing(sqlite3.connect(path))as db:return tuple(sorted(db.iterdump()))
def outcome(flow,s,replies):
 try:
  values=flow.finalize(s,replies)
  return('ok',values,[encode_event(v)for v in values])
 except Exception as error:return(type(error).__name__,str(error))
async def main():
 c=h.f.FriendsTests();await c.asyncSetUp();out=dict(passed=False,cases=[])
 try:
  uid=seed(c,c.alice,'OwnAbyssRO',False);peer=await c.peer(c.alice);await peer.roster();await peer.enter_town(uid);await c.server.periodics.close()
  s=c.app.playing[c.alice['id']];source=s.account.store.path;aid=s.account.account_id
  def clone(name):
   path=c.root/(name+'.sqlite3')
   with contextlib.closing(sqlite3.connect(source))as src,contextlib.closing(sqlite3.connect(path))as dst:src.backup(dst)
   return path
  for index,(name,joined,observed,offset,refresh,fault)in enumerate((
   ('not_participating',False,None,0,False,None),
   ('eligible_not_participating',False,None,0,False,'eligible'),
   ('joined_first_restore',True,None,0,False,None),
   ('joined_quiet',True,week(NOW),0,False,None),
   ('joined_title_refresh',True,week(NOW),0,True,None),
   ('week_rollover',True,week(NOW),604800,False,None),
   ('pending_committed_run',True,week(NOW),0,False,'pending'),
   ('foreign_committed_owner',True,week(NOW),0,False,'foreign'),
   ('failed_positive_recovery',True,None,0,False,'rollback'),
   ('bad_saved_definition',True,None,0,False,'definition'),
  )):
   a=clone('abyss-old-'+str(index))
   with contextlib.closing(sqlite3.connect(a))as db,db:
    if joined or fault=='eligible':db.execute('UPDATE characters SET unit_class=79,transcendence=1 WHERE uid=?',(uid,))
    if joined:Campaign(db).join(aid,uid,NOW-100)
    if fault in('pending','foreign'):
     run=str(uuid.uuid4());Campaign(db).admit(aid,uid,run,34130,True,NOW)
     db.execute('INSERT INTO reward_receipts VALUES(?,?,?,?,?)',(run,'a'*64,json.dumps(dict(owner=uid if fault=='pending'else uid+100,dungeon_clear=[34130,1])),b'own-fixture',json.dumps({})))
    if fault=='definition':db.execute("UPDATE abyss2026_accounts SET definition_sha='owned-invalid'WHERE account=?",(aid,))
   b=c.root/('abyss-new-'+str(index)+'.sqlite3')
   with contextlib.closing(sqlite3.connect(a))as src,contextlib.closing(sqlite3.connect(b))as dst:src.backup(dst)
   expected_flow=old.Flow(None,clock=lambda:NOW+offset);actual_flow=current.Flow(None,clock=lambda:NOW+offset)
   expected_flow.observed=actual_flow.observed=None if observed is None else(uid,observed)
   replies=[Event(0x201,kind=0xc23)]if refresh else[]
   recover=Campaign.recover
   def reject(t,*args):recover(t,*args);raise ValueError('Own recovery rejected')
   with contextlib.ExitStack()as stack:
    if fault=='rollback':stack.enter_context(patch.object(Campaign,'recover',reject))
    s.account.store.path=a;expected=outcome(expected_flow,s,replies)
    s.account.store.path=b
    with committed_reads(connections=c.app.read_connections):actual=outcome(actual_flow,s,replies)
   s.account.store.path=source
   assert actual==expected,(name,expected,actual)
   assert dump(a)==dump(b),(name,'full campaign/receipt/inventory SQL differs')
   def state(flow):return{k:v for k,v in vars(flow).items()if k not in('clock','previous')}
   assert state(actual_flow)==state(expected_flow),(name,'flow state differs')
   if fault in('foreign','rollback','definition'):assert actual[0]=='ValueError',(name,actual)
   else:assert actual[0]=='ok',(name,actual)
   out['cases'].append(dict(name=name,pinned_result_wire_flow_and_full_SQL_equal=True))
  # After the original recovery, the next observation is entirely read-only.
  with contextlib.closing(sqlite3.connect(source))as db,db:
   db.execute('UPDATE characters SET unit_class=79,transcendence=1 WHERE uid=?',(uid,));Campaign(db).join(aid,uid,NOW)
  flow=current.Flow(None,clock=lambda:NOW);flow.finalize(s,[]);before=dump(source);opens=[];connect=sqlite3.connect
  def tracked(*args,**kwargs):opens.append((str(args[0]),kwargs.get('uri',False)));return connect(*args,**kwargs)
  with committed_reads(connections=c.app.read_connections):flow.finalize(s,[])
  with patch.object(sqlite3,'connect',tracked),committed_reads(connections=c.app.read_connections):flow.finalize(s,[])
  assert not opens and dump(source)==before
  assert all(not db.in_transaction for observers,files,readers in c.app.read_connections.workers.values()for db in readers.values())
  out.update(passed=True,prepared_quiet_view_opens_zero_connections=True,no_retained_read_transaction=True)
 finally:
  if 'source'in locals():s.account.store.path=source
  await c.asyncTearDown();out.update(owned_runtime_removed=not c.root.exists(),connections=len(c.server.connections));(h.H/'abyss-readonly-tests.json').write_text(json.dumps(out,indent=2),'utf8')
 print(json.dumps(out))
asyncio.run(main())
