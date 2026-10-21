"""Exact current ordinary native death/known-C continuation shapes."""
from dataclasses import replace
import math,struct
from els_server.protocol.protocol_codec import Event,encode_event

def _count(value):
    if type(value) is not int or not 0<=value<2**31:raise ValueError('Known resurrection count wire bound')
    return value

def box_result(ed,count,changes=()):
    from els_server.protocol.cube_messages import result
    answer=result(ed,changes)
    answer[-1]=replace(answer[-1],payload=answer[-1].payload[:4]+struct.pack('>i',_count(count))+answer[-1].payload[8:])
    for e in answer:encode_event(e)
    return answer

def death_request(payload):
    if not isinstance(payload,bytes) or len(payload)!=34 or payload[-1]not in(0,1):raise ValueError('Native A7 shape')
    killer,user,maximum,reason,a,b,extra,flag=struct.unpack('>iQQBffi?',payload)
    if not math.isfinite(a)or not math.isfinite(b):raise ValueError('Native A7 nonfinite context')
    return dict(killer=killer,user=user,maximum=maximum,reason=reason,a=a,b=b,extra=extra,flag=flag)

def death_ack(result=0):
    # Ordinary base-state A8 consumes pending/result and ignores wait/penalty fields.
    return Event(0x201,kind=0xa8,payload=struct.pack('>fihh',0,result,0,0))

def death_complete(owner):return Event(0x201,kind=0xac,payload=struct.pack('>Q',owner))

def use_request(payload,owner):
    if not isinstance(payload,bytes)or len(payload)!=18 or payload[0]not in(0,1)or payload[17]not in(0,1):raise ValueError('Native160 shape')
    cash,source,target,context=struct.unpack('>?QQ?',payload)
    if cash or source!=0 or target!=owner or context:raise ValueError('Unsupported native160 source/target/mode')
    return target

def use_ack(owner,count,code=0):
    # BA6E70 reads fouri32, bool andQ into packedDTO0..18.
    return Event(0x201,kind=0x161,payload=struct.pack('>iiii?Q',code,30000,_count(count),0,False,owner))

def continuation(owner,count):
    # Solo30000stage0 only: -1 is current native selection of an actual mapkey.
    # Fourthword0 is unused outside currentspecialDungeonIDA1D6.
    answer=[use_ack(owner,count),Event(0x201,kind=0x162,payload=struct.pack('>QQii',owner,owner,-1,0))]
    for e in answer:encode_event(e)
    return answer
