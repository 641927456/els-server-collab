"""Attribute UID-less skill notices to their actual synchronous producer.

Receipts are server metadata, never a client acknowledgement or a SQL commit
claim. A producer exception, changed selection, unknown owner or overflow loses
evidence. It never changes, retries or drops the ordinary business replies.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from els_server.protocol.protocol_codec import Event
from els_server.domain.native_skill_delivery_sources import UpdateReceipt

_CURRENT=ContextVar('native_skill_production',default=None)
MAX_UPDATES=32
MAX_BYTES=4*1024*1024
KINDS=frozenset((0x131,0x123,0x6d1,0x484))


@dataclass(frozen=True)
class ProducedSkills:
    messages:tuple
    updates:tuple
    evidence_complete:bool


def record(event,owner):
    current=_CURRENT.get()
    if current is None or current['overflow']:
        return event
    if (type(event)is not Event or event.event_id!=0x201 or event.kind not in KINDS
            or type(event.payload)is not bytes or type(owner)is not int
            or not 1001<=owner<2**63):
        current.update(rows=[],bytes=0,overflow=True)
        return event
    if len(current['rows'])>=MAX_UPDATES or current['bytes']+len(event.payload)>MAX_BYTES:
        current.update(rows=[],bytes=0,overflow=True)
        return event
    current['rows'].append((owner,event));current['bytes']+=len(event.payload)
    return event


def _selection(session,epoch):
    account=getattr(session,'account',None)
    store=getattr(account,'store',None)
    token=getattr(session,'shop_session_id',None)
    if (account is None or store is None or getattr(session,'released',False)
            or getattr(session,'role',None)!='game'
            or type(token)is not str or not token
            or getattr(account,'uid',None)!=epoch.owner_uid
            or getattr(account,'account_id',None)!=epoch.account_id
            or getattr(store,'uid',None)!=epoch.owner_uid):
        return None
    # Keep references: an equal-looking replacement account/store is a new
    # source lifetime. No SQL read or mutable character projection is added.
    return account,store,token,getattr(session,'phase',None)


def capture(epoch,session,produce,*args,**kwargs):
    """Called inside the serialized worker, for its current transport epoch.

    Only explicit record() calls inside this invocation can attest a notice;
    finding an Event in a returned mailbox is insufficient. The transport must
    still compare epoch identity and commit only after the complete write.
    """
    from els_server.domain.native_attribute_delivery import ActorEpoch
    if type(epoch)is not ActorEpoch:
        raise ValueError('Current server selection epoch required')
    before=_selection(session,epoch)
    current=dict(rows=[],bytes=0,overflow=False);token=_CURRENT.set(current)
    try:
        messages=tuple(produce(*args,**kwargs))
    finally:
        _CURRENT.reset(token)
    if any(type(event)is not Event for event in messages):
        raise ValueError('Original synchronous skill reply Events required')
    after=_selection(session,epoch)
    same=(before is not None and after is not None
          and before[0]is after[0] and before[1]is after[1] and before[2:]==after[2:])
    complete=same and not current['overflow']
    updates=[];seen=set()
    if complete:
        actual={id(event):event for event in messages}
        for owner,event in current['rows']:
            if owner!=epoch.owner_uid or actual.get(id(event))is not event or id(event)in seen:
                continue
            seen.add(id(event));updates.append(UpdateReceipt(epoch,event,owner))
    return ProducedSkills(messages,tuple(updates),complete)
