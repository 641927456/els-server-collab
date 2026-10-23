"""Small authenticated session boundary; no dungeon or combat controls."""
from els_server.protocol import artifact_messages as wire
from els_server.domain.equipment_engrave_flow import current_lease

def handle(s,event,sequence):
 if event.event_id==0x202 and event.kind==0x9cf and s.item_test and s.client_build=='dx11_260923':
  from els_server.storage.artifact_socket_expansion import perform,acknowledgement
  def expansion_failed():return [acknowledgement(result=2005)]
  if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
      or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
      or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return expansion_failed()
  try:return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':artifact-slot:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
  except ValueError:return expansion_failed()
 if event.event_id==0x202 and event.kind==0x6e7 and s.item_test and s.client_build=='dx11_260923':
  from els_server.protocol.artifact_socket_messages import request,acknowledgement
  try:
   target,groups,profession,mode=request(event.payload)
  except ValueError:return [acknowledgement(result=2005)]
  if mode in (7,8,9,10,13):
   if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
       or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
       or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return [acknowledgement(mode=mode,result=2005)]
   from els_server.storage.artifact_spirit import perform as spirit
   try:return spirit(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':artifact-spirit:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
   except ValueError:return [acknowledgement(ed=(s.account.get_reward_balances()['ed'] if current_lease(s) and s.account.store is not None and s.account.store.uid==s.account.uid else 0),mode=mode,result=2005)]
  if mode!=20:return None
  def conversion_failed():return [acknowledgement(ed=(s.account.get_reward_balances()['ed'] if current_lease(s) and s.account.store is not None and s.account.store.uid==s.account.uid else 0),result=2005)]
  if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
      or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
      or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return conversion_failed()
  from els_server.storage.artifact_conversion import perform
  try:return perform(s.account.store.path,s.account.uid,event.payload,s.shop_session_id+':artifact-conversion:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
  except ValueError:return conversion_failed()
 if event.event_id==0x202 and event.kind in (0x438,0x43a) and s.item_test and s.client_build=='dx11_260923' and s.account.characters is not None:
  from els_server.protocol.identification_messages import request,acknowledgement
  from els_server.protocol.protocol_codec import Event
  from els_server.domain.artifact_identification import supported
  try:target,_=request(event.kind,event.payload)
  except ValueError:return None
  if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.store is None or s.account.store.uid!=s.account.uid
      or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
      or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
   return [Event(0x201,kind=event.kind+1,payload=acknowledgement(event.kind,0,result=2005))]
  owned=next((i for i in s.account.get_inventory_snapshot()['items'] if i['uid']==target),None)
  if owned is None or not supported(owned['template']):return None
  def identify_failed():return [Event(0x201,kind=event.kind+1,payload=acknowledgement(event.kind,(s.account.get_reward_balances()['ed'] if current_lease(s) and s.account.store is not None and s.account.store.uid==s.account.uid else 0),result=2005))]
  if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.store is None or s.account.store.uid!=s.account.uid
      or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
      or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return identify_failed()
  from els_server.storage.identification_ui import perform
  try:return perform(s.account.store.path,s.account.uid,event.kind,event.payload,s.shop_session_id+':artifact-identify:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
  except ValueError:return identify_failed()
 if event.event_id!=0x202 or event.kind!=0x907 or not s.item_test or s.client_build!='dx11_260923':return None
 def failed():return [wire.potential_ack(result=2005)]
 if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.characters is None or s.account.store is None or s.account.store.uid!=s.account.uid
     or type(sequence) is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
     or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return failed()
 from els_server.storage.artifact_progression import action
 try:return action(s.account.store.path,s.account.uid,'potential',event.payload,s.shop_session_id+':artifact:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id)
 except ValueError:return failed()

def observe(s,replies):
 if not current_lease(s) or s.account.store is None or s.account.store.uid!=s.account.uid or not replies or s.account.characters is None or not s.item_test or s.client_build!='dx11_260923' or s.role!='game' or s.phase not in ('town_ready','dungeon_active'):return []
 character=s.account.character();a=character.get('artifact')
 if not a:return []
 key=(str(s.account.store.path),character['uid']);current=(a['evolution'],a['level'],a['experience'],tuple(a['potentials']))
 old=getattr(s,'_artifact_view',None);s._artifact_view=(key,current)
 if any(e.kind in (0x2a,0x904) for e in replies):return []
 if old and old[0]==key and old[1]!=current:return [wire.notice(character,old[1][0]!=current[0])]
 return []
