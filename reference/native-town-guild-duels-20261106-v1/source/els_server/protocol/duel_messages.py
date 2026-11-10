"""Original5C6/5C9/5CB and5C7/5C8/5CA layouts, without admission authority.

5C9 reserializes the inviter FullUser from the original5C8 dialog. The caller
supplies that exact frozen server-owned body, so no client FullUser becomes a
role/economic source. Remaining scalar hints retain their native values only.
"""
import struct
from els_server.protocol.local_messages import wstring
from els_server.protocol.protocol_codec import Event


def _set(payload, offset):
    if offset+4>len(payload):raise ValueError('Duel short map set')
    count=struct.unpack_from('>I',payload,offset)[0];offset+=4;end=offset+2*count
    if end>len(payload):raise ValueError('Duel short map entries')
    values=tuple(v[0]for v in struct.iter_unpack('>h',memoryview(payload)[offset:end]))
    if any(a>=b for a,b in zip(values,values[1:])):raise ValueError('Duel noncanonical native set')
    return frozenset(values),end


def _set_wire(values):
    values=sorted(values)
    return struct.pack('>I',len(values))+b''.join(struct.pack('>h',v)for v in values)


def invitation_request(payload):
    if len(payload)<37:raise ValueError('Duel short invitation')
    sender,first,target,second=struct.unpack_from('>QIQI',payload)
    size=struct.unpack_from('>I',payload,24)[0];end=28+size
    if size&1 or end>len(payload):raise ValueError('Duel invitation name bounds')
    name=payload[28:end].decode('utf-16le')
    excluded,end=_set(payload,end)
    if end+5!=len(payload):raise ValueError('Duel invitation trailing fields')
    flag,final=struct.unpack_from('>Bi',payload,end)
    return dict(sender=sender,target=target,name=name,first_hint=first,second_hint=second,
                excluded=excluded,flag=flag,final_hint=final)


def answer_request(payload, *, inviter, recipient, full_user):
    end=20+len(full_user)
    if len(payload)<end+8:raise ValueError('Duel short answer')
    sender,target,decision=struct.unpack_from('>QQi',payload)
    if (sender,target)!=(inviter,recipient)or decision not in(0,1,2):raise ValueError('Duel answer invitation binding')
    if payload[20:end]!=full_user:raise ValueError('Duel changed inviter snapshot')
    excluded,end=_set(payload,end)
    if end+4!=len(payload):raise ValueError('Duel answer trailing fields')
    return dict(inviter=sender,recipient=target,decision=decision,excluded=excluded,
                final_hint=struct.unpack_from('>i',payload,end)[0])


def cancel_request(payload):
    if payload not in(b'\0',b'\1'):raise ValueError('Duel original cancellation flag')
    return payload==b'\1'


def requested(target, result=0):
    return Event(0x201,kind=0x5c7,payload=struct.pack('>iQ',result,target))


def invited(inviter, recipient, first_hint, second_hint, name, full_user, excluded, flag):
    # Native readers take i32, but the request producer writes all u32 bits.
    payload=struct.pack('>QIQI',inviter,first_hint,recipient,second_hint)+wstring(name)
    payload+=full_user+_set_wire(excluded)+struct.pack('>B',flag)
    return Event(0x201,kind=0x5c8,payload=payload)


def declined(target, result):
    # Actual5CA clears the dialog and displays its result. Acceptance starts
    # with original room34B; it is not a fabricated successful5CA.
    return Event(0x201,kind=0x5ca,payload=struct.pack('>iQ',result,target))
