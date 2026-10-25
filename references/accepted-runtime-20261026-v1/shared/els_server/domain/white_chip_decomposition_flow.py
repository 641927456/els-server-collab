"""Current1C0 owned actor; ordinary smith XP shares its original item transaction."""
import sqlite3
from pathlib import Path
from els_server.protocol.protocol_codec import Event
from els_server.protocol.inventory_management_messages import decompose_ack
from els_server.domain.equipment_engrave_flow import current_lease

def _saved_paths(account):
 path=Path(account.store.path).resolve()
 return all(Path(facade.path).resolve()==path and getattr(facade,'uid',account.uid)==account.uid
  and getattr(facade,'account_id',account.account_id)==account.account_id
  for facade in (account.characters,getattr(account,'reward_store',None),getattr(account,'inventory_store',None))if facade is not None)

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x1c0 or not s.item_test or s.client_build!='dx11_260923':return None
 try:
  account=s.account
  def context():
   app=getattr(s,'application',None)
   return bool(s.account is account and current_lease(s) and s.role=='game' and s.phase=='town_ready'
    and s.item_test and s.client_build=='dx11_260923' and account.characters is not None and account.store is not None
    and account.store.uid==account.uid and _saved_paths(account) and type(sequence)is int and 1<=sequence<2**32
    and event.performers in((),(0,)) and event.uid==event.target_uid==0xffffffffffffffff and event.payload_mode==0
    and (app is None or app.registry.enabled(account.account_id)))
  if not context():raise ValueError('Decomposition session envelope/current actor')
  binding=(account.store,account.characters,getattr(account,'root',None),account.uid,account.account_id,
   Path(account.store.path).resolve(),s.shop_session_id,getattr(s,'application',None),getattr(s,'identity',None))
  def authorize():
   return bool(context() and account.store is binding[0] and account.characters is binding[1]
    and getattr(account,'root',None) is binding[2] and (account.uid,account.account_id,Path(account.store.path).resolve(),s.shop_session_id)==binding[3:7]
    and getattr(s,'application',None) is binding[7] and getattr(s,'identity',None) is binding[8])
  from els_server.storage.decomposition import decompose
  def prepare_replay(response):
   # Absolute current profession/XP state, with no duplicate gain or level-up UI.
   return [response[0],s.saved_user_sync(),*response[1:]]
  return decompose(binding[5],binding[3],event.payload,binding[6]+':'+str(binding[3])+':'+str(sequence),account_id=binding[4],authorize=authorize,prepare_replay=prepare_replay)
 except (ValueError,sqlite3.Error):return [Event(0x201,kind=0x1c1,payload=decompose_ack(result=-1))]
