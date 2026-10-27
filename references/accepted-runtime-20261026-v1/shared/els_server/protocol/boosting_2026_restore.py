"""Replace only selected growth records in an existing native2B snapshot.

Ordinary and attendance records, and the native trailing maps/vectors, remain
byte-for-byte intact. Repeating this projection must not append duplicates.
"""
import struct
from dataclasses import replace
from els_server.protocol.protocol_codec import Event
from els_server.protocol.boosting_2026_quest import active_record


def split(payload):
    if type(payload) is not bytes or not 20<=len(payload)<=65536 or payload[:4]!=bytes(4):
        raise ValueError('Unexpected quest initialization')
    offset=8;active=[];done=[];seen=set()
    count=struct.unpack_from('>I',payload,4)[0]
    if count>2048:raise ValueError('Quest vector bound')
    for _ in range(count):
        if offset+24>len(payload):raise ValueError('Truncated active quest')
        qid,owner,reserved,n=struct.unpack_from('>iQQI',payload,offset)
        end=offset+24+7*n
        if n>1024 or end>len(payload) or qid in seen:raise ValueError('Invalid active quest vector')
        active.append((qid,payload[offset:end]));seen.add(qid);offset=end
    if offset+4>len(payload):raise ValueError('Truncated completed count')
    count=struct.unpack_from('>I',payload,offset)[0];offset+=4
    if count>2048 or offset+24*count+12>len(payload):raise ValueError('Invalid completed quest vector')
    for _ in range(count):
        qid=struct.unpack_from('>i',payload,offset)[0]
        if qid in seen:raise ValueError('Duplicate active/completed quest')
        done.append((qid,payload[offset:offset+24]));seen.add(qid);offset+=24
    return active,done,payload[offset:]


def merge(event,definition,active,completed,*,owner_uid):
    if event.event_id!=0x201 or event.kind!=0x2b:return event
    ordinary,history,tail=split(event.payload)
    selected={t.quest_id for t in definition.tasks}
    definition.completed_prefix([r['id'] for r in completed])
    if active is not None:
        expected=definition.tasks[len(completed)].quest_id if len(completed)<len(definition.tasks) else None
        if active['id']!=expected:raise ValueError('Inconsistent growth restore sequence')
    ordinary=[raw for qid,raw in ordinary if qid not in selected]
    history=[raw for qid,raw in history if qid not in selected]
    if active is not None:ordinary.append(active_record(definition,active,owner_uid=owner_uid))
    for row in completed:
        at=row['completed_at']
        if type(at) is not int or not 0<=at<2**64:raise ValueError('Invalid completed time')
        history.append(struct.pack('>iiQQ',row['id'],1,at,0))
    payload=bytes(4)+struct.pack('>I',len(ordinary))+b''.join(ordinary)
    payload+=struct.pack('>I',len(history))+b''.join(history)+tail
    if len(payload)>65536:raise ValueError('Combined quest snapshot bound')
    return replace(event,payload=payload)
