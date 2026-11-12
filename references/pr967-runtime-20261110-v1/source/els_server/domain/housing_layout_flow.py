"""Original935 owned room save, bound to the actual current923 admission."""
from els_server.protocol.housing_layout_messages import empty_layout,save_ack
from els_server.storage import housing_layouts as storage
import sqlite3

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind!=0x935:return None
 from els_server.domain.housing_room_flow import identity,world_state,scene
 try:
  refs,values=identity(s);wr,wv=world_state(s);context=s.housing_own_room
  if context is None or s.phase!='housing_ready'or s.active_map!=26000 or s.pending_map!=26000:raise ValueError('Furniture native room required')
  if(context['values']!=values or any(a is not b for a,b in zip(refs,context['refs']))):raise ValueError('Furniture current selected graph')
  phase=(s.phase,s.active_map,s.pending_map);source=context['source_town'];scene(s,source,context)
  def same():
   try:r,v=identity(s);ar,av=world_state(s);scene(s,source,context)
   except(ValueError,AttributeError,KeyError,TypeError):return False
   return(v==values and all(a is b for a,b in zip(r,refs))and av==wv and all(a is b for a,b in zip(ar,wr))and s.housing_own_room is context and(s.phase,s.active_map,s.pending_map)==phase)
  def guard(db):
   if not same()or db.execute('SELECT town FROM location WHERE uid=?',(values[0],)).fetchone()!=(source,):raise ValueError('Furniture stale actor')
  if(event.performers!=(0,)or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0 or type(sequence)is not int or not 1<=sequence<2**32):raise ValueError('Furniture native envelope')
  return storage.save(refs[1].path,values[0],values[1],event.payload,values[2]+':housing-layout:'+str(values[0])+':'+str(sequence),context['generation'],context['operation'],guard)
 except(ValueError,sqlite3.Error,OverflowError,AttributeError,KeyError,TypeError):
  return[save_ack(empty_layout(),result=-1)]if'same'in locals()and same()else[]
