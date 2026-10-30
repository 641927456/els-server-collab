"""Original559/196 career box consumer, bound to the actual selected actor."""
import sqlite3
from contextlib import closing
from els_server.domain.promotion_reward_boxes import BOXES,outputs_for
from els_server.protocol.ice_messages import preview_request,use_request,preview_ack
from els_server.protocol.cube_messages import result
def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x559,0x196)or s.client_build!='dx11_260923':return None
 preview=event.kind==0x559;template=0;request=None
 try:
  request=preview_request(event.payload)if preview else use_request(event.payload)
  if preview:template=request.template
  else:
   # Bind retries to this native sequence; a removed source never selects a
   # new box from a stale preview or another actor's UID.
   template=getattr(s,'career_box_operations',{}).get(sequence,0)
   with closing(sqlite3.connect(s.account.store.path))as db:
    row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(s.account.uid,request.uid)).fetchone()
   if row is not None:template=row[0]
  if template not in BOXES:return None
  from els_server.domain.tenebros_capacity_flow import selected
  path,owner,account,guard=selected(s)
  if event.performers not in((),(0,))or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32:raise ValueError('Career box native envelope')
  if preview:
   if request.keys not in((),(0,))or request.flag1 not in(0,1)or request.flag2 not in(0,1):raise ValueError('Career box preview parameters')
   from els_server.storage.promotion_reward_boxes import preview as read_preview
   outputs=read_preview(path,owner,account,template,guard)
   return[preview_ack(0,template,selection_count=0,entries=tuple((r['template'],0,r['quantity'])for r in outputs))]
  from els_server.storage.promotion_reward_boxes import open_box
  answer=open_box(path,owner,template,event.payload,s.shop_session_id+':career-box:'+str(owner)+':'+str(sequence),account_id=account,prepare=guard)
  if not hasattr(s,'career_box_operations'):s.career_box_operations={}
  s.career_box_operations[sequence]=template
  return answer
 except(ValueError,sqlite3.Error,OverflowError,AttributeError):
  if template not in BOXES:return None
  return[preview_ack(-1,template)]if preview else result(0,code=-1)
