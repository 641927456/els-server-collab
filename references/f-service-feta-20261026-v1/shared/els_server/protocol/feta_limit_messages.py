"""Original 6BD whole count-map, finite source/quantity/type/target identities."""
import struct
from els_server.protocol.protocol_codec import Event,encode_event

def snapshot_event(db,account,now):
 from els_server.storage.feta_exchange_weekly import used
 # byte12/13 remain the two original0 flags; no unproved field-name mapping.
 rows={335:[(119317,20,3,0,0,710313,used(db,account,710313,now),1),(119317,20,3,0,0,710193,used(db,account,710193,now),1)],336:[(119317,300,1,0,0,0,used(db,account,119216,now),1)],337:[(119317,120,3,0,0,119328,used(db,account,119328,now),1)]}
 payload=struct.pack('>I',len(rows))
 for script,entries in sorted(rows.items()):
  payload+=struct.pack('>iI',script,len(entries))
  for entry in entries:payload+=struct.pack('>iiiBBiii',*entry)
 event=Event(0x201,kind=0x6bd,payload=payload);encode_event(event);return event
