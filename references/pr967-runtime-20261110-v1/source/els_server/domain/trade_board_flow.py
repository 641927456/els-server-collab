"""Original F TradeBoard admission and complete native replies; source flags closed."""
from contextlib import closing
import hashlib,sqlite3,struct
from els_server.domain.trade_board_authority import TradeBoardAuthority
from els_server.storage import trade_board_state as store
from els_server.protocol import trade_board_messages as wire
from els_server.protocol.protocol_codec import encode_event,Event

ADMISSIONS_ENABLED=True
# Bounded local SQL batch, independent from the client's nine-row presentation
# and the Lua450/600 processing constants. It creates no economic allowance.
QUERY_BATCH=200
# Explicit user display choice: actual per-purchase total, before native fee.
HISTORY_AMOUNT='gross_ed'
KINDS=frozenset((0x9fc,0x9fe,0xa00,0xa02,0xa04,0xa06,0xa08,0xa0a,0xa0c,0xa11,0xa13,0xa18))

def _unknown_data_id(identity):
 raise ValueError('TradeBoard native pet/mount data source not bound')

def _read(authority,event):
 from els_server.domain import tradeboard_query as query
 from els_server.domain.tradeboard_metadata import MetadataQuery
 from els_server.protocol.tradeboard_query_messages import simple_request
 from els_server.protocol.tradeboard_query_filters import decode
 from els_server.domain.tradeboard_query_option_policy import quick_option_match,full_option_match
 from els_server.game_data import client_data
 with closing(sqlite3.connect(authority.path.as_uri()+'?mode=ro',uri=True,timeout=15))as db:
  db.execute('PRAGMA query_only=ON');db.execute('BEGIN');now=store.clock()
  store._authority(db,authority,authority.path,authority.owner,authority.account_id,event.kind,now)
  if event.kind==0xa02:
   if event.payload!=b'\x01':raise ValueError('TradeBoard unqualified own-list request')
   result=wire.own_ack(store.own_rows(db,authority.owner,now))
  elif event.kind==0xa13:
   from els_server.protocol.tradeboard_history_messages import request
   from els_server.storage.tradeboard_history_state import response
   request(event.payload);result=response(db,authority.owner,authority.account_id,now,amount=HISTORY_AMOUNT)
  else:
   selected=decode(event.kind,event.payload)if event.kind in(0xa0a,0xa0c)else None
   usable=None
   if event.kind==0xa0c and selected['flag_6a']:
    from els_server.domain.tradeboard_current_use import read_with_eligibility
    snapshot,usable=read_with_eligibility(db,now,authority)
   else:snapshot=query.read_snapshot(db,now,store.read_offers)
   if event.kind==0x9fe:
    # Revision labels this already captured snapshot only. No second SQL read.
    revision=hashlib.sha256(repr(snapshot).encode()).hexdigest()
    native=query.metadata_snapshot(snapshot,revision)
    result=Event(0x201,kind=0x9ff,payload=MetadataQuery(lambda:native,lambda t:client_data().item(t)['item_type'],_unknown_data_id,_unknown_data_id).query(event.payload))
   elif event.kind==0xa00:
    simple_request(event.payload);result=query.reply(0xa01,query.simple(snapshot,QUERY_BATCH))
   elif event.kind==0xa0a:result=query.reply(0xa0b,query.full(snapshot,selected,QUERY_BATCH,option_match=full_option_match))
   elif event.kind==0xa0c:result=query.reply(0xa0d,query.quick(snapshot,selected,QUERY_BATCH,option_match=quick_option_match,usable=usable))
   elif event.kind==0xa18:
    from els_server.domain.tradeboard_minimum_query import response
    from els_server.protocol.tradeboard_minimum_messages import request
    result=response(snapshot,request(event.payload),QUERY_BATCH)
   else:raise ValueError('TradeBoard unqualified query kind')
  encode_event(result);store._authority(db,authority,authority.path,authority.owner,authority.account_id,event.kind,now)
  return[result]

def _failure(kind,payload):
 from els_server.protocol.tradeboard_query_messages import query_reply
 from els_server.protocol.tradeboard_metadata_messages import acknowledgement,request
 if kind==0x9fe:
  try:selected=request(payload).kind
  except ValueError:selected=1
  return Event(0x201,kind=0x9ff,payload=acknowledgement(selected,[],result=1168))
 if kind in(0xa00,0xa0a,0xa0c):return query_reply(kind+1,result=1168)
 if kind==0xa02:return wire.own_ack(result=1168)
 if kind==0xa04:return wire.sale_ack(result=1168)
 if kind==0x9fc:return wire.cancel_ack(0,result=1168)
 if kind==0xa06:return wire.pickup_ack(0,result=1168)
 if kind==0xa18:
  from els_server.protocol.tradeboard_minimum_messages import reply,request
  try:template=request(payload).template
  except ValueError:template=0
  return reply(template,result=1168)
 if kind==0xa13:
  from els_server.protocol.tradeboard_history_messages import reply
  return reply(result=1168)
 if kind==0xa11:
  from els_server.protocol.tradeboard_favorite_messages import reply
  return reply(result=1168)
 return wire.purchase_ack(result=1168)

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in KINDS:return None
 try:
  if not ADMISSIONS_ENABLED:
   # Compatible recovery must retain all real escrow readers/cancel/pickup.
   # Those operations still pass the original F actor and exact SQL source.
   if event.kind in(0xa04,0xa08):raise ValueError('New TradeBoard admission closed')
   if event.kind==0xa11:
    from els_server.protocol.tradeboard_favorite_messages import request
    if request(event.payload).tag!=0:raise ValueError('New saved-search write closed')
  authority=TradeBoardAuthority(s,event,sequence)
  if event.kind in(0x9fe,0xa00,0xa02,0xa0a,0xa0c,0xa13,0xa18):return _read(authority,event)
  operation=s.shop_session_id+':tradeboard-v1:'+str(authority.owner)+':'+str(sequence)
  if event.kind==0xa11:
   from els_server.storage.tradeboard_favorite_state import perform
   return perform(authority.path,authority.owner,event.payload,operation,account_id=authority.account_id,authority=authority)
  handler={0xa04:store.perform_sale,0x9fc:store.perform_cancel,0xa06:store.perform_pickup,0xa08:store.perform_purchase}[event.kind]
  return handler(authority.path,authority.owner,event.payload,operation,account_id=authority.account_id,authority=authority)
 except(ValueError,sqlite3.Error,OverflowError,struct.error):
  result=_failure(event.kind,event.payload);encode_event(result);return[result]
