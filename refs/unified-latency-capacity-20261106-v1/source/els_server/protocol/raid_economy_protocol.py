"""Current native C04/C05/C06/C07, C0B/C0C and813 consumers, source pinned."""
import struct
from els_server.protocol.protocol_codec import Event,encode_event

def point_group(values):
 # BEFE30 -> 2C2CF30 -> 2C3F5A0: map<i32,map<i32,pair<float,i32>>>;
 # followed by the independent map<i32,map<i32,i64>> (empty in this scope).
 wire=struct.pack('>IiI',1,1,len(values))
 for subtype,points,item in values:
  if subtype not in(1,2,3,4)or type(points)is not int or not 0<=points<=100:raise ValueError('Raid accessory wire bound')
  wire+=struct.pack('>ifi',subtype,points,item)
 return wire

def point_snapshot(values,*,db,owner):
 from els_server.protocol.content_count_messages import notification
 from els_server.storage.bank_state import account_for
 event=notification(db,owner,account_for(db,owner),raid_values=values)
 encode_event(event);return event

def weapon_point(index,points):
 # Original101E880, dispatcher813: map<i32,i32>,bool. True is a
 # single-entry delta; False replaces all entries including unrelated Void.
 if index not in(2,3,4,5)or type(points)is not int or not 0<=points<2**31:raise ValueError('Raid weapon point wire bound')
 event=Event(0x201,kind=0x813,payload=struct.pack('>Iii?',1,index,points,True));encode_event(event);return event

def weekly_snapshot(category,normal,story):
 # Original BD9830 writes the third/sixth scalars to category state+8/+14.
 # The four other scalars and nine legacy reward fields have no new grant
 # semantics in this post-May2025 automatic-drop scope and stay zero.
 if category not in(1,2,3,6,7,8)or any(type(v)is not int or not 0<=v<=50 for v in(normal,story)):raise ValueError('Raid native weekly progress bound')
 wire=struct.pack('>7iI9i?',category,0,0,normal,0,0,story,9,*([0]*9),False)
 event=Event(0x201,kind=0x7c1,payload=wire);encode_event(event);return event

def claim_ack(items=(),code=0):
 from els_server.domain.inventory_items import inventory_payload
 event=Event(0x201,kind=0xc07,payload=struct.pack('>i',code)+inventory_payload(list(items)));encode_event(event);return event

def level_ack(index=5,items=(),code=0):
 from els_server.domain.inventory_items import inventory_payload
 event=Event(0x201,kind=0xc0c,payload=struct.pack('>ii',code,index)+inventory_payload(list(items)));encode_event(event);return event
