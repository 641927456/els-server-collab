"""Current705 is one coin templatei32;706 supplies absolute profession state."""
import struct
from els_server.domain.fashion_state import record,empty_record
from els_server.protocol.profession_messages import ProfessionState,state_wire

def request(payload):
    if type(payload)is not bytes or len(payload)!=4:raise ValueError('Sphere request shape')
    coin=struct.unpack('>i',payload)[0]
    if coin not in (117527,117528,118092):raise ValueError('Sphere current selected coin')
    return coin

def acknowledgement(ed=0,rewards=None,changes=(),state=None,result=0):
    if type(ed)is not int or not 0<=ed<2**63 or type(result)is not int or not -2**31<=result<2**31:raise ValueError('Sphere acknowledgement integer')
    rewards={}if rewards is None else rewards;state=ProfessionState()if state is None else state
    if type(rewards)is not dict or len(rewards)>2 or len(changes)>512:raise ValueError('Sphere acknowledgement collection')
    pairs=[]
    for template,count in sorted(rewards.items()):
        if type(template)is not int or not 1<=template<2**31 or type(count)is not int or not 1<=count<2**31:raise ValueError('Sphere reward bound')
        pairs.append(struct.pack('>ii',template,count))
    records=[];seen=set()
    for position,item in changes:
        group,slot=position
        if type(group)is not int or not 0<=group<256 or type(slot)is not int or not 0<=slot<32768 or position in seen:raise ValueError('Sphere slot bound')
        if item is not None and (item['group'],item['slot'])!=position:raise ValueError('Sphere slot mismatch')
        seen.add(position);records.append(empty_record(group,slot)if item is None else record(item))
    return struct.pack('>iQI',result,ed,len(pairs))+b''.join(pairs)+struct.pack('>I',len(records))+b''.join(records)+state_wire(state)
