"""Current 49B/49C/49D and KBuffInfo, verified with original readers."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain import random_mission_rules as rules

def assignment(row):
    if row['found']!=1 or not 0<row['mission']<2**31 or row['percent']not in(110,120,150,200,300,500):raise ValueError('Mission notice identity')
    rules.effect(row['buff'])
    # Current inline reader C375C0:5i,f,2empty maps,2i. This is NOT
    # the incompatible three-int notification in the modified ELS70 tree.
    payload=struct.pack('>iiiiifIIii',row['mission'],5,0,0,30681,0.,0,0,row['percent'],row['buff'])
    return Event(0x201,kind=0x49b,payload=payload)

def completion(result,mission):
    if type(result)is not int or result not in(0,-1)or type(mission)is not int or not 0<mission<2**31:raise ValueError('Mission acknowledgement')
    return Event(0x201,kind=0x49d,payload=struct.pack('>ii',result,mission))

def request(payload):
    if not isinstance(payload,bytes)or len(payload)!=4:raise ValueError('Mission completion request length')
    mission=struct.unpack('>i',payload)[0]
    if mission<=0:raise ValueError('Mission completion request identity')
    return mission

def world_row(owner,row):
    if row.get('_mission')is not True or type(owner)is not int or row['owner']!=owner or not 1001<=owner<2**63 or any(type(row[k])is not int for k in('template','stacks','start','end')) or not 1<=row['stacks']<=3 or not 1<=row['start']<row['end']<2**31 or row['end']-row['start']!=1800:raise ValueError('Mission owned native world row')
    r=rules.effect(row['template'])
    # +44 is the original accumulation byte. 2DE8F90 rebuilds the native
    # factor through +5F8 exactly this many times; no custom stat vector.
    return bytes(8)+struct.pack('>iIQfBif?if?iiiQQ',row['template'],0,owner,0.,row['stacks'],0,0.,False,r['factor'],1.,False,-1,0,0,row['start'],row['end'])
