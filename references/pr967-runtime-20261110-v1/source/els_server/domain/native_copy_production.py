"""Bounded same-invocation Unit writer records for actual reply attribution.

This is server metadata only: no second SQL read, Event mutation, socket write,
client attachment or constructor inference. Overflow loses source evidence,
never business replies and never authorizes a guessed empty source.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import struct
from els_server.protocol.protocol_codec import Event
from els_server.domain.native_skill_delivery_sources import bind_copy

_CURRENT=ContextVar('native_character_copy_production',default=None)
MAX_COPIES=32
MAX_BYTES=4*1024*1024


@dataclass(frozen=True)
class ProducedBatch:
    messages:tuple
    copies:tuple
    evidence_complete:bool


def capture_fields(fields):
    current=_CURRENT.get()
    if current is None or current['overflow']:
        return fields
    if (type(fields)is not tuple or len(fields)>256
            or any(type(row)is not tuple or len(row)!=2 or type(row[0])is not str
                   or type(row[1])is not bytes for row in fields)):
        current.update(rows=[],bytes=0,overflow=True)
        return fields
    size=sum(len(value)for name,value in fields)
    if len(current['rows'])>=MAX_COPIES or current['bytes']+size>MAX_BYTES:
        current.update(rows=[],bytes=0,overflow=True)
        return fields
    raw=b''.join(value for name,value in fields)
    if len(raw)>=17:
        owner,=struct.unpack_from('>Q',raw,9)
        current['rows'].append((owner,raw,fields));current['bytes']+=len(raw)
    return fields


def capture(produce,*args,**kwargs):
    """Call a synchronous business producer inside its existing worker scope.

    Same-writer fields are retained only for this invocation. The returned
    receipts bind the original Event objects; they attest production, not a
    completed transport write. Only actual successful socket delivery may
    subsequently advance the cursor. UID-less skill updates remain separate.
    """
    current=dict(rows=[],bytes=0,overflow=False);token=_CURRENT.set(current)
    try:
        messages=tuple(produce(*args,**kwargs))
    finally:
        _CURRENT.reset(token)
    if any(type(event)is not Event for event in messages):
        raise ValueError('Original synchronous server reply Events required')
    proofs=[]
    if not current['overflow']:
        by_owner={}
        for owner,raw,fields in current['rows']:
            by_owner.setdefault(owner,[]).append((raw,fields))
        for event in messages:
            if event.event_id!=0x201 or event.kind not in(0x2a,0xd9):continue
            prefix=4 if event.kind==0x2a else 0
            if len(event.payload)<prefix+17 or prefix and event.payload[:4]!=bytes(4):continue
            owner,=struct.unpack_from('>Q',event.payload,prefix+9)
            for raw,fields in by_owner.get(owner,()):
                if event.payload[prefix:prefix+len(raw)]!=raw:continue
                try:proof=bind_copy(event,fields)
                except ValueError:continue
                proofs.append(proof);break
    return ProducedBatch(messages,tuple(proofs),not current['overflow'])
