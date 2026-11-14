"""Current small furniture original559/196; no extra sources or client definitions."""
from contextlib import closing
import sqlite3
from els_server.domain.furniture_rules import TEMPLATE
from els_server.protocol.ice_messages import preview_request,use_request,preview_ack
from els_server.protocol.cube_messages import result
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x559,0x196)or s.client_build!='dx11_260923':return None
 preview=event.kind==0x559;template=0
 try:
  request=preview_request(event.payload)if preview else use_request(event.payload)
  if preview:template=request.template
  else:
   template=getattr(s,'furniture_operations',{}).get(sequence,0)
   with closing(sqlite3.connect(s.account.store.path))as db:
    row=db.execute('SELECT template FROM inventory_items WHERE owner=?AND uid=?',(s.account.uid,request.uid)).fetchone()
   if row is not None:template=row[0]
  if template!=TEMPLATE:return None
  from els_server.domain.housing_access_flow import capture
  same,guard=capture(s)
  if event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Furniture original envelope')
  from els_server.storage.furniture_boxes import preview as read_preview,perform
  if preview:
   if request.keys not in((),(0,))or request.flag1 not in(0,1)or request.flag2 not in(0,1):raise ValueError('Furniture preview parameters')
   rows=read_preview(s.account.store.path,s.account.uid,s.account.account_id,guard)
   return[preview_ack(0,TEMPLATE,selection_count=0,entries=tuple((r['template'],0,r['quantity'])for r in rows))]
  answer=perform(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':white-armor:'+str(s.account.uid)+':'+str(sequence),guard)
  if not hasattr(s,'furniture_operations'):s.furniture_operations={}
  s.furniture_operations[sequence]=TEMPLATE;return answer
 except(ValueError,sqlite3.Error,OverflowError,AttributeError):
  if template!=TEMPLATE:return None
  if'same'in locals()and not same():return[]
  return[preview_ack(-1,TEMPLATE)]if preview else result(0,code=-1)
