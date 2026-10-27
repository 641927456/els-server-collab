"""One original135909 UID and selected Rosso mode; no other raid reset."""
import functools,hashlib,sqlite3,struct
from pathlib import Path
TEMPLATE=135909
RECORD_SHA='9780669d82f77f91b06877562251e542b70eef2618399479d0a7a7268899b886'
ADMISSIONS_ENABLED=True

@functools.lru_cache(maxsize=1)
def definition():
 from els_server.game_data import client_data
 item=client_data().item(TEMPLATE)
 if hashlib.sha256(item['record']).hexdigest()!=RECORD_SHA or(item['item_type'],item['metadata'])!=(7,0):raise ValueError('Original Rosso ticket identity')
 return dict(template=TEMPLATE,metadata=0,group=4)

def request(payload):
 # 2CC06D0 case3789 ->2260FD0 -> original C595C0 writer.
 # Here the second u64 is selected mode, not a target item UID.
 if type(payload)is not bytes or len(payload)!=29:raise ValueError('Rosso ticket request size')
 uid,mode,a,b,n,flag=struct.unpack('>QQiiIB',payload)
 if not 0<uid<2**63 or mode not in(1,2)or a or b or n or flag:raise ValueError('Rosso exact owned UID/selected mode')
 return uid,'rosso:shared'if mode==1 else'rosso:story'

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x219:return None
 account=getattr(s,'account',None);store=getattr(account,'store',None)
 if store is None:return None
 from els_server.storage.rosso_reset import recognizes,perform
 operation='rosso-reset-v1:'+s.shop_session_id+':'+str(account.uid)+':'+str(sequence)
 if not recognizes(store.path,account.uid,event.payload,operation):return None
 from els_server.domain.raid_reward_flow import town
 from els_server.domain.equipment_chip_flow import reset_authority
 from els_server.protocol.career_messages import use_ack
 try:
  bound=town(s,sequence);root=account.root;app=getattr(s,'application',None);identity=getattr(s,'identity',None)
  path=Path(store.path).resolve();reward=account.reward_store
  def prepare(db):
   reset_authority(s)
   main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
   if(not db.in_transaction or len(main)!=1 or Path(main[0][2]).resolve()!=path or Path(store.path).resolve()!=path
      or Path(reward.path).resolve()!=path or town(s,sequence)!=bound or s.account is not account or account.store is not store
      or account.root is not root or account.reward_store is not reward or getattr(s,'application',None)is not app
      or getattr(s,'identity',None)is not identity or not {0x28,0x225,0x227}<=s.completed
      or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
    raise ValueError('Rosso reset original actor/save/lease changed')
   return True
  return perform(path,account.uid,account.account_id,event.payload,operation,prepare=prepare)
 except(ValueError,sqlite3.Error):return[use_ack(result=-1)]
