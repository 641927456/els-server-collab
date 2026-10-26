"""Native219 current owned30880 only; other219 consumers retain their order."""
import sqlite3
from els_server.protocol.career_messages import use_ack
WRITER_ENABLED=True

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x219:return None
 a=getattr(s,'account',None);store=getattr(a,'store',None)
 if store is None:return None
 from els_server.storage.feta_gauge import recognizes,perform
 operation=s.shop_session_id+':feta-gauge-v1:'+str(a.uid)+':'+str(sequence)
 if not recognizes(store.path,a.uid,event.payload,operation):return None
 try:
  from els_server.domain.feta_gauge_rules import _GaugeAuthority
  authority=_GaugeAuthority(s,event,sequence,operation)
  return perform(store.path,a.uid,a.account_id,event.payload,operation,authorize=authority)
 except(ValueError,sqlite3.Error):return [use_ack(result=-1)]
