"""Original 559/196 box UI, exact current actor and finite source consumers."""
import sqlite3
from els_server.domain import black_market_box_rules as rules
from els_server.domain.option_conversion_existing_flow import _session,_selected_authorizer
from els_server.protocol.ice_messages import preview_request,preview_ack,use_request
from els_server.protocol.cube_messages import result

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x559,0x196)or not s.item_test or s.client_build!='dx11_260923':return None
 template=None
 if event.kind==0x559:
  try:
   value=preview_request(event.payload)
   if rules.row(value.template)is None:return None
   template=value.template
  except(ValueError,TypeError):return None
 else:
  try:
   value=use_request(event.payload);_session(s)
   item=next((i for i in s.account.get_inventory_snapshot()['items']if i['uid']==value.uid),None)
   cached=getattr(s,'_market_box_operations',{}).get((s.account.uid,sequence))
   template=item['template']if item is not None else cached
   if rules.row(template)is None:return None
  except(ValueError,TypeError,sqlite3.Error):return None
 ed=0
 try:
  selection=_session(s);authorize=_selected_authorizer(s,selection)
  if(type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Market box original request envelope')
  ed=s.account.get_reward_balances()['ed']
  if event.kind==0x559:
   if value.keys not in((),(0,))or value.flag1 not in(0,1)or value.flag2 not in(0,1):raise ValueError('Market box preview mode')
   from els_server.domain.item_expiration import require_current
   from els_server.domain.item_locks import require_unlocked
   owned=next((i for i in s.account.get_inventory_snapshot()['items']if i['template']==template and i['group']==4 and not i.get('sealed')),None)
   if owned is None:raise ValueError('Market box preview requires actual owned source')
   require_current(owned);require_unlocked(owned);r=rules.entry(template)
   return[preview_ack(0,template,selection_count=r['selection_count'],entries=tuple((i['template'],0,i['quantity'])for i in r['entries']))]
  from els_server.storage.black_market_boxes import perform
  reply=perform(*selection,template,event.payload,s.shop_session_id+':market-box:'+str(selection[1])+':'+str(sequence),authorize)
  s._market_box_operations={**getattr(s,'_market_box_operations',{}),(s.account.uid,sequence):template};return reply
 except(ValueError,AttributeError,sqlite3.Error):return[preview_ack(-1,template)]if event.kind==0x559 else result(ed,code=-1)
