"""Original935 owned room save, bound to the actual current923 admission."""
from els_server.protocol.housing_layout_messages import empty_layout,save_ack
from els_server.storage import housing_layouts as storage
import sqlite3,struct

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in(0x219,0x92b,0x935,0xa38,0xa3a,0xd37):return None
 if event.kind==0x219:
  if getattr(s,'housing_own_room',None)is None or len(event.payload)<8:return None
  from contextlib import closing
  from pathlib import Path
  from els_server.storage import housing_expansions
  operation=s.shop_session_id+':housing-expansion:'+str(s.account.uid)+':'+str(sequence)
  source=struct.unpack_from('>Q',event.payload)[0]
  with closing(sqlite3.connect(Path(s.account.store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
   row=db.execute('SELECT template FROM inventory_items WHERE owner=? AND uid=?',(s.account.uid,source)).fetchone()
   replay=db.execute('SELECT 1 FROM inventory_action_receipts WHERE operation_id=?',(operation,)).fetchone()if db.execute("SELECT 1 FROM sqlite_master WHERE name='inventory_action_receipts'").fetchone()else None
  if(row is None or row[0]not in housing_expansions.TEMPLATES)and not replay:return None
 from els_server.domain.housing_room_flow import identity,world_state,scene
 try:
  context=getattr(s,'housing_own_room',None)
  if context is None or s.phase!='housing_ready'or s.active_map!=26000 or s.pending_map!=26000:raise ValueError('Furniture native room required')
  arrived=not context.get('login',False)
  refs,values=identity(s,arrived=arrived);wr,wv=world_state(s)
  if(context['values']!=values or any(a is not b for a,b in zip(refs,context['refs']))):raise ValueError('Furniture current selected graph')
  phase=(s.phase,s.active_map,s.pending_map);source=context['source_town'];scene(s,source,context);current_floor=context.get('floor',0)
  def same():
   try:r,v=identity(s,arrived=arrived);ar,av=world_state(s);scene(s,source,context)
   except(ValueError,AttributeError,KeyError,TypeError):return False
   return(v==values and all(a is b for a,b in zip(r,refs))and av==wv and all(a is b for a,b in zip(ar,wr))and s.housing_own_room is context and context.get('floor',0)==current_floor and(s.phase,s.active_map,s.pending_map)==phase)
  def guard(db):
   if not same()or db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(source,):raise ValueError('Furniture stale actor')
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Furniture native envelope')
  if event.kind==0x92b:
   from contextlib import closing
   from els_server.protocol.housing_layout_messages import movement_floor
   floor=movement_floor(event.payload)
   if floor==current_floor:return []
   from els_server.storage import housing_expansions
   import time
   with closing(sqlite3.connect(refs[1].path))as db:
    db.execute('BEGIN');guard(db)
    room=housing_expansions.require_room(db,values[0],values[1],context['generation'],context['operation'],int(time.time()))
    if floor not in dict(room['layout']):raise ValueError('Housing movement uses an unowned floor')
    guard(db)
   context['floor']=floor
   return []
  if event.kind==0xd37:
   from els_server.storage import housing_presets
   return housing_presets.save(refs[1].path,values[0],values[1],event.payload,values[2]+':housing-preset:'+str(values[0])+':'+str(sequence),context['generation'],context['operation'],current_floor,guard)
  if event.kind==0x219:
   return housing_expansions.use(refs[1].path,values[0],values[1],event.payload,operation,context['generation'],context['operation'],guard)
  if event.kind!=0x935:
   from els_server.storage.housing_pets import perform
   return perform(refs[1].path,values[0],values[1],event.kind,event.payload,values[2]+':housing-pet:'+str(values[0])+':'+str(sequence),context['generation'],context['operation'],guard)
  from els_server.domain.housing_social import layout_boxes
  boxes={}
  def notify(db,layout,selected):
   boxes.update(layout_boxes(s,db,layout,selected))
  answer=storage.save(refs[1].path,values[0],values[1],event.payload,values[2]+':housing-layout:'+str(values[0])+':'+str(sequence),context['generation'],context['operation'],guard,notify=notify)
  for peer,mailbox in boxes.items():peer.mailbox=mailbox
  return answer
 except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):
  if 'same'not in locals()or not same():return []
  if event.kind==0x935:return[save_ack(empty_layout(),result=-1)]
  if event.kind==0x92b:return []
  if event.kind==0xd37:
   from els_server.protocol.housing_preset_messages import acknowledgement
   return[acknowledgement((0,'',-1,[],[]),result=-1)]
  if event.kind==0x219:
   from els_server.protocol.career_messages import use_ack
   return[use_ack(result=-1)]
  from els_server.protocol.housing_pet_messages import placement_ack
  return[placement_ack(-1,[],kind=event.kind+1)]
