"""Only original Feta80-prototype/60-core223; retain every existing route."""
import sqlite3,struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.feta_exchange_messages import acknowledgement
from els_server.domain.feta_exchange_rules import _FetaAuthority
from els_server.domain.cartridge_exchange_flow import _selected,_context

WRITER_ENABLED=True

def handle(s,event,sequence):
 if not(s.item_test and s.client_build=='dx11_260923'and event.event_id==0x202 and event.kind==0x223):return None
 body=event.payload
 if(type(body)is not bytes or len(body)<20 or struct.unpack_from('>i',body)[0]!=40326
    or not((struct.unpack_from('>i',body,12)[0]==119216 and struct.unpack_from('>i',body,16)[0]in(60,80))or(struct.unpack_from('>i',body,12)[0]==119317 and struct.unpack_from('>i',body,16)[0]in(20,120,300)))):return None
 kind=1 if len(body)>=28 and struct.unpack_from('>i',body,24)[0]==1 else 3
 if not _selected(s):raise ValueError('Feta exchange before current owned selection')
 try:
  if not WRITER_ENABLED or not _context(s):raise ValueError('Feta current F context')
  op=s.shop_session_id+':feta-exchange-v1:'+str(s.account.uid)+':'+str(sequence)
  authority=_FetaAuthority(s,event,sequence,op)
  from els_server.storage.feta_exchange import exchange
  return exchange(authority.path,authority.owner,body,op,account_id=authority.account_id,authorize=authority)
 except(ValueError,sqlite3.Error):
  from els_server.domain.cartridge_exchange_flow import _failed
  failed=_failed(s);ed=struct.unpack_from('>Q',failed[0].payload,len(failed[0].payload)-8)[0]
  return[Event(0x201,kind=0x224,payload=acknowledgement(ed,result=-1,exchange_type=kind))]
