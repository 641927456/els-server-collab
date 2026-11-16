"""Native deterministic regional NPC exchange using the current owned actor."""
import sqlite3,struct
from pathlib import Path
from contextlib import closing
from els_server.domain.regional_drop_materials import catalog,recipe
from els_server.protocol.purifier_exchange_messages import ExchangeRequest
from els_server.protocol.fish_exchange_messages import acknowledgement
from els_server.protocol.protocol_codec import Event,encode_event

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x223 or len(event.payload)<16:return None
 house=struct.unpack_from('>i',event.payload)[0];source=struct.unpack_from('>i',event.payload,12)[0]
 if not any((r['house'],r['source'])==(house,source)for r in catalog()['recipes']):return None
 from els_server.domain.dungeon_hp_c1 import _lease
 from els_server.domain.town_travel_flow import _ordinary_binding
 if not _lease(s)or s.role!='game'or s.account.characters is None or 0x28 not in s.completed:return[]
 bound=_ordinary_binding(s);town=s.active_map;path=Path(s.account.store.path).resolve()
 def current():
  return _lease(s)and _ordinary_binding(s)==bound and s.active_map==town and s.phase=='town_ready'and not s.dungeon_return_pending and getattr(s,'town_warp_transition',None)is None
 def failure():
  if not current():return[]
  with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True))as db:
   row=db.execute('SELECT ed FROM reward_balances b JOIN character_owners o ON o.uid=b.uid WHERE b.uid=?AND o.account_id=?',(bound[2],bound[3])).fetchone()
  if row is None:return[]
  return[Event(0x201,kind=0x224,payload=acknowledgement(row[0],result=-1,exchange_type=1))]
 try:
  if(not current()or not s.item_test or s.client_build!='dx11_260923'or type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or len(event.payload)!=37):raise ValueError('Regional exchange native actor/envelope')
  r=ExchangeRequest(*struct.unpack('>iQiiiiiBi',event.payload));row=recipe(r,town)
  def guard(db):
   if not current():raise ValueError('Regional exchange actor changed')
  from els_server.storage.material_exchange import exchange
  ack=lambda ed,changes=(),rewards=():acknowledgement(ed,changes,rewards,exchange_type=1)
  return exchange(path,bound[2],town,event.payload,s.shop_session_id+':regional-material-exchange:'+str(bound[2])+':'+str(sequence),r,account_id=bound[3],source_quantity=row['source_quantity'],destination=row['destination'],output_quantity=row['quantity'],acknowledgement=ack,guard=guard)
 except(ValueError,sqlite3.Error,OverflowError):return failure()
