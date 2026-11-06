"""Original C5A/C5C/C5E/C60 and quest records, fixed6c6b5180 consumer."""
import struct
from els_server.protocol.protocol_codec import Event

def state(row):
    #12DA2F0: u64 character, i32 points, u64 claimed mask, u64 converted UID.
    values=(0,0,0,0)if row is None else(row['character'],row['points'],row['rewards_mask'],row['converted_uid'])
    return Event(0x201,kind=0xc5a,payload=struct.pack('>QiQQ',*values))
def ack(kind,result=0):return Event(0x201,kind=kind,payload=struct.pack('>i',result))
def converted(result=0,items=()):
    from els_server.domain.fashion_state import record
    return Event(0x201,kind=0xc60,payload=struct.pack('>iI',result,len(items))+b''.join(record(i)for i in items))
def active(quest,subquest,owner,count,limit):return struct.pack('>iQQIiHB',quest,owner,0,1,subquest,count,int(count>=limit))
def progress(records):return Event(0x201,kind=0xf3,payload=struct.pack('>I',len(records))+b''.join(records))
